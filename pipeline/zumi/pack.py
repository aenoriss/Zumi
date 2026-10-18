"""Write a .zumi file: manifest.json plus panels/<id>/... inside a zip."""

from __future__ import annotations

import zipfile
from pathlib import Path

from PIL import Image

from .manifest import Manifest


def pack(manifest: Manifest, panel_images: dict[str, Image.Image], out: Path) -> Path:
    """panel_images maps panel id -> base layer image (RGB/RGBA). Written as panels/<id>/layers/base.png."""
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as z:
        z.writestr("manifest.json", manifest.to_json())
        for pid, im in panel_images.items():
            with z.open(f"panels/{pid}/layers/base.png", "w") as f:
                im.save(f, format="PNG", optimize=False)
    return out
