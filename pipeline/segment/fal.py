"""fal.ai, the one module that talks to it: TRELLIS (image to textured GLB) and BiRefNet (foreground matte), both for
the props (props.py). FAL_KEY in pipeline/.env, never printed. TRELLIS reserves its price under the shared daily cap
(spend.py) and goes into .data/spend/fal.jsonl; BiRefNet is listed at 0 USD but still reaches the network, so every
call here is refused in an offline run (OfflineCall) before anything is sent.

    trellis(image, seed, texture, simplify, tag) -> GLB bytes   image: RGBA, the object on a transparent ground
    birefnet(image) -> bool mask (image size)
"""
from __future__ import annotations

import base64
import functools
import io
import os
import time
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from spend import no_call_offline, payment_refused, record, reserve

ROOT = Path(__file__).resolve().parents[1]  # pipeline/
TRELLIS = "https://fal.run/fal-ai/trellis"
BIREFNET = "https://fal.run/fal-ai/birefnet/v2"  # listed at 0 USD per compute second
TRELLIS_USD = 0.02                               # per model, fal's listed price
DOWNLOADS = 4         # tries at a paid model's download
DOWNLOAD_PAUSE = 5    # s between them


@functools.lru_cache(maxsize=1)
def _key() -> str:
    if os.environ.get("FAL_KEY"):  # a cloud container gets it as a secret, not as a file
        return os.environ["FAL_KEY"]
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("FAL_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("FAL_KEY missing from pipeline/.env")


def _uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _post(url: str, body: dict) -> dict:
    no_call_offline(url)
    r = requests.post(url, headers={"Authorization": f"Key {_key()}"}, json=body, timeout=600)
    payment_refused("fal", r.status_code, r.text)
    r.raise_for_status()
    return r.json()


def _mask_of(out: dict, size) -> np.ndarray:
    """The mask image of a fal reply (a data URI or a URL), as a bool array of `size`."""
    url = out["image"]["url"]
    data = base64.b64decode(url.split(",", 1)[1]) if url.startswith("data:") else requests.get(url, timeout=60).content
    return np.asarray(Image.open(io.BytesIO(data)).convert("L").resize(size)) > 127


def birefnet(img: Image.Image) -> np.ndarray:
    return _mask_of(_post(BIREFNET, {"image_url": _uri(img), "model": "General Use (Heavy)", "mask_only": True,
                                     "sync_mode": True}), img.size)


def trellis(img: Image.Image, seed: int, texture: int, simplify: float, tag: str = "TRELLIS") -> bytes:
    """A GLB of the object; texture: the texture's side in px, simplify: the share of faces removed."""
    with reserve(TRELLIS_USD, tag):
        out = _post(TRELLIS, {"image_url": _uri(img), "texture_size": texture, "mesh_simplify": simplify, "seed": seed})
        record("fal", TRELLIS_USD, model="fal-ai/trellis", seed=seed, tag=tag)
    # The model is paid for once recorded: a download that fails here loses it and the next run pays again, so a
    # dropped connection or a busy CDN gets a few more tries.
    for k in range(DOWNLOADS):
        try:
            r = requests.get(out["model_mesh"]["url"], timeout=120)
            r.raise_for_status()
            return r.content
        except requests.RequestException:
            if k == DOWNLOADS - 1:
                raise
            time.sleep(DOWNLOAD_PAUSE)
