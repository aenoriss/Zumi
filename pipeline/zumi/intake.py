"""Intake: turn what the artist (or a webtoon episode folder) gives us into ordered panel images.

Two inputs:
- a folder of per-panel files (p01.png, p02.png, ...): each file is a panel, no splitting;
- a folder of webtoon slices (01.jpg, 02.jpg, ...): stitched into one strip, then cut at gutters.

Gutter scan (see docs/research/webtoon-panel-splitting-2026-10.md):
1. background colour = most frequent colour in the strip's left and right margins;
2. a row is blank when < 0.2 % of its pixels are farther than `tolerance` from the row's median
   colour; the background colour is recorded for the reader but not used to decide cuts, since episodes change it mid-strip;
3. a break of <= 2 non-blank rows between blank rows is grain and counts as blank;
4. a run of >= `min_gutter` blank rows is a gutter; the panel boundary is the run's edges.
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
    """Concatenate slices vertically. Widths must match (WEBTOON 800 or Naver 700)."""
    images = [Image.open(f).convert("RGB") for f in files]
    widths = {im.width for im in images}
    if len(widths) != 1:
        raise ValueError(f"slices have different widths: {sorted(widths)}")
    width = widths.pop()
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


def blank_rows(arr: np.ndarray, tolerance: int, max_outliers: float = 0.002, chunk: int = 4096) -> np.ndarray:
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
    out = np.empty(arr.shape[0], dtype=bool)
    for y in range(0, arr.shape[0], chunk):
        rows = arr[y : y + chunk].astype(np.int16)
        median = np.median(rows, axis=1).astype(np.int16)  # (h, 3)
        outlier = (np.abs(rows - median[:, None, :]) > tolerance).any(axis=2)  # (h, w)
        out[y : y + chunk] = outlier.mean(axis=1) < max_outliers
    return out


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


def find_slabs(blank: np.ndarray, min_gutter: int, max_break: int = 2) -> list[Slab]:
    """Split rows into content slabs separated by blank runs of at least min_gutter rows."""
    blank = bridge_breaks(blank, max_break)
    n = len(blank)
    # run-length encode
    edges = np.flatnonzero(np.diff(blank.astype(np.int8))) + 1
    starts = np.concatenate([[0], edges])
    ends = np.concatenate([edges, [n]])
    runs = [(int(s), int(e), bool(blank[s])) for s, e in zip(starts, ends)]

    # mark short blank runs as content so they do not cut
    cut = [is_blank and (e - s) >= min_gutter for s, e, is_blank in runs]

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


def flatness(region: np.ndarray, top: int = 4) -> float:
    """Share of pixels covered by the `top` most frequent colours (5 bits per channel).

    A bubble, caption box, sound effect or speck is a fill, an outline and lettering: 0.73-0.99 on the fixture
    episodes, mostly >= 0.93. Art is shaded: Sweet Home 14's red text plates 0.23-0.41, Lore Olympus 9's tiny
    reaction panels 0.53-0.67. Height alone could not separate the two (tuning-log, iteration 2).
    """
    q = (region[..., 0] >> 3).astype(np.int32) << 10 | (region[..., 1] >> 3).astype(np.int32) << 5 | region[..., 2] >> 3
    counts = np.sort(np.bincount(q.ravel()))[::-1]
    return float(counts[:top].sum() / counts.sum())


def attach_floaters(
    slabs: list[Slab],
    arr: np.ndarray,
    max_floater: int,
    min_flatness: float,
    gap_factor: float,
    min_panel: int = 120,
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
    cap = gap_factor * float(np.median([s.gutter_after for s in slabs[:-1]]))
    units: list[tuple[Slab, bool]] = []
    for s in slabs:
        # under min_panel nothing is a panel, flat or not (a credit line on grainy dark brown is not flat)
        floater = s.h < min_panel or (s.h < max_floater and flatness(arr[s.y : s.y + s.h]) >= min_flatness)
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
    blank = blank_rows(arr, tolerance)
    slabs = attach_floaters(find_slabs(blank, min_gutter), arr, max_floater, min_flatness, gap_factor)
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
        top, bottom = s.y * scale, (s.y + s.h) * scale
        draw.rectangle([(0, top), (w - 1, bottom)], outline=(230, 40, 40), width=2)
        draw.text((6, top + 4), f"{i}", fill=(230, 40, 40))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
