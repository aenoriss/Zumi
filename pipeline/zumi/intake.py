"""Intake: turn what the artist (or a webtoon episode folder) gives us into ordered panel images.

Two inputs:
- a folder of per-panel files (p01.png, p02.png, ...): each file is a panel, no splitting;
- a folder of webtoon slices (01.jpg, 02.jpg, ...): stitched into one strip, then cut at gutters.

Gutter scan (see docs/research/webtoon-panel-splitting-2026-10.md):
1. background colour = most frequent colour in the strip's left and right margins;
2. a row is blank when < 0.2 % of its pixels are farther than `tolerance` from the row's median
   colour; the background colour is recorded for the reader but not used to decide cuts, since episodes change it mid-strip;
3. a break of <= 2 non-blank rows between blank rows is grain and counts as blank;
4. a run of >= `min_gutter` blank rows is a gutter if one of its rows has the local page colour (flat sky
   inside a panel is not); the panel boundary is the run's edges.
Slice seams are invisible after stitching, so they never produce a cut. A bubble sitting in a gutter
shortens the gutter but is not blank, so it comes out as its own small slab; `attach_floaters` joins
such flat, short slabs to the nearer panel (until a bubble detector runs first).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def _natural_key(p: Path):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]


def list_images(folder: Path) -> list[Path]:
    files = [p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT]
    return sorted(files, key=_natural_key)


@dataclass
class Slab:
    y: int  # top row on the strip
    h: int
    gutter_after: int  # blank rows between this slab and the next (or the strip end)


@dataclass
class Strip:
    image: Image.Image  # RGB, full stitched strip
    background: tuple[int, int, int]
    slabs: list[Slab]
    seams: list[int]  # y of each slice boundary, for the report only


def stitch(files: list[Path]) -> tuple[Image.Image, list[int]]:
    """Concatenate slices vertically (WEBTOON 800 or Naver 700 wide).

    A slice of another width is scaled to the width covering most rows: Tower of God S1 ep 0 is seven 700-px
    slices and a final 800-px one, which used to abort intake.
    """
    images = [Image.open(f).convert("RGB") for f in files]
    rows: dict[int, int] = {}
    for im in images:
        rows[im.width] = rows.get(im.width, 0) + im.height
    width = max(rows, key=rows.get)
    images = [
        im if im.width == width else im.resize((width, round(im.height * width / im.width)), Image.LANCZOS)
        for im in images
    ]
    total = sum(im.height for im in images)
    strip = Image.new("RGB", (width, total))
    seams, y = [], 0
    for im in images:
        strip.paste(im, (0, y))
        y += im.height
        seams.append(y)
    return strip, seams[:-1]


def background_colour(arr: np.ndarray, margin: int = 8) -> tuple[int, int, int]:
    """Most frequent colour in the left and right margins."""
    edges = np.concatenate([arr[:, :margin].reshape(-1, 3), arr[:, -margin:].reshape(-1, 3)])
    colours, counts = np.unique(edges, axis=0, return_counts=True)
    r, g, b = colours[counts.argmax()]
    return int(r), int(g), int(b)


def row_stats(arr: np.ndarray, tolerance: int, chunk: int = 4096) -> tuple[np.ndarray, np.ndarray]:
    """Per row: the median colour (h, 3) and the share of pixels with any channel farther than `tolerance` from it."""
    share = np.empty(arr.shape[0], dtype=np.float64)
    medians = np.empty((arr.shape[0], 3), dtype=np.int16)
    for y in range(0, arr.shape[0], chunk):
        rows = arr[y : y + chunk].astype(np.int16)
        median = np.median(rows, axis=1).astype(np.int16)  # (h, 3)
        medians[y : y + chunk] = median
        share[y : y + chunk] = (np.abs(rows - median[:, None, :]) > tolerance).any(axis=2).mean(axis=1)
    return medians, share


def outlier_share(arr: np.ndarray, tolerance: int) -> np.ndarray:
    """Per row, the share of pixels with any channel farther than `tolerance` from the row's median colour."""
    return row_stats(arr, tolerance)[1]


