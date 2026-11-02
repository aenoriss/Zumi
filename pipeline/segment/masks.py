"""Segment masks and their .npz files, without torch or SAM: scripts that only read masks start in under a second.
Found is the one mask type of the pipeline: lettering (kind bubble, caption, sfx), characters (character, crowd),
objects (object, with the picker's name). The frames have a file of their own (boxstore.Box.save_frames)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import hashlib

import numpy as np

# one colour per numbered mask, in the overlays the reviewer is shown (review_loop.marked) and the debug sheets
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 200, 200), (240, 50, 230),
           (150, 190, 30), (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 128)]


@dataclass
class Found:
    mask: np.ndarray  # full panel size, bool
    score: float
    kind: str
    name: str | None = None  # an object's name ("beer mug 2"); None for the other kinds
    box: tuple[int, int, int, int] | None = None  # y0, y1, x0, x1 of the mask, filled on first use
    aka: tuple[str, ...] = ()  # names of masks merged into this one (the review's "same"), so relations to them hold

    def bbox(self) -> tuple[int, int, int, int]:
        if self.box is None:
            ys, xs = np.flatnonzero(self.mask.any(axis=1)), np.flatnonzero(self.mask.any(axis=0))
            self.box = (int(ys[0]), int(ys[-1]) + 1, int(xs[0]), int(xs[-1]) + 1) if len(ys) else (0, 0, 0, 0)
        return self.box


def union(found: list[Found], shape: tuple[int, int]) -> np.ndarray:
    """All the masks in one (empty masks of `shape` when there are none)."""
    return np.logical_or.reduce([f.mask for f in found]) if found else np.zeros(shape, bool)


def top_key(mask: np.ndarray) -> tuple[int, int]:
    """A mask's place in top_order: its top row, then its leftmost column."""
    ys, xs = np.nonzero(mask)
    return int(ys.min()), int(xs.min())


def top_order(found: list) -> list:
    """Masks top to bottom, then left to right: the saved order, so a mask's index (a bubble id, a Transcribe element
    id) is the same in memory and on disk. episode.py sorted only on saving and gave Understand (Transcribe's
    predecessor) the unsorted list: its ids pointed at other bubbles after a --from-masks re-run (133 of 329 bubbles, P&C 37-39)."""
    return sorted(found, key=lambda f: top_key(f.mask))


def stamp(found: list[Found]) -> str:
    """The masks' identity in the order given (the saved order, top_order): what a result keyed by mask index (a
    bubble id) was made from, so a result for other masks, or for the same masks numbered otherwise, is told apart
    from a current one (P&C 37-38: 24 boxes' bubbles numbered in an order their re-saved masks no longer had)."""
    h = hashlib.sha1()
    for f in found:
        h.update(str(f.mask.shape).encode())
        h.update(np.packbits(f.mask).tobytes())
    return h.hexdigest()[:16]


def save_masks(path: Path, found: list[Found]) -> None:
    """Masks in top_order, bit-packed, with their kinds, scores and names."""
    path.parent.mkdir(parents=True, exist_ok=True)
    found = top_order(found)
    shape = found[0].mask.shape if found else (0, 0)
    np.savez_compressed(
        path,
        masks=np.packbits(np.stack([f.mask for f in found]), axis=-1) if found else np.zeros((0, 0, 0), np.uint8),
        shape=np.array(shape),
        kinds=np.array([f.kind for f in found]),
        scores=np.array([f.score for f in found]),
        **({"names": np.array([f.name or "" for f in found])} if any(f.name for f in found) else {}),
    )


def load_masks(path: Path) -> list[Found]:
    d = np.load(path)
    h, w = d["shape"]
    names = [str(n) or None for n in d["names"]] if "names" in d.files else [None] * len(d["kinds"])
    return [Found(np.unpackbits(m, axis=-1, count=w).astype(bool)[:h], float(s), str(k), n)
            for m, k, s, n in zip(d["masks"], d["kinds"], d["scores"], names)]
