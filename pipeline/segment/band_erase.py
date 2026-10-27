"""Step 3, the erase, as settled with the user on 2026-10-27 (tests in experiments/prefill_*.py, erase_review/):
what is behind every card is painted by FLUX Erase, from as much real background as the model can use.

Per box, from its flat layers (mesh/<pid>.cards.json: the cards and the frames' windows):
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
6. the model's colour cast removed (a per-channel fit on the background away from the cards), the tone matched at
   every outline (seam_match).

Writes plates/<pid>/band-plate.png (the whole box, the art outside the cards) and band-raw[-fK].npz (the paid
outputs, keyed on the mask: a rerun with the same mask pays nothing); episode.layers_step uses band-plate.png as
the backdrop when it exists.

    uv run python band_erase.py <episode.zumi> <out dir> [--panels 3,7] [--dry]
"""
from __future__ import annotations

import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, distance_transform_edt as edt

import flux_erase as FE

LEAN = 0.3 / 1.5     # the head move the band covers, in units of the reading distance (30 cm at 1.5 m)
BAND_PAD = 6         # px past that shift
MAX_SHARE = 0.55     # a frame's band grown while its masked share stays under this
GROW_STEP = 8        # px per growth step
WINDOW_GROW = 13     # a window is cut 12 px inside its frame (cards.INSET): grown back to the frame's edge
UNDER_GROW = 4       # px past the cards where the model's output replaces the art
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


