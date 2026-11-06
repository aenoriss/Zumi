"""Character masks with SAM 3.1: one mask per character; a crowd meant as a mass becomes one mask.

    uv run python characters.py <episode.zumi> <out dir> --panels 3,7,12

Each panel is cut into the same square tiles as the bubble pass. Per tile, text prompts ("person", "character",
"creature") return one mask per instance, so characters that touch or overlap stay separate. Masks found twice
(two prompts, overlapping tiles) are merged when they overlap by more than half. A "crowd" prompt finds masses of
figures; instances inside a crowd mask that are small join it, so spectators become one layer while a character
standing in front of the crowd keeps its own mask.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt, label

from chapter import Chapter
from masks import COLOURS, PART_MIN, SMALL, Found, clean
from sam import Segmenter

# any kind of character: SAM 3 reuses one tile encoding for every prompt, so extra prompts are cheap; the reviewer
# removes what is not a character
PROMPTS = [("person", 0.45), ("character", 0.45), ("creature", 0.5), ("animal", 0.5), ("monster", 0.5), ("figure", 0.5)]
CROWD = ("group of people", 0.4)  # "crowd" scored nothing on ToG 223 p79; this prompt found the mass at 0.45-0.52
MIN_SHARE = 0.002  # masks under this share of the panel are specks
CROWD_MARGIN = 4  # px around each character taken out of a crowd mask (exclusive): its outline goes with it
SPECK_PX_MAX, SPECK_SHARE, SPECK_PX = 400, 0.8, 8  # a mask's piece of at most this many px, mostly within SPECK_PX of
                                                    # another mask, is that one's edge pixels (exclusive)


def same_instance(a: np.ndarray, b: np.ndarray) -> bool:
    """Two prompts on one tile: overlap by more than half. Two tiles: one figure cut at the seam lines up in the
    rows both masks occupy (ToG 223 p48: head in one tile, suit in the next), two figures side by side do not."""
    inter = np.logical_and(a, b).sum()
    if not inter:
        return False
    if inter / min(a.sum(), b.sum()) > 0.5:
        return True
    rows = a.any(axis=1) & b.any(axis=1)
    if rows.sum() < 20:
        return False
    aa, bb = a[rows], b[rows]
    return np.logical_and(aa, bb).sum() / np.logical_or(aa, bb).sum() >= 0.5


def merge(found: list[Found], new: Found) -> None:
    for i, f in enumerate(found):
        if f.kind == new.kind and same_instance(f.mask, new.mask):
            found[i] = Found(np.logical_or(f.mask, new.mask), max(f.score, new.score), f.kind)
            return
    found.append(new)


def segment(seg: Segmenter, img: Image.Image) -> list[Found]:
    """Kind "character" or "crowd"."""
    chars: list[Found] = []
    crowds: list[Found] = []
    crowd = len(PROMPTS)
    for k, full, s in seg.find(img, PROMPTS + [CROWD]):
        if full.mean() < MIN_SHARE:
            continue
        merge(crowds if k == crowd else chars, Found(full, s, "crowd" if k == crowd else "character"))
    # small instances inside a crowd join it; big ones (a character in front) stay individual
    keep = []
    for c in chars:
        host = next((j for j, k in enumerate(crowds) if np.logical_and(c.mask, k.mask).sum() > 0.6 * c.mask.sum()), None)
        if host is not None and c.mask.mean() < SMALL:
            crowds[host] = Found(crowds[host].mask | c.mask, crowds[host].score, crowds[host].kind)
        else:
            keep.append(c)
    # a "group of people" made of the characters already kept is just those characters (True Beauty 7 p38: two
    # guys); a real crowd is mostly figures too small to be characters
    crowds = [k for k in crowds
              if not keep or np.logical_and(k.mask, np.logical_or.reduce([c.mask for c in keep])).sum() < 0.6 * k.mask.sum()]
    return [Found(clean(c.mask), c.score, c.kind) for c in settle(keep)] + crowds


def settle(chars: list[Found]) -> list[Found]:
    """Merge until no pair is the same instance: merge() compares each new mask once, so a mask that grows later
    can end up overlapping one kept earlier (ToG 228 p94: one figure as two masks overlapping by 92%)."""
    chars = list(chars)
    changed = True
    while changed:
        changed = False
        for a in range(len(chars)):
            for b in range(a + 1, len(chars)):
                if same_instance(chars[a].mask, chars[b].mask):
                    chars[a] = Found(chars[a].mask | chars[b].mask, max(chars[a].score, chars[b].score), chars[a].kind)
                    del chars[b]
                    changed = True
                    break
            if changed:
                break
    return chars


def exclusive(found: list[Found]) -> list[Found]:
    """The box's character masks with every pixel on one mask only, as the layers will cut them, without the leftovers
    that cutting makes (run after the review, which can add overlaps):
    1. a crowd loses every character masked on its own, grown CROWD_MARGIN px so their outlines go too;
    2. two masks that share pixels: the smaller keeps them (cards.exclusive's rule);
    3. every speck of a mask (a piece of at most SPECK_PX_MAX px) with SPECK_SHARE of it within SPECK_PX of another
       mask goes to the mask it lies nearest: a mask's specks along another's outline are that one's edge pixels. A
       figure cut into a few big pieces by what stands in front of it keeps them (P&C 37-p006).
    P&C 36-p025: the crowd mask also held the two girls in front; its piece in their frame, cut by their own masks,
    was 91 specks along their outlines (the largest 192 px), a card that grouped with one girl and won a tail aimed at
    the other."""
    chars = [f for f in found if f.kind != "crowd"]
    crowds = [f for f in found if f.kind == "crowd"]
    if chars and crowds:
        taken = binary_dilation(np.logical_or.reduce([c.mask for c in chars]), iterations=CROWD_MARGIN)
        crowds = [Found(c.mask & ~taken, c.score, c.kind, c.name) for c in crowds]
    out = chars + crowds
    if not out:
        return out
    masks, claimed = [None] * len(out), np.zeros_like(out[0].mask)
    for k in sorted(range(len(out)), key=lambda k: int(out[k].mask.sum())):
        masks[k] = out[k].mask & ~claimed
        claimed |= masks[k]
    for i in range(len(masks)):
        lab, n = label(masks[i])
        if n < 2:
            continue
        sizes = np.bincount(lab.ravel())
        owner = np.zeros(masks[i].shape, np.int32)
        for j, o in enumerate(masks):
            if j != i and o.any():
                owner[o] = j + 1
        if not owner.any():
            continue
        d, (iy, ix) = distance_transform_edt(owner == 0, return_indices=True)
        near = owner[iy, ix]
        for p in range(1, n + 1):
            if sizes[p] > SPECK_PX_MAX:
                continue
            piece = lab == p
            if (piece & (d <= SPECK_PX)).sum() >= SPECK_SHARE * sizes[p]:
                masks[int(np.bincount(near[piece]).argmax()) - 1] |= piece
                masks[i] &= ~piece
    # what is left too small for a card goes (the layers keep a piece of at least cards.PART_MIN px); segmentation's
    # MIN_SHARE is no floor here: on a 1200 x 3649 credits page it is 8,700 px, more than a mascot
    return [Found(m, f.score, f.kind, f.name) for f, m in zip(out, masks) if m.sum() >= PART_MIN]


def overlay(img: Image.Image, chars: list[Found]) -> Image.Image:
    base = np.asarray(img).astype(np.float32)
    for k, c in enumerate(chars):
        col = np.array((150, 150, 150) if c.kind == "crowd" else COLOURS[k % len(COLOURS)])
        base[c.mask] = base[c.mask] * 0.45 + col * 0.55
    out = Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(out)
    for k, c in enumerate(chars):
        ys, xs = np.nonzero(c.mask)
        col = (90, 90, 90) if c.kind == "crowd" else COLOURS[k % len(COLOURS)]
        d.rectangle([(xs.min(), ys.min()), (xs.max(), ys.max())], outline=col, width=3)
        d.rectangle([(xs.min(), ys.min()), (xs.min() + 110, ys.min() + 20)], fill=col)
        d.text((xs.min() + 4, ys.min() + 4), f"{'crowd' if c.kind == 'crowd' else f'char {k + 1}'} {c.score:.2f}", fill=(255, 255, 255))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", required=True)
    a = ap.parse_args()
    seg = Segmenter()
    ch = Chapter(a.zumi)
    a.out.mkdir(parents=True, exist_ok=True)
    for i in [int(x) for x in a.panels.split(",")]:
        img = ch.image(i)
        t = time.perf_counter()
        chars = segment(seg, img)
        overlay(img, chars).save(a.out / f"{ch.pid(i)}.png")
        n = sum(c.kind == "character" for c in chars)
        print(f"panel {i:3d}: {n} characters, {len(chars) - n} crowds, {time.perf_counter() - t:.2f}s")


if __name__ == "__main__":
    main()
