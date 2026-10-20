"""Magiv3 test run: text extraction and character identification on a few boxes (research use).

    uv run --group magi python magi_run.py <episode.zumi> <out dir> --panels 1,2 [--stack 14-16]

Magiv3 (Sachdeva & Zisserman, ICCV 2025; personal/research/non-commercial licence) squashes every input to
768 x 768. It was trained on manga pages (about 1:1.4), so tall webtoon boxes get white side margins to that
shape and boxes are mapped back. Per image it returns panel, text, character and tail boxes, character
clusters (same person within the image), text-to-character links, a dialogue/non-dialogue flag per text, and
OCR with its own regions. A --stack joins consecutive boxes into one image so clusters can link a character
across them.
"""

from __future__ import annotations

import argparse
import io
import json
import time
import zipfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFont
from transformers import AutoModelForCausalLM, AutoProcessor

MODEL = Path(__file__).resolve().parent.parent / ".models/magiv3"
MAX_ASPECT = 1.45  # height / width of a manga page, roughly
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (0, 160, 160), (240, 50, 230), (128, 128, 0)]


def pad(img: Image.Image) -> tuple[Image.Image, int]:
    """White side margins so height / width <= MAX_ASPECT; returns the image and the left offset."""
    w, h = img.size
    if h <= MAX_ASPECT * w:
        return img, 0
    nw = int(round(h / MAX_ASPECT))
    out = Image.new("RGB", (nw, h), (255, 255, 255))
    left = (nw - w) // 2
    out.paste(img, (left, 0))
    return out, left


def unpad(box: list[float], left: int) -> list[float]:
    return [box[0] - left, box[1], box[2] - left, box[3]]


def render(img: Image.Image, det: dict, ocr: dict, title: str) -> Image.Image:
    im = img.convert("RGB").copy()
    d = ImageDraw.Draw(im)
    f = ImageFont.load_default(size=max(14, img.width // 40))
    labels = det["character_cluster_labels"]
    for k, (b, lab) in enumerate(zip(det["characters"], labels)):
        c = COLOURS[lab % len(COLOURS)]
        d.rectangle(b, outline=c, width=4)
        d.text((b[0] + 4, b[1] + 2), f"C{lab}", fill=c, font=f, stroke_width=2, stroke_fill=(255, 255, 255))
    speaker = {t: c for t, c in det["text_character_associations"]}
    for t, b in enumerate(det["texts"]):
        essential = det["is_essential_text"][t] if t < len(det["is_essential_text"]) else False
        d.rectangle(b, outline=(0, 0, 0) if essential else (150, 150, 150), width=3)
        d.text((b[0] + 3, b[1] + 2), f"T{t}", fill=(0, 0, 0), font=f, stroke_width=2, stroke_fill=(255, 255, 0))
        if t in speaker and speaker[t] < len(det["characters"]):
            cb = det["characters"][speaker[t]]
            lab = labels[speaker[t]]
            d.line([((b[0] + b[2]) / 2, (b[1] + b[3]) / 2), ((cb[0] + cb[2]) / 2, (cb[1] + cb[3]) / 2)], fill=COLOURS[lab % len(COLOURS)], width=4)
    for b in det["tails"]:
        d.rectangle(b, outline=(255, 0, 255), width=2)
    lines = [title, ""]
    for t, b in enumerate(det["texts"]):
        sp = f"C{labels[speaker[t]]}" if t in speaker and speaker[t] < len(labels) else "-"
        ess = "dialogue" if t < len(det["is_essential_text"]) and det["is_essential_text"][t] else "non-dialogue"
        lines.append(f"T{t} -> {sp}  ({ess})")
    lines += ["", "OCR:"] + [f"  {t.strip()[:60]}" for t in ocr["ocr_texts"]]
    panel = 560
    s = min(1.0, 1100 / im.height)
    im = im.resize((int(im.width * s), int(im.height * s)))
    out = Image.new("RGB", (im.width + panel, max(im.height, 22 * len(lines) + 20)), (255, 255, 255))
    out.paste(im, (0, 0))
    dd = ImageDraw.Draw(out)
    for k, line in enumerate(lines):
        dd.text((im.width + 10, 10 + 22 * k), line, fill=(0, 0, 0), font=ImageFont.load_default(size=16))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", default="")
    ap.add_argument("--stack", default="", help="first-last, consecutive boxes joined into one image")
    a = ap.parse_args()

    t0 = time.perf_counter()
    model = AutoModelForCausalLM.from_pretrained(str(MODEL), torch_dtype=torch.float16, trust_remote_code=True).cuda().eval()
    processor = AutoProcessor.from_pretrained(str(MODEL), trust_remote_code=True)
    print(f"loaded in {time.perf_counter() - t0:.1f}s, VRAM {torch.cuda.memory_allocated() / 1e9:.1f} GB")

    z = zipfile.ZipFile(a.zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    load = lambda i: Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
    jobs = [(f"p{int(i):03d}", load(int(i))) for i in a.panels.split(",") if i]
    if a.stack:
        lo, hi = (int(x) for x in a.stack.split("-"))
        parts = [load(i) for i in range(lo, hi + 1)]
        strip = Image.new("RGB", (max(p.width for p in parts), sum(p.height + 40 for p in parts)), (255, 255, 255))
        y = 0
        for p in parts:
            strip.paste(p, (0, y))
            y += p.height + 40
        jobs.append((f"stack{lo:03d}-{hi:03d}", strip))

    a.out.mkdir(parents=True, exist_ok=True)
    results = {}
    for name, img in jobs:
        padded, left = pad(img)
        t = time.perf_counter()
        with torch.no_grad():
            det = model.predict_detections_and_associations([padded], processor)[0]
            ocr = model.predict_ocr([padded], processor)[0]
        dt = time.perf_counter() - t
        for key in ("panels", "texts", "characters", "tails"):
            det[key] = [unpad(b, left) for b in det[key]]
        ocr["bboxes"] = [unpad(b, left) for b in ocr["bboxes"]]
        results[name] = {"detections": det, "ocr": ocr, "seconds": round(dt, 2)}
        render(img, det, ocr, f"Magiv3 {a.zumi.stem} {name}").save(a.out / f"{a.zumi.stem}-{name}.png")
        print(f"{name}: {len(det['texts'])} texts, {len(det['characters'])} characters in "
              f"{len(set(det['character_cluster_labels']))} clusters, {len(det['text_character_associations'])} speaker links, "
              f"{len(ocr['ocr_texts'])} OCR lines, {dt:.1f}s")
    (a.out / f"{a.zumi.stem}.json").write_text(json.dumps(results, indent=1, default=float, ensure_ascii=False))
    print(f"peak VRAM {torch.cuda.max_memory_allocated() / 1e9:.1f} GB")


if __name__ == "__main__":
    main()
