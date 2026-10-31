"""Clean text crops: each dialogue mask cut out as black lettering on white (bubbles.py's CLI saves them), and the
letter count the lettering filters use (letter_count).

For one bubble or caption mask:
1. inner area = the mask shrunk past its outline (outline width scales with the bubble's size);
2. fill colour = median colour of the inner area (white bubble, black card, coloured plate alike);
3. a pixel is lettering when it is far from the fill colour; the cut-off comes from Otsu's method on that
   distance, so dark-on-light, light-on-dark and glowing text all binarise the same way;
4. lettering is looked for over the whole mask; the outline, tail and burst spikes are connected to the
   mask's outer boundary while letters float on the fill, so blobs touching the boundary are dropped.
   Periods and apostrophes are a few pixels, so only blobs under MIN_BLOB px count as specks. A blob
   spanning most of the bubble both ways is an inset frame or a burst ring; a small blob far from all
   other lettering is a stray mark (a tail tip, a fleck);
5. the lettering is cropped with a margin and upscaled for reading.
"""

from __future__ import annotations

import numpy as np
from PIL import Image
from scipy.ndimage import binary_erosion, distance_transform_edt, find_objects, label
from scipy.ndimage import mean as ndi_mean

PAD = 16  # white margin around the lettering, px after scaling
SCALE = 2  # upscale factor; OCR and vision models read small comic lettering better larger
MIN_CUTOFF = 40  # never call a pixel lettering if it is this close to the fill colour (JPEG noise, glow fringe)
MIN_BLOB = 6  # px; a period at 700 px wide is about 5 x 5
FRAME_SPAN = 0.8  # a blob spanning this share of the bubble's width and height is a frame or ring
STRAY_GAP = 1.5  # in letter heights: a small blob farther than this from any other blob is a stray mark
CORE = 0.45  # depth share (of the mask's deepest point) that separates the core from the outer part
RING_RATIO, RING_SECTORS, RING_COVER = 3.0, 36, 0.7  # burst: outer ink > 3x core ink, around 70 % of 36 sectors
LINE_GAP = 0.8  # in letter heights: an outer blob this close to a kept letter on its row continues the line


def _otsu(values: np.ndarray) -> float:
    hist = np.bincount(values.astype(np.int64), minlength=256).astype(np.float64)
    p = hist / max(1.0, hist.sum())
    omega, mu = np.cumsum(p), np.cumsum(p * np.arange(256))
    with np.errstate(divide="ignore", invalid="ignore"):
        between = (mu[-1] * omega - mu) ** 2 / (omega * (1 - omega))
    if np.isnan(between).all():  # every value equal (a flat region, ToG 228): no split; MIN_CUTOFF decides
        return 0.0
    return float(np.nanargmax(between))


def _drop_strays(ids: np.ndarray, boxes: np.ndarray, sizes: np.ndarray) -> np.ndarray:
    """Small blobs farther than STRAY_GAP letter heights from all other lettering are stray marks."""
    if len(ids) < 3:
        return ids
    letter_h = float(np.median(boxes[:, 1] - boxes[:, 0]))
    gy = np.maximum(0, np.maximum(boxes[:, None, 0] - boxes[None, :, 1], boxes[None, :, 0] - boxes[:, None, 1]))
    gx = np.maximum(0, np.maximum(boxes[:, None, 2] - boxes[None, :, 3], boxes[None, :, 2] - boxes[:, None, 3]))
    near = np.maximum(gx, gy) <= STRAY_GAP * letter_h
    np.fill_diagonal(near, False)
    return ids[~(~near.any(axis=1) & (sizes < np.median(sizes) * 3))]


