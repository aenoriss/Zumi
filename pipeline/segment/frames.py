"""Drawn frames inside one box: a page comic box (Pepper&Carrot) nearly always holds several, a webtoon box rarely
(ToG 228 p64). Each frame is its own scene and its own camera, so the layers step fits depth per frame (layers.py).

    answers = ask(ep, imgs)                    the panel boxes (paid, cached; runs in the background while SAM segments)
    update(ep, imgs, letters, answers)         the frames split and saved per box (Box.save_frames), the step
    split(img, gutter, layout(img)) -> Split(frames, flat, page)     one box

Panel boxes from Claude Sonnet 5.5 (OpenRouter, under the 2 USD/day cap of openrouter.py; about 0.0043 USD and 3 s a
box), chosen 2026-10-30: on the 6 hard boxes of the panel comparison (panel_llm.py and panel_score.py, now only in the
git history) it
drew the same panels as the Opus 5.5 reference on all 6 (F1 1.00, box IoU 0.98), where Magiv3 got the count right on 1
(F1 0.80): it missed panels that touch or overlap (36-p003, 36-p025). Asked 4 times per box (panel_repeat.py, likewise) it never
varied (24/24); Gemini 3.1 Pro, as good and a little cheaper, dropped a panel once in 30 calls (37-p000), so it is the
fallback, not the default.
  1. the model returns each panel's box in 0-1000 units (prompt history above PROMPT), corner points for a slanted
     panel, the region's kind (story, title, credits, text) and its text blocks; an unusable answer (no panel list,
     a coordinate outside 0-1000, cut off at its budget) is asked again once; answers are cached by image and prompt
     (CACHE), so a rerun costs nothing;
  2. boxes covering nearly the same area are one frame (IoU above DUP_IOU); boxes under MIN_SIDE px are dropped;
  3. the page: the gutter given (page.gutter) plus a flat colour holding FLAT_SHARE of the pixels outside every
     box (the dark grey page of P&C 36/38, which page.gutter misses);
  4. each box is fitted to its gutters (_fit): edge lines that are page are trimmed, an edge on art snaps out to a
     gutter line within SNAP;
  5. a frame is its box, or its corner polygon for a slanted panel; a pixel inside several belongs to the smallest
     (an inset is its own frame);
  6. art outside every box joins the frame it touches (a leg past a loose box, a close-up's art running past it:
     without this 23 of 62 multi-frame boxes lost art, 52k character px); lettering past every box joins none (the
     lettering layer draws it); art cut off from every frame by page (credits under the last panel) and the text
     regions form one flat frame; specks under DUST_PX are page;
  7. each frame (not a slanted one) is the rectangle around its box and the art that joined it, taking the free
     pixels in it; nothing is taken out: the page inside stays (a vignette's white ground, the gaps between bubbles
     on a border). Taking it out (until 2026-10-30) made vignettes silhouettes (39-p027, 38-p018, 39-p025: about half
     carved), notched frames at bubbles (39-p008) and left 36-p012's frame #2 too small for a backdrop.
A box with no story panels (credits, a text page) is one flat frame (its backdrop gets no relief; its characters are
still cards); no answer, one frame. Frames are exclusive, and with the page and the lettering past them they cover the
box. Measured 2026-10-30 on the 81 P&C boxes with the cached v2 answers (no model call): no overlap and no art lost on
any box; story frames' area / bounding box median 1.000, below 0.97 only where an inset or a neighbour takes part of
the box; flat frames on the 4 credits/end pages only; speakers 310/333 against 316 on the saved frames (the losses:
two labels naming another card of the same man (38-p009), slanted or break-out panels as rectangles (36-p025, 39-p025,
36-p013), a cross-frame tail the rules miss (37-p000), a tailed credits caption (36-p028)). The audit behind steps
3-7: .data/out/frames_audit/REPORT.md.

    uv run python frames.py <episode.zumi> [...]    frames per box per episode (paid calls for boxes not cached)
"""
from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass

import numpy as np
from PIL import Image

