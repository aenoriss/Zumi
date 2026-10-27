"""Two decisions per box a person made by eye, made by one small vision call each (Claude Haiku via openrouter.py):

  choose_objects  before the erase: which big foreground objects (furniture, vehicles, big props in front of floor or
                  wall) to erase so the background behind them is revealed, each as a SAM text prompt and a point on it
                  (the box is shown with a coordinate grid in box pixels, so the points can be read off it)
  judge_tears     after the mesh: for each tear on tears.list_tears' contact sheet, "close" (the depth model split one
                  surface) or "keep" (a real object edge)

    python scene_judge.py objects <image.png>
    python scene_judge.py tears <tears dir>          (tears_sheet.png + tears.json from tears.list_tears)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from openrouter import chat, image_part

MODEL = "anthropic/claude-haiku-5.5"
EFFORT = "high"
REASONING_TOKENS = 4000  # reasoning spends from max_tokens (review_loop.py)
MAX_SIDE = 1568          # the model's own downscale limit: a bigger image only costs upload


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def _ask(content: list, tag: str, max_tokens: int) -> tuple[dict, float]:
    text, usage = chat(MODEL, [{"role": "user", "content": content}], max_tokens=max_tokens + REASONING_TOKENS,
                       tag=tag, reasoning=EFFORT)
    return _json(text), float(usage.get("cost", 0) or 0)


def grid_image(img: Image.Image, step: int | None = None) -> Image.Image:
    """The box scaled to fit MAX_SIDE, a thin line every `step` box pixels across it (dashed, light and dark so it
    reads on any colour), labelled in BOX pixels inside the art (red, white outline) along the top and left edges.
    No margin: with a 44 x 22 px label margin Haiku measured half its points in the picture instead of reading the
    labels, landing them 44 px right and 22 px down of the object (committee test, P&C 39); without it points fell
    within ~15 px."""
    img = img.convert("RGB")
    w, h = img.size
    step = step or (100 if max(w, h) <= 2400 else 200)
    s = min(1.0, MAX_SIDE / max(w, h))
    sw, sh = round(w * s), round(h * s)
    out = img.resize((sw, sh), Image.LANCZOS)
    d = ImageDraw.Draw(out)
    f = ImageFont.load_default(size=15)
    for x in range(0, w, step):
        px = round(x * s)
        for y0 in range(0, sh, 8):
            d.line([(px, y0), (px, min(y0 + 4, sh))], fill=(255, 255, 255), width=1)
            d.line([(px, y0 + 4), (px, min(y0 + 8, sh))], fill=(0, 0, 0), width=1)
        if x:
            d.text((px + 2, 2), str(x), fill=(220, 0, 0), font=f, stroke_width=2, stroke_fill="white")
    for y in range(0, h, step):
        py = round(y * s)
        for x0 in range(0, sw, 8):
            d.line([(x0, py), (min(x0 + 4, sw), py)], fill=(255, 255, 255), width=1)
            d.line([(x0 + 4, py), (min(x0 + 8, sw), py)], fill=(0, 0, 0), width=1)
        if y:
            d.text((2, py + 1), str(y), fill=(220, 0, 0), font=f, stroke_width=2, stroke_fill="white")
    return out


# merged from a three-member committee (recall, precision, relations; P&C 39, 2026-10-26) and the user's rulings:
# counters and booth seats are cards, fountains backdrop; held items join their holder's card; close-ups list only
# what is held; an animal is an object only where the character masks missed it
OBJECTS_PROMPT = """This is one comic box, {w} x {h} pixels; it may hold one frame or several frames side by side. \
It will be shown in 3D as flat layers: the characters and the lettering are cut out separately, everything else stays \
in one painted backdrop, and every OBJECT you list is cut out of the backdrop (the hole is repainted) and shown as its \
own flat card in front of it. Anything you leave out stays PAINTED on the backdrop (a cup left out stays behind when \
its table moves), and a wrong pick tears a hole in a wall or the ground. So list every movable object, and nothing \
that is part of the place itself.