def _burst_core(ink: np.ndarray, m: np.ndarray, blobs: np.ndarray, ids: np.ndarray, boxes: np.ndarray) -> np.ndarray:
    """In a burst, keep the core text and the letters that continue its lines; elsewhere keep all.

    A burst's ring of spikes breaks into hundreds of pieces, so no per-blob shape rule catches it. What does:
    most of the ink lies in the outer part of the mask (depth under CORE of the deepest point), all the way
    around (most angular sectors). Ordinary bubbles keep most of their ink, the text, in the core. Text in a
    burst can run to the edge (True Beauty 5 p31), so outer blobs on the same row as a kept letter and next to
    it are kept too, repeatedly; the spike ring sits away from the text and never joins.
    """
    depth = distance_transform_edt(m)
    outer = depth < CORE * depth.max()
    outer_ink, core_ink = (ink & outer).sum(), (ink & ~outer).sum()
    if outer_ink <= RING_RATIO * max(core_ink, 1):
        return ids
    ys, xs = np.nonzero(ink & outer)
    cy, cx = np.argwhere(m).mean(axis=0)
    sectors = np.unique((np.arctan2(ys - cy, xs - cx) + np.pi) / (2 * np.pi) * RING_SECTORS).astype(int) % RING_SECTORS
    if len(np.unique(sectors)) < RING_COVER * RING_SECTORS:
        return ids
    in_core = ndi_mean(~outer, labels=blobs, index=ids) > 0.5
    if not in_core.any():
        return ids[in_core]
    b = boxes[ids - 1]
    letter_h = float(np.median(b[in_core, 1] - b[in_core, 0]))
    kept = in_core.copy()
    while True:
        k = b[kept]
        vy = np.minimum(b[:, None, 1], k[None, :, 1]) - np.maximum(b[:, None, 0], k[None, :, 0])
        same_row = vy >= 0.5 * np.minimum(b[:, None, 1] - b[:, None, 0], k[None, :, 1] - k[None, :, 0])
        gx = np.maximum(0, np.maximum(b[:, None, 2] - k[None, :, 3], k[None, :, 2] - b[:, None, 3]))
        grow = ~kept & (same_row & (gx <= LINE_GAP * letter_h)).any(axis=1)
        if not grow.any():
            return ids[kept]
        kept |= grow


def clean_crop(pixels: np.ndarray, mask: np.ndarray) -> Image.Image | None:
    """Black-on-white image of the lettering inside `mask`, or None if there is none."""
    text, _ = lettering(pixels, mask)
    if text is None:
        return None
    out = Image.fromarray(np.where(text, 0, 255).astype(np.uint8))
    out = out.resize((out.width * SCALE, out.height * SCALE), Image.LANCZOS)
    framed = Image.new("L", (out.width + 2 * PAD, out.height + 2 * PAD), 255)
    framed.paste(out, (PAD, PAD))
    return framed


def letter_count(pixels: np.ndarray, mask: np.ndarray) -> int:
    """How many lettering blobs (glyphs, or glyph parts) the mask holds; 0 for a shape with no text."""
    return lettering(pixels, mask)[1]


def lettering(pixels: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray | None, int]:
    """The lettering inside `mask` as a tight boolean image, and its blob count; (None, 0) if there is none."""
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None, 0
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    region = pixels[y0:y1, x0:x1].astype(np.int16)
    m = mask[y0:y1, x0:x1]
    inner = binary_erosion(m, iterations=max(3, int(0.03 * min(y1 - y0, x1 - x0))))
    if inner.sum() < 100:
        inner = m
    fill = np.median(region[inner], axis=0)
    dist = np.abs(region - fill).max(axis=2)
    cutoff = max(MIN_CUTOFF, _otsu(dist[inner]))
    ink = (dist > cutoff) & m

    blobs, n = label(ink)
    if n == 0:
        return None, 0
    ids = np.arange(1, n + 1)
    sizes = np.bincount(blobs.ravel(), minlength=n + 1)[1:]
    boundary = np.pad(m, 1) & ~binary_erosion(np.pad(m, 1), iterations=2)  # padded: the crop edge is boundary too
    touching = np.isin(ids, np.unique(blobs[boundary[1:-1, 1:-1]]))
    boxes = np.array([[s[0].start, s[0].stop, s[1].start, s[1].stop] for s in find_objects(blobs)])
    h, w = y1 - y0, x1 - x0
    frame = ((boxes[:, 1] - boxes[:, 0]) > FRAME_SPAN * h) & ((boxes[:, 3] - boxes[:, 2]) > FRAME_SPAN * w)
    # a blob whose box holds at least half of the other blobs (3 or more) is a frame or a connected burst ring
    # around the text; no letter encloses other letters
    inside = (
        (boxes[None, :, 0] >= boxes[:, None, 0]) & (boxes[None, :, 1] <= boxes[:, None, 1])
        & (boxes[None, :, 2] >= boxes[:, None, 2]) & (boxes[None, :, 3] <= boxes[:, None, 3])
    )
    np.fill_diagonal(inside, False)
    held = inside.sum(axis=1)
    frame |= (held >= 3) & (held >= 0.5 * (n - 1))
    ok = (sizes >= MIN_BLOB) & ~touching & ~frame
    if not ok.any():
        return None, 0
    kept = _burst_core(ink, m, blobs, ids[ok], boxes)
    sel = np.isin(ids, kept)
    keep = _drop_strays(ids[sel], boxes[sel], sizes[sel])
    if not len(keep):
        return None, 0
    text = np.isin(blobs, keep)
    ty, tx = np.nonzero(text)
    return text[ty.min() : ty.max() + 1, tx.min() : tx.max() + 1], len(keep)
