"""Lettering masks with SAM 3.1 (step 2a): speech bubbles, caption boxes, confident sound effects.

    uv run python bubbles.py <episode.zumi> <out dir> [--panels 3,7,12]   (masks saved as an episode run's, boxstore)

Dialogue is always masked: the reader redraws bubbles and captions as live text, so they are erased and the art
behind them inpainted. A sound effect is masked only when its segmentation is confident; otherwise it stays
part of the art (decided 2026-10-19). Confident = score >= 0.5, mask stability >= 0.75 (share of the pixels
SAM 3 is unsure about, probability 0.3-0.7 band edges, that are clearly in: above 0.7), and a lettering shape.
Measured on 368 sound-effect hits from 12 panels labelled by eye: clean letters had stability 0.76-0.95;
letters mixed with a crowd of small figures (Tower of God 223 p81) had 0.17-0.58 and scores under 0.4.

SAM 3 resizes every input to a 1008 x 1008 square, so a tall panel is cut into square tiles (side = panel
width, 25 % overlap). Each tile gets:
- text passes at full resolution: "speech bubble" (round and shaped bubbles), "caption box";
- exemplar passes (SAM 3 concept mode): the tile shrunk to 756 px with example crops from other panels in a
  margin, each marked as a positive box, so SAM 3 finds everything that looks like them. Examples come from a
  hand-picked bank (`.data/exemplars/bank.json`), never from the panel being segmented. The two dialogue groups
  share one canvas; each sound-effect group has its own (LAYOUT). A tile's images (the tile and its canvases) are
  encoded in one batch and each text prompt is encoded once: 7.34 -> 6.08 s per panel on 12 test panels, same
  masks (52 of 53 at IoU >= 0.8, 1 at 0.5-0.8). Tile by tile, not the whole panel at once: every encoded image
  holds 108 MB of GPU memory until its passes are done, and a 15-tile webtoon box (Omniscient Reader 0, 800 x
  8754) held 60 of them, filling the 12 GB and 18.8 GB of commit.

Masks of the same kind that overlap by more than half are one object seen twice (overlapping tiles); different
kinds merge only when near-identical, so a sound effect crossing a caption box stays a separate mask (Tower of
God 223 p4). A "bubble" inside a caption card is the card's text block; letters inside a bubble or caption are
its dialogue; both are dropped. A sound effect's letters are grouped into one mask per word.

Measured: "speech bubble" finds round bubbles at 0.95+ and black bursts at 0.35; "caption box" finds light
captions (0.78) but not black cards (0.14-0.24); card exemplars find a missed black card at 0.98.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_fill_holes, label

from boxstore import Box
from chapter import Chapter
from masks import Found, top_order
from sam import SIDE as CANVAS, Segmenter, tiles
from shape import dialogue_like, letter_shaped
from textcrops import clean_crop

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / ".data/exemplars/bank.json"
TILE = 756  # the tile's side inside an exemplar canvas (CANVAS, SAM's input side)
# Exemplar canvases: (groups sharing one canvas, margin cell side, examples per group). A 252 px cell gives 7
# margin cells, a 126 px cell 28. Dialogue examples keep their hits at 126 px; sound-effect examples lost hits
# on busy art when shrunk to 126 px (Tower of God 223 p79: GMHHH and AKREEE missed), so they keep full cells.
LAYOUT = [(("card", "burst"), 126, 7), (("sfx",), 252, 7), (("sfx_outline",), 252, 7)]
KIND_COLOUR = {"bubble": (255, 70, 70), "caption": (60, 140, 255), "sfx": (255, 0, 220)}
KIND_RANK = {"bubble": 2, "caption": 2, "sfx": 1}  # same shape found as two kinds: the container wins
DIALOGUE = ("bubble", "caption")
MAX_INSIDE = 0.6  # a bubble mostly inside a caption card is the card's text block
MAX_SFX_INSIDE = 0.9  # letters almost wholly inside a bubble are its dialogue; letters crossing its edge are their
#                       own element (True Beauty 5 p71 "DAMN IT!" over the burst)


@dataclass(frozen=True)
class Pass:
    prompt: str  # text prompt; with exemplars it names the concept the examples share
    min_score: float
    kind: str
    exemplars: str | None = None  # bank group, or None for a plain text pass
    min_stability: float = 0.0


PASSES = [
    Pass("speech bubble", 0.30, "bubble"),
    Pass("caption box", 0.5, "caption"),
    Pass("caption box", 0.5, "caption", exemplars="card"),
    Pass("speech bubble", 0.3, "bubble", exemplars="burst"),  # the black "!" splat in ToG 228 p89 scored 0.30
    Pass("letters", 0.5, "sfx", exemplars="sfx", min_stability=0.7),  # "DAMN IT!" 0.74; crowd blotches <= 0.58
    Pass("letters", 0.5, "sfx", exemplars="sfx_outline", min_stability=0.7),  # white letters, dark outline
]


def window(*fs: Found, pad: int = 0) -> tuple[slice, slice] | None:
    """The overlap of the masks' boxes (grown by pad), or None when the boxes do not touch."""
    y0 = max(f.bbox()[0] for f in fs) - pad
    y1 = min(f.bbox()[1] for f in fs) + pad
    x0 = max(f.bbox()[2] for f in fs) - pad
    x1 = min(f.bbox()[3] for f in fs) + pad
    if y0 >= y1 or x0 >= x1:
        return None
    return slice(max(0, y0), y1), slice(max(0, x0), x1)


