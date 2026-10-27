"""Segment masks and their .npz files, without torch or SAM: scripts that only read masks start in under a second
(importing them from bubbles.py loaded SAM 3 and torch, ~4.5 s per script)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Found:
    mask: np.ndarray  # full panel size, bool
    score: float
    kind: str
    box: tuple[int, int, int, int] | None = None  # y0, y1, x0, x1 of the mask, filled on first use

    def bbox(self) -> tuple[int, int, int, int]:
        if self.box is None:
            ys, xs = np.flatnonzero(self.mask.any(axis=1)), np.flatnonzero(self.mask.any(axis=0))
            self.box = (int(ys[0]), int(ys[-1]) + 1, int(xs[0]), int(xs[-1]) + 1) if len(ys) else (0, 0, 0, 0)
        return self.box


def load_masks(path: Path) -> list[Found]:
    d = np.load(path)
    h, w = d["shape"]
    return [Found(np.unpackbits(m, axis=-1, count=w).astype(bool)[:h], float(s), str(k)) for m, k, s in zip(d["masks"], d["kinds"], d["scores"])]
