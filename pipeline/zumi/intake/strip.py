"""Strip I/O: list and stitch webtoon slices, crop beats, draw the cut report."""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from .beats import Slab
from .gutters import WORKERS

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp"}


def list_images(folder: Path) -> list[Path]:
    """Image files in natural order (2.jpg before 10.jpg)."""
    key = lambda p: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", p.name)]
    return sorted((p for p in folder.iterdir() if p.suffix.lower() in IMAGE_EXT), key=key)


def _read_rgb(path: Path) -> np.ndarray:
    im = Image.open(path)
    return np.asarray(im if im.mode == "RGB" else im.convert("RGB"))


def stitch(files: list[Path]) -> tuple[np.ndarray, list[int]]:
    """Slices stacked into one (h, w, 3) strip, and the y of each slice seam.

    Slices of another width are scaled to the width covering most rows (Tower of God S1 ep 0 ends on an
    800-px slice after seven 700-px ones).
    """
    with ThreadPoolExecutor(WORKERS) as pool:
        parts = list(pool.map(_read_rgb, files))
    rows: dict[int, int] = {}
    for a in parts:
        rows[a.shape[1]] = rows.get(a.shape[1], 0) + a.shape[0]
    w = max(rows, key=rows.get)
    parts = [
        a if a.shape[1] == w else np.asarray(Image.fromarray(a).resize((w, round(a.shape[0] * w / a.shape[1])), Image.LANCZOS))
        for a in parts
    ]
    return np.concatenate(parts), np.cumsum([a.shape[0] for a in parts])[:-1].tolist()


def background_colour(pixels: np.ndarray, margin: int = 8) -> tuple[int, int, int]:
    """Most frequent colour in the left and right margins (ties go to the lowest RGB)."""
    edges = np.concatenate([pixels[:, :margin].reshape(-1, 3), pixels[:, -margin:].reshape(-1, 3)]).astype(np.int32)
    colours, counts = np.unique(edges[:, 0] << 16 | edges[:, 1] << 8 | edges[:, 2], return_counts=True)
    c = int(colours[counts.argmax()])
    return c >> 16, c >> 8 & 255, c & 255


@dataclass
class Strip:
    pixels: np.ndarray  # (h, w, 3) uint8
    background: tuple[int, int, int]  # dominant margin colour, for the reader; cuts never use it
    slabs: list[Slab]
    seams: list[int]

    @property
    def width(self) -> int:
        return self.pixels.shape[1]

    @property
    def height(self) -> int:
        return self.pixels.shape[0]

    def crop(self, slab: Slab) -> Image.Image:
        return Image.fromarray(self.pixels[slab.y : slab.end])


def report(strip: Strip, out: Path, scale: float = 0.25) -> Path:
    """The strip at `scale` with each beat outlined in red (just outside the box, so it hides no lettering)."""
    w, h = int(strip.width * scale), int(strip.height * scale)
    im = Image.fromarray(strip.pixels).resize((w, h), Image.BILINEAR)
    draw = ImageDraw.Draw(im)
    for y in strip.seams:
        draw.line([(0, y * scale), (w, y * scale)], fill=(80, 140, 255), width=1)
    for i, s in enumerate(strip.slabs):
        top, bottom = s.y * scale, s.end * scale
        draw.rectangle([(0, top - 2), (w - 1, bottom + 1)], outline=(230, 40, 40), width=2)
        draw.text((6, top - 14), f"{i}", fill=(230, 40, 40))
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out
