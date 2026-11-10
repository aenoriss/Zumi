"""Black Forest Labs, the one module that talks to its API: FLUX Erase (the erase step's model, and the places' gap
fill) and FLUX 3 Image (the places' wide views). BFL_API_KEY in pipeline/.env, never printed. Every call reserves its
worst case under the shared daily cap (spend.py) and raises BudgetExceeded before sending if it could pass it; its
credits go into .data/spend/bfl.jsonl (1 credit = 0.01 USD). A job id is returned at once and polled until a final
status: FLUX 3 passes through Pending, Reasoning, Processing.

    flux_erase(image, mask, dilate) -> (image, seconds, credits)       image + binary mask in, no prompt
    flux2(prompt, images, width, height, model, tag, seed) -> (image, credits)
    flux3(prompt, images, aspect_ratio, resolution, tag) -> (image, credits)
"""
from __future__ import annotations

import base64
import functools
import io
import os
import time
from pathlib import Path

import requests
from PIL import Image

from spend import record, reserve

ROOT = Path(__file__).resolve().parents[1]  # pipeline/
API = "https://api.bfl.ai/v1"
ERASE_RESERVE_USD = 0.06  # per erase: the most one has cost (5.8 credits)
FLUX3_RESERVE_USD = {"1.5k": 0.10, "2k": 0.25, "4k": 0.70}  # per FLUX 3 image by resolution, measured 2026-11-08:
                          # 7 credits at 1.5k (every call that day), 60.7 at 4k; 2k untested, reserved between
FLUX2_RESERVE_USD = 0.10  # per FLUX.2 image at ~1 MP (pro: 0.03 + 0.015 per MP, bfl.ai/pricing as read 2026-11-07)
DILATE = 8                # px the erase API grows the mask by itself (dilate_pixels)
MAX_TRIES = 6             # on HTTP 429 (more than 24 requests in flight, docs.bfl.ai integration guidelines; or one
                          # task at a time while the credit balance is low, 2026-11-08): back off
FAILED = ("Error", "Failed", "Content Moderated", "Request Moderated")


@functools.lru_cache(maxsize=1)
def key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("BFL_API_KEY="):
            return line.split("=", 1)[1].strip()
    return os.environ["BFL_API_KEY"]


def b64(im: Image.Image, fmt: str = "PNG") -> str:
    b = io.BytesIO()
    im.save(b, format=fmt, **({"quality": 92} if fmt == "JPEG" else {}))
    return base64.b64encode(b.getvalue()).decode()


def _run(path: str, body: dict, timeout_s: float, what: str) -> tuple[Image.Image, float | None, float]:
    """POST a job, poll it to a final status: (the image, its credits, seconds)."""
    h = {"x-key": key(), "accept": "application/json"}
    for k in range(MAX_TRIES):
        r = requests.post(f"{API}/{path}", headers=h, timeout=120, json=body)
        if r.status_code != 429:
            break
        time.sleep(min(60, 5 * 2 ** k))  # 5..60 s, ~3 min in all: a low-credit account runs one task at a time (~60 s)
    if r.status_code >= 400:
        raise RuntimeError(f"{what}: HTTP {r.status_code} {r.text[:300]}")
    job = r.json()
    t = time.perf_counter()
    while True:
        time.sleep(1.5)
        p = requests.get(job.get("polling_url") or f"{API}/get_result", headers=h, params={"id": job["id"]}, timeout=60).json()
        if p.get("status") == "Ready":
            break
        if p.get("status") in FAILED:
            raise RuntimeError(f"{what}: {p.get('status')} {str(p)[:300]}")
        if time.perf_counter() - t > timeout_s:
            raise TimeoutError(f"{what} took over {timeout_s:.0f} s (job {job['id']})")
    cost = job.get("cost") if job.get("cost") is not None else p.get("cost")
    out = Image.open(io.BytesIO(requests.get(p["result"]["sample"], timeout=120).content)).convert("RGB")
    return out, cost, round(time.perf_counter() - t, 1)


def flux_erase(img: Image.Image, mask: Image.Image, dilate: int = DILATE, tag: str = "FLUX Erase"):
    """One erase: (the output image, seconds, credits). Raises BudgetExceeded before sending if the cap would break."""
    with reserve(ERASE_RESERVE_USD, tag):  # raises OfflineCall in an offline run
        out, cost, secs = _run("flux-tools/erase-v1", {"image": b64(img), "mask": b64(mask), "dilate_pixels": dilate,
                                                       "output_format": "png"}, 300, "FLUX Erase")
        record("bfl", (cost or 0) / 100, credits=cost, size=img.size, model="flux-erase", tag=tag)
    return out, secs, cost


def flux2(prompt: str, images: list[Image.Image], width: int, height: int, model: str = "flux-2-pro",
          tag: str = "FLUX 2", seed: int | None = None) -> tuple[Image.Image, float | None]:
    """One FLUX.2 image (/v1/flux-2-pro by default; max, flex, klein-9b, klein-4b take the same inputs): the prompt
    with up to 8 reference images (4 on klein) as input_image, input_image_2, ... (the image, its credits). A seed
    makes a validated result repeatable; without one the model picks its own."""
    body = {"prompt": prompt, "width": width, "height": height, "output_format": "png"}
    if seed is not None:
        body["seed"] = seed
    for n, im in enumerate(images[:8], 1):
        body["input_image" if n == 1 else f"input_image_{n}"] = b64(im.convert("RGB"), "JPEG")
    with reserve(FLUX2_RESERVE_USD, tag):
        out, cost, _ = _run(model, body, 600, "FLUX 2")
        record("bfl", (cost or 0) / 100, credits=cost, size=out.size, model=model, tag=tag)
    return out, cost


def flux3(prompt: str, images: list[Image.Image], aspect_ratio: str = "16:9", resolution: str = "1.5k",
          tag: str = "FLUX 3") -> tuple[Image.Image, float | None]:
    """One FLUX 3 Image (/v1/flux-3-image): the prompt with up to 10 reference images, no web grounding.
    (the image, its credits)."""
    body = {"prompt": prompt, "images": [b64(im.convert("RGB"), "JPEG") for im in images][:10],
            "aspect_ratio": aspect_ratio, "resolution": resolution, "grounding": False}
    with reserve(FLUX3_RESERVE_USD.get(resolution, max(FLUX3_RESERVE_USD.values())), tag):
        out, cost, _ = _run("flux-3-image", body, 600, "FLUX 3")
        record("bfl", (cost or 0) / 100, credits=cost, size=out.size, model="flux-3-image", tag=tag)
    return out, cost
