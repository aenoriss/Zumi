"""Magiv3 on superframes: consecutive boxes laid out as a manga page, versus one box at a time (research use).

    uv run --group magi python magi_superframe.py

For each labelled run of consecutive boxes: windows of WINDOW boxes, overlapping by WINDOW - STRIDE, laid out
in two columns at manga-page shape (first box in the right column for "rtl", the left for "ltr"). Magiv3 returns
character boxes, same-person scores and text-to-character scores (probabilities); everything is mapped back to
box coordinates. Characters in the boxes two windows share are matched by overlap, which chains clusters into
one identity per run. Each labelled element gets the text boxes whose centre lies in its mask and their best
speaker score. Reported: share of lines linked at Magi's 0.8 cut-off and with the top-score fallback, and
speaker accuracy after mapping each identity to the labelled speaker it most often has.
"""

from __future__ import annotations

import io
import json
import time
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from torch.nn.utils.rnn import pad_sequence
from transformers import AutoModelForCausalLM, AutoProcessor

from bubbles import load_masks
from magi_run import MODEL, pad

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".data/out/magi/superframe"
LABELS = json.loads((ROOT / ".data/out/understand/labels.json").read_text(encoding="utf-8"))
RUNS = {
    "true-beauty-5": [[0, 1, 2], [14, 15, 16, 17, 18], [29, 30, 31, 32], [55, 56, 57, 58], [71]],
    "tower-of-god-s3-228": [[6, 7, 8, 9, 10, 11], [40, 41, 42, 43, 44], [86, 87], [89, 90], [100, 101, 102, 103, 104, 105]],
}
WINDOW, STRIDE, COL_W, GAP = 4, 2, 700, 40
CUT = 0.8
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (0, 160, 160), (240, 50, 230), (128, 128, 0)]


def windows(run: list[int], size: int) -> list[list[int]]:
    if size == 1:
        return [[i] for i in run]
    if len(run) <= size:
        return [run]
    starts = list(range(0, len(run) - size + 1, STRIDE))
    if starts[-1] != len(run) - size:
        starts.append(len(run) - size)
    return [run[s : s + size] for s in starts]


def layout(images: list[Image.Image], order: str) -> tuple[Image.Image, list[tuple[float, int, int]]]:
    """Two columns, filled in reading order until the first holds about half the height.
    Returns the page and, per box, (scale, x, y) of its placement."""
    scaled = [im.resize((COL_W, round(im.height * COL_W / im.width))) for im in images]
    if len(scaled) == 1:
        return scaled[0], [(COL_W / images[0].width, 0, 0)]
    total = sum(s.height + GAP for s in scaled)
    cols, acc = [[], []], 0
    for k, s in enumerate(scaled):
        target = 0 if acc < total / 2 or not cols[0] else 1
        cols[target].append(k)
        acc += s.height + GAP if target == 0 else 0
    if not cols[1]:
        cols[1].append(cols[0].pop())
    first_x = COL_W + GAP if order == "rtl" else 0
    second_x = 0 if order == "rtl" else COL_W + GAP
    h = max(sum(scaled[k].height + GAP for k in c) for c in cols)
    page = Image.new("RGB", (2 * COL_W + GAP, h), (255, 255, 255))
    place = [None] * len(scaled)
    for col, x in ((cols[0], first_x), (cols[1], second_x)):
        y = 0
        for k in col:
            page.paste(scaled[k], (x, y))
            place[k] = (COL_W / images[k].width, x, y)
            y += scaled[k].height + GAP
    return page, place


def detect(model, processor, img: Image.Image) -> dict:
    """predict_detections_and_associations, keeping the score matrices instead of thresholding them."""
    padded, left = pad(img)
    batch = processor(
        batch_input_text=["Find all panels, texts, characters, and speech-bubble tails in the image."],
        batch_input_list_of_list_of_bboxes=[[]], batch_images=[padded], padding=True, truncation=True,
        max_input_length_including_image_tokens=1024, max_output_length=1024, return_tensors="pt",
        dtype=model.dtype, device=model.device,
    )
    gen = model.generate(input_ids=batch["input_ids"], pixel_values=batch["pixel_values"], max_new_tokens=1024, do_sample=False, num_beams=3)
    texts, boxes, idx = processor.postprocess_output(gen, [padded])
    cat = {"<pa": "panels", "<te": "texts", "<ch": "characters", "<ta": "tails"}
    out = {"panels": [], "texts": [], "characters": [], "tails": []}
    for (i, j), bb in zip(idx[0], boxes[0]):
        c = cat.get(texts[0][j : j + 3])
        if c:
            out[c].extend([[b[0] - left, b[1], b[2] - left, b[3]] for b in bb])
    g = gen[0]
    g = g[torch.where(g == processor.tokenizer.bos_token_id)[0][-1].item() :]
    assoc = model(input_ids=batch["input_ids"], pixel_values=batch["pixel_values"],
                  decoder_input_ids=pad_sequence([g], batch_first=True, padding_value=processor.tokenizer.pad_token_id),
                  tokenizer=processor.tokenizer)
    out["cc"] = assoc.character_character_affinity_matrices[0].float().cpu().numpy()
    out["tc"] = assoc.text_character_association_matrices[0].float().cpu().numpy()
    return out


