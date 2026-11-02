"""Step 3, the erase, as settled with the user on 2026-10-27 (the tests behind it, experiments/prefill_*.py, are in
the git history; their outputs in .data/out/dataset/erase_review/): what is behind every card is painted by FLUX
Erase (flux_erase.erase_image), from as much real background as the model can use.

Per box, from its planned layers (cards.plan: the cards before any pixels are drawn) and the frame step's frames:
1. every card's interior is prefilled with the plain background colour of its own frame (membrane interpolation,
   no texture): the model then has no character left to continue (masking only a band left the figure visible and
   it painted it back), and no strokes to copy (a textured prefill came back as cracked plaster);
2. the mask is a band inside each card's outline, as wide as a 30 cm head move uncovers (its shift + 6 px), bubbles
   whole, then grown frame by frame while the frame's masked share stays under MAX_SHARE: on wide shots the model
   paints the whole interior, on close-ups the cap keeps real background in view (past ~60-75% masked it answers
   with a flat placeholder colour);
3. one FLUX Erase call per box, sent alone (packing two copies per call tipped borderline boxes into failure);
4. the model's whole output is taken under the cards: one source, so no seams (pasting its pixels only in the band
   and ours elsewhere drew a contour at every meeting line);
5. two checks on every result, a fill with under TEX_MIN of the real background's texture, or a flat colour over
   FLAT_MIN of the mask absent from the scene (the placeholder: green, khaki, teal, white; the old colour transform
   disguised it as a brown or grey field). On a hit the box is retried frame by frame: the failing boxes were frames
   of unrelated scenes side by side (P&C 39 p23, a warm tavern beside an icy battle), and each frame alone works;
6. the model's colour cast removed (colour_transform, fitted on the background away from the cards), the tone
   matched at every outline (seam_match).

Writes plates/<pid>/band-plate.png (the whole box, the art outside the cards) and band-raw[-fK].npz (the paid
outputs, keyed on the mask: a rerun with the same mask pays nothing); cards.render uses band-plate.png as the
backdrop when it exists.

    uv run python band_erase.py <episode.zumi> <out dir> [--panels 3,7] [--dry]
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import binary_dilation, distance_transform_edt as edt

import flux_erase as FE
from boxstore import Box
from cards import Plan
from chapter import Chapter
from spend import paid_map
from view import focal

LEAN = 0.3 / 1.5     # the head move the band covers, in units of the reading distance (30 cm at 1.5 m)
BAND_PAD = 6         # px past that shift
MAX_SHARE = 0.55     # a frame's band grown while its masked share stays under this
GROW_STEP = 8        # px per growth step
MARGIN_PX = 10       # px each character and bubble is grown outward, in the mask and in what is replaced
MARGIN_OBJ_PX = 16   # ...each object
SEAM_GROW = 24       # px past that over which the model's output is blended into the art
API_DILATE = FE.DILATE  # px the erase API grows the mask itself
WORKERS = 16         # boxes erased at once (BFL allows 24 requests in flight; a box's frame retries add to it)
INPUT_VERSION = "white-page"  # part of the saved outputs' key: v1 sent the page as it was
TEX_MIN = 0.12       # placeholder check: fill texture / real background texture (failures 0.00-0.12, fills 0.13+)
TEX_MIN_SHARE = 0.20 # ...applied to masks of at least this share of the art
FLAT_MIN = 0.40      # placeholder check: share of the mask in one flat colour...
SEEN_MAX = 0.02      # ...seen in under this share of the real background


def membrane(img: np.ndarray, known: np.ndarray) -> np.ndarray:
    """The smoothest colour field equal to img on `known` (Laplace's equation): solved exactly on a coarse grid, then
    each finer level starts from it and relaxes with the known pixels fixed, so the fill meets the art seamlessly."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    pyr = [(img.astype(np.float32), known)]
    while max(pyr[-1][1].shape) > 160:
        c, k = pyr[-1]
        kk = cv2.resize(k.astype(np.float32), (k.shape[1] // 2, k.shape[0] // 2), interpolation=cv2.INTER_AREA)
        cc = cv2.resize(c * k[..., None], (k.shape[1] // 2, k.shape[0] // 2), interpolation=cv2.INTER_AREA)
        pyr.append((cc / np.maximum(kk, 1e-6)[..., None], kk > 0.5))
    c, k = pyr[-1]
    h, w = k.shape
    idx = -np.ones((h, w), int)
    unk = np.argwhere(~k)
    idx[~k] = np.arange(len(unk))
    rows, cols, vals, rhs = [], [], [], np.zeros((len(unk), 3))
    for n, (y, x) in enumerate(unk):
        nb = [(y + dy, x + dx) for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)) if 0 <= y + dy < h and 0 <= x + dx < w]
        rows.append(n); cols.append(n); vals.append(len(nb))
        for yy, xx in nb:
            if k[yy, xx]:
                rhs[n] += c[yy, xx]
            else:
                rows.append(n); cols.append(idx[yy, xx]); vals.append(-1)
    fill = c.copy()
    if len(unk):
        A = coo_matrix((vals, (rows, cols)), shape=(len(unk), len(unk))).tocsr()
        fill[~k] = np.stack([spsolve(A, rhs[:, ch]) for ch in range(3)], -1)
    for c, k in reversed(pyr[:-1]):
        f = cv2.resize(fill, (k.shape[1], k.shape[0]), interpolation=cv2.INTER_LINEAR)
        f[k] = c[k]
        for _ in range(40):
            f = np.where(k[..., None], c, cv2.blur(f, (3, 3)))
        fill = f
    return fill


def sliding_cards(plan: Plan) -> list[dict]:
    """The plan's cards ({mask, kind, shift}: shift = px a LEAN head move slides the card over its backdrop)."""
    f = focal(plan.w, plan.h)
    cards = []
    for c in plan.cards():
        mid = c.z * (1 - c.amp * 0.5)  # between the card's plane and its relief peak
        cards.append({"mask": c.mask((plan.h, plan.w)), "kind": c.kind,
                      "shift": f * LEAN * (1 / mid - 1 / plan.back_z(c.frame))})
    return cards


def band_mask(cards: list[dict], frames: list[np.ndarray], art: np.ndarray) -> np.ndarray:
    """The erase mask: per card a band of its shift + BAND_PAD px, then grown per frame toward the interior while
    the frame's masked share stays under MAX_SHARE; the bubbles whole, past the frames too. A bubble clipped to its
    frame left its outer half in the image and the model completed its lettering into the fill (garbled text in
    P&C 39 p6, p8, p14, p17)."""
    foot = np.logical_or.reduce([c["mask"] for c in cards])
    d = edt(foot)
    band = np.zeros_like(foot)
    bubbles = np.zeros_like(foot)
    for c in cards:
        if c["kind"] == "lettering":
            bubbles |= c["mask"]
        else:
            band |= c["mask"] & (d <= abs(c["shift"]) + BAND_PAD)
    band |= bubbles | margin(cards, sent=True)
    for fa in frames:
        fa = fa & art
        if not fa.any():
            continue
        extra = 0
        while extra < 400 and ((band | (foot & (d <= extra + GROW_STEP))) & fa).sum() / fa.sum() < MAX_SHARE:
            extra += GROW_STEP
        band |= foot & fa & (d <= extra)
    return (band & art) | bubbles


def margin(cards: list[dict], sent: bool = False) -> np.ndarray:
    """The ring each card is grown by outward, MARGIN_PX (objects MARGIN_OBJ_PX): a figure's dark outline, glow and
    anti-aliased fringe go with it (at 8 px around objects the model kept a ghost of a desk). Without it the outline
    stayed in the backdrop beside the sliding card. sent: the part of it the mask itself
    carries, the API adding API_DILATE px (the full ring in the mask put boxes at 80-90% masked, where the model
    answers with its placeholder)."""
    out = np.zeros_like(cards[0]["mask"])
    for c in cards:
        r = MARGIN_OBJ_PX if c["kind"] == "object" else MARGIN_PX
        # sent: figures and bubbles carry none (the API's own 8 px repaint their outline; the 2 px beyond that
        # are taken from the model's output too, where it reproduces the art), objects the rest of their 16
        r = (max(0, r - API_DILATE) if c["kind"] == "object" else 0) if sent else r
        if r > 0:
            out |= binary_dilation(c["mask"], iterations=r) & ~c["mask"]
    return out


def colour_transform(got: np.ndarray, ref: np.ndarray, same: np.ndarray) -> np.ndarray:
    """got brought to ref's colours by one 3x3 + offset transform (least squares in RGB), fitted where both show the
    same scene: the model shifts the tone of its whole image, hue included, which a per-channel gain cannot undo."""
    if same.sum() < 200:
        return got.astype(np.float32)
    X = np.c_[got[same].reshape(-1, 3).astype(np.float64), np.ones(int(same.sum()))]
    Y = ref[same].reshape(-1, 3).astype(np.float64)
    sub = np.arange(len(X))[:: max(1, len(X) // 200000)]
    A, *_ = np.linalg.lstsq(X[sub], Y[sub], rcond=None)
    flat = np.c_[got.reshape(-1, 3).astype(np.float64), np.ones(got.shape[0] * got.shape[1])] @ A
    return np.clip(flat, 0, 255).reshape(got.shape).astype(np.float32)


def prefill(img: np.ndarray, foot: np.ndarray, mask: np.ndarray, frames: list[np.ndarray]) -> np.ndarray:
    """The card interiors (cards minus the mask) in the plain background colour of their own frame."""
    out = img.copy()
    for fa in frames:
        hole = foot & ~mask & fa
        if hole.any():
            out[hole] = membrane(img, fa & ~foot).clip(0, 255).astype(np.uint8)[hole]
    return out


def placeholder(got: np.ndarray, m: np.ndarray, img: np.ndarray, art: np.ndarray) -> str | None:
    """Why `got` is the model's placeholder rather than a fill, or None. The texture test only on masks of at least
    TEX_MIN_SHARE of the art: a small mask is often meant to come back plain (the credits page, P&C 39 p30, a
    false alarm that paid 5 retries)."""
    if m.sum() < 500:
        return None
    g8 = np.clip(got, 0, 255).astype(np.uint8)
    grey = lambda a: cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)
    sd = lambda a, k: np.sqrt(np.maximum(cv2.blur(grey(a) ** 2, (k, k)) - cv2.blur(grey(a), (k, k)) ** 2, 0))
    inner = m & ~binary_dilation(~m, iterations=6)
    ref = ~m & ~binary_dilation(m, iterations=4) & art
    if inner.any() and ref.any() and m[art].mean() >= TEX_MIN_SHARE:
        ratio = float(np.median(sd(g8, 7)[inner]) / max(np.median(sd(img, 7)[ref]), 1e-6))
        if ratio < TEX_MIN:
            return f"texture {ratio:.2f} of the background's"
    q = (g8[m] // 8).astype(int)
    key = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    mode = np.bincount(key).argmax()
    col = np.array([mode // 1024, (mode // 32) % 32, mode % 32]) * 8 + 4
    flat = float(((np.abs(g8.astype(int) - col).max(-1) < 14) & (sd(g8, 9) < 3))[m].mean())
    seen = float((np.abs(img.astype(int) - col).max(-1) < 20)[ref].mean()) if ref.any() else 0.0
    if flat > FLAT_MIN and seen < SEEN_MAX:
        return f"flat {tuple(int(v) for v in col)} on {flat:.0%} of the mask"
    return None


def lettering_free(img: np.ndarray, lettering: np.ndarray, frames: list[np.ndarray]) -> np.ndarray:
    """The box with its lettering filled in by each frame's surrounding colour: what the depth model sees, so a
    bubble gets no depth of its own. Smooth is enough there; the backdrop under the bubbles is FLUX's (erase_box)."""
    out = img.copy()
    for fa in frames:
        hole = lettering & fa
        if hole.any() and (fa & ~lettering).sum() > 200:
            out[hole] = membrane(img, fa & ~lettering).clip(0, 255).astype(np.uint8)[hole]
    return out


def seam_match(img, res, foot, page, reach, cap=30.0, sat_max=200, S=8.0):
    """res with the tone step at every card outline removed: (real background just outside) - (fill just inside),
    measured without bright or saturated accents, clipped to its 5-95% range and CAP levels, spread inward and faded
    over `reach` px."""
    d = edt(foot)
    hsv = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2HSV)
    ok = (img.max(-1) < 235) & (hsv[..., 1] < sat_max)
    src = ~binary_dilation(foot, iterations=4) & binary_dilation(foot, iterations=12) & ~page & ok
    inn = foot & (d >= 2) & (d <= 8) & (res.max(-1) < 235)

    def avg(a, m):
        w = cv2.GaussianBlur(m.astype(np.float32), (0, 0), S)
        return cv2.GaussianBlur(np.where(m[..., None], a, 0), (0, 0), S) / np.maximum(w, 1e-6)[..., None], w

    ro, wo = avg(img.astype(np.float32), src)
    ri, wi = avg(res, inn)
    seam = foot & (d <= 8) & (wo > 0.05) & (wi > 0.05)
    if not seam.any():
        return res
    off = np.where(seam[..., None], ro - ri, 0).astype(np.float32)
    lo, hi = np.percentile(off[seam], [5, 95], axis=0)
    off = np.clip(np.where(seam[..., None], np.clip(off, lo, hi), 0), -cap, cap)
    w = cv2.GaussianBlur(seam.astype(np.float32), (0, 0), 2 * S)
    offs = cv2.GaussianBlur(off, (0, 0), 2 * S) / np.maximum(w, 1e-6)[..., None]
    return np.clip(res + offs * np.clip(1 - d / reach, 0, 1)[..., None] * foot[..., None], 0, 255)


def _call(sent: np.ndarray, m: np.ndarray, cache: Path, dry: bool):
    """FLUX Erase on sent/m, or the saved output for this very mask. (output, log line)."""
    # the key: the mask, and INPUT_VERSION for changes to what is sent beside it (bump it when the input changes).
    # The image sent is not in the key, so a prefill tweak does not pay for every box again; its hash is saved
    # beside the output, and a saved output for the same mask under different pixels is used with a warning
    key = hashlib.sha1(np.packbits(m).tobytes() + str(m.shape).encode() + INPUT_VERSION.encode()).hexdigest()[:16]
    sent_h = hashlib.sha1(np.ascontiguousarray(sent).tobytes()).hexdigest()[:16]
    if cache.exists():
        z = np.load(cache)
        if str(z["key"]) == key:
            was = str(z["sent"]) if "sent" in z.files else None
            if was is not None and was != sent_h:
                return z["g"], "saved output, WARNING: sent for other pixels (delete it to pay for a new one)"
            return z["g"], "saved output"
    if dry:
        return None, "dry"
    got, line = FE.erase_image(sent.copy(), m)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cache, g=got.astype(np.uint8), key=key, sent=sent_h)
    return got, line


def erase_box(box: Box, img: np.ndarray, plan: Plan, dry: bool = False, log=print) -> np.ndarray | None:
    """The band-erase plate of one box (the art outside its cards), from its plan (cards.plan) and the frame step's
    frames, saved in its plates dir; None when it has no cards (or dry)."""
    fr = box.frames()
    cards = sliding_cards(plan)
    frames = fr.masks if fr else []
    if not cards or not frames:
        return None
    # what lies outside every frame (the page, and lettering past the frames) is not erased and goes to the model
    # white: a near-white test took the bubbles' white interiors for page, so they were neither masked nor painted and
    # each bubble stayed in its plate (a ghost behind the bubble card)
    art = np.logical_or.reduce(frames)
    page = ~art
    foot = np.logical_or.reduce([c["mask"] for c in cards])
    mask = band_mask(cards, frames, art)
    pre = prefill(img, foot, mask, frames)
    # the page goes to the model white: a bubble crossing a frame's edge left its outer part (outside the mask) in
    # the image, and the model continued its lettering into the mask (garbled text in P&C 39 p6, p8, p14, p17)
    pre[page] = 255
    ys, xs = np.nonzero(art)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    got, line = _call(pre[y0:y1, x0:x1], mask[y0:y1, x0:x1], box.erase_output_file(), dry)
    log(f"  mask {mask[art].mean():.0%} of the art; {line}")
    if got is None:
        return None
    g = np.zeros(img.shape, np.float32)
    g[y0:y1, x0:x1] = got
    # checked frame by frame: a placeholder in one frame of a box hid behind the other frames' good fills (a white
    # close-up in P&C 39 p10); only the failing frames are retried
    for k, fa in enumerate(frames):
        fy, fx = np.nonzero(fa)
        if not len(fy) or not (mask & fa).any():
            continue
        fy0, fy1, fx0, fx1 = fy.min(), fy.max() + 1, fx.min(), fx.max() + 1
        sl = np.s_[fy0:fy1, fx0:fx1]
        fm = mask[sl] & fa[sl]
        why = placeholder(g[sl], fm, img[sl], fa[sl])
        if not why:
            continue
        log(f"  frame {k}: placeholder ({why}): retry this frame alone")
        got_k, line_k = _call(pre[sl], fm, box.erase_output_file(k), dry)
        if got_k is None:
            return None
        why_k = placeholder(got_k, fm, img[sl], fa[sl])
        log(f"    {line_k}" + (f"; still a placeholder ({why_k})" if why_k else ""))
        g[sl] = np.where(fa[sl][..., None], got_k, g[sl])
    g = colour_transform(g, img, art & ~binary_dilation(mask, iterations=8))
    # the model's pixels under the cards and their margin (outline, glow), then blended into the art over SEAM_GROW px
    # past it: a hard switch left a visible seam around each patch
    under = (foot | margin(cards)) & art
    res = np.where(under[..., None], g, img.astype(np.float32))
    reach = max(abs(c["shift"]) + BAND_PAD for c in cards)
    res = seam_match(img, res, under, page, reach)
    a = np.clip(1 - edt(~under) / SEAM_GROW, 0, 1) * art
    res = (res * a[..., None] + img.astype(np.float32) * (1 - a[..., None])).clip(0, 255).astype(np.uint8)
    box.save_plate(res)
    return res


def erase_boxes(jobs: list[tuple[Box, np.ndarray, Plan]], dry: bool = False, workers: int = WORKERS,
                log=print) -> None:
    """erase_box on every (box, image, plan), WORKERS boxes at a time (spend.paid_map): a call is 5-9 s of waiting on
    BFL, so in sequence 29 boxes took ~4 min. Each box's lines are printed together when it is done. The daily cap
    (flux_erase reserves every call in flight) stops the boxes not yet sent; a refused box (BFL moderation) skips only
    itself."""
    def one(k):
        box, img, plan = jobs[k]
        lines = [box.pid]
        try:
            erase_box(box, img, plan, dry, log=lines.append)
        except FE.BudgetExceeded:
            raise
        except Exception as e:
            lines.append(f"  failed, box kept on its old plate (or the art): {str(e)[:160]}")
        return lines

    _, stopped = paid_map(one, range(len(jobs)), workers, on_done=lambda k, lines: log("\n".join(lines)))
    for k in stopped:
        log(f"{jobs[k][0].pid}\n  not sent (the daily cap, or an offline run): left for the next run")


def main():
    """The erase on the saved masks and frames (cards.plan, the depth model), then the layers drawn on the plates;
    --dry pays for nothing (only saved outputs are used) and draws nothing."""
    import cards as CD
    import depth as DP
    zumi, out = Path(sys.argv[1]), Path(sys.argv[2])
    dry = "--dry" in sys.argv
    ch = Chapter(zumi)
    picks = range(len(ch))
    if "--panels" in sys.argv:
        picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    mono = DP.load()
    depth_fn = lambda rgb: DP.frame_infer(mono, rgb)  # noqa: E731
    jobs = []
    for i in picks:
        box = Box(out, ch.pid(i))
        letters, chars, fr = box.letters(), box.characters(), box.frames()
        if letters is not None and chars is not None and fr and fr.current:
            jobs.append((box, ch.image(i), CD.plan(box, ch.image(i), letters, chars, depth_fn)))
    erase_boxes([(b, np.asarray(img), p) for b, img, p in jobs], dry)
    if not dry:
        for b, img, p in jobs:
            print(f"  {b.pid} layers: {CD.render(b, p, img, depth_fn)}")
    print(f"spent today {FE.spent_today('bfl'):.2f} USD on erases, {FE.spent_today():.2f} in all")


if __name__ == "__main__":
    main()
