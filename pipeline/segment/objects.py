"""Masks for the big objects scene_judge.choose_objects picked, by SAM 3.1: for each {"name", "point": [x, y]} the box is
prompted with the name (square tiles, as characters.py) and the mask that contains the point, best score first, is kept.
The point is the model's way of saying "this one": text prompts alone also returned floors and walls.

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

from masks import Found, save_masks
from sam import THRESHOLD, Segmenter, tiles

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


def masks_for_objects(seg: Segmenter, img: Image.Image, objs: list[dict], log=print, _retry: bool = True) -> tuple[np.ndarray, list[dict]]:
    """(union of the objects' masks, [{"name", "point", "mask", "score"} per object found]). An object whose point
    lies in no mask of its name (or within NEAR_PX of one) is left out."""
    img = img.convert("RGB")
    w, h = img.size
    union = np.zeros((h, w), bool)
    if not objs:
        return union, []
    found = [[] for _ in objs]  # (inside, distance, score, mask) per candidate
    for top in tiles(h, w):
        tile = img.crop((0, top, w, min(h, top + w)))
        todo = [k for k, o in enumerate(objs) if top <= o["point"][1] < top + tile.height]
        if not todo:
            continue
        # every instance SAM returns (its floor, sam.THRESHOLD): the point decides, not the score
        for k, hits in zip(todo, seg.instances(tile, [(sam_name(objs[k]["name"]), THRESHOLD) for k in todo])):
            x, y = (int(round(v)) for v in objs[k]["point"])
            x, y = min(max(x, 0), w - 1), min(max(y, 0), h - 1)
            for m, s in hits:
                if m[y - top, x]:
                    d = 0.0
                else:
                    r0, r1 = max(0, y - top - NEAR_PX), y - top + NEAR_PX + 1
                    c0, c1 = max(0, x - NEAR_PX), x + NEAR_PX + 1
                    win = m[r0:r1, c0:c1]
                    if not win.any():
                        continue
                    d = float(distance_transform_edt(~win)[y - top - r0, x - c0])
                    if d > NEAR_PX:
                        continue
                full = np.zeros((h, w), bool)
                full[top:top + m.shape[0]] = m
                found[k].append((d == 0, -d, s, full))
    # a name SAM finds nothing for at the point gets other names, in order: the head noun alone ("bar counter" ->
    # "counter"), then SYNONYMS of it (P&C 39 p1: no mask for "broom", the brooms found as "broomstick" at 0.62)
    for _ in range(MAX_ALT if _retry else 0):
        retry = [o for o, c in zip(objs, found) if not c and o.get("_alts", alt_names(o["name"]))]
        if not retry:
            break
        for o in retry:
            o.setdefault("_alts", alt_names(o["name"]))
        alt = [{**o, "name": o["_alts"].pop(0)} for o in retry]
        _, again = masks_for_objects(seg, img, alt, log=lambda s: None, _retry=False)
        for o, a in zip(retry, alt):
            hit = next((g for g in again if g["name"] == a["name"] and g["point"] == o["point"]), None)
            if hit:
                found[objs.index(o)] = [(True, 0.0, hit["score"], hit["mask"])]
                log(f"  {o['name']}: found as '{a['name']}'")
    for o in objs:
        o.pop("_alts", None)
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
        union |= m
        log(f"  {o['name']}: score {s:.2f}, {m.mean() * 100:.1f}% of the box" + ("" if inside else f", point {-nd:.0f} px off"))
    return union, out


def main():
    img = Image.open(sys.argv[1]).convert("RGB")
    objs = json.loads(Path(sys.argv[2]).read_text())
    _, per = masks_for_objects(Segmenter(), img, objs)
    save_masks(Path(sys.argv[3]), [Found(p["mask"], p["score"], "object", p["name"]) for p in per])


if __name__ == "__main__":
    main()
