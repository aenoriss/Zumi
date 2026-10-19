"""Dialogue masks with SAM 3.1 (stage 2b, local GPU test): speech bubbles and caption boxes.

    uv run python bubbles.py <episode.zumi> <out dir> [--panels 3,7,12]

Only dialogue is masked: the reader redraws bubbles and captions as live text, so they are erased and the art
behind them inpainted. Sound effects drawn on the art stay part of the art (decided 2026-10-19).

SAM 3 resizes every input to a 1008 x 1008 square, so a tall panel is cut into square tiles (side = panel
width, 25 % overlap). Each tile gets:
- text passes at full resolution: "speech bubble" (round and shaped bubbles), "caption box";
- exemplar passes (SAM 3 concept mode): the tile shrunk to 756 px with example crops from other panels in a
  margin, each marked as a positive box, so SAM 3 finds everything that looks like them. Examples come from a
  hand-picked bank (`.data/exemplars/bank.json`), never from the panel being segmented.

Masks of the same kind that overlap by more than half are one object seen twice (overlapping tiles); a bubble
and a caption merge only when near-identical, so overlapping dialogue elements stay separate masks. A "bubble"
lying inside a caption card is that card's text block and is dropped.

Measured: "speech bubble" finds round bubbles at 0.95+ and black bursts at 0.35; "caption box" finds light
captions (0.78) but not black cards (0.14-0.24); card exemplars find a missed black card at 0.98.
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
from scipy.ndimage import binary_fill_holes

from sam3 import build_sam3_image_model
from sam3.model.sam3_image_processor import Sam3Processor

ROOT = Path(__file__).resolve().parent.parent
CKPT = ROOT / ".models/sam3/official/sam3.1_multiplex.pt"
BANK = ROOT / ".data/exemplars/bank.json"
CANVAS, TILE = 1008, 756  # composite side, tile side inside it; the margin holds up to 7 examples
KIND_COLOUR = {"bubble": (255, 70, 70), "caption": (60, 140, 255)}
MAX_INSIDE = 0.6  # a bubble mostly inside a caption card is the card's text block


@dataclass(frozen=True)
class Pass:
    prompt: str  # text prompt; with exemplars it names the concept the examples share
    min_score: float
    kind: str
    exemplars: str | None = None  # bank group, or None for a plain text pass


PASSES = [
    Pass("speech bubble", 0.30, "bubble"),
    Pass("caption box", 0.5, "caption"),
    Pass("caption box", 0.5, "caption", exemplars="card"),
    Pass("speech bubble", 0.4, "bubble", exemplars="burst"),
]


@dataclass
class Found:
    mask: np.ndarray  # full panel size, bool
    score: float
    kind: str


def tiles(h: int, w: int, overlap: float = 0.25) -> list[int]:
    """Top rows of square tiles covering a panel of height h and width w."""
    if h <= w:
        return [0]
    step = max(1, int(w * (1 - overlap)))
    return sorted(set(list(range(0, h - w, step)) + [h - w]))


class Bank:
    """Example crops by group, loaded from the .zumi files they were picked from."""

    def __init__(self, path: Path, episodes: Path):
        spec = json.loads(path.read_text())
        self.crops: dict[str, list[tuple[str, int, Image.Image]]] = {}
        for group, items in spec.items():
            if group.startswith("_"):
                continue
            for ep, panel, box in items:
                z = zipfile.ZipFile(episodes / f"{ep}.zumi")
                image = json.loads(z.read("manifest.json"))["panels"][panel]["layers"][0]["image"]
                crop = Image.open(io.BytesIO(z.read(image))).convert("RGB").crop(box)
                self.crops.setdefault(group, []).append((ep, panel, crop))

    def pick(self, group: str, episode: str, panel: int, n: int = 7) -> list[Image.Image]:
        return [c for ep, p, c in self.crops.get(group, []) if (ep, p) != (episode, panel)][:n]


def composite(tile: Image.Image, examples: list[Image.Image]) -> tuple[Image.Image, list[list[float]]]:
    """Tile at TILE px top-left, examples centred in the margin cells; boxes as normalised cx, cy, w, h."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
    canvas.paste(tile.resize((TILE, TILE)), (0, 0))
    m = CANVAS - TILE
    cells = [(TILE, y) for y in range(0, CANVAS, m)] + [(x, TILE) for x in range(0, TILE, m)]
    boxes = []
    for (cx, cy), crop in zip(cells, examples):
        crop = crop.copy()
        crop.thumbnail((m - 8, m - 8))
        ox, oy = cx + (m - crop.width) // 2, cy + (m - crop.height) // 2
        canvas.paste(crop, (ox, oy))
        boxes.append([(ox + crop.width / 2) / CANVAS, (oy + crop.height / 2) / CANVAS, crop.width / CANVAS, crop.height / CANVAS])
    return canvas, boxes