WHAT TO LIST
- Every physical object that stands, sits or lies free in the space, whatever its size: furniture (table, desk, \
chair, stool, bar stool, bench, sofa, bed, cabinet, chest, bar counter, shop counter, booth seat), props (cup, mug, \
glass, bottle, jug, pitcher, teapot, plate, bowl, pot, vase, potted plant, book, paper, candle, basket, sack, barrel, \
crate, box), weapons and tools lying on the floor or a table or leaning on something (sword, flail, axe, shield, \
broom, staff), carts and vehicles, statues, free-standing lamps. Small items count too: a vase on a side table, cups \
on a table, a mug on a counter. A table with characters sitting all around it is still listed, even when they hide \
most of it.
- Every instance is its own entry: four bar stools are four entries. A heap of the same things that touch (a pile of \
baskets, a stack of folded clothes) is ONE entry.
- An item that rests on another object is listed together with that support: if there are mugs on a table, the table \
is an entry too.
- Items a character HOLDS that are separate from the body, for every character, background ones included: a \
newspaper or book being read, a cup, mug or glass, a plate, a sword, a shield, an instrument, a broom, a staff, a \
garment held in the hands (not worn). Give them "held": true. If no part of a held item shows outside the hands and \
body, leave it out.
- An animal or pet (a cat, a bird, a horse) gets "animal": true.
If the box (or one of its frames) has no scene behind its subject (a close-up of a face or body on a plain, blurred, \
abstract or effect-lines background), list only what the characters there hold.

NEVER LIST (it is the backdrop)
- Characters or any part of them, and anything they WEAR (clothes, hats, armour, bags, jewellery).
- Lettering, speech bubbles, caption boxes, sound effects, music notes, motion lines, panel borders and gutters.
- The place itself: floor, ground, walls, ceiling, roof, beams, pillars and posts, sky, clouds, water, windows and \
doors, archways, gates, stairs and steps, railings and fences, fireplaces, and anything built into the ground: \
fountains and their basins, wells, monuments.
- Anything FIXED to a wall, ceiling, pillar, beam or building: pictures and paintings, signs, wall lamps, sconces, \
lanterns or lamps hanging from above, bells, clocks, wall shelves and EVERYTHING on them, hooks and whatever hangs on \
them (a hat, an instrument, keys, a pan), racks, hanging baskets, curtains, banners, awnings, trellises, window \
boxes, unless a character is holding or taking it down (then it is a held item).
- Outdoors: buildings, towers, stalls built against a building, trees, bushes, hedges, grass, flowers or vines \
growing in the ground or on a wall, rocks, cliffs, mountains, paths, pools. Only a movable thing standing in the open \
counts (a cart, a barrel, a crate, a table, a chair, a potted plant).
- Things flat on the floor (rugs, mats, puddles, shadows, patches of light), things in the far distance (behind the \
main scene, much smaller than the characters), and an object of which only a small sliver shows at a frame border.
When unsure whether something is fixed or part of the place, leave it out.

NAMES (a segmentation model finds each object from its name as a text prompt plus its point)
- A plain noun phrase of what the object IS, ending with its noun: "table", "bar counter", "beer mug", "bar stool", \
"wicker basket", "newspaper". No positions, owners or actions: never "mug on the counter", "glass held by the bull", \
"left stool", "wizard's chair".
- Only when several objects in the box share a name, add a number at the end: "beer mug 1", "beer mug 2". An object \
that is the only one of its kind gets no number.
- Each frame is its own scene: an object drawn in two frames is listed once per frame (numbered like any repeat), and \
items rest only on objects in their own frame.

POINT
"point": [x, y] in the box's own pixels, read off the grid: a dashed line every {step} px, its value in red along \
the top edge (x) and the left edge (y); the top-left corner is [0, 0]. Check that the grid cell your point falls in \
contains the object. The point lies ON the object, on a plainly visible part well inside its outline (a small item: \
its middle; a thin one like a broom or sword: its widest part), never on a character, a hand or anything in front \
of it: for a held item, its largest bare part away from the hands and body.

