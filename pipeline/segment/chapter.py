"""A chapter as step 1 (intake) packed it: a .zumi whose manifest lists the episode's boxes in reading order, each
with its image (the box's first layer) and where it sat in the stitched strip.

    ch = Chapter(path); ch.stem; len(ch); ch.image(i); ch.pid(i); ch.panels[i]["strip"]
"""
from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from PIL import Image

from boxstore import pid_of


class Chapter:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.zip = zipfile.ZipFile(self.path)
        self.manifest = json.loads(self.zip.read("manifest.json"))
        self.panels: list[dict] = self.manifest["panels"]

    @property
    def stem(self) -> str:
        """The episode's name: the .zumi's file name without its suffix, the prefix of every box id."""
        return self.path.stem

    def __len__(self) -> int:
        return len(self.panels)

    def image(self, i: int) -> Image.Image:
        """Box i's image, RGB."""
        return Image.open(io.BytesIO(self.zip.read(self.panels[i]["layers"][0]["image"]))).convert("RGB")

    def pid(self, i: int) -> str:
        return pid_of(self.stem, i)