import openrouter as OR
from boxstore import Episode
from masks import MIN_FRAME_PX, union
from spend import paid_map
from workers import pmap


# =====================================================================================================
# The page (was page.py): the gutters and margins of a box, white, grey or black. gutter() is the first guess, from
# colour alone; split adds a flat page colour it learns outside the panel boxes, and its page is the one every later
# step reads (boxstore.Box.frames().page).
# =====================================================================================================

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


# =====================================================================================================
# The panel model
# =====================================================================================================

MODEL = "anthropic/claude-sonnet-5.5"  # fallback: "google/gemini-3.1-pro-preview"
REASONING = "low"
MAX_SIDE = 1600    # px, longest side of the image sent
DUP_IOU = 0.85     # two panel boxes overlapping this much are one frame
MIN_SIDE = 60      # px, smallest frame side kept
TRIM_LINE = 0.98   # share of a box's edge line that must be gutter-like for the line to be trimmed off
GUTTER_LINE = 0.9  # ... for a line to be the gutter an edge on art snaps out to
SNAP = 0.03        # share of the box's width (x edges) or height (y edges) an edge may move out: the model's boxes are
                   # off by 1-3% (36-p012: a panel's top 27 px, 2.5%, below its border)
FLAT_MIN = 2000    # px outside every panel needed to learn a flat page colour from them
FLAT_SHARE = 0.8   # share of those px within FLAT_TOL of their commonest colour for it to be the page: 0.92-1.00 on
                   # the 17 P&C 36/38 boxes whose dark grey page page.gutter missed, 0.08-0.58 where it is art
FLAT_TOL = 2 * PAGE_TOL  # CIELAB
POLY_MIN = 0.5     # a slanted panel's corner polygon must fill this share of its box to replace it
PIECE_GAP = 6      # px: art outside the panels closer than twice this is one piece (letters into words and blocks)
TOUCH_PX = 3       # px: a piece this close to a frame touches it and joins it; farther, it is loose (a flat frame)
DUST_PX = 50       # px: a loose piece smaller than this is page dust, not a frame (37-p000: 9 px; 37-p016: specks <= 38)
TEXT_MIN = MIN_FRAME_PX  # px a text region must hold, outside the panels and the page, to be a flat frame of its
                         # own: the smallest frame the layers lay out
