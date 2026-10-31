"""The page around the art: the gutters and margins of a box, white, grey or black. gutter() is the first guess,
from colour alone; the frame step (frames.split) adds a flat page colour it learns outside the panel boxes, and its
page is the one every later step reads (boxstore.Box.frames().page).
"""
from __future__ import annotations

import numpy as np
from PIL import Image

PAGE_TOL = 4.0     # CIELAB distance (L 0..100) from the page colour that still counts as page: a flat digital page
                   # varies by under 0.5 (ToG 223 grey 214 +- 1)
PAGE_BORDER = 0.6  # share of the box's border pixels the page colour must hold ...
PAGE_CUT = 0.8     # ... or of each of its top and bottom rows (a box is cut from the strip at page gutters; a bubble
                   # touching the cut leaves 0.90-0.95 page in those rows, ToG 223 p94, p98)


def lab(img: Image.Image) -> np.ndarray:
    """The box in CIELAB (float32, L 0..100)."""
    import cv2
    return cv2.cvtColor(np.asarray(img.convert("RGB")).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)


def page_colour(img: Image.Image) -> np.ndarray | None:
    """The page's CIELAB colour when it is not white (light grey ToG 223, black), else None (white or no uniform
    page). Candidates: the most common colour (2-unit Lab bins) of the whole border, and of the top and bottom rows;
    a candidate is the page when it holds PAGE_BORDER of the border or PAGE_CUT of each of the two cut rows, within
    PAGE_TOL. White (min channel >= 245) is left to white_margin."""
    lb = lab(img)
    rgb = np.asarray(img.convert("RGB"))
    border = np.concatenate([lb[0], lb[-1], lb[1:-1, 0], lb[1:-1, -1]])
    cut = np.concatenate([lb[0], lb[-1]])
    for src in (border, cut):
        vals, cnt = np.unique(np.round(src / 2), axis=0, return_counts=True)
        c = vals[cnt.argmax()] * 2
        near = np.linalg.norm(src - c, axis=-1) <= PAGE_TOL
        c = np.median(src[near], axis=0)  # the bin's centre refined to the page's own colour
        share = lambda px: float((np.linalg.norm(px - c, axis=-1) <= PAGE_TOL).mean())
        if share(border) >= PAGE_BORDER or (share(lb[0]) >= PAGE_CUT and share(lb[-1]) >= PAGE_CUT):
            edge = np.concatenate([rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]])
            on = np.linalg.norm(border - c, axis=-1) <= PAGE_TOL
            if np.median(edge[on], axis=0).min() >= 245:
                return None
            return c.astype(np.float32)
    return None


def white_margin(img: Image.Image, exclude: np.ndarray | None = None) -> np.ndarray:
    """White reaching the box's edge (min channel >= 245), grown 4 px, plus a 2 px band along the box's border.
    `exclude`: pixels the white may not spread through (speech bubbles, which are white and often touch the edge)."""
    from scipy.ndimage import binary_dilation, label
    a = np.asarray(img.convert("RGB"))
    white = (a.min(axis=2) >= 245)
    if exclude is not None:
        white &= ~exclude
    lb, _ = label(white)
    edge_ids = np.unique(np.concatenate([lb[0], lb[-1], lb[:, 0], lb[:, -1]]))
    out = binary_dilation(np.isin(lb, edge_ids[edge_ids > 0]), iterations=4)
    out[:2], out[-2:], out[:, :2], out[:, -2:] = True, True, True, True
    return out


def gutter(img: Image.Image, letters: np.ndarray | None = None, white_share: float = 0.98) -> np.ndarray:
    """The page around the art: white_margin, plus every row or column that is page apart from lettering. A caption
    box half in the gutter (ToG 228 p6) is not white, so the white alone kept its gutter half as art, and an erase
    mask had FLUX Erase paint floor tiles into the page.
    A page of another colour (page_colour: light grey ToG 223, black) is added the same way: pixels within PAGE_TOL
    of it connected to the box's edge, grown 4 px like the white; and those pixels count as page in the row and
    column rule.
    Speech bubbles are white and often touch the box edge, so the white flood took whole bubbles over the art as page
    (91% of ToG 228 p10's lettering). The page is found without them, then each bubble pixel takes the class of the
    nearest pixel outside the bubbles: a bubble on the art is art, a bubble on the page is page, one hanging off the
    art onto the page is split where it crosses."""
    from scipy.ndimage import binary_dilation, distance_transform_edt, label
    bub = binary_dilation(letters, iterations=3) if letters is not None and letters.any() else None
    g = white_margin(img, exclude=bub)
    page = None
    pc = page_colour(img)
    if pc is not None:
        page = np.linalg.norm(lab(img) - pc, axis=-1) <= PAGE_TOL
        lb, _ = label(page & ~bub if bub is not None else page)
        ids = np.unique(np.concatenate([lb[0], lb[-1], lb[:, 0], lb[:, -1]]))
        g = g | binary_dilation(np.isin(lb, ids[ids > 0]), iterations=4)
    if bub is None:
        return g
    if not bub.all():
        _, (iy, ix) = distance_transform_edt(bub, return_indices=True)
        g = np.where(bub, g[iy, ix], g)
    else:  # the box is all lettering: page
        g = np.ones_like(g)
    white = np.asarray(img.convert("RGB")).min(axis=2) >= 245
    if page is not None:
        white = white | page
    # lettering grown 3 px: the box's outline sits just outside its mask (gutter rows read 0.975 white without it, 1.0
    # with it)
    art = ~binary_dilation(letters, iterations=3)
    rows = ((white & art).sum(1) >= white_share * art.sum(1)) & (art.sum(1) > 0)
    cols = ((white & art).sum(0) >= white_share * art.sum(0)) & (art.sum(0) > 0)
    return g | rows[:, None] | cols[None, :]
