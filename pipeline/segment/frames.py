"""Drawn frames inside one box: a page comic box (Pepper&Carrot) nearly always holds several, a webtoon box rarely
(ToG 228 p64). Each frame is its own scene and its own camera, so step 4 fits depth per frame (parallax.build).

frames(img, page_mask) -> list of bool HxW masks, one per frame (an empty list or one mask: the box is one scene).

Recursive XY-cut, from experiments/frame_count.py, with the page defined by the box's gutter mask (parallax.gutter:
white, light grey or black page) instead of near-white alone, which made a grey page "art": the old count split
speech bubbles on ToG 223's grey page into two to four "frames" (p52, p94, p120...).
  1. gutter-like pixels: the page mask, pixels of the page's colour, and white (bubbles crossing a gutter);
  2. a region is trimmed to its rows and columns that are not gutter-like (share under GUT), then cut at the first
     band of at least BAND rows (or columns) that are GUT gutter-like, leaving at least MIN_PART px on both sides;
     recurse on both sides;
  3. a leaf is a frame when it is at least MIN_FRAME px on each side and holds drawn art: at least ART_SHARE of the
     leaf and ART_PX pixels that are mid-tone or coloured (not near-black, not near-white) and not page. Lettering
     is black on white (caption boxes, bubbles, a bubble cluster in the page) and fails this; the old count's
     mid-tone test passed it on a grey page, whose 214 grey is a mid-tone.
The mask of a frame is its leaf rectangle minus the page.
Not detected: inset frames drawn over a larger frame, frames that touch with no gutter between them.

    python frames.py <episode.zumi> [...]    frames per box per episode
"""
from __future__ import annotations

import numpy as np
from PIL import Image

BAND = 5          # px, narrowest gutter
GUT = 0.85        # share of a band's pixels that must be gutter-like (a bubble, an SFX or art may cross the gutter:
                  # a feather drawn across P&C 39 p12's gutter left 87-90% of its rows gutter)
PAGE_BAND = 0.7   # ... and real page (the page mask)
MIN_PART = 80     # px, smallest part a cut may leave
MIN_FRAME = 150   # px, smallest frame side
ART_SHARE = 0.25  # share of the leaf that must be drawn art
ART_PX = 12000    # px of drawn art a frame needs at least
FILL = 0.5        # share of the leaf that is not page: a drawn frame fills its rectangle, an SFX letter in the gutter
                  # (ToG 228 p93's red R) fills a fraction of it. Not "not gutter-like": white bubbles and highlights
                  # inside a frame are (fill 0.42-0.50 on ToG 228 p15, ToG 223 p46, p102; not page 0.72-0.87)
PAGE_TOL = 4.0    # CIELAB distance to the page colour (parallax.PAGE_TOL)


def _gutter_like(a: np.ndarray, page_mask: np.ndarray) -> np.ndarray:
    import cv2
    gl = page_mask | (a.min(axis=2) >= 240)
    if page_mask.any():
        lab = cv2.cvtColor(a.astype(np.float32) / 255, cv2.COLOR_RGB2LAB)
        pc = np.median(lab[page_mask], axis=0)
        gl |= np.linalg.norm(lab - pc, axis=-1) <= PAGE_TOL
    return gl


def _trim(gl, y0, y1, x0, x1):
    sub = gl[y0:y1, x0:x1]
    r = np.flatnonzero(sub.mean(axis=1) < GUT)
    c = np.flatnonzero(sub.mean(axis=0) < GUT)
    if not len(r) or not len(c):
        return None
    return int(y0 + r[0]), int(y0 + r[-1] + 1), int(x0 + c[0]), int(x0 + c[-1] + 1)


def _cut(gl, page, art, y0, y1, x0, x1, memo) -> tuple[list, list]:
    """(frames, rejected leaves) of one region. Each gutter band is tried; the first whose two sides both hold a frame
    is the cut. Failing that the region is one frame if it passes the art test as a whole: a white bubble column
    inside a frame (Pepper&Carrot 39 p8) or a bubble band across one (p9) is gutter-like, and cut there the frame
    lost its other half to a rejected leaf. Failing that too, the first band with a frame on one side is the cut (ToG
    228 p64: a hand under its bubbles, whose art share the bubbles dilute); else the region is a rejected leaf."""
    t = _trim(gl, y0, y1, x0, x1)
    if t is None:
        return [], []
    if t in memo:
        return memo[t]
    y0, y1, x0, x1 = t
    sub, psub = gl[y0:y1, x0:x1], page[y0:y1, x0:x1]
    res, half = None, None
    for axis in (0, 1):  # 0: a horizontal gutter (rows), 1: a vertical one (columns)
        # a gutter is gutter-like across GUT of the region and mostly real page: white art (ToG 228 p7's fur) is
        # gutter-like but enclosed by the frame (page share 0.53 there, 0.92-1.0 across real gutters)
        ok = (sub.mean(axis=1 - axis) >= GUT) & (psub.mean(axis=1 - axis) >= PAGE_BAND)
        ok = np.concatenate([[False], ok, [False]]).astype(np.int8)
        n = len(ok) - 2
        d = np.diff(ok)
        for a, b in zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)):  # maximal gutter-like runs [a, b)
            if b - a >= BAND and a >= MIN_PART and n - b >= MIN_PART:
                a, b = int(a), int(b)
                if axis == 0:
                    k1, d1 = _cut(gl, page, art, y0, y0 + a, x0, x1, memo)
                    k2, d2 = _cut(gl, page, art, y0 + b, y1, x0, x1, memo)
                else:
                    k1, d1 = _cut(gl, page, art, y0, y1, x0, x0 + a, memo)
                    k2, d2 = _cut(gl, page, art, y0, y1, x0 + b, x1, memo)
                if k1 and k2:
                    res = (k1 + k2, d1 + d2)
                    break
                if (k1 or k2) and half is None:
                    half = (k1 + k2, d1 + d2)
        if res:
            break
    if res is None:
        area = (y1 - y0) * (x1 - x0)
        n = int(art[y0:y1, x0:x1].sum())
        big = y1 - y0 >= MIN_FRAME and x1 - x0 >= MIN_FRAME
        if big and n >= ART_PX and n >= ART_SHARE * area and (~psub).mean() >= FILL:
            res = ([t], [])
        else:
            res = half or ([], [t])
    memo[t] = res
    return res