def panel_edge(arr: np.ndarray, rows: range, page: np.ndarray, tolerance: int) -> float:
    """Longest unbroken stretch of off-page pixels in any of `rows`, as a share of the strip width.

    A panel's top or bottom edge, bordered or not, is one long stretch (Housecat frames 0.44-0.89 of the width);
    a bubble, a caption line or a sound effect is short (mostly under 0.2 on the round-2 hard set).
    """
    best = 0
    for y in rows:
        off = (np.abs(arr[y].astype(np.int16) - page) > tolerance).any(axis=1).astype(np.int8)
        edges = np.flatnonzero(np.diff(np.concatenate([[0], off, [0]])))
        if len(edges):
            best = max(best, int((edges[1::2] - edges[::2]).max()))
    return best / arr.shape[1]


def page_gutters(
    blank: np.ndarray,
    medians: np.ndarray,
    min_gutter: int,
    window: int = 4000,
    tolerance: int = 20,
    min_span: int = 48,
    arr: np.ndarray | None = None,
    min_narrow: int = 8,
    min_edge: float = 0.4,
    lone_h: int = 400,
) -> np.ndarray:
    """Keep a blank run of >= `min_gutter` rows as gutter only if one of its rows has the local page colour,
    or its colour travels more than `min_span` from end to end (a fade or scene-change gradient).

    Flat art reads as blank too: a pink sunset sky under a bubble (unOrdinary 395, median (231,208,198) on a
    #413F40 page), a pale sky (Tower of God 235, (226,239,242) on white), a grey wall (Cursed Princess Club 1).
    Cutting there split a panel's top off and dropped it (tuning-log, fade-clip). Local page colour = the most
    common blank-row colour (4 bits per channel) within +-`window` rows, since episodes change page colour
    mid-strip. A scene-change gradient still counts: it starts or ends on the page colour.

    With `arr`, a page-coloured run of `min_narrow` to `min_gutter` rows is a gutter too when the rows just
    above or below it hold a panel edge (`panel_edge` >= `min_edge`), unless the edgeless side is a lone block
    under `lone_h` rows followed by a full gutter; other short runs become content.
    """
    out = blank.copy()
    ys = np.flatnonzero(blank)
    if len(ys) == 0:
        return out
    q = medians[ys] >> 4
    keys = (q[:, 0].astype(np.int32) << 8) | (q[:, 1] << 4) | q[:, 2]
    edges = np.flatnonzero(np.diff(blank.astype(np.int8))) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [len(blank)]])
    sep = [(s, e) for s, e in zip(starts, ends) if blank[s] and e - s >= min_narrow]
    sep_s = np.array([a for a, _ in sep], dtype=np.int64)
    sep_e = np.array([b for _, b in sep], dtype=np.int64)
    for s, e in zip(starts, ends):
        narrow = arr is not None and min_narrow <= e - s < min_gutter
        if not blank[s] or (e - s < min_gutter and not narrow):
            continue
        # page colour above and below separately: at a white-to-dark scene change a single window's mode is
        # the white half, which would make the first dark gutter "not page" (Sweet Home 14, y 20700-20965)
        pages = []
        for lo_y, hi_y in ((s - window, e), (s, e + window)):
            lo, hi = np.searchsorted(ys, [lo_y, hi_y])
            k = np.bincount(keys[lo:hi]).argmax()
            pages.append(np.median(medians[ys[lo:hi][keys[lo:hi] == k]], axis=0))

        def page_or_fade(a: int, b: int) -> bool:
            seg = medians[a:b]
            touches = any((np.abs(seg - p).max(axis=1) <= tolerance).any() for p in pages)
            return touches or int((seg.max(axis=0) - seg.min(axis=0)).max()) > min_span

        if narrow:
            # a gutter under min_gutter counts only on page colour against a panel edge: Housecat Philosophy's
            # grids (11-31 px) and unOrdinary's prologue (24-36 px) were never cut (tuning-log, round 2).
            # A lone burst or bubble 9-30 px under a frame has the edge on one side too; when the block on the
            # edgeless side is under `lone_h` rows and a full gutter follows it, it is that panel's text, not a
            # panel (True Beauty 7 41288, Sweet Home 14 "PHEW...")
            page = np.median(medians[s:e], axis=0)
            on_page = any(np.abs(page - p).max() <= tolerance for p in pages)
            edge_up = panel_edge(arr, range(max(0, s - 3), s), page, tolerance) >= min_edge
            edge_down = panel_edge(arr, range(e, min(len(blank), e + 3)), page, tolerance) >= min_edge
            lone = False
            if edge_up != edge_down:
                i = int(np.searchsorted(sep_s, s))  # this run is sep[i]
                j = i + 1 if edge_up else i - 1
                if 0 <= j < len(sep_s):
                    block = sep_s[j] - e if edge_up else s - sep_e[j]
                    lone = block < lone_h and sep_e[j] - sep_s[j] >= min_gutter
            if not (on_page and (edge_up or edge_down)) or lone:
                out[s:e] = False
            continue
        if not page_or_fade(s, e):
            out[s:e] = False
            continue
        # a frame line and the flat sky or wall under it are blank rows too, and joined the page-coloured gutter,
        # so boxes lost their border and up to 110 px of art (tuning-log, frame-eaten). Split the run where the
        # colour jumps; flat off-page segments at either end go back to the content they touch.
        jumps = np.flatnonzero(np.abs(np.diff(medians[s:e], axis=0)).max(axis=1) > tolerance) + 1 + s
        segs = list(zip(np.concatenate([[s], jumps]), np.concatenate([jumps, [e]])))
        if s > 0:
            for a, b in segs:
                if page_or_fade(a, b):
                    break
                out[a:b] = False
        if e < len(blank):
            for a, b in reversed(segs):
                if page_or_fade(a, b):
                    break
                out[a:b] = False
    return out


