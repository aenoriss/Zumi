"""Intake: a folder of webtoon slices in, ordered beats out.

1. stitch: slices stacked into one strip; seams are invisible from here on.
2. row profile: each row's median colour and its share of outlier pixels; a row is blank under 0.2 %.
3. gutters: blank runs judged against the local page colour, fades, panel edges and nearby blocks
   (gutters.py).
4. beats: content between gutters, with specks folded into gutters, slivers joined and floating text
   attached to its panel or kept as a beat of its own (beats.py).

Thresholds live in params.py; the history behind each is in pipeline/tuning-log.md.
"""

from __future__ import annotations

from pathlib import Path

from .beats import Slab, beats
from .gutters import gutters, row_profile
from .params import Params
from .strip import Strip, background_colour, list_images, report, stitch

__all__ = ["Params", "Slab", "Strip", "list_images", "report", "split_strip", "stitch"]


def split_strip(files: list[Path], params: Params = Params()) -> Strip:
    pixels, seams = stitch(files)
    medians, share = row_profile(pixels, params.tolerance)
    cuts = gutters(pixels, medians, share, params)
    return Strip(pixels, background_colour(pixels), beats(cuts, share, pixels, params), seams)
