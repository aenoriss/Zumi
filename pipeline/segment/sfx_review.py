"""Sound-effect review loop: a vision LLM checks each sound-effect mask, SAM 3.1 re-segments what it says is missing.

For each sound-effect mask the model sees two copies of a generous crop around it: plain, and with this mask
tinted magenta (other masks of the panel cyan). It answers whether the magenta region is sound-effect lettering,
whether every letter of that effect is covered, and boxes around uncovered letters. Missing letters are
re-segmented by SAM 3.1 on a zoomed crop of each box (the letters fill SAM's input, so thin strokes survive) and
the result is reviewed once more. A mask that is not lettering, or still incomplete after the retry, is dropped:
an effect left whole in the art beats a half-erased word.
"""

from __future__ import annotations

import json
import re

import numpy as np
from PIL import Image

from openrouter import chat, image_part

MODEL = "meta-llama/llama-4-maverick"
SIDE = 1008  # SAM 3 input side
ZOOM_PAD = 16  # px around a box before zooming
CONTEXT = 1.0  # crop grows by this share of the mask's box on each side...
MIN_CONTEXT = 160  # ...and at least this many px, so a word whose mask holds one letter is still in view
MAGENTA, CYAN = np.array([255, 0, 220]), np.array([0, 200, 255])

PROMPT = """Image: the same comic crop twice. LEFT is the plain art. RIGHT marks pixels that will be erased: MAGENTA is the sound effect under review, CYAN are other elements already handled (ignore them).

Answer about the MAGENTA element only:
1. "lettering": true if the magenta region is sound-effect lettering (onomatopoeia such as BANG, WHOOSH, AAAH), false if it is mostly art (hair, clothing, faces, background) or not lettering.
2. "complete": true if every letter of that sound effect is magenta. A sound effect is one word or one run of repeated letters; letters of the same word that are not magenta make it incomplete, even when only part of a letter is missing. Separate, unrelated sound effects elsewhere do not count.
3. "missing": if incomplete, one box per uncovered group of letters of that same sound effect, as [x0, y0, x1, y1] in percent of the LEFT image (0 = left/top, 100 = right/bottom), generous rather than tight. Empty list if complete.

Reply with JSON only: {"lettering": true, "complete": true, "missing": []}"""


def context_box(m: np.ndarray) -> tuple[int, int, int, int]:
    h, w = m.shape
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    gy = max(MIN_CONTEXT, int(CONTEXT * (y1 - y0)))
    gx = max(MIN_CONTEXT, int(CONTEXT * (x1 - x0)))
    return max(0, x0 - gx), max(0, y0 - gy), min(w, x1 + gx), min(h, y1 + gy)


def review_image(pixels: np.ndarray, m: np.ndarray, others: list[np.ndarray], box) -> Image.Image:
    x0, y0, x1, y1 = box
    crop = pixels[y0:y1, x0:x1]
    marked = crop.astype(np.float32).copy()
    for o in others:
        oo = o[y0:y1, x0:x1]
        marked[oo] = marked[oo] * 0.45 + CYAN * 0.55
    mm = m[y0:y1, x0:x1]
    marked[mm] = marked[mm] * 0.4 + MAGENTA * 0.6
    gap = 12
    out = Image.new("RGB", (crop.shape[1] * 2 + gap, crop.shape[0]), (255, 255, 255))
    out.paste(Image.fromarray(crop), (0, 0))
    out.paste(Image.fromarray(marked.astype(np.uint8)), (crop.shape[1] + gap, 0))
    return out


def parse(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        raise ValueError(text[:200])
    d = json.loads(m.group(0))
    return {"lettering": bool(d.get("lettering", True)), "complete": bool(d.get("complete", True)),
            "missing": [b for b in d.get("missing", []) if isinstance(b, list) and len(b) == 4]}


def ask(img: Image.Image, tag: str) -> tuple[dict, float]:
    content = [{"type": "text", "text": PROMPT}, image_part(img, max_side=1024, quality=88)]
    text, usage = chat(MODEL, [{"role": "user", "content": content}], max_tokens=300, tag=tag, reasoning=None)
    return parse(text), float(usage.get("cost", 0) or 0)


def zoom(proc, img: Image.Image, box, region: np.ndarray, prompts=("letters",), thr: float = 0.45) -> np.ndarray:
    """SAM 3.1 on a crop of `box` enlarged to fill its input; masks kept where they lie mostly in `region`."""
    x0, y0, x1, y1 = box
    crop = img.crop(box)
    s = SIDE / max(crop.size)
    big = crop.resize((max(1, round(crop.width * s)), max(1, round(crop.height * s))), Image.LANCZOS)
    canvas = Image.new("RGB", (SIDE, SIDE), (255, 255, 255))
    canvas.paste(big, (0, 0))
    base = proc.set_image(canvas)
    keep = np.zeros(region.shape, bool)
    for prompt in prompts:
        state = proc.set_text_prompt(prompt, base)
        for p in state["masks_logits"][:, 0].float().cpu().numpy():
            # downsample the probabilities, then threshold: smooth edges, thin strokes survive
            mm = np.asarray(Image.fromarray(p[: big.height, : big.width].astype(np.float32)).resize(crop.size, Image.BILINEAR)) > thr
            if mm.sum() and (mm & region).sum() >= 0.7 * mm.sum():
                keep |= mm
    return keep & region


def resegment(proc, img: Image.Image, m: np.ndarray, boxes_px: list) -> np.ndarray:
    h, w = m.shape
    out = m.copy()
    for bx0, by0, bx1, by1 in boxes_px:
        bx = (max(0, bx0 - ZOOM_PAD), max(0, by0 - ZOOM_PAD), min(w, bx1 + ZOOM_PAD), min(h, by1 + ZOOM_PAD))
        if bx[2] - bx[0] < 4 or bx[3] - bx[1] < 4:
            continue
        region = np.ones((bx[3] - bx[1], bx[2] - bx[0]), bool)
        out[bx[1]:bx[3], bx[0]:bx[2]] |= zoom(proc, img, bx, region)
    return out


def to_px(b, box) -> tuple[int, int, int, int]:
    """Percent box in the LEFT image -> panel pixels."""
    x0, y0, x1, y1 = box
    W, H = x1 - x0, y1 - y0
    p = [min(100.0, max(0.0, float(v))) for v in b]
    return (x0 + int(p[0] / 100 * W), y0 + int(p[1] / 100 * H), x0 + int(np.ceil(p[2] / 100 * W)), y0 + int(np.ceil(p[3] / 100 * H)))


def review(proc, img: Image.Image, m: np.ndarray, others: list[np.ndarray], tag: str, retries: int = 1) -> tuple[np.ndarray | None, str, float]:
    """(mask or None if dropped, outcome, cost in USD)."""
    pixels = np.asarray(img)
    cost = 0.0
    for attempt in range(retries + 1):
        box = context_box(m)
        verdict, c = ask(review_image(pixels, m, others, box), f"{tag} try{attempt}")
        cost += c
        if not verdict["lettering"]:
            return None, "dropped-not-lettering", cost
        if verdict["complete"] or not verdict["missing"]:
            return m, ("ok" if attempt == 0 else "resegmented"), cost
        if attempt == retries:
            return None, "dropped-incomplete", cost
        grown = resegment(proc, img, m, [to_px(b, box) for b in verdict["missing"]])
        if grown.sum() <= m.sum() * 1.02:  # SAM found nothing new where the model pointed
            return None, "dropped-incomplete", cost
        m = grown
    return m, "resegmented", cost