def blank_rows(arr: np.ndarray, tolerance: int, max_outliers: float = 0.002) -> np.ndarray:
    """Boolean per row: True when the row is one flat colour up to noise.

    A pixel is an outlier when any channel is farther than `tolerance` from the row's median colour;
    the row is blank when fewer than `max_outliers` of its pixels are outliers. Row median, not the
    global background: unOrdinary 395 switches from white margins to dark grey halfway through.
    Median plus outlier fraction, not max - min: Sweet Home 14's dark brown gutters carry JPEG grain
    with a per-row spread of 21-29, so "every pixel within 6" never fired and the dark half came out
    as one 67 000-px panel (tuning-log iteration 0). 20 is the knee of that grain: the share of dark
    rows passing goes 0.8 % at 10, 26 % at 15, 32 % at 20, 32 % at 30.
    The cost is that a flat block inside a panel (a black "everything went dark" beat) also reads as
    blank; min_gutter absorbs the short ones.
    """
    return outlier_share(arr, tolerance) < max_outliers


def bridge_breaks(blank: np.ndarray, max_break: int) -> np.ndarray:
    """Treat runs of <= `max_break` non-blank rows with blank rows on both sides as blank.

    JPEG grain leaves isolated rows in a flat background with two or three pixels just over tolerance
    (Sweet Home 14, y 25180: 2 of 700 pixels more than 20 off). Each one split a 280-px pause into pieces
    under min_gutter, so the box above ran 228 px into plain background (tuning-log, padded-edge).
    """
    out = blank.copy()
    edges = np.flatnonzero(np.diff(blank.astype(np.int8))) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [len(blank)]])
    for s, e in zip(starts, ends):
        if not blank[s] and e - s <= max_break and s > 0 and e < len(blank):
            out[s:e] = True
    return out


def find_slabs(
    blank: np.ndarray,
    min_gutter: int,
    max_break: int = 2,
    medians: np.ndarray | None = None,
    arr: np.ndarray | None = None,
    min_narrow: int = 8,
) -> list[Slab]:
    """Split rows into content slabs separated by blank runs of at least min_gutter rows.

    With `medians` (per-row median colours), runs that never touch the local page colour are content.
    With `arr` too, page-coloured runs of `min_narrow` rows or more against a panel edge also cut.
    """
    blank = bridge_breaks(blank, max_break)
    if medians is not None:
        blank = page_gutters(blank, medians, min_gutter, arr=arr, min_narrow=min_narrow)
    if medians is None or arr is None:
        min_narrow = min_gutter
    n = len(blank)
    # run-length encode
    edges = np.flatnonzero(np.diff(blank.astype(np.int8))) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [n]])
    runs = [(int(s), int(e), bool(blank[s])) for s, e in zip(starts, ends)]

    # mark short blank runs as content so they do not cut
    cut = [is_blank and (e - s) >= min_narrow for s, e, is_blank in runs]

    slabs: list[Slab] = []
    y, in_content = None, False
    for (s, e, _), is_cut in zip(runs, cut):
        if is_cut:
            if in_content:
                slabs.append(Slab(y=y, h=s - y, gutter_after=e - s))
                in_content = False
        else:
            if not in_content:
                y, in_content = s, True
    if in_content:
        slabs.append(Slab(y=y, h=n - y, gutter_after=0))
    return slabs


