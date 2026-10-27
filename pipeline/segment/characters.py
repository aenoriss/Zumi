"""Character masks with SAM 3.1 (prototype): one mask per character; a crowd meant as a mass becomes one mask.

    uv run python characters.py <episode.zumi> <out dir> --panels 3,7,12

Each panel is cut into the same square tiles as the bubble pass. Per tile, text prompts ("person", "character",
"creature") return one mask per instance, so characters that touch or overlap stay separate. Masks found twice
(two prompts, overlapping tiles) are merged when they overlap by more than half. A "crowd" prompt finds masses of
figures; instances inside a crowd mask that are small join it, so spectators become one layer while a character
standing in front of the crowd keeps its own mask.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import zipfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw
from scipy.ndimage import binary_closing, binary_fill_holes, label

from bubbles import CKPT, tiles
from sam3 import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor

# any kind of character: SAM 3 reuses one tile encoding for every prompt, so extra prompts are cheap; the reviewer
# removes what is not a character
PROMPTS = [("person", 0.45), ("character", 0.45), ("creature", 0.5), ("animal", 0.5), ("monster", 0.5), ("figure", 0.5)]
CROWD = ("group of people", 0.4)  # "crowd" scored nothing on ToG 223 p79; this prompt found the mass at 0.45-0.52
MIN_SHARE = 0.002  # masks under this share of the panel are specks
SMALL = 0.02  # an instance under this share of the panel, lying in a crowd mask, belongs to the crowd
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230),
           (210, 245, 60), (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 128)]


@dataclass
class Char:
    mask: np.ndarray
    score: float
    kind: str  # "character" or "crowd"


def tile_masks(proc: Sam3Processor, base: dict, prompt: str, thr: float, tile: Image.Image) -> list[tuple[np.ndarray, float]]:
    state = proc.set_text_prompt(prompt, base)
    out = []
    for p, s in zip(state["masks_logits"][:, 0].float().cpu().numpy(), state["scores"].float().cpu().numpy()):
        if s >= thr:
            out.append((binary_fill_holes(p > 0.5), float(s)))
    return out


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


def merge(found: list[Char], new: Char) -> None:
    for i, f in enumerate(found):
        if f.kind == new.kind and same_instance(f.mask, new.mask):
            found[i] = Char(np.logical_or(f.mask, new.mask), max(f.score, new.score), f.kind)
            return
    found.append(new)


def segment(proc: Sam3Processor, img: Image.Image) -> list[Char]:
    w, h = img.size
    chars: list[Char] = []
    crowds: list[Char] = []
    for top in tiles(h, w):
        tile = img.crop((0, top, w, min(h, top + w)))
        base = proc.set_image(tile)
        for prompt, thr in PROMPTS + [CROWD]:
            for m, s in tile_masks(proc, base, prompt, thr, tile):
                full = np.zeros((h, w), bool)
                full[top : top + m.shape[0]] = m
                if full.mean() < MIN_SHARE:
                    continue
                merge(crowds if prompt == CROWD[0] else chars, Char(full, s, "crowd" if prompt == CROWD[0] else "character"))
    # small instances inside a crowd join it; big ones (a character in front) stay individual
    keep = []
    for c in chars:
        host = next((k for k in crowds if np.logical_and(c.mask, k.mask).sum() > 0.6 * c.mask.sum()), None)
        if host is not None and c.mask.mean() < SMALL:
            host.mask |= c.mask
        else:
            keep.append(c)
    # a "group of people" made of the characters already kept is just those characters (True Beauty 7 p38: two
    # guys); a real crowd is mostly figures too small to be characters
    crowds = [k for k in crowds
              if not keep or np.logical_and(k.mask, np.logical_or.reduce([c.mask for c in keep])).sum() < 0.6 * k.mask.sum()]
    return [Char(clean(c.mask), c.score, c.kind) for c in settle(keep)] + crowds


def settle(chars: list[Char]) -> list[Char]:
    """Merge until no pair is the same instance: merge() compares each new mask once, so a mask that grows later
    can end up overlapping one kept earlier (ToG 228 p94: one figure as two masks overlapping by 92%)."""
    chars = list(chars)
    changed = True
    while changed:
        changed = False
        for a in range(len(chars)):
            for b in range(a + 1, len(chars)):
                if same_instance(chars[a].mask, chars[b].mask):
                    chars[a] = Char(chars[a].mask | chars[b].mask, max(chars[a].score, chars[b].score), chars[a].kind)
                    del chars[b]
                    changed = True
                    break
            if changed:
                break
    return chars


def clean(m: np.ndarray) -> np.ndarray:
    """Speckle and pinholes out of a character mask (ToG 228 p94, ToG 223 p48: gloved hands came out as noise):
    close small gaps, fill holes, drop specks under 0.5% of the mask."""
    m = binary_fill_holes(binary_closing(m, structure=np.ones((5, 5), bool), iterations=1) | m)
    lab, n = label(m)
    if n > 1:
        sizes = np.bincount(lab.ravel())
        m = np.isin(lab, [k for k in range(1, n + 1) if sizes[k] >= 0.005 * m.sum()])
    return m


import os

REVIEW_MODEL = os.environ.get("CHAR_REVIEW_MODEL", "anthropic/claude-haiku-5.5")
REVIEW_EFFORT = os.environ.get("CHAR_REVIEW_REASONING", "high")


def review(proc: Sam3Processor, img: Image.Image, chars: list[Char], tag: str) -> tuple[list[Char], dict, float]:
    """The reasoning layer of review_loop.py (task "characters"): fixes by mask number, carried out by SAM 3.1 and
    checked one mask at a time."""
    from review_loop import El, review as loop
    els, log = loop(proc, img, [El(c.mask, c.kind, c.score) for c in chars], "characters", REVIEW_MODEL, REVIEW_EFFORT, tag)
    return [Char(e.mask, e.score, e.kind) for e in els], {"applied": log.applied, "rejected": log.rejected}, log.cost


def confirm(proc: Sam3Processor, img: Image.Image, box) -> np.ndarray | None:
    """SAM 3.1 on a zoomed crop of the box: the largest character mask lying mostly inside it, or None."""
    x0, y0, x1, y1 = box
    pad = int(0.1 * max(x1 - x0, y1 - y0))
    w, h = img.size
    bx = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
    crop = img.crop(bx)
    s = 1008 / max(crop.size)
    big = crop.resize((max(1, round(crop.width * s)), max(1, round(crop.height * s))), Image.LANCZOS)
    canvas = Image.new("RGB", (1008, 1008), (255, 255, 255))
    canvas.paste(big, (0, 0))
    base = proc.set_image(canvas)
    best, best_s = None, 0.0
    for prompt in ("character", "person", "creature"):
        st = proc.set_text_prompt(prompt, base)
        for p, sc in zip(st["masks_logits"][:, 0].float().cpu().numpy(), st["scores"].float().cpu().numpy()):
            if sc < 0.3 or sc <= best_s:
                continue
            mm = np.asarray(Image.fromarray(p[: big.height, : big.width].astype(np.float32)).resize(crop.size, Image.BILINEAR)) > 0.5
            if mm.mean() > 0.8:  # fills the whole box: SAM marked the crop, not a figure (ToG 223 p2, p48)
                continue
            best, best_s = mm, float(sc)
    if best is None or best.sum() < 200:
        return None
    full = np.zeros((h, w), bool)
    full[bx[1]:bx[3], bx[0]:bx[2]] = binary_fill_holes(best)
    return full


def overlay(img: Image.Image, chars: list[Char]) -> Image.Image:
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
    ap.add_argument("--review", action="store_true", help="Maverick review pass; saves before | after")
    a = ap.parse_args()
    proc = Sam3Processor(build_sam3_image_model(checkpoint_path=str(CKPT), load_from_HF=False), confidence_threshold=0.3)
    z = zipfile.ZipFile(a.zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    a.out.mkdir(parents=True, exist_ok=True)
    for i in [int(x) for x in a.panels.split(",")]:
        img = Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
        t = time.perf_counter()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            chars = segment(proc, img)
            verdict, cost = {}, 0.0
            if a.review:
                before = overlay(img, chars)
                chars, verdict, cost = review(proc, img, chars, f"{a.zumi.stem} p{i} chars")
        after = overlay(img, chars)
        if a.review:
            both = Image.new("RGB", (img.width * 2 + 20, img.height), (255, 255, 255))
            both.paste(before, (0, 0)); both.paste(after, (img.width + 20, 0))
            after = both
        after.save(a.out / f"{a.zumi.stem}-p{i:03d}.png")
        n = sum(c.kind == "character" for c in chars)
        print(f"panel {i:3d}: {n} characters, {len(chars) - n} crowds, {time.perf_counter() - t:.2f}s"
              + (f", review {json.dumps(verdict)}, {cost * 100:.2f} c" if a.review else ""))


if __name__ == "__main__":
    main()