def run_pass(proc: Sam3Processor, tile: Image.Image, ps: Pass, examples: list[Image.Image], cache: dict) -> list[tuple[np.ndarray, float]]:
    """(tile-size mask, score) for one pass on one tile."""
    if ps.exemplars is None:
        if "plain" not in cache:
            cache["plain"] = proc.set_image(tile)  # one backbone pass shared by the text passes
        state = proc.set_text_prompt(ps.prompt, cache["plain"])
        masks, scores, crop = state["masks"][:, 0].cpu().numpy(), state["scores"].float().cpu().numpy(), None
    else:
        if not examples:
            return []
        canvas, boxes = composite(tile, examples)
        state = proc.set_image(canvas)
        state["backbone_out"].update(proc.model.backbone.forward_text([ps.prompt], device=proc.device))
        state["geometric_prompt"] = proc.model._get_dummy_prompt()
        # all example boxes in one call: add_geometric_prompt reruns the detection head once per box
        b = torch.tensor(boxes, device=proc.device, dtype=torch.float32).view(-1, 1, 4)
        state["geometric_prompt"].append_boxes(b, torch.ones((len(boxes), 1), device=proc.device, dtype=torch.bool))
        state = proc._forward_grounding(state)
        masks, scores, crop = state["masks"][:, 0].cpu().numpy(), state["scores"].float().cpu().numpy(), TILE
    out = []
    for m, s in zip(masks, scores):
        if s < ps.min_score:
            continue
        if crop:
            if m[:crop, :crop].sum() <= 0.9 * m.sum():  # an example in the margin, not the tile
                continue
            m = np.asarray(Image.fromarray(m[:crop, :crop]).resize(tile.size, Image.NEAREST))
        out.append((binary_fill_holes(m), float(s)))
    return out


def add(found: list[Found], new: Found) -> None:
    for i, f in enumerate(found):
        inter = np.logical_and(f.mask, new.mask).sum()
        if not inter:
            continue
        a, b = f.mask.sum(), new.mask.sum()
        same_object = f.kind == new.kind and inter / min(a, b) > 0.5
        same_shape = inter / (a + b - inter) > 0.7
        if same_object or same_shape:
            kind = f.kind if f.score >= new.score else new.kind
            found[i] = Found(np.logical_or(f.mask, new.mask), max(f.score, new.score), kind)
            return
    found.append(new)


def drop_card_text(found: list[Found]) -> list[Found]:
    cards = [f.mask for f in found if f.kind == "caption"]
    if not cards:
        return found
    inside = np.logical_or.reduce(cards)
    return [f for f in found if f.kind != "bubble" or np.logical_and(f.mask, inside).sum() <= MAX_INSIDE * f.mask.sum()]


def segment(proc: Sam3Processor, img: Image.Image, bank: Bank, episode: str, panel: int) -> list[Found]:
    w, h = img.size
    found: list[Found] = []
    for top in tiles(h, w):
        tile = img.crop((0, top, w, min(h, top + w)))
        cache: dict = {}
        for ps in PASSES:
            examples = bank.pick(ps.exemplars, episode, panel) if ps.exemplars else []
            for m, s in run_pass(proc, tile, ps, examples, cache):
                full = np.zeros((h, w), bool)
                full[top : top + m.shape[0]] = m
                add(found, Found(full, s, ps.kind))
    return drop_card_text(found)


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
    model = build_sam3_image_model(checkpoint_path=str(CKPT), load_from_HF=False)
    proc = Sam3Processor(model, confidence_threshold=min(p.min_score for p in PASSES))
    bank = Bank(BANK, a.zumi.parent)
    print(f"model and bank loaded in {time.perf_counter() - t0:.1f}s")

    z = zipfile.ZipFile(a.zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    pick = [int(i) for i in a.panels.split(",") if i] or list(range(len(panels)))
    a.out.mkdir(parents=True, exist_ok=True)
    for i in pick:
        img = Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
        t = time.perf_counter()
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):  # mixed precision, as in Meta's examples
            found = segment(proc, img, bank, a.zumi.stem, i)
        overlay(img, found).save(a.out / f"{a.zumi.stem}-p{i:03d}.png")
        kinds = {k: sum(f.kind == k for f in found) for k in KIND_COLOUR}
        print(f"panel {i:3d} {img.width}x{img.height}: {kinds}, {time.perf_counter() - t:.2f}s")
    print(f"peak VRAM {torch.cuda.max_memory_allocated() / 1e9:.1f} GB")


if __name__ == "__main__":
    main()