def drop_specks(slabs: list[Slab], share: np.ndarray, max_h: int = 300, max_ink: float = 0.015) -> list[Slab]:
    """Fold speck slabs (under `max_h` px, mean outlier share under `max_ink`) back into the gutter.

    A sweat drop, a fleck of ash or a star alone in a gutter is a slab of its own; attached to the nearer panel
    it dragged that box's edge out to the speck, through 130-290 px of empty page (unOrdinary 395 boxes 100,
    101), and a trail of ash flecks welded a pause beat to the panel above (Lore Olympus 9). Measured: specks
    0.07-1.4 % ink; the faintest real slab, a 22-px credit line, 1.9 %. The marks stay in the strip, outside
    any panel.
    """
    out: list[Slab] = []
    for s in slabs:
        if s.h < max_h and share[s.y : s.y + s.h].mean() < max_ink:
            if out:
                out[-1].gutter_after += s.h + s.gutter_after
            continue
        out.append(Slab(y=s.y, h=s.h, gutter_after=s.gutter_after))
    return out


def flatness(region: np.ndarray, top: int = 4) -> float:
    """Share of pixels covered by the `top` most frequent colours (5 bits per channel).

    A bubble, caption box, sound effect or speck is a fill, an outline and lettering: 0.73-0.99 on the fixture
    episodes, mostly >= 0.93. Art is shaded: Sweet Home 14's red text plates 0.23-0.41, Lore Olympus 9's tiny
    reaction panels 0.53-0.67. Height alone could not separate the two (tuning-log, iteration 2).
    """
    q = (region[..., 0] >> 3).astype(np.int32) << 10 | (region[..., 1] >> 3).astype(np.int32) << 5 | region[..., 2] >> 3
    counts = np.sort(np.bincount(q.ravel()))[::-1]
    return float(counts[:top].sum() / counts.sum())


def join_slivers(slabs: list[Slab], max_sliver: int) -> list[Slab]:
    """Join each slab under `max_sliver` rows to the nearer neighbour, however far: no beat is that thin.

    A 4-row rule line under a frame (Housecat Philosophy 09, y 3063) came out as a box of its own once narrow
    gutters cut on both sides of it, since the floater cap (0.75 x a 15-row median gutter) is under both gaps.
    """
    out = [Slab(y=s.y, h=s.h, gutter_after=s.gutter_after) for s in slabs]
    i = 0
    while i < len(out) and len(out) > 1:
        s = out[i]
        if s.h >= max_sliver:
            i += 1
            continue
        up = out[i - 1].gutter_after if i > 0 else None
        down = s.gutter_after if i + 1 < len(out) else None
        if down is None or (up is not None and up <= down):
            p = out[i - 1]
            out[i - 1] = Slab(y=p.y, h=s.y + s.h - p.y, gutter_after=s.gutter_after)
        else:
            n = out[i + 1]
            out[i + 1] = Slab(y=s.y, h=n.y + n.h - s.y, gutter_after=n.gutter_after)
        del out[i]
    return out


