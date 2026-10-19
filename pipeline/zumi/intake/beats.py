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
    return attach_floaters(drop_specks(between(cuts, len(share)), share, p), pixels, p)


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
