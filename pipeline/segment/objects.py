"""Masks for the big objects scene_judge.choose_objects picked, by SAM 3.1: for each {"name", "point": [x, y]} the box is
prompted with the name (square tiles, as characters.py) and the mask that contains the point, best score first, is kept.
The point is the model's way of saying "this one": text prompts alone also returned floors and walls.

    per = masks_for_objects(seg, img, picked)     [{"name", "point", "mask", "score", and the relations}]
    per = reviewed(review's masks, per)           the same after the review: names and relations carried through
    python objects.py <image.png> <objects.json> <out.npz>   (masks.save_masks: kind "object", the name kept)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt

from boxstore import OBJECT_META_KEYS
from masks import Found, save_masks
from sam import THRESHOLD, Segmenter

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


if __name__ == "__main__":
    main()
