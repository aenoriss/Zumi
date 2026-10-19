"""From gutters to beats: the content between gutters, then specks, slivers and floating text resolved."""

from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from .params import Params


@dataclass(frozen=True)
class Slab:
    y: int  # top row on the strip
    h: int
    gutter_after: int  # blank rows between this slab and the next (or the strip end)

    @property
    def end(self) -> int:
        return self.y + self.h

    def through(self, other: Slab) -> Slab:
        """This slab extended down to the end of `other`, a later slab."""
        return Slab(self.y, other.end - self.y, other.gutter_after)


def beats(cuts: np.ndarray, share: np.ndarray, pixels: np.ndarray, p: Params) -> list[Slab]:
    slabs = attach_floaters(drop_specks(between(cuts, len(share)), share, p), pixels, p)
    return merge_short(link_bays(slabs, pixels, p), pixels, p)


def _bays(pixels: np.ndarray, s: Slab, page: np.ndarray, facing: str, p: Params) -> list[tuple[int, int]]:
    """Page-coloured bays cut into a panel's edge: (x0, x1) of each bay's chord along that edge.

    A bubble whose fill is the page colour and that overlaps a panel's edge shows only as this: a run of page
    pixels along the panel's last (or first) row, closed by art on both sides, reaching into the art.
    """
    w = pixels.shape[1]
    depth = min(s.h, max(1, int(p.bay_band * w)))
    band = pixels[s.end - depth : s.end][::-1] if facing == "bottom" else pixels[s.y : s.y + depth]  # edge row first
    is_page = (np.abs(band.astype(np.int16) - page) <= p.colour_match).all(axis=2)
    reach = np.where(is_page.all(axis=0), depth, np.argmin(is_page, axis=0))  # page rows from the edge, per column
    open_col = reach > p.bay_art_reach * w  # not the panel's edge here: page colour reaches into the art
    d = np.diff(np.concatenate(([0], open_col.astype(np.int8), [0])))
    runs = list(zip(np.flatnonzero(d == 1), np.flatnonzero(d == -1)))
    def dome(r: np.ndarray) -> bool:
        """Highest near the middle, low at both ends: a bubble's curve, not a fade or a flat strip."""
        k = max(1, len(r) // 10)
        top = int(np.argmax(r))
        return len(r) // 4 <= top <= 3 * len(r) // 4 and max(r[:k].mean(), r[-k:].mean()) <= p.bay_end_share * r.max()

    bays = [
        (int(a), int(b)) for a, b in runs
        if a > 0 and b < w  # closed by art on both sides; runs reaching the strip border are side margins
        and p.bay_min_w * w <= b - a <= p.bay_max_w * w and reach[a:b].max() >= p.bay_min_depth * w
        and dome(reach[a:b])
    ]
    if not bays:
        return []
    inside = np.zeros(w, bool)
    for a, b in bays:
        inside[a:b] = True
    return bays if (~open_col[~inside]).mean() >= p.bay_min_art else []  # the rest of the edge is a hard art edge


def _is_text(pixels: np.ndarray, s: Slab, p: Params) -> bool:
    return s.h < p.min_panel or (s.h < p.max_floater and flatness(pixels[s.y : s.end]) >= p.min_flatness)


def _ink_x(pixels: np.ndarray, s: Slab, page: np.ndarray, p: Params) -> tuple[int, int]:
    cols = np.flatnonzero((np.abs(pixels[s.y : s.end].astype(np.int16) - page) > p.colour_match).any(axis=2).any(axis=0))
    return (int(cols[0]), int(cols[-1]) + 1) if len(cols) else (0, pixels.shape[1])


def link_bays(slabs: list[Slab], pixels: np.ndarray, p: Params) -> list[Slab]:
    """Merge panels joined by a bubble whose fill is the page colour (Tower of God 223 frames 31-33).

    Panel A has a bay in its bottom edge and the next art panel B a bay in its top edge, at overlapping x, within
    `bay_max_span`; the text slabs between them, if any, sit inside that x range. That is one bubble across the
    gutter, so A, the text and B are one frame (user rule 2026-10-18: art overlapping a gutter links the beats).
    """
    w = pixels.shape[1]
    out = list(slabs)
    i = 0
    while i < len(out) - 1:
        a = out[i]
        if _is_text(pixels, a, p):
            i += 1
            continue
        page_below = np.median(pixels[a.end : a.end + max(1, a.gutter_after)].reshape(-1, 3), axis=0)
        down = _bays(pixels, a, page_below, "bottom", p)
        j, linked = i + 1, False
        while down and j < len(out) and out[j].y - a.end <= p.bay_max_span * w:
            b = out[j]
            if _is_text(pixels, b, p):
                x0, x1 = _ink_x(pixels, b, page_below, p)
                if not any(x0 < bx1 and bx0 < x1 for bx0, bx1 in down):
                    break
                j += 1
                continue
            page_above = np.median(pixels[out[j - 1].end : b.y].reshape(-1, 3), axis=0)
            up = _bays(pixels, b, page_above, "top", p)
            linked = any(ax0 < bx1 and bx0 < ax1 for ax0, ax1 in down for bx0, bx1 in up)
            break
        if linked:
            out[i : j + 1] = [a.through(out[j])]
        else:
            i += 1
    return out


def merge_short(slabs: list[Slab], pixels: np.ndarray, p: Params) -> list[Slab]:
    """Merge art beats shorter than `min_aspect` x the width into the neighbour across the smaller gap.

    A letterbox panel alone makes a sliver of a view (Pepper&Carrot 39: two 250-px panels on a 1200-px page).
    Text-only beats are left alone: a caption with space around it is a deliberate pause (True Beauty 7
    "WAIT..."). Never across a gap over `merge_gap` x the median gutter, which is a scene change.
    """
    if len(slabs) < 2:
        return slabs
    out = list(slabs)
    w = pixels.shape[1]
    cap = min(p.merge_gap * float(np.median([s.gutter_after for s in out[:-1]])), p.max_merge_gap * w / 800)
    is_text = lambda s: s.h < p.min_panel or flatness(pixels[s.y : s.end]) >= p.min_flatness
    while True:
        short = [i for i, s in enumerate(out) if s.h < p.min_aspect * w and not is_text(s)]
        options = []
        for i in short:
            if i > 0 and out[i - 1].gutter_after <= cap:
                options.append((out[i - 1].gutter_after, out[i].h, i - 1))  # merge i into i-1
            if i + 1 < len(out) and out[i].gutter_after <= cap:
                options.append((out[i].gutter_after, out[i].h, i))  # merge i+1 into i
        if not options:
            return out
        _, _, k = min(options)  # tightest gap first; ties go to the shorter beat
        out[k : k + 2] = [out[k].through(out[k + 1])]


def between(cuts: np.ndarray, n: int) -> list[Slab]:
    """The content runs between gutters; leading blank rows belong to no slab."""
    slabs, pos = [], 0
    for s, e in cuts:
        if s > pos:
            slabs.append(Slab(pos, int(s) - pos, int(e - s)))
        pos = int(e)
    if pos < n:
        slabs.append(Slab(pos, n - pos, 0))
    return slabs


def drop_specks(slabs: list[Slab], share: np.ndarray, p: Params) -> list[Slab]:
    """Fold specks (a sweat drop, ash, a star; 0.07-1.4 % ink vs 1.9 % for the faintest credit line) into the gutter."""
    out: list[Slab] = []
    for s in slabs:
        if s.h < p.speck_h and share[s.y : s.end].mean() < p.speck_ink:
            if out:
                out[-1] = replace(out[-1], gutter_after=out[-1].gutter_after + s.h + s.gutter_after)
            continue
        out.append(s)
    return out


def flatness(region: np.ndarray, top: int = 4) -> float:
    """Share of pixels in the `top` most frequent colours at 5 bits per channel.

    Text is a fill, an outline and lettering (0.73-0.99); art is shaded (0.23-0.67).
    """
    q = (region[..., 0] >> 3).astype(np.int32) << 10 | (region[..., 1] >> 3).astype(np.int32) << 5 | region[..., 2] >> 3
    counts = np.sort(np.bincount(q.ravel()))[::-1]
    return float(counts[:top].sum() / counts.sum())


def join_slivers(slabs: list[Slab], max_sliver: int) -> list[Slab]:
    """Join slabs under `max_sliver` rows (a rule line under a frame) to the nearer neighbour."""
    out = list(slabs)
    i = 0
    while i < len(out) and len(out) > 1:
        s = out[i]
        if s.h >= max_sliver:
            i += 1
            continue
        up = out[i - 1].gutter_after if i > 0 else None
        down = s.gutter_after if i + 1 < len(out) else None
        if down is None or (up is not None and up <= down):
            out[i - 1] = out[i - 1].through(s)
        else:
            out[i + 1] = s.through(out[i + 1])
        del out[i]
    return out


def attach_floaters(slabs: list[Slab], pixels: np.ndarray, p: Params) -> list[Slab]:
    """Join floating text to the panel it belongs to.

    A floater is a short flat slab (bubble, caption, sound effect). Consecutive floaters closer than
    `gap_factor` x the median gutter form one unit (a title card's lines); a unit joins the nearer panel when
    that gap is under `max_attach` px, otherwise it is a beat of its own. Nearer, not always the one above:
    captions often head the panel below (Lore Olympus 9's dog roll-call).
    """
    if len(slabs) < 2:
        return slabs
    median = float(np.median([s.gutter_after for s in slabs[:-1]]))
    slabs = join_slivers(slabs, p.max_sliver)
    if len(slabs) < 2:
        return slabs
    cap = p.gap_factor * median
    attach_cap = min(cap, p.max_attach * pixels.shape[1] / 800)

    units: list[tuple[Slab, bool]] = []
    for k, s in enumerate(slabs):
        region = pixels[s.y : s.end]
        floater = s.h < p.min_panel or (s.h < p.max_floater and flatness(region) >= p.min_flatness)
        # a reaction burst with a spiky rim is less flat (0.77-0.79) but sits far closer to its panel than the
        # episode's gutters (True Beauty 7: 41-52 px on 340-540-px gutters)
        near = [g for g in (slabs[k - 1].gutter_after if k else None, s.gutter_after if k + 1 < len(slabs) else None) if g is not None]
        if not floater and s.h < p.max_tight and any(p.min_gutter <= g < p.tight * median for g in near):
            floater = flatness(region) >= p.min_tight_flatness
        if floater and units and units[-1][1] and units[-1][0].gutter_after < cap:
            units[-1] = (units[-1][0].through(s), True)
        else:
            units.append((s, floater))

    out: list[Slab] = []
    pending: Slab | None = None  # a floater unit waiting to head the next panel
    for i, (u, floater) in enumerate(units):
        if not floater:
            out.append(pending.through(u) if pending else u)
            pending = None
            continue
        up = units[i - 1][0].gutter_after if i > 0 and not units[i - 1][1] else None
        down = u.gutter_after if i + 1 < len(units) and not units[i + 1][1] else None
        options = [(g, side) for g, side in ((up, "up"), (down, "down")) if g is not None and g < attach_cap]
        if not options:
            out.append(u)
        elif min(options)[1] == "up":
            out[-1] = out[-1].through(u)
        else:
            pending = u
    return out
