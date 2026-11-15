"""Google's image model Nano Banana 2 through the Gemini API (the interactions endpoint), the one module that calls
it: a prompt and reference images in, one image out.

edit()  gemini-3.1-flash-image, the model Google's docs name Nano Banana 2 (aistudio.google.com/docs/image-generation,
where ai.google.dev now redirects, read 2026-11-12; the same page lists a newer Nano Banana 2.1,
gemini-nano-banana-2.1, with the same sizes). The first image is the one being edited; up to REFS images in all. The
output's shape is one of the model's fixed aspect ratios (SIZES) at 1K, 2K or 4K: there is no free width and height,
and no seed, so a call made again does not give the same image. The reply is a JPEG: the endpoint refuses PNG
(HTTP 400, 2026-11-12). Priced per output image by size (PRICE, the pricing
page read the same day), plus the tokens of what is sent and of the model's thinking, counted when the reply gives
its usage. Every call goes through the shared daily cap (spend.reserve) and the gemini ledger. The key is
GEMINI_API_KEY in pipeline/.env, never printed.

    nearest(width, height) -> "2:3"            the model's aspect ratio closest to a shape
    size_for(aspect, width) -> "4K"            the smallest size at least that wide, or the largest
    edit(prompt, images, aspect, size, tag) -> (image, usd)
"""
from __future__ import annotations

import base64
import io
import json
import math
import time
import urllib.error
import urllib.request

from PIL import Image

from lyria import API, REVISION, _key
from spend import no_call_offline, payment_refused, record, reserve

NANO = "gemini-3.1-flash-image"
REFS = 14         # images one call takes, the edited one included ("up to 14 reference images")
SIZES = {"1:1": (1024, 1024), "1:4": (512, 2048), "1:8": (384, 3072), "2:3": (848, 1264), "3:2": (1264, 848),
         "3:4": (896, 1200), "4:1": (2048, 512), "4:3": (1200, 896), "4:5": (928, 1152), "5:4": (1152, 928),
         "8:1": (3072, 384), "9:16": (768, 1376), "16:9": (1376, 768), "21:9": (1584, 672)}  # pixels at 1K
TIMES = {"1K": 1, "2K": 2, "4K": 4}                  # each size's pixels over 1K's, per side
PRICE = {"1K": 0.067, "2K": 0.101, "4K": 0.151}      # USD per output image
INPUT_USD, THOUGHT_USD = 0.50e-6, 3.00e-6            # per token sent, and per token of text or thinking in the reply
MARGIN_USD = 0.03  # reserved over the image's price for those tokens: a 4K page and its sheets are a few thousand
JPEG = 92          # quality of the images sent


def nearest(width: int, height: int) -> str:
    """The model's aspect ratio closest to width:height (by the ratio of the two shapes, so 2:1 off is as far as
    1:2 off)."""
    return min(SIZES, key=lambda a: abs(math.log((width / height) / (SIZES[a][0] / SIZES[a][1]))))


def size_for(aspect: str, width: int) -> str:
    """The smallest size whose image of that aspect is at least `width` wide, so nothing sent is made smaller; the
    largest when none is."""
    return next((s for s, k in TIMES.items() if SIZES[aspect][0] * k >= width), "4K")


def _usage_usd(usage: dict) -> float:
    """What the reply's usage adds to the image's price: the tokens sent, and the reply's tokens that are not the
    image (its thinking and any text)."""
    image = sum(m.get("tokens", 0) for m in usage.get("output_tokens_by_modality") or [] if m.get("modality") == "image")
    rest = max(0, (usage.get("total_output_tokens") or 0) - image)  # the first page's reply: 3193 out, 2520 the image
    return (usage.get("total_input_tokens") or 0) * INPUT_USD + rest * THOUGHT_USD


def edit(prompt: str, images: list[Image.Image], aspect: str, size: str = "1K",
         tag: str = "Nano Banana 2") -> tuple[Image.Image, float]:
    """One image from the prompt and up to REFS images, the first the one being edited: (the image, as large as
    SIZES and TIMES say for `aspect` and `size`; its cost in USD). Raises BudgetExceeded before sending if the cap
    would break."""
    no_call_offline(tag)
    parts = [{"type": "text", "text": prompt}]
    for im in images[:REFS]:
        b = io.BytesIO()
        im.convert("RGB").save(b, format="JPEG", quality=JPEG)
        parts.append({"type": "image", "mime_type": "image/jpeg", "data": base64.b64encode(b.getvalue()).decode()})
    body = {"model": NANO, "input": parts,
            "response_format": {"type": "image", "mime_type": "image/jpeg", "aspect_ratio": aspect, "image_size": size}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Api-Revision": REVISION,
                                          "x-goog-api-key": _key()})
    with reserve(PRICE[size] + MARGIN_USD, tag):
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    resp = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                detail = e.read()[:400].decode(errors="replace")
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(10 * (attempt + 1))
                    continue
                payment_refused("gemini", e.code, detail)
                raise RuntimeError(f"Nano Banana 2: HTTP {e.code} {detail}") from None
        found = [c["data"] for s in resp.get("steps", []) if s.get("type") == "model_output"
                 for c in s.get("content", []) if c.get("type") == "image" and c.get("data")]
        usage = resp.get("usage") or {}
        usd = (PRICE[size] if found else 0.0) + _usage_usd(usage)
        record("gemini", usd, model=NANO, tag=tag, call="image", size=size, aspect=aspect, usage=usage)
    if not found:
        raise RuntimeError(f"Nano Banana 2: no image in the reply ({json.dumps(resp)[:300]})")
    return Image.open(io.BytesIO(base64.b64decode(found[-1]))).convert("RGB"), usd
