"""Which rows are gutters: a per-row colour profile, then a verdict on every blank run."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import numpy as np

from .. import WORKERS
from .params import Params

CHUNK = 256  # rows per worker task; numpy's partition and comparisons release the GIL


def runs(mask: np.ndarray) -> np.ndarray:
    """(start, end) of every run of True in a 1-D mask, shape (n, 2)."""
    d = np.diff(np.concatenate(([0], mask.astype(np.int8), [0])))
    return np.column_stack((np.flatnonzero(d == 1), np.flatnonzero(d == -1)))


def row_profile(pixels: np.ndarray, tolerance: int) -> tuple[np.ndarray, np.ndarray]:
    """Per row: the median colour, (h, 3) int16, and the share of pixels with a channel more than `tolerance` from it.

    Row median, not one background colour: episodes change page colour mid-strip (unOrdinary 395 goes white to
    grey). Outlier share, not max - min: JPEG grain on dark pages spreads 21-29 per row (Sweet Home 14).
    """
    h, w, _ = pixels.shape
    k = w // 2
    medians = np.empty((h, 3), np.int16)
    share = np.empty(h)

    def chunk(y: int) -> None:
        planes = np.ascontiguousarray(pixels[y : y + CHUNK].transpose(2, 0, 1))  # (3, rows, w)
        if w % 2:
            m = np.partition(planes, k, axis=2)[:, :, k].astype(np.int16)
        else:  # np.median's mean of the middle pair, truncated
            p = np.partition(planes, (k - 1, k), axis=2)
            m = (p[:, :, k - 1].astype(np.int16) + p[:, :, k]) // 2
        medians[y : y + CHUNK] = m.T
        lo = np.clip(m - tolerance, 0, 255).astype(np.uint8)[:, :, None]
        hi = np.clip(m + tolerance, 0, 255).astype(np.uint8)[:, :, None]
        share[y : y + CHUNK] = np.count_nonzero(((planes < lo) | (planes > hi)).any(axis=0), axis=1) / w

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(chunk, range(0, h, CHUNK)))
    return medians, share


def _bridge(blank: np.ndarray, max_break: int) -> np.ndarray:
    """Count interior non-blank runs of at most `max_break` rows as blank: grain, not ink."""
    out = blank.copy()
    for s, e in runs(~blank):
        if e - s <= max_break and s > 0 and e < len(blank):
            out[s:e] = True
    return out


def _panel_edge(pixels: np.ndarray, rows: range, page: np.ndarray, tol: int) -> float:
    """Longest unbroken stretch of off-page pixels in any of `rows`, as a share of the width.

    A panel's edge, framed or not, is one long stretch (Housecat frames 0.44-0.89); text is short.
    """
    best = 0
    for y in rows:
        off = runs((np.abs(pixels[y].astype(np.int16) - page) > tol).any(axis=1))
        if len(off):
            best = max(best, int((off[:, 1] - off[:, 0]).max()))
    return best / pixels.shape[1]


def gutters(pixels: np.ndarray, medians: np.ndarray, share: np.ndarray, p: Params) -> np.ndarray:
    """(start, end) of every gutter, in strip order.

    A blank run of `min_gutter` rows or more is a gutter when it touches the local page colour or fades
    (flat sky or a wall inside a panel reads blank too); off-page flat bands at its ends go back to the art
    they touch, keeping frame lines in their box. A run of `min_narrow` rows or more is a gutter when it is
    page-coloured and a panel edge sits on one side, unless the other side is a lone block of text
    followed by a full gutter.
    """
    n = len(share)
    tol = p.colour_match
    blank = _bridge(share < p.max_outliers, p.max_break)
    out = blank.copy()
    ys = np.flatnonzero(blank)
    if len(ys):
        q = medians[ys] >> 4  # page colour = the most common blank-row colour at 4 bits per channel
        keys = (q[:, 0].astype(np.int32) << 8) | (q[:, 1] << 4) | q[:, 2]
        sep = runs(blank)
        sep = sep[sep[:, 1] - sep[:, 0] >= p.min_narrow]

        def page_colours(s: int, e: int) -> list[np.ndarray]:
            # above and below separately: across a white-to-dark scene change one window's mode is the white half
            pages = []
            for lo_y, hi_y in ((s - p.page_window, e), (s, e + p.page_window)):
                lo, hi = np.searchsorted(ys, [lo_y, hi_y])
                mode = np.bincount(keys[lo:hi]).argmax()
                pages.append(np.median(medians[ys[lo:hi][keys[lo:hi] == mode]], axis=0))
            return pages

        for idx, (s, e) in enumerate(sep):
            pages = page_colours(s, e)

            if e - s < p.min_gutter:
                page = np.median(medians[s:e], axis=0)
                on_page = any(np.abs(page - c).max() <= tol for c in pages)
                edge_up = _panel_edge(pixels, range(max(0, s - 3), s), page, tol) >= p.min_edge
                edge_down = _panel_edge(pixels, range(e, min(n, e + 3)), page, tol) >= p.min_edge
                lone = False
                if edge_up != edge_down:
                    j = idx + 1 if edge_up else idx - 1
                    if 0 <= j < len(sep):
                        block = sep[j, 0] - e if edge_up else s - sep[j, 1]
                        lone = block < p.lone_h and sep[j, 1] - sep[j, 0] >= p.min_gutter
                if lone or not (on_page and (edge_up or edge_down)):
                    out[s:e] = False
                continue

            def page_or_fade(a: int, b: int) -> bool:
                seg = medians[a:b]
                touches = any((np.abs(seg - c).max(axis=1) <= tol).any() for c in pages)
                return touches or int((seg.max(axis=0) - seg.min(axis=0)).max()) > p.min_span

            if not page_or_fade(s, e):
                out[s:e] = False
                continue
            jumps = np.flatnonzero(np.abs(np.diff(medians[s:e], axis=0)).max(axis=1) > tol) + 1 + s
            segs = list(zip(np.concatenate([[s], jumps]), np.concatenate([jumps, [e]])))
            for at_edge, order in ((s > 0, segs), (e < n, segs[::-1])):
                if at_edge:
                    for a, b in order:
                        if page_or_fade(a, b):
                            break
                        out[a:b] = False

    cuts = runs(out)
    return cuts[cuts[:, 1] - cuts[:, 0] >= p.min_narrow]
