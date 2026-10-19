"""Write a .zumi file: manifest.json plus panels/<id>/... inside a zip."""

from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

from . import WORKERS
from .manifest import Manifest


def _png(im: Image.Image) -> bytes:
    buf = io.BytesIO()
    im.save(buf, format="PNG", optimize=False)
    return buf.getvalue()


def pack(manifest: Manifest, panel_images: dict[str, Image.Image], out: Path) -> Path:
    """panel_images maps panel id -> base layer image (RGB/RGBA). Written as panels/<id>/layers/base.png.

    PNGs are encoded on threads (Pillow releases the GIL) and stored without a second deflate pass: they are
    already zlib-compressed, and deflating them again saved 0.05 % for 1.9 s on unOrdinary 395.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(WORKERS) as pool:
        pngs = list(pool.map(_png, panel_images.values()))
    with zipfile.ZipFile(out, "w") as z:
        z.writestr("manifest.json", manifest.to_json(), compress_type=zipfile.ZIP_DEFLATED)
        for pid, data in zip(panel_images, pngs):
            z.writestr(f"panels/{pid}/layers/base.png", data, compress_type=zipfile.ZIP_STORED)
    return out
