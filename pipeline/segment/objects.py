"""Step 2c, the objects: every movable thing in front of the backdrop per box, picked by one small vision call
(choose_objects: Claude Haiku names each as a SAM text prompt with a point on it and its relations: on, held,
front, except), masked by SAM 3.1 (masks_for_objects: the mask of that name holding the point), reviewed like the
characters and the lettering (review_loop, task "objects"), saved (Box.save_objects) and reused on reruns. The
layers step cuts each out of the backdrop as a card of its own (the erase paints behind it).

    find(ep, seg, imgs, chars, review_on, log)     the step for an episode's boxes (episode.py's 2c)
    per = masks_for_objects(seg, img, picked)      [{"name", "point", "mask", "score", and the relations}]
    per = reviewed(review's masks, per)            the same after the review: names and relations carried through
    python objects.py <image.png> <objects.json> <out.npz>   (masks.save_masks: kind "object", the name kept)

The point is the model's way of saying "this one": text prompts alone also returned floors and walls.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import distance_transform_edt

from boxstore import OBJECT_META_KEYS, Episode
from masks import Found, save_masks, union
from openrouter import Truncated, ask_json, image_part
from review_loop import review
from sam import THRESHOLD, Segmenter
from spend import paid_map

NEAR_PX = 80  # a point this close to a mask still picks it: the model reads points off a 100 px grid, and on small
              # objects they missed by more than 12 px (vase, teapot, plate on ToG 228 p6, all found by SAM at 0.88-0.93);
              # a mask holding the point still wins


def sam_name(name: str) -> str:
    """The text SAM is prompted with: the picker's name without the number that tells repeats apart ("beer mug 2")."""
    return re.sub(r"\s+\d+$", "", name.strip()) or name


DUP_IOU = 0.8  # two entries whose masks overlap this much are one object (repeats whose points found the same mask)


SYNONYMS = {  # names SAM 3.1 knows better for things the picker names plainly
    "broom": ["broomstick", "staff", "stick"], "staff": ["stick", "pole"], "wand": ["stick", "staff"],
    "mug": ["cup", "glass"], "tankard": ["mug", "cup"], "goblet": ["cup", "glass"], "flagon": ["jug", "bottle"],
    "lute": ["guitar", "mandolin"], "mandolin": ["lute", "guitar"], "newspaper": ["paper", "book"],
    "flail": ["mace", "weapon"], "axe": ["weapon"], "sword": ["blade", "weapon"], "shield": ["round shield"],
    "booth": ["bench", "sofa"], "stool": ["chair"], "counter": ["table", "bar"], "pitcher": ["jug", "bottle"],
}
MAX_ALT = 3  # other names tried per object


def alt_names(name: str) -> list[str]:
    """Other names for an object SAM found nothing for: its head noun, then that noun's SYNONYMS."""
    n = sam_name(name)
    head = n.split()[-1]
    out = ([head] if head != n else []) + SYNONYMS.get(head, [])
    return [x for x in dict.fromkeys(out) if x != n][:MAX_ALT]


def masks_for_objects(seg: Segmenter, img: Image.Image, objs: list[dict], log=print, _retry: bool = True) -> list[dict]:
    """[{"name", "point", "mask", "score"} per object found]. An object whose point lies in no mask of its name (or
    within NEAR_PX of one) is left out."""
    img = img.convert("RGB")
    w, h = img.size
    if not objs:
        return []
    found = [[] for _ in objs]  # (inside, distance, score, mask) per candidate
    # every instance SAM returns (its floor, sam.THRESHOLD), each name asked on the tiles holding its point: the
    # point decides, not the score
    for k, m, s in seg.find(img, [(sam_name(o["name"]), THRESHOLD) for o in objs], rows=[o["point"][1] for o in objs]):
        x, y = (int(round(v)) for v in objs[k]["point"])
        x, y = min(max(x, 0), w - 1), min(max(y, 0), h - 1)
        if m[y, x]:
            d = 0.0
        else:
            r0, r1 = max(0, y - NEAR_PX), y + NEAR_PX + 1
            c0, c1 = max(0, x - NEAR_PX), x + NEAR_PX + 1
            win = m[r0:r1, c0:c1]
            if not win.any():
                continue
            d = float(distance_transform_edt(~win)[y - r0, x - c0])
            if d > NEAR_PX:
                continue
        found[k].append((d == 0, -d, s, m))
    # a name SAM finds nothing for at the point gets other names, in order: the head noun alone ("bar counter" ->
    # "counter"), then SYNONYMS of it (P&C 39 p1: no mask for "broom", the brooms found as "broomstick" at 0.62)
    alts = {k: alt_names(o["name"]) for k, o in enumerate(objs)} if _retry else {}
    for _ in range(MAX_ALT if _retry else 0):
        retry = [k for k, c in enumerate(found) if not c and alts[k]]
        if not retry:
            break
        alt = [{**objs[k], "name": alts[k].pop(0)} for k in retry]
        again = masks_for_objects(seg, img, alt, log=lambda s: None, _retry=False)
        for k, a in zip(retry, alt):
            hit = next((g for g in again if g["name"] == a["name"] and g["point"] == objs[k]["point"]), None)
            if hit:
                found[k] = [(True, 0.0, hit["score"], hit["mask"])]
                log(f"  {objs[k]['name']}: found as '{a['name']}'")
    out = []
    for o, cands in zip(objs, found):
        if not cands:
            log(f"  {o['name']}: no mask at the point")
            continue
        inside, nd, s, m = max(cands, key=lambda t: (t[0], t[2], t[1]))
        dup = next((p for p in out if (p["mask"] & m).sum() > DUP_IOU * (p["mask"] | m).sum()), None)
        if dup is not None:
            log(f"  {o['name']}: same mask as {dup['name']}, kept once")
            continue
        out.append({**o, "mask": m, "score": s})
        log(f"  {o['name']}: score {s:.2f}, {m.mean() * 100:.1f}% of the box" + ("" if inside else f", point {-nd:.0f} px off"))
    return out


