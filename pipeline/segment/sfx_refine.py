"""Step 2a, sound-effect refinement: tighten each sound-effect mask to its letters with a zoomed SAM 3.1 pass.

The first pass (bubbles.py) finds sound effects on a whole tile, so their masks are loose (art between letters, a
whisper's "per" beside "whis"). Per mask: SAM re-runs "letters" on a crop of the mask enlarged to 1008 px and keeps
only what lies in the old mask; pieces it missed get a second zoomed pass ("letters", "text"); an empty result drops
the effect unless the old mask is stroke-shaped (an isolated letter SAM will not re-find). Letters of the same word
the old mask lacked are looked for around it and kept only if SAM confirms them. Then pieces of one word are grouped
(only a fragment of 1-2 letters joins a neighbour) and the whole word is re-segmented; a word with a gap still wider
than 2.2 letter spacings loses its fragments. Tuned on Tower of God 223 / 228, True Beauty 5, Pepper&Carrot 39
(variant v9 of a scratch script, 2026-10-23).
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, label

from masks import Found

C = dict(prompts=["letters"], prompts2=["letters", "text"], rescue=["text"], pad=16, fallback=0.35, margin=1, thr=0.45,
         missing_frac=0.3)


def zoom_masks(seg, img, box, region, prompts, thr):
    """Every instance SAM finds on the zoomed box (sam.Segmenter.zoom) that lies mostly inside `region`, united."""
    keep = np.zeros(region.shape, bool)
    for prob, _, _ in seg.zoom(img, box, prompts):
        # downsampled probabilities, then thresholded: smooth edges, thin strokes survive
        mm = prob > thr
        if mm.sum() and (mm & region).sum() >= 0.7 * mm.sum():
            keep |= mm
    return keep & region


def bbox(m, pad, h, w):
    ys, xs = np.nonzero(m)
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(w, xs.max() + pad + 1), min(h, ys.max() + pad + 1))


def colour_codes(pixels):
    q = (pixels // 16).astype(np.int32)
    return q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]


def refine(seg, img, m):
    """One sound-effect mask -> (tightened mask, status); an empty mask means the effect is dropped."""
    c = C
    h, w = m.shape
    region = binary_dilation(m, iterations=3)
    out = np.zeros_like(m)
    x0, y0, x1, y1 = bbox(m, c["pad"], h, w)
    out[y0:y1, x0:x1] = zoom_masks(seg, img, (x0, y0, x1, y1), region[y0:y1, x0:x1], c["prompts"], c["thr"])
    if out.sum() < c["fallback"] * m.sum():  # e.g. white outlined letters on white
        out[y0:y1, x0:x1] |= zoom_masks(seg, img, (x0, y0, x1, y1), region[y0:y1, x0:x1], c["rescue"], c["thr"])
    rest = m & ~binary_dilation(out, iterations=6)
    lab, n = label(rest)
    for k in range(1, n + 1):
        part = lab == k
        if part.sum() < 0.03 * m.sum() or part.sum() < 150:
            continue
        bx = bbox(part, c["pad"], h, w)
        out[bx[1]:bx[3], bx[0]:bx[2]] |= zoom_masks(seg, img, bx, binary_dilation(part, iterations=3)[bx[1]:bx[3], bx[0]:bx[2]],
                                                    c["prompts2"], c["thr"])
    if out.sum() < c["fallback"] * m.sum():
        # SAM would not re-find it zoomed, but the original mask looks like strokes, not a flat region: an isolated
        # letter (ToG 223: K, R, H, E, PAT were wrongly dropped; hair, cape, skin were flat or solid)
        ys, xs = np.nonzero(m)
        fill = m.sum() / ((ys.ptp() + 1) * (xs.ptp() + 1))
        vals = np.asarray(img)[m].astype(int)
        uni = (np.abs(vals - np.median(vals, 0)).max(1) <= 30).mean()
        if fill <= 0.55 and uni <= 0.45:
            return m, "kept-original"
        return np.zeros_like(m), "dropped"
    out, status = complete(np.asarray(img), m, out)
    if status == "partial":
        return np.zeros_like(m), "dropped-partial"
    out, st2 = extend(seg, img, out)
    if st2 != "ok":
        status = st2 if status == "ok" else status + "+" + st2
    region = region | binary_dilation(out, iterations=3)
    out = binary_dilation(out, iterations=c["margin"]) & region
    return out, status


def complete(pixels, orig, out):
    """Letters SAM's zoomed pass missed: blobs of the original mask, away from the new mask, whose colours match the
    captured letters rather than the gaps between them. Recapture them; a letter-like leftover still unresolved is
    reported, so the whole effect is dropped instead of half-erased."""
    if not out.any():
        return out, "ok"
    code = colour_codes(pixels)
    gaps = orig & ~binary_dilation(out, iterations=2)
    letters_h = np.bincount(code[out], minlength=4096) / max(1, out.sum())
    gaps_h = np.bincount(code[gaps], minlength=4096) / max(1, gaps.sum())
    letter_colour = letters_h > 2.0 * gaps_h + 1e-4  # far commoner in the letters than in the gaps
    rest = orig & ~binary_dilation(out, iterations=4)
    cand = rest & letter_colour[code]
    lab, n = label(cand)
    if not n:
        return out, "ok"
    letter_lab, _ = label(out)
    areas = np.bincount(letter_lab.ravel())[1:]
    typical = float(np.median(areas)) if len(areas) else 0
    sizes = np.bincount(lab.ravel())
    missing = [k for k in range(1, n + 1) if sizes[k] >= C["missing_frac"] * typical]
    if not missing:
        return out, "ok"
    add = binary_dilation(np.isin(lab, missing), iterations=2) & orig  # the blob plus its outline ring
    new = out | add
    left = orig & ~binary_dilation(new, iterations=4) & letter_colour[code]
    ll, nn = label(left)
    if nn and np.bincount(ll.ravel())[1:].max() >= C["missing_frac"] * typical:
        return out, "partial"
    return new, "recaptured"


def extend(seg, img, out):
    """A letter the original mask never had: a blob near the captured letters with their colours and size, in line
    with the word. Added only if SAM confirms it on a zoomed crop; an unconfirmed candidate is ignored (Tower of God
    223: all 4 effects dropped on an unconfirmed candidate were complete words)."""
    if not out.any():
        return out, "ok"
    pixels = np.asarray(img)
    h, w = out.shape
    lab, nl = label(out)
    hs, areas = [], []
    for j in range(1, nl + 1):
        ys = np.nonzero(lab == j)[0]
        hs.append(ys.max() - ys.min() + 1)
        areas.append((lab == j).sum())
    H, A = float(np.median(hs)), float(np.median(areas))
    if H < 8:
        return out, "ok"
    code = colour_codes(pixels)
    band = binary_dilation(out, iterations=int(1.2 * H)) & ~binary_dilation(out, iterations=3)
    letters_h = np.bincount(code[out], minlength=4096) / max(1, out.sum())
    band_h = np.bincount(code[band], minlength=4096) / max(1, band.sum())
    letter_colour = letters_h > 3.0 * band_h + 1e-4
    cand = band & letter_colour[code]
    top2 = np.argsort(letters_h)[::-1][:2]  # fill and outline: a missing letter must hold both
    cy = np.array([np.mean(np.nonzero(lab == j)[0]) for j in range(1, nl + 1)])
    cx = np.array([np.mean(np.nonzero(lab == j)[1]) for j in range(1, nl + 1)])
    pts = np.stack([cx, cy], 1)
    centre = pts.mean(0)
    axis = np.linalg.svd(pts - centre)[2][0] if nl >= 2 else np.array([1.0, 0.0])
    cl, cn = label(binary_dilation(cand, iterations=1))
    status = "ok"
    for k in range(1, cn + 1):
        blob = (cl == k) & cand
        ys, xs = np.nonzero(blob)
        bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        if not (0.3 * A <= blob.sum() <= 3 * A and 0.5 * H <= bh <= 2 * H):
            continue
        if blob.sum() / (bh * bw) > 0.66:  # solid: art, not a stroke
            continue
        if min((code[blob] == t).mean() for t in top2) < 0.1:
            continue
        d = np.array([xs.mean(), ys.mean()]) - centre
        if abs(d[0] * axis[1] - d[1] * axis[0]) > H:  # not in line with the word
            continue
        bx = bbox(blob, C["pad"], h, w)
        got = zoom_masks(seg, img, bx, binary_dilation(blob, iterations=4)[bx[1]:bx[3], bx[0]:bx[2]], C["prompts"], C["thr"])
        if got.sum() >= 0.5 * blob.sum():
            out[bx[1]:bx[3], bx[0]:bx[2]] |= got
            status = "extended"
    return out, status


def letter_stats(m):
    """(letter count, letter height) of a word mask."""
    lab, n = label(m)
    if not n:
        return 0, 0.0
    hs = []
    for j in range(1, n + 1):
        ys = np.nonzero(lab == j)[0]
        hs.append(ys.max() - ys.min() + 1)
    big = [h for h in hs if h >= 0.4 * max(hs)]
    H = float(np.median(big))
    # touching letters (SCRITCH) form one blob: also estimate the count from the word's length along its axis,
    # with the letter height taken as the word's thickness across that axis
    ys, xs = np.nonzero(m)
    pts = np.stack([xs, ys], 1).astype(float)
    if len(pts) > 2000:
        pts = pts[:: len(pts) // 2000]
    vt = np.linalg.svd(pts - pts.mean(0), full_matrices=False)[2]
    along, across = (pts - pts.mean(0)) @ vt[0], (pts - pts.mean(0)) @ vt[1]
    thick = np.percentile(across, 97) - np.percentile(across, 3)
    by_length = int(round((along.max() - along.min()) / max(thick, 1.0)))
    return max(len(big), by_length), H


def same_word(code, a, b):
    """Two sound-effect masks are pieces of one word: same letter colours, similar letter height, close."""
    ha = np.bincount(code[a], minlength=4096) / max(1, a.sum())
    hb = np.bincount(code[b], minlength=4096) / max(1, b.sum())
    if np.minimum(ha, hb).sum() < 0.4:
        return False
    _, Ha = letter_stats(a)
    _, Hb = letter_stats(b)
    if not Ha or not Hb or max(Ha, Hb) / min(Ha, Hb) > 1.7:
        return False
    ya, xa = np.nonzero(a)
    yb, xb = np.nonzero(b)
    gy = max(0, max(ya.min(), yb.min()) - min(ya.max(), yb.max()))
    gx = max(0, max(xa.min(), xb.min()) - min(xa.max(), xb.max()))
    return (gy ** 2 + gx ** 2) ** 0.5 <= 3 * max(Ha, Hb)


def gap_letters(code, union, H, A, region):
    """Letter-like blobs (the word's colours, letter size, stroke-shaped) inside `region` not covered by `union`."""
    # background colours from the whole panel outside the word, not a ring around it: a ring would hold the missing
    # letters themselves (RUMBLE, ToG 223 p2)
    band = ~binary_dilation(union, iterations=3)
    lh = np.bincount(code[union], minlength=4096) / max(1, union.sum())
    bh = np.bincount(code[band], minlength=4096) / max(1, band.sum())
    colour = lh > 3.0 * bh + 1e-4
    top2 = np.argsort(lh)[::-1][:2]
    cand = region & ~binary_dilation(union, iterations=3) & colour[code]
    cl, cn = label(binary_dilation(cand, iterations=1))
    out = np.zeros_like(union)
    for k in range(1, cn + 1):
        blob = (cl == k) & cand
        ys, xs = np.nonzero(blob)
        bh_, bw_ = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        if not (0.3 * A <= blob.sum() <= 3 * A and 0.5 * H <= bh_ <= 2.2 * H):
            continue
        if blob.sum() / (bh_ * bw_) > 0.66:
            continue
        if min((code[blob] == t).mean() for t in top2) < 0.08:
            continue
        out |= blob
    return out


def widest_gap(m, H):
    """Largest gap between consecutive letters along the word's axis, in normal letter spacings (or letter heights
    when there are too few letters to measure spacing)."""
    lab, n = label(m)
    cents = []
    for j in range(1, n + 1):
        ys, xs = np.nonzero(lab == j)
        if ys.ptp() + 1 >= 0.4 * H:
            cents.append((xs.mean(), ys.mean()))
    if len(cents) < 2:
        return 0.0
    pts = np.array(cents)
    axis = np.linalg.svd(pts - pts.mean(0))[2][0]
    gaps = np.diff(np.sort((pts - pts.mean(0)) @ axis))
    unit = float(np.median(gaps)) if len(gaps) >= 3 else H
    return float(gaps.max() / max(unit, 1.0))


def word_check(seg, img, pieces):
    """Pieces judged to be one word (or one short fragment alone) -> (mask, or per-piece list, or None; status)."""
    union = np.logical_or.reduce(pieces)
    _, H = letter_stats(union)
    h, w = union.shape
    if len(pieces) > 1:
        # zoom SAM on the whole word to capture letters between the pieces, then require even spacing
        if not H or H < 8:
            return union, "word-joined"
        bx = bbox(union, int(0.5 * H), h, w)
        got = zoom_masks(seg, img, bx, np.ones((bx[3] - bx[1], bx[2] - bx[0]), bool), C["prompts"], C["thr"])
        grown = union.copy()
        grown[bx[1]:bx[3], bx[0]:bx[2]] |= got
        before, after = widest_gap(union, H), widest_gap(grown, H)
        if after > 2.2:
            # letters still missing: drop the fragments (1-2 letters, the half-erasure risk), keep complete words
            # (GAAAAH beside a stray "AA" of another word, ToG 223 p4)
            return [p if letter_stats(p)[0] > 2 else None for p in pieces], "dropped-word-gap"
        return grown, ("word-captured" if before > 2.2 else "word-joined")
    if not H or H < 8:
        return union, "ok"
    code = colour_codes(np.asarray(img))
    lab, _ = label(union)
    A = float(np.median(np.bincount(lab.ravel())[1:]))
    missing = gap_letters(code, union, H, A, binary_dilation(union, iterations=int(1.5 * H)))
    if not missing.any():
        return union, "ok"
    bx = bbox(union | missing, C["pad"], h, w)
    got = zoom_masks(seg, img, bx, binary_dilation(union | missing, iterations=6)[bx[1]:bx[3], bx[0]:bx[2]], C["prompts"], C["thr"])
    grown = union.copy()
    grown[bx[1]:bx[3], bx[0]:bx[2]] |= got
    left = missing & ~binary_dilation(grown, iterations=2)
    if left.sum() < 0.3 * missing.sum():
        return grown, "fragment-captured"
    return None, "dropped-fragment"


def refine_panel(seg, img: Image.Image, found: list[Found]) -> list[Found]:
    """All sound effects of a panel refined and grouped into words; bubbles and captions pass through unchanged."""
    items, seen = [], set()
    for f in found:
        if f.kind != "sfx":
            continue
        k = f.mask.tobytes().__hash__()
        if k in seen:
            continue
        seen.add(k)
        r, _ = refine(seg, img, f.mask)
        items.append([f, r])
    code = colour_codes(np.asarray(img))
    live = [k for k, it in enumerate(items) if it[1].any()]
    parent = {k: k for k in live}

    def find(k):
        while parent[k] != k:
            k = parent[k]
        return k

    letters = {k: letter_stats(items[k][1])[0] for k in live}
    for i1 in live:
        for i2 in live:
            # two pieces of 3+ letters each are separate words (SCRITCH beside SCRIBBLE, MUMBLE MUMBLE); only a
            # fragment of 1-2 letters is joined to a neighbour (RUMBLE split as R + LE)
            if i1 < i2 and min(letters[i1], letters[i2]) <= 2 and same_word(code, items[i1][1], items[i2][1]):
                parent[find(i1)] = find(i2)
    groups: dict[int, list[int]] = {}
    for k in live:
        groups.setdefault(find(k), []).append(k)
    for ks in groups.values():
        if len(ks) == 1 and letters[ks[0]] > 2:
            continue  # a word of 3+ letters on its own: nothing to check
        res, _ = word_check(seg, img, [items[k][1] for k in ks])
        for n_, k in enumerate(ks):
            if isinstance(res, list):
                items[k][1] = res[n_] if res[n_] is not None else np.zeros_like(items[k][1])
            else:
                items[k][1] = res if res is not None else np.zeros_like(items[k][1])
    out = [f for f in found if f.kind != "sfx"]
    return out + [Found(r, f.score, "sfx") for f, r in items if r.any()]
