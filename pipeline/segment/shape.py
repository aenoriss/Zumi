"""The lettering shape rules, one place for every pass that judges a lettering mask: the first pass and the
sound-effect refinement (bubbles.py) and the review's additions and extensions (review_loop.py).

The shares below are of a TILE, the square one box-width wide the first pass runs SAM on (sam.tiles), not of the
whole box: a caller with a box-size mask passes ref_area=tile_area(h, w). The review once judged its additions by
the box's area, so on a box three times as tall as wide a word counted as a third of its share.

    letter_shaped(m, ref_area)                       a sound-effect mask that could be letters
    dialogue_like(pixels, m, kind, score, ref_area)  a bubble or caption mask that holds text
    letter_stats(m)                                  (letter count, letter height) of a word
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import label

from textcrops import letter_count

# Dialogue masks must hold dialogue (measured on 85 hits from 8 panels, labelled by eye): blood drops and specks
# held 0-2 lettering blobs at 0.1-0.8 % of the tile; real bubbles 2-70 blobs; a bubble holding only "!" is large.
MIN_LETTERS, MIN_FEW_LETTER_SHARE = 3, 0.01  # 3+ blobs, or 1+ blob in a mask over 1 % of the tile
# A caption is a flat card: share of its pixels within 30 of its median colour was 0.71-0.93 for real cards and
# 0.09-0.28 for whole panels the card pass returned (Pepper&Carrot 39 rows 8 and 14, Tower of God 223 p4).
MIN_CAPTION_UNIFORMITY = 0.5
# Weak hits must be flat shapes: the black "!" splat (ToG 228 p89, score 0.30) had uniformity 0.89-0.91; the
# face the burst pass picked at 0.31-0.32 (True Beauty 5 p57) 0.19-0.57. Spiky bursts are not flat but score 0.8+.
WEAK_SCORE, WEAK_MIN_UNIFORMITY = 0.4, 0.8

# Lettering shape of a sound-effect mask (same 368 hits): letters are strokes with gaps.
MAX_SFX_SHARE = 0.15  # never more than this share of the tile
BIG_SFX_SHARE, MAX_BIG_FILL = 0.04, 0.30  # over 4 % of the tile, words filled 0.15-0.29 of their box, art more
MAX_SFX_FILL, MIN_SOLID_SHARE = 0.6, 0.03  # solid shapes over 3 % of the tile are art
MAX_ANY_FILL = 0.68  # letters filled at most 0.66 of their box at any size; a head (ToG 223 p11) filled 0.80
MIN_STRIP_ASPECT = 0.06  # a box this flat (height / width) is a band along a panel edge, not a word


def tile_area(h: int, w: int) -> int:
    """The area the shares are of, for a box h x w: one tile, a square of the box's width (the box itself when it
    is wider than tall)."""
    return w * min(h, w)


def uniformity(pixels: np.ndarray, m: np.ndarray) -> float:
    """Share of the mask's pixels within 30 (any channel) of its median colour: high for a flat card or splat."""
    vals = pixels[m].astype(np.int16)
    return float((np.abs(vals - np.median(vals, axis=0)).max(axis=1) <= 30).mean())


def letter_shaped(m: np.ndarray, ref_area: int | None = None) -> bool:
    """Could this sound-effect mask be letters rather than a piece of art or a panel-edge band? ref_area: what its
    share is of (default the mask's own frame: a tile)."""
    share = m.sum() / (ref_area or m.size)
    if share == 0 or share > MAX_SFX_SHARE:
        return False
    ys, xs = np.nonzero(m)
    bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
    fill = m.sum() / (bh * bw)
    if bh < MIN_STRIP_ASPECT * bw:
        return False
    if share > BIG_SFX_SHARE:
        return fill <= MAX_BIG_FILL
    return fill <= MAX_ANY_FILL and not (fill > MAX_SFX_FILL and share > MIN_SOLID_SHARE)


def dialogue_like(pixels: np.ndarray, m: np.ndarray, kind: str, score: float, ref_area: int | None = None) -> bool:
    """Does this bubble or caption mask hold text, and is it a flat shape where it has to be (captions, weak hits)?
    ref_area: what its share is of (default the mask's own frame: a tile)."""
    if not m.any():
        return False
    if kind == "caption" or score < WEAK_SCORE:
        if uniformity(pixels, m) < (WEAK_MIN_UNIFORMITY if score < WEAK_SCORE else MIN_CAPTION_UNIFORMITY):
            return False
    n = letter_count(pixels, m)
    return n >= MIN_LETTERS or (n >= 1 and m.sum() / (ref_area or m.size) >= MIN_FEW_LETTER_SHARE)


def letter_stats(m: np.ndarray) -> tuple[int, float]:
    """(letter count, letter height) of a word mask: the height the median of its blobs at least 0.4 as tall as the
    tallest."""
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