def area(f: Found) -> int:
    y0, y1, x0, x1 = f.bbox()
    return int(f.mask[y0:y1, x0:x1].sum())


class Bank:
    """Example crops by group, loaded from the .zumi files they were picked from."""

    def __init__(self, path: Path, episodes: Path):
        spec = json.loads(path.read_text())
        self.crops: dict[str, list[tuple[str, int, Image.Image]]] = {}
        for group, items in spec.items():
            if group.startswith("_"):
                continue
            for ep, panel, box in items:
                crop = Chapter(episodes / f"{ep}.zumi").image(panel).crop(box)
                self.crops.setdefault(group, []).append((ep, panel, crop))

    def pick(self, group: str, episode: str, panel: int, n: int = 7) -> list[Image.Image]:
        return [c for ep, p, c in self.crops.get(group, []) if (ep, p) != (episode, panel)][:n]


def margin_cells(cell: int) -> list[tuple[int, int]]:
    """Top-left corners of the cell x cell squares in the canvas margin (right strip, then bottom strip)."""
    right = [(x, y) for y in range(0, CANVAS - cell + 1, cell) for x in range(TILE, CANVAS - cell + 1, cell)]
    bottom = [(x, y) for y in range(TILE, CANVAS - cell + 1, cell) for x in range(0, TILE - cell + 1, cell)]
    return right + bottom