def leaves(img: Image.Image, page_mask: np.ndarray) -> tuple[list, list]:
    """(frame rectangles, rejected leaf rectangles) as (y0, y1, x0, x1)."""
    a = np.asarray(img.convert("RGB"))
    gl = _gutter_like(a, page_mask)
    art = ~gl & (a.max(axis=2) > 40) & (a.min(axis=2) < 215)
    return _cut(gl, page_mask, art, 0, a.shape[0], 0, a.shape[1], {})


PIECE_MIN = 0.02   # share of the art a piece between gutters must hold to be a frame of its own
PIECE_MAX = 8      # more pieces than this is a page of text (credits: 16), not frames


def by_gutter(page_mask: np.ndarray) -> list[np.ndarray]:
    """The art's connected pieces between gutters that hold at least PIECE_MIN of it; [] when there are more than
    PIECE_MAX of them (text pages)."""
    from scipy.ndimage import label
    art = ~page_mask
    lab, n = label(art)
    if not n:
        return []
    size = np.bincount(lab.ravel())[1:]
    ids = [k + 1 for k in np.flatnonzero(size >= PIECE_MIN * art.sum())]
    return [lab == k for k in ids] if len(ids) <= PIECE_MAX else []


def frames(img: Image.Image, page_mask: np.ndarray) -> list[np.ndarray]:
    """One mask per frame: its rectangle minus the page. With several frames, the art no rectangle holds (a rejected
    leaf: a caption, a bubble cluster, an SFX in the gutter) joins the nearest frame, so the masks cover every non-page
    pixel exactly once."""
    from scipy.ndimage import distance_transform_edt
    keep, _ = leaves(img, page_mask)
    lab = np.zeros(page_mask.shape, np.int32)
    for k, (y0, y1, x0, x1) in enumerate(keep, 1):
        lab[y0:y1, x0:x1] = k
    if len(keep) > 1:
        _, (iy, ix) = distance_transform_edt(lab == 0, return_indices=True)
        lab = lab[iy, ix]
    pieces = by_gutter(page_mask)
    if len(pieces) > 1:
        # the rectangle cuts need a straight gutter across the whole box: slanted gutters left a row of four insets as
        # ONE frame, and the depth model saw them as one picture (P&C 39 p12); the art's pieces between gutters split
        # them, and the rectangle cuts still split pieces that art drawn across a gutter joins (the hat inset's
        # feather into the big panel below). A frame is a piece of one rectangle
        plab = np.zeros(page_mask.shape, np.int32)
        for k, p in enumerate(pieces, 1):
            plab[p] = k
        _, (iy, ix) = distance_transform_edt(plab == 0, return_indices=True)
        both = np.where(page_mask, 0, lab * (len(pieces) + 1) + plab[iy, ix])
        art = (~page_mask).sum()
        ids, size = np.unique(both[both > 0], return_counts=True)
        big = ids[size >= PIECE_MIN * art]
        lab = np.zeros(page_mask.shape, np.int32)
        for k, v in enumerate(big, 1):
            lab[both == v] = k
        _, (iy, ix) = distance_transform_edt(lab == 0, return_indices=True)  # crumbs join the nearest frame
        lab = lab[iy, ix]
        keep = list(big)
    return [(lab == k) & ~page_mask for k in range(1, len(keep) + 1)]


def main() -> None:
    import io
    import json
    import sys
    import zipfile
    from pathlib import Path
    import parallax as PX
    for zp in map(Path, sys.argv[1:]):
        z = zipfile.ZipFile(zp)
        counts = []
        for p in json.loads(z.read("manifest.json"))["panels"]:
            img = Image.open(io.BytesIO(z.read(p["layers"][0]["image"]))).convert("RGB")
            counts.append(len(frames(img, PX.gutter(img))))
        hist = {k: counts.count(k) for k in sorted(set(counts))}
        print(f"{zp.stem}: {len(counts)} boxes, frames per box {hist}; multi: {[i for i, c in enumerate(counts) if c > 1]}")


if __name__ == "__main__":
    main()