CACHE = OR.ROOT / ".data/cache/panels"
# The prompt's history (docs/research/frame-prompt-committee-2026-10.md); the old texts stay because the cache keys
# of their answers are made from them:
# v1: one sentence per panel type, boxes only. Right count on 78 of 81 P&C boxes; boxes stopping short (a vignette
#     boxed around its main figure: 39-p025, 38-p018; a panel stopped at its inset: 36-p000; an edge 8% off: 36-p012),
#     credits pages framed as story (36-p028, 37-p017, 39-p030).
# v2: a three-reviewer committee's rules (Opus 5.5, a third of the boxes each): what a panel is and is not, the
#     region's kind, text regions, whole scenes for vignettes, inset extent, shared edges. Fusing panels joined by a
#     crossing bubble was rejected: 16 crossings, none one scene (mostly shot / reverse shot), so it says the opposite.
#     The 3 credits pages came back with no panels; but 39-p026 came back with x in pixels and y in 0-1000 units,
#     likely from its sentence on separately scaled axes.
# v3 (PROMPT): v2 with the image's size given and the units spelt out per axis, and corner points for slanted panels.
PROMPT_V2 = """This image is a region cut from a comic page. It may hold story panels, and it may also hold things that
are not story panels. Find the story panels.

What a panel is
- A panel is one picture of the story seen from one viewpoint at one moment. Most panels are enclosed by a border
  line or separated from their neighbours by a gutter (a strip of bare page), but the border is only the usual cue,
  not the definition.
- These are panels too:
  a. a panel with no border, whose art fades out or stops on the bare page;
  b. a panel whose art runs to the edge of the image;
  c. an inset: a smaller panel drawn on top of a bigger one (return both; they overlap);
  d. two panels that touch with no gutter, where the picture changes viewpoint or scene along an edge;
  e. a vignette: a character or object drawn on the bare page with no frame and no background, when it shows a
     moment of the story (it is drawn at the same scale and finish as the panels around it, or a bubble is spoken
     from it).
- These are not panels: speech bubbles, captions, sound effects, titles and logos, page numbers, blocks of text
  (credits, lists of names, licence lines, "The End"), and small drawings that only decorate text (a mascot beside
  the credits, an ornament, a signature).
- Two areas are one panel only if the drawing runs on between them with no border or gutter: same background, same
  scale, same viewpoint, and no character shown twice. Do not split a panel at something drawn inside the scene that
  looks like a divider: bars, a pillar, a door frame, a beam of light, or a background that changes colour.
- Bubbles, captions, sound effects and pieces of art (a hat, a tail, a weapon) often cross a panel's border or a
  gutter. Ignore them when deciding where panels are: they never set a panel's edges and never join two panels.

What kind of region it is
- "story": story panels, with or without bubbles and captions.
- "title": a title page or cover. Its illustration is one panel; the title lettering, logo and episode number on it
  are not separate panels.
- "credits": credits, patrons, licence, author notes, an end card.
- "text": a page that is mostly prose (a foreword, a letter).
- A region holding both story panels and text (the last panel above the credits) is "story", and the text goes in
  "text_regions".

Answer with JSON only:
{"kind": "story" | "title" | "credits" | "text",
 "panels": [[x0, y0, x1, y1], ...],
 "text_regions": [[x0, y0, x1, y1], ...]}
- x runs from 0 at the image's left edge to 1000 at its right edge; y from 0 at the top edge to 1000 at the bottom
  edge. The axes are scaled separately, so in a wide image a square panel spans more y units than x units.
- Each panel's box is the smallest axis-aligned rectangle containing all of its art, including its border line.
- A panel without a border (a vignette, art fading into the page) gets a box around everything that belongs to its
  scene: all its characters, props and sound effects out to the outermost art, not just the main figure.
- When an inset is drawn over a bigger panel, the bigger panel's box covers its whole picture, including the part
  under and around the inset; do not stop it at the inset's edge.
- Where two panels meet along a straight gutter or border, put both boxes' edges on that line: neighbouring boxes
  should neither leave art between them nor overlap past it (an inset is the exception). Along a slanted or
  irregular border the rectangles will include some gutter and overlap; that is expected, do not shrink them.
- "panels" lists the story panels in reading order. It may be empty.
- "text_regions" lists the blocks of text and decoration on the bare page that are not panels. Do not list speech
  bubbles or captions there."""