def reviewed(found: list[Found], picked: list[dict]) -> list[dict]:
    """The objects after the review (review_loop, task "objects": its masks, `found`), from those it was given
    (`picked`, masks_for_objects): each mask keeps its pick's name and relations; a mask the review added is a plain
    "object"; repeated names (a split mask's parts, additions) get a number, as the picker numbers repeats ("table",
    "table 2"); a relation naming an object the review merged into another (Found.aka) names that one."""
    meta = {o["name"]: o for o in picked}
    merged_into = {a: e.name for e in found if e.name for a in e.aka}
    seen, out = {}, []
    for e in found:
        base = e.name if e.name in meta else "object"
        seen[base] = seen.get(base, 0) + 1
        rel = {k: meta.get(base, {}).get(k) for k in OBJECT_META_KEYS}
        if rel.get("on") in merged_into:
            rel["on"] = merged_into[rel["on"]]
        out.append({"name": base if seen[base] == 1 else f"{base} {seen[base]}", "mask": e.mask, "score": e.score, **rel})
    return out


def main():
    img = Image.open(sys.argv[1]).convert("RGB")
    objs = json.loads(Path(sys.argv[2]).read_text())
    per = masks_for_objects(Segmenter(), img, objs)
    save_masks(Path(sys.argv[3]), [Found(p["mask"], p["score"], "object", p["name"]) for p in per])


# =====================================================================================================
# The picker (was scene_judge.py): which objects to cut out of the backdrop, one Claude Haiku call per box (the box
# shown with a coordinate grid in box pixels, so the points can be read off it); each object a SAM text prompt and a
# point on it, with its relations (on, held, front, except).
# =====================================================================================================

MODEL = "anthropic/claude-haiku-5.5"
EFFORT = "high"
MAX_SIDE = 1568          # the model's own downscale limit: a bigger image only costs upload


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
    object in the scene, small ones included, each a layer of its own (layers.py), an item resting on another listed
    object joined to it, a held one to its holder. chars (optional, box-sized bool): a point on a character is moved to
    the nearest pixel off it within SNAP_PX, else dropped; an animal's point is never moved (on a character mask it IS
    that character, already cut out). Raises openrouter.Truncated (no answer) and BudgetExceeded: the caller must
    not take either for "no objects"."""
    from scipy.ndimage import distance_transform_edt
    img = img.convert("RGB")
    w, h = img.size
    step = 100 if max(w, h) <= 2400 else 200
    prompt = OBJECTS_PROMPT.format(w=w, h=h, step=step)
    # 3000 for the answer (plus the gateway's reasoning allowance): on a busy box (P&C 39 p12, ~27 objects) a 1500
    # answer budget cut it short
    res, cost = ask_json(MODEL, [{"type": "text", "text": prompt}, image_part(grid_image(img, step), max_side=MAX_SIDE)],
                         tag, 3000, EFFORT)
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
    return out


# =====================================================================================================
# The step
# =====================================================================================================

def find(ep: Episode, seg: Segmenter | None, imgs: dict, chars: dict, review_on: bool, log: dict) -> None:
    """The objects of every box in imgs ({index: image}; chars: its character masks) that has none saved: picked
    (choose_objects, calls in parallel under the daily cap), masked (masks_for_objects; the Segmenter made here when
    none is given and a box has objects), reviewed when review_on, saved (Box.save_objects). A box whose pick fails
    (the cap, a reply cut off) is not saved, so the next run asks again. Each review's record goes into log under
    "p<i> objects". The first version listed big furniture only (it chose what to erase): the vase on ToG 228 p6's
    side table stayed painted on the backdrop."""
    def pick(i):
        img = imgs[i]
        try:
            return choose_objects(img, union(chars[i], (img.height, img.width)), tag=f"{ep.stem} p{i} objects")
        except Truncated as e:  # no answer is not "no objects": nothing saved, so the next run asks again
            print(f"p{i}: objects not chosen ({e}); not saved")
            return None

    picked, _ = paid_map(pick, [i for i in imgs if not ep.box(i).has_objects()])  # the cap: the rest next run
    todo = {}
    for i, objs in picked.items():
        if objs is None:
            continue
        if objs:
            seg = seg or Segmenter()
        todo[i] = masks_for_objects(seg, imgs[i], objs) if objs else []

    def check(i):
        per = todo[i]
        if not per or not review_on:
            return per, None
        new, lg = review(seg, imgs[i], [Found(o["mask"], o["score"], "object", o["name"]) for o in per], "objects",
                         f"{ep.stem} p{i} objects")
        return reviewed(new, per), lg

    done, _ = paid_map(check, list(todo))
    for i, (per, lg) in sorted(done.items()):
        ep.box(i).save_objects(per)
        if lg is not None:
            log[f"p{i} objects"] = lg.record()
        fixes = f", review: {lg.applied}" if lg is not None and lg.applied else ""
        print(f"p{i}: objects {[o['name'] + (' @ ' + o['on'] if o.get('on') else '') + (' [held]' if o.get('held') else '') + (' [front]' if o.get('front') else '') for o in per] or 'none'}{fixes}")


if __name__ == "__main__":
    main()