def composite(tile: Image.Image, groups: dict[str, list[Image.Image]], cell: int) -> tuple[Image.Image, dict[str, list[list[float]]]]:
    """Tile at TILE px top-left; the groups' examples share the margin in cell x cell squares.
    Returns the canvas and, per group, its example boxes as normalised cx, cy, w, h."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
    canvas.paste(tile.resize((TILE, TILE)), (0, 0))
    cells = iter(margin_cells(cell))
    boxes: dict[str, list[list[float]]] = {}
    for group, examples in groups.items():
        for crop, (cx, cy) in zip(examples, cells):
            crop = crop.copy()
            crop.thumbnail((cell - 6, cell - 6))
            ox, oy = cx + (cell - crop.width) // 2, cy + (cell - crop.height) // 2
            canvas.paste(crop, (ox, oy))
            boxes.setdefault(group, []).append(
                [(ox + crop.width / 2) / CANVAS, (oy + crop.height / 2) / CANVAS, crop.width / CANVAS, crop.height / CANVAS])
    return canvas, boxes


def stability(prob: np.ndarray) -> float:
    """Share of the pixels above 0.3 that are also above 0.7: 1 for a crisp mask, low for a hesitant one."""
    return float((prob > 0.7).sum() / max(1, (prob > 0.3).sum()))


def run_pass(seg: Segmenter, state: dict, tile: Image.Image, ps: Pass, boxes: list[list[float]] | None) -> list[tuple[np.ndarray, float]]:
    """(tile-size mask, score) for one pass on one tile. `state` holds the encoded tile (text passes) or the
    encoded canvas (exemplar passes, with this group's example boxes)."""
    if ps.exemplars is not None and not boxes:
        return []
    crop = None if ps.exemplars is None else TILE
    probs, scores = seg.ground(state, ps.prompt, boxes if ps.exemplars is not None else None)  # sigmoid probabilities
    out = []
    for p, s in zip(probs, scores):
        if s < ps.min_score:
            continue
        m = p > 0.5
        if crop:
            if m[:crop, :crop].sum() <= 0.9 * m.sum():  # an example in the margin, not the tile
                continue
            p = p[:crop, :crop]
            m = np.asarray(Image.fromarray(m[:crop, :crop]).resize(tile.size, Image.NEAREST))
        if ps.min_stability and stability(p) < ps.min_stability:
            continue
        m = binary_fill_holes(m)
        if ps.kind == "sfx" and not letter_shaped(m):
            continue
        if ps.kind in DIALOGUE and not dialogue_like(np.asarray(tile), m, ps.kind, float(s)):
            continue
        out.append((m, float(s)))
    return out


def add(found: list[Found], new: Found) -> None:
    b = area(new)
    for i, f in enumerate(found):
        win = window(f, new)
        if win is None:
            continue
        inter = np.logical_and(f.mask[win], new.mask[win]).sum()
        if not inter:
            continue
        a = area(f)
        same_object = f.kind == new.kind and inter / min(a, b) > 0.5
        same_shape = inter / (a + b - inter) > 0.7
        if same_object or same_shape:
            kind = max((f, new), key=lambda x: (KIND_RANK[x.kind], x.score)).kind
            found[i] = Found(np.logical_or(f.mask, new.mask), max(f.score, new.score), kind)
            return
    found.append(new)


def drop_inner_text(found: list[Found]) -> list[Found]:
    """Drop masks lying mostly inside a container: a bubble inside a caption card is the card's text block,
    letters inside a bubble or caption are its dialogue."""
    def inside(f: Found, kinds: tuple[str, ...], share: float) -> bool:
        cs = [g for g in found if g.kind in kinds and g is not f and window(f, g) is not None]
        if not cs:
            return False
        y0, y1, x0, x1 = f.bbox()
        cover = np.logical_or.reduce([g.mask[y0:y1, x0:x1] for g in cs])
        return np.logical_and(f.mask[y0:y1, x0:x1], cover).sum() > share * area(f)

    return [
        f for f in found
        if not (f.kind == "bubble" and inside(f, ("caption",), MAX_INSIDE) or f.kind == "sfx" and inside(f, DIALOGUE, MAX_SFX_INSIDE))
    ]


def group_letters(found: list[Found], reach: int) -> list[Found]:
    """Letters of one sound effect become one mask: sfx masks within `reach` px of each other join."""
    sfx = [f for f in found if f.kind == "sfx"]
    if len(sfx) < 2:
        return found
    h, w = sfx[0].mask.shape
    # dilate within the letters' joint box (plus the reach), not over the whole panel
    y0 = max(0, min(f.bbox()[0] for f in sfx) - reach)
    y1 = min(h, max(f.bbox()[1] for f in sfx) + reach)
    x0 = max(0, min(f.bbox()[2] for f in sfx) - reach)
    x1 = min(w, max(f.bbox()[3] for f in sfx) + reach)
    crops = [f.mask[y0:y1, x0:x1] for f in sfx]
    words, n = label(binary_dilation(np.logical_or.reduce(crops), iterations=reach))
    # a mask whose letters lie far apart touches two words; words sharing a mask are one word, so each mask ends up
    # in exactly one group (ToG 223 p79: 6 masks came out as 9, six of them duplicates)
    parent = list(range(n + 1))

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    labels = [set(np.unique(words[c])) - {0} for c in crops]
    for ls in labels:
        ls = sorted(ls)
        for a in ls[1:]:
            parent[find(a)] = find(ls[0])
    groups: dict[int, list[Found]] = {}
    for f, ls in zip(sfx, labels):
        if ls:
            groups.setdefault(find(min(ls)), []).append(f)
    grouped = [Found(np.logical_or.reduce([f.mask for f in g]), max(f.score for f in g), "sfx") for g in groups.values()]
    return [f for f in found if f.kind != "sfx"] + grouped


def segment(seg: Segmenter, img: Image.Image, bank: Bank, episode: str, panel: int) -> list[Found]:
    w, h = img.size
    tops = tiles(h, w)
    layout = [(names, cell, {g: bank.pick(g, episode, panel, n) for g in names}) for names, cell, n in LAYOUT]
    found: list[Found] = []
    for top in tops:
        tile = img.crop((0, top, w, min(h, top + w)))
        # the tile, then one canvas per layout entry: one encoder batch, freed before the next tile
        images, where = [tile], {}  # where[group] = (image index, example boxes)
        for names, cell, groups in layout:
            canvas, boxes = composite(tile, groups, cell)
            for g in names:
                where[g] = (len(images), boxes.get(g))
            images.append(canvas)
        states = seg.encode(images)
        for ps in PASSES:
            if ps.exemplars is None:
                hits = run_pass(seg, states[0], tile, ps, None)
            else:
                i, boxes = where[ps.exemplars]
                hits = run_pass(seg, states[i], tile, ps, boxes)
            for m, s in hits:
                full = np.zeros((h, w), bool)
                full[top : top + m.shape[0]] = m
                add(found, Found(full, s, ps.kind))
        del states
    return group_letters(drop_inner_text(found), reach=max(8, w // 40))


def overlay(img: Image.Image, found: list[Found]) -> Image.Image:
    base = np.asarray(img.convert("RGB")).astype(np.float32)
    for f in found:
        base[f.mask] = base[f.mask] * 0.45 + np.array(KIND_COLOUR[f.kind]) * 0.55
    out = Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(out)
    for f in found:
        ys, xs = np.nonzero(f.mask)
        d.rectangle([(xs.min(), ys.min()), (xs.max(), ys.max())], outline=KIND_COLOUR[f.kind], width=3)
        d.text((xs.min() + 4, ys.min() + 2), f"{f.kind} {f.score:.2f}", fill=(0, 0, 0))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", default="")
    a = ap.parse_args()

    t0 = time.perf_counter()
    seg = Segmenter(min(p.min_score for p in PASSES))
    bank = Bank(BANK, a.zumi.parent)
    print(f"model and bank loaded in {time.perf_counter() - t0:.1f}s")

    ch = Chapter(a.zumi)
    pick = [int(i) for i in a.panels.split(",") if i] or list(range(len(ch)))
    a.out.mkdir(parents=True, exist_ok=True)
    for i in pick:
        img = ch.image(i)
        t = time.perf_counter()
        found = segment(seg, img, bank, ch.stem, i)
        overlay(img, found).save(a.out / f"{ch.pid(i)}.png")
        Box(a.out, ch.pid(i)).save_letters(found)
        pixels = np.asarray(img)
        dialogue = top_order([f for f in found if f.kind in DIALOGUE])  # text crops are for reading dialogue
        for k, f in enumerate(dialogue):
            if (crop := clean_crop(pixels, f.mask)) is not None:
                (a.out / "text").mkdir(exist_ok=True)
                crop.save(a.out / "text" / f"{ch.pid(i)}-{k:02d}-{f.kind}.png")
        kinds = {k: sum(f.kind == k for f in found) for k in ("bubble", "caption", "sfx")}
        print(f"panel {i:3d} {img.width}x{img.height}: {kinds}, {time.perf_counter() - t:.2f}s")


if __name__ == "__main__":
    main()