def attach_floaters(
    slabs: list[Slab],
    arr: np.ndarray,
    max_floater: int,
    min_flatness: float,
    gap_factor: float,
    min_panel: int = 120,
    tight: float = 0.25,
    min_tight_flatness: float = 0.7,
    max_tight: int = 300,
    max_sliver: int = 8,
    min_gutter: int = 40,
) -> list[Slab]:
    """Join floaters (slabs under `max_floater` px that are at least `min_flatness` flat) to the panel they belong to.

    1. consecutive floaters closer than the cap group into one unit (a title card's lines, a speck trail);
    2. a floater unit joins the nearer non-floater neighbour if that gap is under the cap, otherwise it stays a box.
    cap = `gap_factor` x the strip's median gutter. Nearer, not "always the one above": captions head the panel
    below them (Lore Olympus 9's dog roll call). Capped, because the old always-up sliver rule welded a 116-px
    title ornament onto a scream panel across a 1960-px gradient and a frame onto a cemetery panel across a
    2734-px pause (tuning-log, iterations 1-2).
    """
    if len(slabs) < 2:
        return slabs
    median = float(np.median([s.gutter_after for s in slabs[:-1]]))
    slabs = join_slivers(slabs, max_sliver)
    if len(slabs) < 2:
        return slabs
    cap = gap_factor * median
    units: list[tuple[Slab, bool]] = []
    for k, s in enumerate(slabs):
        # under min_panel nothing is a panel, flat or not (a credit line on grainy dark brown is not flat)
        floater = s.h < min_panel or (s.h < max_floater and flatness(arr[s.y : s.y + s.h]) >= min_flatness)
        # a fairly flat short slab far closer to a neighbour than the episode's gutters is text bound to it:
        # reaction bursts with dense spiky rims (flatness 0.77-0.79) sat 41-52 px under their panel on 340-540-px
        # gutters (True Beauty 7 41/44, 4 47; tuning-log, round 2). Not across a narrow gutter, which was cut
        # because a panel edge sits on it, and not for shaded art (Lore Olympus 9's reaction panels, 0.53-0.67) or
        # anything `max_tight` rows or taller (Lore Olympus 9's 662-row "HA HA" panel is 0.74 flat, 41 px from the next)
        near = [g for g in (slabs[k - 1].gutter_after if k else None, s.gutter_after if k + 1 < len(slabs) else None) if g is not None]
        if not floater and s.h < max_tight and any(min_gutter <= g < tight * median for g in near):
            floater = flatness(arr[s.y : s.y + s.h]) >= min_tight_flatness
        prev = units[-1] if units else None
        if floater and prev and prev[1] and prev[0].gutter_after < cap:
            units[-1] = (Slab(y=prev[0].y, h=s.y + s.h - prev[0].y, gutter_after=s.gutter_after), True)
        else:
            units.append((Slab(y=s.y, h=s.h, gutter_after=s.gutter_after), floater))

    out: list[Slab] = []
    pending: Slab | None = None  # a floater unit joining the next panel down
    for i, (u, floater) in enumerate(units):
        if not floater:
            if pending is not None:
                u = Slab(y=pending.y, h=u.y + u.h - pending.y, gutter_after=u.gutter_after)
                pending = None
            out.append(u)
            continue
        gap_up = units[i - 1][0].gutter_after if i > 0 and not units[i - 1][1] else None
        gap_down = u.gutter_after if i + 1 < len(units) and not units[i + 1][1] else None
        options = [(g, side) for g, side in ((gap_up, "up"), (gap_down, "down")) if g is not None and g < cap]
        if not options:
            out.append(u)
        elif min(options)[1] == "up":
            out[-1] = Slab(y=out[-1].y, h=u.y + u.h - out[-1].y, gutter_after=u.gutter_after)
        else:
            pending = u
    return out


def split_strip(
    files: list[Path],
    *,
    tolerance: int = 20,
    min_gutter: int = 40,
    max_floater: int = 700,
    min_flatness: float = 0.85,
    gap_factor: float = 0.75,
) -> Strip:
    image, seams = stitch(files)
    arr = np.asarray(image)
    bg = background_colour(arr)  # dominant margin colour, informational
    medians, share = row_stats(arr, tolerance)
    slabs = drop_specks(find_slabs(share < 0.002, min_gutter, medians=medians, arr=arr), share)
    slabs = attach_floaters(slabs, arr, max_floater, min_flatness, gap_factor, min_gutter=min_gutter)
    # leading blank rows are not a slab; record them as the first slab's offset only
    return Strip(image=image, background=bg, slabs=slabs, seams=seams)


def crop_slabs(strip: Strip) -> list[Image.Image]:
    return [strip.image.crop((0, s.y, strip.image.width, s.y + s.h)) for s in strip.slabs]


def report(strip: Strip, out: Path, scale: float = 0.25) -> Path:
    """Downscaled strip with cuts in red, seams in blue, slab index labels. For eyeballing."""
    w = int(strip.image.width * scale)
    h = int(strip.image.height * scale)
    im = strip.image.resize((w, h), Image.BILINEAR).convert("RGB")
    draw = ImageDraw.Draw(im)
    for y in strip.seams:
        draw.line([(0, y * scale), (w, y * scale)], fill=(80, 140, 255), width=1)
    for i, s in enumerate(strip.slabs):
        # outline drawn just outside the box: drawn on the edge, a 2-px line at 0.25 scale hid 8 strip rows
        # of the box's own first and last lines (thin lettering looked clipped; tuning-log, iteration 4)
        top, bottom = s.y * scale, (s.y + s.h) * scale
        draw.rectangle([(0, top - 2), (w - 1, bottom + 1)], outline=(230, 40, 40), width=2)
        draw.text((6, top - 14), f"{i}", fill=(230, 40, 40))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
