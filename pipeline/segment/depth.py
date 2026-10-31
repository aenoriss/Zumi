"""Monocular depth with Depth Anything 3 (DA3MONO-LARGE, Apache 2.0; the LARGE/GIANT/NESTED checkpoints are
CC BY-NC 4.0 and are not used), run on each frame alone (frame_infer): it orders the cards of the flat layers.

The DA3 source sits in pipeline/.vendor/Depth-Anything-3 and is imported from there, not installed: its package pulls
in open3d, pycolmap and numpy<2 for 3D export, none of which depth needs, so the export module is stubbed.

    model = load(); d = frame_infer(model, rgb)   # float32 H x W, relative depth
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import torch
from PIL import Image

SRC = Path(__file__).resolve().parents[1] / ".vendor/Depth-Anything-3/src"
MODEL_ID = "depth-anything/DA3MONO-LARGE"
MAX_SHORT = 700  # px, short side given to the model: webtoon panels are 700 wide
PAD_ASPECT = 1.8  # a frame longer than this (long side / short side) is padded to it before its one pass


def load(model_id: str = MODEL_ID):
    if str(SRC) not in sys.path:
        sys.path.insert(0, str(SRC))
    # 3D export and multi-view pose alignment are not used for single-image depth
    for name, attr in (("depth_anything_3.utils.export", "export"), ("depth_anything_3.utils.pose_align", "align_poses_umeyama")):
        stub = types.ModuleType(name)
        setattr(stub, attr, lambda *a, **k: None)
        sys.modules.setdefault(name, stub)
    from depth_anything_3.api import DepthAnything3
    return DepthAnything3.from_pretrained(model_id).to("cuda").eval()


def _infer(model, arr, res):
    with torch.inference_mode():
        pred = model.inference([arr], process_res=res, process_res_method="lower_bound_resize")
    d = np.asarray(pred.depth[0], dtype=np.float32)
    if d.shape != arr.shape[:2]:
        d = np.asarray(Image.fromarray(d).resize((arr.shape[1], arr.shape[0]), Image.BILINEAR))
    return d


def frame_infer(model, rgb: np.ndarray) -> np.ndarray:
    """Depth of ONE frame in one pass. A very tall or wide frame is mirror-padded on its short side up to PAD_ASPECT
    (DA3 trained up to 1:1.8), inferred whole, and cropped back. Tiled windows lost the figure on a 160 x 388 px
    close-up (P&C 39 p24, third frame: a smooth gradient, while one pass on the crop showed her)."""
    h, w = rgb.shape[:2]
    if max(h, w) > PAD_ASPECT * min(h, w):
        if h > w:
            p = int(np.ceil(h / PAD_ASPECT)) - w
            pads = ((0, 0), (p // 2, p - p // 2), (0, 0))
        else:
            p = int(np.ceil(w / PAD_ASPECT)) - h
            pads = ((p // 2, p - p // 2), (0, 0), (0, 0))
        big = np.pad(rgb, pads, mode="reflect" if max(pads[0][1], pads[1][1]) < min(h, w) else "edge")
    else:
        pads, big = ((0, 0), (0, 0), (0, 0)), rgb
    bh, bw = big.shape[:2]
    d = _infer(model, np.ascontiguousarray(big), min(MAX_SHORT, bh, bw) // 14 * 14)
    return d[pads[0][0]:pads[0][0] + h, pads[1][0]:pads[1][0] + w].astype(np.float32)
