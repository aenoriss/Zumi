"""fal.ai, the one module that talks to it: TRELLIS (image to textured GLB) and BiRefNet (foreground matte), both for
the props (props.py). FAL_KEY in pipeline/.env, never printed. TRELLIS reserves its price under the shared daily cap
(spend.py) and goes into .data/spend/fal.jsonl; BiRefNet is listed at 0 USD but still reaches the network, so every
call here is refused in an offline run (OfflineCall) before anything is sent.

    trellis(image, seed, tag) -> GLB bytes       image: RGBA, the object on a transparent ground
    birefnet(image) -> bool mask (image size)
"""
from __future__ import annotations

import base64
import functools
import io
import os
from pathlib import Path

import numpy as np
import requests
from PIL import Image

from spend import no_call_offline, record, reserve

ROOT = Path(__file__).resolve().parents[1]  # pipeline/
TRELLIS = "https://fal.run/fal-ai/trellis"
BIREFNET = "https://fal.run/fal-ai/birefnet/v2"  # listed at 0 USD per compute second
TRELLIS_USD = 0.02                               # per model, fal's listed price
TEXTURE = 1024        # TRELLIS texture side, as validated 2026-11-10: the cutouts it copies are 1024 px long
SIMPLIFY = 0.95       # TRELLIS mesh_simplify (share of faces removed), as validated 2026-11-10: a prop is small in the room


@functools.lru_cache(maxsize=1)
def key() -> str:
    for line in (ROOT / ".env").read_text().splitlines():
        if line.startswith("FAL_KEY="):
            return line.split("=", 1)[1].strip()
    return os.environ["FAL_KEY"]


def uri(img: Image.Image) -> str:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def post(url: str, body: dict) -> dict:
    no_call_offline(url)
    r = requests.post(url, headers={"Authorization": f"Key {key()}"}, json=body, timeout=600)
    r.raise_for_status()
    return r.json()


def mask_of(out: dict, size) -> np.ndarray:
    """The mask image of a fal reply (a data URI or a URL), as a bool array of `size`."""
    url = out["image"]["url"]
    data = base64.b64decode(url.split(",", 1)[1]) if url.startswith("data:") else requests.get(url, timeout=60).content
    return np.asarray(Image.open(io.BytesIO(data)).convert("L").resize(size)) > 127


def birefnet(img: Image.Image) -> np.ndarray:
    return mask_of(post(BIREFNET, {"image_url": uri(img), "model": "General Use (Heavy)", "mask_only": True,
                                   "sync_mode": True}), img.size)


def trellis(img: Image.Image, seed: int, tag: str = "TRELLIS") -> bytes:
    with reserve(TRELLIS_USD, tag):
        out = post(TRELLIS, {"image_url": uri(img), "texture_size": TEXTURE, "mesh_simplify": SIMPLIFY, "seed": seed})
        record("fal", TRELLIS_USD, model="fal-ai/trellis", seed=seed, tag=tag)
    return requests.get(out["model_mesh"]["url"], timeout=120).content