RELATIONS
- "on": for an item that rests on, stands on or hangs from ANOTHER OBJECT IN YOUR LIST, that object's name copied \
letter for letter as you wrote it in its own entry (with its number only if it has one). Chains are fine (cup on \
tray, tray on table). null when what it rests on is not in your list (cut off by the frame border, or the floor); \
leave the item out entirely if its support is fixed to a wall. Never name a character in "on".
- "held": true when a character holds or carries the item in a hand or arms. An item merely lying on a table in front \
of someone is not held.
- "front": true if the object is NEARER to the viewer than the characters it touches or overlaps (a desk in front of \
a seated person, a table whose edge hides a seated person's lap, a counter with the barkeeper behind it), false if it \
is behind them (the chair, bench or booth a person sits in or leans against, a table or shelf behind them). false \
when it touches no character, and for a held item.
- "except": usually []. When the object is in front of some characters it touches but behind others, one point \
[x, y] on the body of each character for whom the opposite of "front" holds (a bar counter with the barkeeper behind \
it and a customer standing in front of it: "front": true, "except": [a point on the customer]). For every counter, \
table or booth, check whether characters are on both sides of it.

Answer with JSON only:
{{"room": true, "objects": [{{"name": "...", "point": [x, y], "on": null, "held": false, "front": false, \
"except": [], "animal": false}}]}}"""


SNAP_PX = 25  # a point this close to a character's edge is moved off it: points that land on a character missed by
              # 1-23 px (the dining table, the lute, the staff on P&C 39), and dropping them lost 13-17 objects a run


def _xy(p):
    """[x, y] or {"x":, "y":} -> (x, y) ints; Haiku returns both."""
    if isinstance(p, dict):
        p = [p.get("x"), p.get("y")]
    return tuple(int(round(float(v))) for v in p[:2])


def choose_objects(img: Image.Image, chars: np.ndarray | None = None, tag: str = "", log=print) -> list[dict]:
    """[{"name", "point": [x, y], "on", "held", "front", "except": [[x, y], ...], "animal"}] in box pixels: every
    object in the scene, small ones included, each a layer of its own (cards.py), an item resting on another listed
    object joined to it, a held one to its holder. chars (optional, box-sized bool): a point on a character is moved to
    the nearest pixel off it within SNAP_PX, else dropped; an animal's point is never moved (on a character mask it IS
    that character, already cut out)."""
    from scipy.ndimage import distance_transform_edt
    img = img.convert("RGB")
    w, h = img.size
    step = 100 if max(w, h) <= 2400 else 200
    prompt = OBJECTS_PROMPT.format(w=w, h=h, step=step)
    # 3000: on a busy box (P&C 39 p12, ~27 objects) the answer ran into a 1500 + 4000 reasoning cap and came back cut
    res, cost = _ask([{"type": "text", "text": prompt}, image_part(grid_image(img, step), max_side=MAX_SIDE)],
                     f"scene_judge objects {tag}".strip(), 3000)
    near = None
    if chars is not None and chars.any():
        dist, (iy, ix) = distance_transform_edt(chars, return_indices=True)
        near = (dist, iy, ix)
    out = []
    for o in res.get("objects") or []:
        try:
            name = str(o["name"]).strip()
            x, y = _xy(o["point"])
        except (KeyError, TypeError, ValueError, IndexError):
            continue
        if not name or not (0 <= x < w and 0 <= y < h):
            log(f"  dropped {o}: point outside the box")
            continue
        animal = o.get("animal") is True
        if near is not None and chars[y, x]:
            if animal or near[0][y, x] > SNAP_PX:
                log(f"  dropped {name} at {x},{y}: the point is on a character" + (" (an animal: it is one)" if animal else ""))
                continue
            nx, ny = int(near[2][y, x]), int(near[1][y, x])
            log(f"  {name}: point {x},{y} on a character, moved {near[0][y, x]:.0f} px to {nx},{ny}")
            x, y = nx, ny
        exc = []
        for p in o.get("except") or []:
            try:
                exc.append(list(_xy(p)))
            except (TypeError, ValueError, IndexError):
                pass
        on = o.get("on")
        out.append({"name": name, "point": [x, y], "on": str(on).strip() if on else None, "held": o.get("held") is True,
                    "front": o.get("front") is True, "except": exc, "animal": animal})
    log(f"  objects {tag}: {[o['name'] for o in out] or 'none'} (room {res.get('room')}, {cost:.4f} USD)")
    choose_objects.last_cost = cost
    return out


choose_objects.last_cost = 0.0


TEARS_PROMPT = """A comic panel was turned into a 3D surface from an estimated depth map. Where the depth jumps, the \
surface is cut open (a "tear"). The image shows each tear in its own numbered tile: a crop of the panel with the tear \
drawn in solid red. The tile title gives the tear's number, its size in grid cells (one cell = {stride} px) and its \
depth ratio (how much farther one side is than the other: x1.04 = 4%).
{stats}