PROMPT_V1 = """This image is one strip (a "box") cut from a comic page. Find every drawn PANEL (frame) in it: each separate
picture the artist framed, including panels without a border, panels whose art bleeds to the edge, inset panels drawn
over a bigger one, and panels that touch with no gutter between them. Speech bubbles and captions are not panels.
Answer with JSON only: {"panels": [[x0, y0, x1, y1], ...]} where the coordinates are each panel's bounding box in
0-1000 units of the image's width (x) and height (y), top-left origin, panels in reading order."""  # its cached answers
PROMPT = """This image is a region cut from a comic page, {w} x {h} pixels. It may hold story panels, and it may also
hold things that are not story panels. Find the story panels.

What a panel is
- A panel is one picture of the story seen from one viewpoint at one moment. Most panels are enclosed by a border
  line or separated from their neighbours by a gutter (a strip of bare page), but the border is only the usual cue,
  not the definition.
- These are panels too:
  a. a panel with no border, whose art fades out or stops on the bare page;
  b. a panel whose art runs to the edge of the image;
  c. an inset: a smaller panel drawn on top of a bigger one (return both; they overlap);
  d. two panels that touch with no gutter, where the picture changes viewpoint or scene along an edge;
  e. a vignette: a character or object drawn on the bare page with no frame and no background, when it shows a
     moment of the story (it is drawn at the same scale and finish as the panels around it, or a bubble is spoken
     from it).
- These are not panels: speech bubbles, captions, sound effects, titles and logos, page numbers, blocks of text
  (credits, lists of names, licence lines, "The End"), and small drawings that only decorate text (a mascot beside
  the credits, an ornament, a signature).
- Two areas are one panel only if the drawing runs on between them with no border or gutter: same background, same
  scale, same viewpoint, and no character shown twice. Do not split a panel at something drawn inside the scene that
  looks like a divider: bars, a pillar, a door frame, a beam of light, or a background that changes colour.
- Bubbles, captions, sound effects and pieces of art (a hat, a tail, a weapon) often cross a panel's border or a
  gutter. Ignore them when deciding where panels are: they never set a panel's edges and never join two panels.

What kind of region it is
- "story": story panels, with or without bubbles and captions.
- "title": a title page or cover. Its illustration is one panel; the title lettering, logo and episode number on it
  are not separate panels.
- "credits": credits, patrons, licence, author notes, an end card.
- "text": a page that is mostly prose (a foreword, a letter).
- A region holding both story panels and text (the last panel above the credits) is "story", and the text goes in
  "text_regions".

Answer with JSON only:
{{"kind": "story" | "title" | "credits" | "text",
 "panels": [{{"box": [x0, y0, x1, y1]}}, {{"box": [x0, y0, x1, y1], "corners": [[x, y], ...]}}, ...],
 "text_regions": [[x0, y0, x1, y1], ...]}}
- Every coordinate is in 0-1000 units, never in pixels: x = 1000 * (pixels from the left edge) / {w}, and
  y = 1000 * (pixels from the top edge) / {h}. Both x and y run from 0 to 1000, whatever the image's shape.
- Each panel's box is the smallest axis-aligned rectangle containing all of its art, including its border line.
- If a panel's border is slanted or not a rectangle, also give its corner points in order, as "corners"; otherwise
  leave "corners" out.
- A panel without a border (a vignette, art fading into the page) gets a box around everything that belongs to its
  scene: all its characters, props and sound effects out to the outermost art, not just the main figure.
- When an inset is drawn over a bigger panel, the bigger panel's box covers its whole picture, including the part
  under and around the inset; do not stop it at the inset's edge.
- Where two panels meet along a straight gutter or border, put both boxes' edges on that line: neighbouring boxes
  should neither leave art between them nor overlap past it (an inset is the exception). Along a slanted or
  irregular border the boxes will include some gutter and overlap; that is expected, do not shrink them.
- "panels" lists the story panels in reading order. It may be empty.
- "text_regions" lists the blocks of text and decoration on the bare page that are not panels. Do not list speech
  bubbles or captions there."""
KINDS = ("story", "title", "credits", "text")


class PanelError(RuntimeError):
    """The model's answer held no readable panel list."""


def _box(v) -> list[float] | None:
    if isinstance(v, list) and len(v) == 4 and all(isinstance(x, (int, float)) for x in v):
        return [float(x) for x in v]
    return None


def _points(v) -> list[list[float]] | None:
    if isinstance(v, list) and len(v) >= 3 and all(isinstance(p, list) and len(p) == 2 and
                                                    all(isinstance(x, (int, float)) for x in p) for p in v):
        return [[float(x) for x in p] for p in v]
    return None


def _in_range(vals) -> bool:
    return all(-1 <= x <= 1001 for x in vals)