def centre(b):
    return (b[0] + b[2]) / 2, (b[1] + b[3]) / 2


def iou(a, b):
    ix = max(0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    return inter / max(1e-6, (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        self.p[self.find(a)] = self.find(b)


def run_mode(model, processor, ep: str, size: int, order: str, panels: list, z) -> list[dict]:
    """One record per labelled kept element: kind, label speaker, best link score, linked identity."""
    load = lambda i: Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
    records = []
    for run in RUNS[ep]:
        uf = UF()
        per_box = defaultdict(list)  # box -> [(window id, char idx, box-local char box)]
        texts_in_box = defaultdict(list)  # box -> [(local text box, best score, (window id, char idx))]
        for w_id, win in enumerate(windows(run, size)):
            imgs = [load(i) for i in win]
            page, place = layout(imgs, order)
            det = detect(model, processor, page)
            # which box each detection centre falls in, and box-local coordinates
            def to_box(b):
                cx, cy = centre(b)
                for k, (s, x, y) in enumerate(place):
                    if x <= cx < x + COL_W and y <= cy < y + imgs[k].height * s:
                        return win[k], [(b[0] - x) / s, (b[1] - y) / s, (b[2] - x) / s, (b[3] - y) / s]
                return None, None
            chars = [to_box(b) for b in det["characters"]]
            n = len(chars)
            for a in range(n):
                uf.find((w_id, a))
                for b in range(a + 1, n):
                    if det["cc"][a, b] > 0.5:  # Magi's same-person cut-off
                        uf.union((w_id, a), (w_id, b))
            for k, (box, local) in enumerate(chars):
                if box is not None:
                    per_box[box].append((w_id, k, local))
            for t, b in enumerate(det["texts"]):
                box, local = to_box(b)
                if box is None:
                    continue
                if n:
                    c = int(np.argmax(det["tc"][t])) if det["tc"].shape[1] else None
                    score = float(det["tc"][t, c]) if c is not None else 0.0
                else:
                    c, score = None, 0.0
                texts_in_box[box].append((local, score, (w_id, c) if c is not None else None))
            if size > 1:
                page.save(OUT / f"{ep}-{order}-{win[0]:03d}-{win[-1]:03d}.png")
        # the same character seen by two windows (same box, overlapping boxes) is one identity
        for box, items in per_box.items():
            for i in range(len(items)):
                for j in range(i + 1, len(items)):
                    if items[i][0] != items[j][0] and iou(items[i][2], items[j][2]) > 0.5:
                        uf.union(items[i][:2], items[j][:2])
        for box in run:
            masks = load_masks(ROOT / f".data/out/understand/seg2/masks/{ep}-p{box:03d}.npz")
            for e, lab in LABELS[ep]["panels"].get(str(box), {}).items():
                if not lab["keep"]:
                    continue
                f = masks[int(e) - 1]
                best = (0.0, None)
                for local, score, who in texts_in_box.get(box, []):
                    cx, cy = centre(local)
                    if 0 <= int(cy) < f.mask.shape[0] and 0 <= int(cx) < f.mask.shape[1] and f.mask[int(cy), int(cx)] and score > best[0]:
                        best = (score, who)
                ident = f"{run[0]}:{uf.find(best[1])}" if best[1] is not None else None
                records.append({"box": box, "el": e, "kind": "sfx" if f.kind == "sfx" else "dialogue",
                                "label": lab["speaker"], "score": best[0], "ident": ident})
    return records


def summarise(records: list[dict], cut: float) -> str:
    dia = [r for r in records if r["kind"] == "dialogue"]
    linked = [r for r in dia if r["ident"] and r["score"] >= cut]
    scored = [r for r in linked if r["label"] != "?"]
    votes = defaultdict(Counter)
    for r in scored:
        votes[r["ident"]][r["label"]] += 1
    mapping = {k: v.most_common(1)[0][0] for k, v in votes.items()}
    right = sum(mapping[r["ident"]] == r["label"] for r in scored)
    idents = len({r["ident"] for r in linked})
    return f"linked {len(linked)}/{len(dia)} ({len(linked) / len(dia):.0%}), speaker right {right}/{len(scored)}, {idents} identities"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    model = AutoModelForCausalLM.from_pretrained(str(MODEL), torch_dtype=torch.float16, trust_remote_code=True).cuda().eval()
    processor = AutoProcessor.from_pretrained(str(MODEL), trust_remote_code=True)
    report = {}
    for size, order in ((1, "single"), (WINDOW, "rtl"), (WINDOW, "ltr")):
        t = time.perf_counter()
        allrec = []
        for ep in RUNS:
            z = zipfile.ZipFile(ROOT / ".data/out/chapters" / f"{ep}.zumi")
            panels = json.loads(z.read("manifest.json"))["panels"]
            with torch.no_grad():
                rec = run_mode(model, processor, ep, size, order, panels, z)
            for r in rec:
                r["ep"] = ep
            allrec += rec
        report[order] = allrec
        print(f"{order:6s} cut 0.8: {summarise(allrec, CUT)} | top-score: {summarise(allrec, 0.0)} | {time.perf_counter() - t:.0f}s")
    (OUT / "records.json").write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