For each tear decide:
- "close": there is NO real depth edge there; the depth model split ONE continuous surface. Typical: a line on a wall \
(a pillar or panel line, a moulding, a seam), a straight line along the panel's top or bottom border, a crease or a \
plank line on the floor, the edge of a cast shadow or of a patch of light on the floor or wall, the edge where a \
character's own cast shadow meets the floor. Closing joins both sides into one surface.
- "keep": the red line follows a REAL OBJECT'S OUTLINE against what is behind it: a table, desk or chair edge or leg \
against the floor or wall, a vase or pot against the wall or table, a chair back against the floor, a hand or arm \
resting on a table, any object standing in front of the background. Keeping leaves the cut, which is right there.
Look at what lies on EACH side of the red line: two different things at different distances -> keep; the same \
surface on both sides -> close.
CHARACTERS ARE NOT PART OF THIS SURFACE: they are cut out and placed separately, so a character's outline is never a \
reason to keep. A tear that runs along a character's outline (robe, sleeve, hair, shoes) is the depth model bleeding \
the character's depth onto the floor or wall right next to it: judge only the scene beside it. If there is just \
floor, shadow or wall there -> close. Keep it only if a real object (table, chair, desk) lies along the red line, e.g. \
a hand resting ON a table's edge, a chair back behind a character.
The depth ratio is evidence too: a wrongly split surface rarely jumps by more than about 10% (x1.10); a jump of 15% \
or more (x1.15+) is almost always a real edge, so close one only if the picture plainly shows one surface.

Answer with JSON only, one entry per tear:
{{"tears": [{{"id": 1, "what": "<few words: what is on each side of the red line>", "decision": "close"}}]}}"""


def _sheet_relayout(sheet: Image.Image, n: int, cols_in: int = 8, tw: int = 190, th: int = 205, cols: int = 4) -> Image.Image:
    """list_tears' sheet (8 tiles of 190 x 205 per row) re-laid in 4 columns and enlarged to fill MAX_SIDE: each tear
    gets about twice the pixels it had in the model's view."""
    rows = (n + cols - 1) // cols
    out = Image.new("RGB", (cols * tw, rows * th), "white")
    for i in range(n):
        tile = sheet.crop(((i % cols_in) * tw, (i // cols_in) * th, (i % cols_in + 1) * tw, (i // cols_in + 1) * th))
        out.paste(tile, ((i % cols) * tw, (i // cols) * th))
    s = min(MAX_SIDE / max(out.size), (1.15e6 / (out.width * out.height)) ** 0.5)
    return out.resize((round(out.width * s), round(out.height * s)), Image.LANCZOS) if s > 1 else out


def judge_tears(sheet_png, tears_json, stride: int = 2, tag: str = "", log=print) -> dict:
    """{"close": [ids], "keep": [ids], "what": {id: description}}. A tear the model leaves out is kept (a wrong close
    pulls a real object edge into a rubber sheet; a wrong keep only leaves a cut)."""
    T = json.loads(Path(tears_json).read_text()) if not isinstance(tears_json, list) else tears_json
    if not T:
        return {"close": [], "keep": [], "what": {}}
    sheet = Image.open(sheet_png).convert("RGB")
    stats = "\n".join(f"#{t['id']}: {t['n']} cells, x{t['ratio']}" for t in T)
    res, cost = _ask([{"type": "text", "text": TEARS_PROMPT.format(stride=stride, stats=stats)},
                      image_part(_sheet_relayout(sheet, len(T)), max_side=MAX_SIDE)],
                     f"scene_judge tears {tag}".strip(), 60 + 40 * len(T))
    got = {}
    for e in res.get("tears") or []:
        try:
            got[int(e["id"])] = e
        except (KeyError, TypeError, ValueError):
            continue
    ids = [t["id"] for t in T]
    close = [i for i in ids if str(got.get(i, {}).get("decision", "")).lower() == "close"]
    keep = [i for i in ids if i not in close]
    missing = [i for i in ids if i not in got]
    if missing:
        log(f"  tears {tag}: no decision for {missing}, kept")
    log(f"  tears {tag}: close {close}, keep {keep} ({cost:.4f} USD)")
    judge_tears.last_cost = cost
    return {"close": close, "keep": keep, "what": {i: got.get(i, {}).get("what") for i in ids}}


judge_tears.last_cost = 0.0


def main():
    cmd, path = sys.argv[1], Path(sys.argv[2])
    if cmd == "objects":
        print(json.dumps(choose_objects(Image.open(path)), indent=1))
    elif cmd == "tears":
        stride = json.loads(Path(sys.argv[3]).read_text())["stride"] if len(sys.argv) > 3 else 2
        print(json.dumps(judge_tears(path / "tears_sheet.png", path / "tears.json", stride), indent=1))
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