def answer(img: Image.Image, model: str = MODEL, reasoning: str | None = REASONING, tag: str = "",
           prompt: str | None = None) -> dict:
    """The model's answer, uncached: {"kind", "panels": [box], "corners": [points or None, one per panel],
    "text_regions": [box]}, in 0-1000 units. A panel may come as [x0, y0, x1, y1] (v1, v2) or {"box", "corners"}
    (v3). Raises PanelError when the answer has no panel list, a coordinate outside 0-1000 (39-p026 under v2: x in
    pixels) or was cut off at its budget; BudgetExceeded before a call the daily cap forbids."""
    img = img.convert("RGB")
    try:
        v, _ = OR.ask_json(model, [{"type": "text", "text": prompt if prompt is not None else _prompt(img)},
                                   OR.image_part(img, max_side=MAX_SIDE)], tag, 1500, reasoning)
    except OR.Truncated as e:
        raise PanelError(f"{model}: {e}") from None
    if not isinstance(v.get("panels"), list):
        raise PanelError(f"{model}: no panel list in the answer")
    panels, corners = [], []
    for p in v["panels"]:
        b = _box(p) if isinstance(p, list) else _box(p.get("box")) if isinstance(p, dict) else None
        if b is not None:
            panels.append(b)
            corners.append(_points(p.get("corners")) if isinstance(p, dict) else None)
    text_regions = [b for b in map(_box, v.get("text_regions") or []) if b is not None]
    flat = [x for b in panels + text_regions for x in b] + [x for c in corners if c for p in c for x in p]
    if not _in_range(flat):
        raise PanelError(f"{model}: a coordinate outside 0-1000 ({min(flat)} .. {max(flat)})")
    return {"kind": v.get("kind") if v.get("kind") in KINDS else "story", "panels": panels, "corners": corners,
            "text_regions": text_regions}


def _prompt(img: Image.Image) -> str:
    """PROMPT filled with the size the model sees (image_part scales the image to MAX_SIDE)."""
    s = min(1.0, MAX_SIDE / max(img.size))
    return PROMPT.format(w=round(img.width * s), h=round(img.height * s))


def cache_file(img: Image.Image, prompt: str | None = None):
    """Where the answer for this image and prompt is cached (default: the current prompt, filled for its size)."""
    img = img.convert("RGB")
    prompt = _prompt(img) if prompt is None else prompt
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return CACHE / f"{hashlib.sha1(buf.getvalue() + (MODEL + prompt).encode()).hexdigest()[:20]}.json"


def _cached(img: Image.Image, tag: str, prompt: str | None = None) -> dict:
    f = cache_file(img, prompt)
    if f.exists():
        return json.loads(f.read_text())
    try:
        v = answer(img, tag=tag, prompt=prompt)
    except PanelError as e:  # one more try; an answer that fails twice is not cached, so the next run asks again
        print(f"frames {tag}: {e}; asking again")
        v = answer(img, tag=tag, prompt=prompt)
    CACHE.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"model": MODEL, "tag": tag, **v}))
    return v


@dataclass
class Layout:
    """The model's answer in box pixels: panels clipped to the box, near-duplicates merged, small ones dropped,
    largest first, each with its corner polygon or None; the region's kind; its text regions."""
    kind: str
    panels: list[tuple[int, int, int, int]]
    corners: list[np.ndarray | None]
    text: list[tuple[int, int, int, int]]


def _px(b, w, h) -> tuple[int, int, int, int]:
    x0, x1 = sorted((b[0], b[2])); y0, y1 = sorted((b[1], b[3]))
    return (max(0, round(x0 * w / 1000)), max(0, round(y0 * h / 1000)), min(w, round(x1 * w / 1000)), min(h, round(y1 * h / 1000)))


def to_layout(v: dict, w: int, h: int) -> Layout:
    """A cached answer (any prompt version) in box pixels."""
    corners = v.get("corners") or [None] * len(v["panels"])
    cand = []
    for b, c in zip(v["panels"], corners):
        p = _px(b, w, h)
        if p[2] - p[0] >= MIN_SIDE and p[3] - p[1] >= MIN_SIDE:
            cand.append((p, None if c is None else np.array([[x * w / 1000, y * h / 1000] for x, y in c])))
    cand.sort(key=lambda pc: -(pc[0][2] - pc[0][0]) * (pc[0][3] - pc[0][1]))
    kept = []
    for p, c in cand:
        if all(_iou(p, k[0]) < DUP_IOU for k in kept):
            kept.append((p, c))
    text = [t for t in (_px(b, w, h) for b in v.get("text_regions") or []) if t[2] > t[0] and t[3] > t[1]]
    return Layout(v.get("kind", "story"), [k[0] for k in kept], [k[1] for k in kept], text)


