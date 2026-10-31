"""FLUX Erase (Black Forest Labs API, May 2026): image + binary mask in, no prompt; trained for removal, it also takes
the shadows the mask misses. The adapter band_erase.py paints through: erase_image(rgb, mask) -> (rgb, log line).

BFL_API_KEY in pipeline/.env. Every call reserves its worst case under the shared daily cap (spend.py, model calls
and erases together) and raises BudgetExceeded before sending if it could pass it; its credits go into
.data/spend/bfl.jsonl (1 credit = 0.01 USD).
"""
import base64
import functools
import io
import os
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from spend import BudgetExceeded, reserve, record, spent_today  # noqa: F401  (BudgetExceeded, spent_today: for callers)

ROOT = Path(__file__).resolve().parents[1]  # pipeline/
API = "https://api.bfl.ai/v1"
RESERVE_USD = 0.06  # per call: the most one erase has cost (5.8 credits)
DILATE = 8          # px the API grows the mask by itself (dilate_pixels)
MAX_TRIES = 6       # on HTTP 429 (more than 24 requests in flight, docs.bfl.ai integration guidelines): back off


@functools.lru_cache(maxsize=1)
def key():
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("BFL_API_KEY="):
            return line.split("=", 1)[1].strip()
    return os.environ["BFL_API_KEY"]


def b64(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return base64.b64encode(b.getvalue()).decode()


def erase(img: Image.Image, mask: Image.Image, dilate: int = DILATE):
    """One API call: (output image, seconds, credits). Raises BudgetExceeded before sending if the cap would break."""
    with reserve(RESERVE_USD, "FLUX Erase"):
        return _erase(img, mask, dilate)


def _erase(img, mask, dilate):
    h = {"x-key": key(), "accept": "application/json"}
    body = {"image": b64(img), "mask": b64(mask), "dilate_pixels": dilate, "output_format": "png"}
    for k in range(MAX_TRIES):
        r = requests.post(f"{API}/flux-tools/erase-v1", headers=h, timeout=60, json=body)
        if r.status_code != 429:
            break
        time.sleep(2 ** k)
    r.raise_for_status()
    job = r.json()
    t = time.perf_counter()
    while True:
        time.sleep(1.0)
        p = requests.get(job.get("polling_url") or f"{API}/get_result", headers=h, params={"id": job["id"]}, timeout=60).json()
        if p["status"] == "Ready":
            break
        if p["status"] not in ("Pending", "Processing", "Queued"):
            raise RuntimeError(f"FLUX Erase: {p['status']} {p}")
        if time.perf_counter() - t > 300:
            raise TimeoutError("FLUX Erase took over 5 min")
    cost = job.get("cost", p.get("cost"))
    record("bfl", (cost or 0) / 100, credits=cost, size=img.size)
    out = Image.open(io.BytesIO(requests.get(p["result"]["sample"], timeout=120).content)).convert("RGB")
    return out, round(time.perf_counter() - t, 1), cost


def erase_image(rgb: np.ndarray, mask: np.ndarray) -> tuple[np.ndarray, str]:
    """The model's whole output for rgb (H x W x 3) and its mask, in one call: the image padded to the nearest trained
    aspect (1:2 for a tall webtoon panel) with its own mirrored edges (and mirrored mask: a mirrored box or character
    left unmasked in the padding would read as scene to keep), scaled to ~1 MP, the padding cut off again. Returns
    (output, log line); raises BudgetExceeded."""
    h, w = mask.shape
    pw = max(0, int(np.ceil(h * 0.5)) - w)  # extra width for 1:2
    ph = max(0, int(np.ceil(w * 0.5)) - h)  # extra height for 2:1 (wide panels)
    l, t = pw // 2, ph // 2
    padded = np.pad(rgb, ((t, ph - t), (l, pw - l), (0, 0)), mode="reflect")
    pm = np.pad(mask, ((t, ph - t), (l, pw - l)), mode="reflect")
    PH, PW = pm.shape
    s = (1024 * 1024 / (PW * PH)) ** 0.5
    W, H = round(PW * s / 16) * 16, round(PH * s / 16) * 16
    out, secs, cost = erase(Image.fromarray(padded).resize((W, H), Image.LANCZOS),
                            Image.fromarray(pm.astype(np.uint8) * 255).resize((W, H), Image.NEAREST))
    got = np.asarray(out.resize((PW, PH), Image.LANCZOS))[t:t + h, l:l + w]
    return got, (f"one call: {w}x{h} padded to {PW}x{PH} (aspect {PW / PH:.2f}) -> {W}x{H}, holes "
                 f"{mask.mean() * 100:.0f}%; erase {secs} s, {cost} credits")
