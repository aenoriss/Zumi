"""Steps 4-5 on a fixed set of ~16 boxes that cover the hard cases, instead of a whole episode (~0.65 USD of FLUX
Erase and ~10 min per run). One contact sheet per run: box | erase masks | layer 1 | layer 2.

    uv run python testset.py <run name> [--no-layers]

Masks come from the held-out test (reviewed, .data/out/heldout/{tog228,tb4}) or from an episode.py run on the boxes
that had none (.data/out/testset/masks_run/<episode>/masks). Writes .data/out/testset/<run>/ (viewer layout under
parallax/, plates/, sheet.png, run.json).
"""
from __future__ import annotations

import io
import json
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

import depth as DP
import parallax as PX
from hidden_layers import build_plain, erase_boxes, finish, prepare
from masks import load_masks

DATA = Path(__file__).resolve().parents[1] / ".data"
CHAPTERS = DATA / "out" / "chapters"
HELDOUT = DATA / "out" / "heldout"
RUN_MASKS = DATA / "out" / "testset" / "masks_run"

# (episode, box, what it tests)
BOXES = [
    ("tower-of-god-s3-228", 6, "objects behind a character (two layers), caption boxes"),
    ("tower-of-god-s3-228", 7, "character fills the frame, bubbles into the gutter"),
    ("tower-of-god-s3-228", 8, "small figures on a large ground"),
    ("tower-of-god-s3-228", 9, "two characters, dark background, object touching"),
    ("tower-of-god-s3-228", 10, "close-up, bubbles over the art"),
    ("true-beauty-4", 5, "everyday scene, other artist"),
    ("true-beauty-4", 15, "everyday scene, other artist"),
    ("true-beauty-4", 25, "everyday scene, other artist"),
    ("true-beauty-4", 35, "everyday scene, other artist"),
    ("tower-of-god-s3-228", 64, "two frames in one box"),
    ("tower-of-god-s3-223", 46, "several frames in one box"),
    ("tower-of-god-s3-223", 94, "grey page, several frames"),
    ("tower-of-god-s3-223", 98, "grey page, two frames"),
    ("true-beauty-5", 43, "product shots without frame borders"),
    ("pepper-carrot-39", 6, "page comic, several frames per box (CC BY 4.0)"),
    ("pepper-carrot-39", 8, "page comic, several frames per box (CC BY 4.0)"),
]


def masks_for(ep: str, i: int, shape) -> tuple[np.ndarray, np.ndarray] | None:
    pid = f"{ep}-p{i:03d}"
    short = {"tower-of-god-s3-228": "tog228", "true-beauty-4": "tb4"}.get(ep)
    cands = []
    if short:
        cands.append((HELDOUT / short / "characters_rev" / f"{pid}.npz", HELDOUT / short / "lettering_rev" / f"{pid}.npz"))
    cands.append((RUN_MASKS / ep / "masks" / f"{pid}-characters.npz", RUN_MASKS / ep / "masks" / f"{pid}-lettering.npz"))
    for c, l in cands:
        if c.exists() and l.exists():
            u = lambda els: np.logical_or.reduce([e.mask for e in els]) if els else np.zeros(shape, bool)
            return u(load_masks(c)), u(load_masks(l))
    return None


def main() -> None:
    run = sys.argv[1]
    out = DATA / "out" / "testset" / run
    root = out / "parallax"
    t0 = time.perf_counter()
    lines = []
    log = lambda s: (print(s), lines.append(s))
    zips = {}
    imgs, figs = {}, {}
    for ep, i, why in BOXES:
        z = zips.setdefault(ep, zipfile.ZipFile(CHAPTERS / f"{ep}.zumi"))
        panels = json.loads(z.read("manifest.json"))["panels"]
        img = Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
        m = masks_for(ep, i, (img.height, img.width))
        if m is None:
            log(f"{ep} p{i}: no masks, skipped")
            continue
        imgs[(ep, i)], figs[(ep, i)] = img, m
    # the pipeline's order: lettering first (erase), then depth on the lettering-free base image
    boxes = {}
    if "--no-layers" not in sys.argv:
        for (ep, i), img in imgs.items():
            pid = f"{ep}-p{i:03d}"
            b = prepare(pid, img, *figs[(ep, i)], out / "plates" / pid, log=log)
            if b:
                boxes[(ep, i)] = b
    crops = erase_boxes(list(boxes.values()), log=log) if boxes else {}
    mono, metric = DP.load(), DP.load(DP.METRIC_ID)
    for (ep, i), img in imgs.items():
        pid = f"{ep}-p{i:03d}"
        if (ep, i) in boxes and pid in crops:
            finish(boxes[(ep, i)], crops[pid], mono, metric, root, log=lambda s: lines.append(s))
        else:
            build_plain(pid, img, *figs[(ep, i)], mono, metric, root, log=lambda s: lines.append(s))
    log(f"{time.perf_counter() - t0:.0f} s: done")
    # contact sheet: one row per box, all at the same height
    H, rows = 520, []
    for (ep, i), img in imgs.items():
        pid = f"{ep}-p{i:03d}"
        d = out / "plates" / pid
        cells = [img] + [Image.open(d / n) for n in ("base.png", "plate-full.png") if (d / n).exists()]
        cells = [c.convert("RGB").resize((max(1, int(c.width * H / c.height)), H)) for c in cells]
        row = Image.new("RGB", (sum(c.width + 8 for c in cells) + 8, H + 26), "white")
        x = 8
        for c in cells:
            row.paste(c, (x, 26))
            x += c.width + 8
        why = next(w for e, k, w in BOXES if (e, k) == (ep, i))
        ImageDraw.Draw(row).text((8, 6), f"{ep} p{i}: {why}   |   box | base (no lettering) | hidden layer", fill=(0, 0, 0))
        rows.append(row)
    cols = 2
    W = max(r.width for r in rows)
    sheet = Image.new("RGB", (W * cols, ((len(rows) + cols - 1) // cols) * (H + 34)), "white")
    for k, r in enumerate(rows):
        sheet.paste(r, ((k % cols) * W, (k // cols) * (H + 34)))
    sheet.save(out / "sheet.png")
    (out / "run.json").write_text(json.dumps({"boxes": [f"{e}-p{k:03d}" for e, k in imgs], "log": lines}, indent=1))


if __name__ == "__main__":
    main()