def layout(img: Image.Image, tag: str = "panels", prompt: str | None = None) -> Layout:
    """The cached answer for this box, asked for when not cached. prompt: another prompt than the current one (an
    earlier version, PROMPT_V1, PROMPT_V2: its cached answers). Raises OR.BudgetExceeded (spend.OfflineCall in an
    offline run, when not cached), or PanelError after two unusable answers."""
    img = img.convert("RGB")
    return to_layout(_cached(img, tag, prompt), *img.size)


def _iou(a, b) -> float:
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def _fit(b, T: np.ndarray, w: int, h: int) -> tuple[int, int, int, int]:
    """A panel box fitted to the gutters around it. T: pixels that are page and look like page. Trimmed first: an
    edge line that is TRIM_LINE page moves in (a loose box took in gutter, or a vignette's bare ground), two passes.
    Then snapped: an edge on art moves out to the first line that is GUTTER_LINE page, if one lies within SNAP of the
    box's size (the image edge counts as a gutter); else it stays (touching panels, insets)."""
    x0, y0, x1, y1 = b
    row = lambda y, a, c: T[y, a:c].mean() if c > a else 0.0  # noqa: E731
    col = lambda x, a, c: T[a:c, x].mean() if c > a else 0.0  # noqa: E731
    for _ in range(2):
        while y1 - y0 > MIN_SIDE and row(y0, x0, x1) >= TRIM_LINE:
            y0 += 1
        while y1 - y0 > MIN_SIDE and row(y1 - 1, x0, x1) >= TRIM_LINE:
            y1 -= 1
        while x1 - x0 > MIN_SIDE and col(x0, y0, y1) >= TRIM_LINE:
            x0 += 1
        while x1 - x0 > MIN_SIDE and col(x1 - 1, y0, y1) >= TRIM_LINE:
            x1 -= 1
    ry, rx = max(2, round(SNAP * h)), max(2, round(SNAP * w))

    def out(edge, step, reach, limit, line):
        if line(edge) >= GUTTER_LINE:
            return edge
        for d in range(1, reach + 1):
            e = edge + step * d
            if e == limit:  # the image's edge
                return e
            if line(e) >= GUTTER_LINE:
                return e - step
        return edge
    y0n = out(y0, -1, ry, -1, lambda y: row(y, x0, x1))
    y1n = out(y1 - 1, 1, ry, h, lambda y: row(y, x0, x1)) + 1
    x0n = out(x0, -1, rx, -1, lambda x: col(x, y0, y1))
    x1n = out(x1 - 1, 1, rx, w, lambda x: col(x, y0, y1)) + 1
    return (max(0, x0n), max(0, y0n), min(w, x1n), min(h, y1n))


@dataclass
class Split:
    """A box's frames: masks (exclusive; with the page they cover the box), which of them are flat (text, credits:
    no backdrop relief; their characters are still cards), and the page they leave out."""
    frames: list[np.ndarray]
    flat: list[bool]
    page: np.ndarray


def split_box(job: tuple) -> Split:
    """split for one box from (img, its lettering masks' union, the model's layout or None), the gutter found from
    the lettering: the frame step's per-box work, one argument so workers.pmap can run boxes in parallel."""
    img, letters, lay = job
    return split(img, gutter(img, letters if letters.any() else None), lay, letters)