def box_layers(cj: dict, mesh: Path) -> tuple[list[dict], list[np.ndarray]]:
    """The box's cards ({mask, kind, shift}: shift = px a LEAN head move slides the card over its backdrop) and its
    frames (each window grown back to the frame's edge)."""
    w, h = cj["w"], cj["h"]
    f = max(w, h) / (2 * np.tan(np.radians(cj["fov"] / 2)))
    back_z = {l["frame"]: l["z"] for l in cj["layers"] if l["kind"] == "backdrop"}
    cards, frames = [], []
    for l in cj["layers"]:
        if l["kind"] == "backdrop":
            wa = np.asarray(Image.open(mesh / l["window"]))[..., 3] > 0
            fa = np.zeros((h, w), bool)
            x0, y0 = l["window_bbox"][:2]
            fa[y0:y0 + wa.shape[0], x0:x0 + wa.shape[1]] = wa
            frames.append(binary_dilation(fa, iterations=WINDOW_GROW))
            continue
        a = np.asarray(Image.open(mesh / l["png"]).convert("RGBA"))[..., 3] > 127
        x0, y0, x1, y1 = l["bbox"]
        m = np.zeros((h, w), bool)
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        m[sy0:sy1, sx0:sx1] = a[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        zb = back_z.get(l.get("frame"), max(back_z.values()) if back_z else 1.2)
        mid = l["z"] * (1 - l.get("relief_amp", 0) * 0.5)  # between the card's plane and its relief peak
        cards.append({"mask": m, "kind": l["kind"], "shift": f * LEAN * (1 / mid - 1 / zb)})
    return cards, frames


def band_mask(cards: list[dict], frames: list[np.ndarray], art: np.ndarray) -> np.ndarray:
    """The erase mask: per card a band of its shift + BAND_PAD px (bubbles whole), then grown per frame toward the
    interior while the frame's masked share stays under MAX_SHARE."""
    foot = np.logical_or.reduce([c["mask"] for c in cards])
    d = edt(foot)
    band = np.zeros_like(foot)
    for c in cards:
        band |= c["mask"] if c["kind"] == "lettering" else c["mask"] & (d <= abs(c["shift"]) + BAND_PAD)
    for fa in frames:
        fa = fa & art
        if not fa.any():
            continue
        extra = 0
        while extra < 400 and ((band | (foot & (d <= extra + GROW_STEP))) & fa).sum() / fa.sum() < MAX_SHARE:
            extra += GROW_STEP
        band |= foot & fa & (d <= extra)
    return band & art


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


def cast_fit(got: np.ndarray, ref: np.ndarray, m: np.ndarray) -> np.ndarray:
    """Per channel, got -> ref by least squares on the pixels m (the model's colour cast)."""
    out = got.astype(np.float32).copy()
    if m.sum() < 200:
        return out
    for c in range(3):
        A = np.c_[got[m][:, c], np.ones(int(m.sum()))]
        k, *_ = np.linalg.lstsq(A, ref[m][:, c].astype(np.float64), rcond=None)
        out[..., c] = got[..., c] * k[0] + k[1]
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
    # the key: the mask, and INPUT_VERSION for changes to what is sent beside it (bump it when the input changes)
    key = hashlib.sha1(np.packbits(m).tobytes() + str(m.shape).encode() + INPUT_VERSION.encode()).hexdigest()[:16]
    if cache.exists():
        z = np.load(cache)
        if str(z["key"]) == key:
            return z["g"], "saved output"
    if dry:
        return None, "dry"
    _, got, line = FE.erase_panel(sent.copy(), m)
    np.savez_compressed(cache, g=got.astype(np.uint8), key=key)
    return got, line


def erase_box(img: np.ndarray, cj: dict, mesh: Path, out: Path, dry: bool = False, log=print) -> np.ndarray | None:
    """The band-erase plate of one box (the art outside its cards), or None when it has no cards (or dry)."""
    cards, frames = box_layers(cj, mesh)
    if not cards or not frames:
        return None
    # the page is what lies outside every frame: a near-white test took the bubbles' white interiors for page, so
    # they were neither masked nor painted and each bubble stayed in its plate (a ghost behind the bubble card)
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
    out.mkdir(parents=True, exist_ok=True)
    got, line = _call(pre[y0:y1, x0:x1], mask[y0:y1, x0:x1], out / "band-raw.npz", dry)
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
        got_k, line_k = _call(pre[sl], fm, out / f"band-raw-f{k}.npz", dry)
        if got_k is None:
            return None
        why_k = placeholder(got_k, fm, img[sl], fa[sl])
        log(f"    {line_k}" + (f"; still a placeholder ({why_k})" if why_k else ""))
        g[sl] = np.where(fa[sl][..., None], got_k, g[sl])
    fit = ~binary_dilation(foot, iterations=12) & art
    g = cast_fit(g, img, fit)
    # the model's pixels under the cards and UNDER_GROW px past them (the API grows the mask 8 px): the outline's
    # mixed pixels and the backdrop under the cards' 2 px pad (cards.build) are background too, not the figure's edge
    under = binary_dilation(foot, iterations=UNDER_GROW) & art
    res = np.where(under[..., None], g, img.astype(np.float32))
    reach = max(abs(c["shift"]) + BAND_PAD for c in cards)
    res = seam_match(img, res, under, page, reach).clip(0, 255).astype(np.uint8)
    Image.fromarray(res).save(out / "band-plate.png")
    return res


def main():
    zumi, out = Path(sys.argv[1]), Path(sys.argv[2])
    dry = "--dry" in sys.argv
    z = zipfile.ZipFile(zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    picks = range(len(panels))
    if "--panels" in sys.argv:
        picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    mesh = out / "parallax" / "mesh"
    for i in picks:
        pid = f"{zumi.stem}-p{i:03d}"
        cjp = mesh / f"{pid}.cards.json"
        if not cjp.exists():
            continue
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        print(pid)
        try:
            erase_box(img, json.loads(cjp.read_text()), mesh, out / "parallax" / "plates" / pid, dry)
        except SystemExit as e:  # the daily budget
            print(f"STOP: {e}")
            break
        except Exception as e:  # one refused box (BFL moderation) skips only itself
            print(f"  failed, box kept on its old plate: {str(e)[:160]}")
    print(f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