def split(img: Image.Image, gutter: np.ndarray, lay: Layout | None, letters: np.ndarray | None = None) -> Split:
    """The frames of one box from the model's layout (None: no answer, the box is one scene); letters: the lettering
    masks' union (its parts past every panel join no frame). See the module doc."""
    import cv2
    from scipy.ndimage import distance_transform_edt
    img = img.convert("RGB")
    w, h = img.size
    rgb = np.asarray(img)
    page = gutter.copy()
    kind = lay.kind if lay is not None else "story"
    panels = list(lay.panels) if lay is not None else []
    corners = list(lay.corners) if lay is not None else []
    flat = [False] * len(panels)
    if not panels:  # no answer, or a region without story panels: the whole box, flat unless it is a story
        panels, corners, flat = [(0, 0, w, h)], [None], [lay is not None and kind != "story"]
    rect = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in panels:
        rect[y0:y1, x0:x1] = True
    # what looks like page: white, the page colour page_colour finds, and a flat colour holding FLAT_SHARE of the
    # pixels outside every panel (the dark grey page of P&C 36/38, missed by gutter: its gutters and margins sat
    # inside the frames)
    labc = lab(img)
    looks = rgb.min(axis=2) >= 245
    pc = page_colour(img)
    if pc is not None:
        looks |= np.linalg.norm(labc - pc, axis=-1) <= PAGE_TOL
    outside = ~rect & ~page
    flatc = np.zeros((h, w), bool)
    if lay is not None and lay.panels and outside.sum() >= FLAT_MIN:
        vals, cnt = np.unique(np.round(labc[outside] / 2), axis=0, return_counts=True)
        near = np.linalg.norm(labc - vals[cnt.argmax()] * 2, axis=-1) <= FLAT_TOL
        if near[outside].mean() >= FLAT_SHARE:
            flatc = near
            page |= near & ~rect  # only outside the panels: inside, the same colour may be art
    # gutter-like, for fitting the boxes: looks like page and is page (or lies outside every panel), or is the flat
    # page colour (a loose box's edge in a grey gutter that gutter() missed)
    G = (looks & (page | ~rect)) | flatc
    panels = [_fit(b, G, w, h) for b in panels]
    masks, slanted = [], []
    for (x0, y0, x1, y1), c in zip(panels, corners):
        m = np.zeros((h, w), bool)
        m[y0:y1, x0:x1] = True
        poly = None
        if c is not None:  # a slanted panel: its polygon, when it fills most of its box
            poly = np.zeros((h, w), np.uint8)
            cv2.fillPoly(poly, [np.round(c).astype(np.int32)], 1)
            poly = poly.astype(bool)
            poly = poly if poly.sum() >= POLY_MIN * m.sum() else None
        masks.append(m if poly is None else poly)
        slanted.append(poly is not None)
    lab_ = np.zeros((h, w), np.int32)
    for k in sorted(range(len(masks)), key=lambda k: -masks[k].sum()):  # largest first: a smaller one wins its pixels
        lab_[masks[k]] = k + 1
    text = np.zeros((h, w), bool)
    for x0, y0, x1, y1 in (lay.text if lay is not None else []):
        text[y0:y1, x0:x1] = True
    text &= (lab_ == 0) & ~page  # the text blocks no panel holds
    if text.sum() < TEXT_MIN:  # a scrap: it joins the nearest frame like any art outside the panels
        text[:] = False
    # art outside every panel joins the nearest frame (the text frame among them), one piece at a time (pixels within
    # 2 * PIECE_GAP of each other, so a word or a text block is one piece), when the piece touches a frame (within
    # TOUCH_PX): a leg past a loose box (38-p018), a close-up's art running past its box, a bubble crossing a border.
    # A piece cut off from every frame by page is loose and goes to the text frame (created when there is none): the
    # credits under a story's last panel grew it by 421 px (37-p016), an end page's scroll by 1525 px (36-p028)
    from scipy.ndimage import binary_dilation, label as cc
    n = len(masks)
    if text.any():
        lab_[text] = n + 1
    lettering = letters if letters is not None else np.zeros((h, w), bool)
    # lettering past every panel (a bubble breaking the border) is drawn by the lettering layer, unclipped: it joins
    # no frame, or its overhang grew the frame into bumps (39-p008)
    spill = (lab_ == 0) & ~page & ~lettering
    if spill.any() and (lab_ > 0).any():
        dist, (iy, ix) = distance_transform_edt(lab_ == 0, return_indices=True)
        near = lab_[iy, ix]
        pieces, npieces = cc(binary_dilation(spill, iterations=PIECE_GAP), structure=np.ones((3, 3)))
        pieces = np.where(spill, pieces, 0)
        mind = np.full(npieces + 1, np.inf)
        np.minimum.at(mind, pieces[spill], dist[spill])
        loose = spill & (mind[pieces] > TOUCH_PX)
        size = np.bincount(pieces[loose], minlength=npieces + 1)
        dust = loose & (size[pieces] < DUST_PX)  # a speck cut off from every frame: page (37-p016's credits: 38 px)
        page |= dust
        loose &= ~dust
        lab_ = np.where(spill & ~loose & ~dust, near, lab_)
        if loose.any():
            lab_[loose] = n + 1
    # each frame (but a slanted one) is the rectangle around its box and the art that joined it: the free pixels in
    # that rectangle (page, lettering) join it, those of other frames stay theirs; smallest first. Without it a
    # vignette's ground hung off its box as a blob (39-p027: the table's shading under the girl and the cat)
    for k in sorted(range(n), key=lambda k: masks[k].sum()):
        mk = lab_ == k + 1
        if not mk.any() or flat[k] or slanted[k]:
            continue
        ys, xs = np.nonzero(mk)
        sub = lab_[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        sub[sub == 0] = k + 1
    out = [(lab_ == k + 1, flat[k]) for k in range(n) if (lab_ == k + 1).any()]
    if (lab_ == n + 1).any():
        out.append((lab_ == n + 1, True))
    return Split([m for m, _ in out], [f for _, f in out], page)


def ask(ep: Episode, imgs: dict[int, Image.Image]) -> dict[int, Layout | None]:
    """The panel boxes per box (layout: Claude Sonnet 5.5, boxes asked at once, answers cached). They need only the
    images, so episode.py asks for them in the background while SAM segments. A box with no answer (the daily cap,
    two unreadable replies) gets None: one scene for now, asked again next run."""
    def one(i):
        try:
            return layout(imgs[i], f"panels:{ep.box(i).pid}")
        except PanelError as e:
            print(f"p{i}: no panel boxes ({e}); one scene for now")
            return None

    asked, stopped = paid_map(one, list(imgs))
    return asked | {i: None for i in stopped}


def update(ep: Episode, imgs: dict[int, Image.Image], letters: dict[int, list], answers: dict) -> None:
    """The step: each box's frames (split_box on ask's answers, boxes across processes) saved with the page they
    leave out (Box.save_frames), which every later step uses as the page. The lettering masks feed the gutter (a
    bubble touching the box edge is not page). A box with no answer is saved as unanswered, so the next run asks
    again."""
    jobs = [(img, union(letters[i], (img.height, img.width)), answers[i]) for i, img in imgs.items()]
    counts = []
    for i, s in zip(imgs, pmap(split_box, jobs)):
        ep.box(i).save_frames(s.frames, s.flat, s.page, answers[i] is not None)
        counts.append(len(s.frames))
    print(f"frames per box: {counts}")


def main() -> None:
    """Frames per box per episode, from the gutter alone: without the lettering masks the pipeline gives update, a
    bubble touching the box edge can read as page, so counts may differ from the pipeline's."""
    import sys
    from pathlib import Path
    from chapter import Chapter
    for zp in map(Path, sys.argv[1:]):
        ch = Chapter(zp)
        counts, flats = [], []
        for i in range(len(ch)):
            img = ch.image(i)
            try:
                lay = layout(img, f"panels:{ch.pid(i)}")
            except (OR.BudgetExceeded, PanelError) as e:
                print(f"p{i}: no answer ({e})")
                lay = None
            s = split(img, gutter(img), lay)
            counts.append(len(s.frames))
            flats += [i] if any(s.flat) else []
        hist = {k: counts.count(k) for k in sorted(set(counts))}
        print(f"{ch.stem}: {len(counts)} boxes, frames per box {hist}; multi: {[i for i, c in enumerate(counts) if c > 1]}; "
              f"with a flat frame: {flats}")


if __name__ == "__main__":
    main()
