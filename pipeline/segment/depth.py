"""Monocular depth with Depth Anything 3 (DA3MONO-LARGE, Apache 2.0; the LARGE/GIANT/NESTED checkpoints are
CC BY-NC 4.0 and are not used). Meta has no open depth model (docs/architecture/decisions.md, step 6).

The DA3 source sits in pipeline/.vendor/Depth-Anything-3 and is imported from there, not installed: its package pulls
in open3d, pycolmap and numpy<2 for 3D export, none of which depth needs, so the export module is stubbed.

    from depth import load, depth_map
    model = load(); d = depth_map(model, pil_image)   # float32 H x W, larger = nearer (relative)
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
METRIC_ID = "depth-anything/DA3METRIC-LARGE"  # Apache 2.0, same architecture, trained on metric depth (no shift)


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


MAX_SHORT = 700  # px, short side given to the model: webtoon panels are 700 wide


def depth_map(model, img: Image.Image, exclude: np.ndarray | None = None, res: int | None = None,
              method: str = "lower_bound_resize") -> np.ndarray:
    """Relative nearness at the panel's resolution (larger = nearer), scaled so the panel's background spans 0..1.

    The model sees the whole panel (it needs the context; white holes would read as objects). `exclude` (segmented
    elements, grown by a margin) is left out of the scaling: characters set the top of the range and squeezed the
    background, lettering got a depth of its own (a bubble floating between two people, True Beauty 4 p9). Values
    are not clipped, so a character in front reads above 1.

    Resolution: the panel's own short side, capped at MAX_SHORT. DA3's default (longest side 504) analysed a 700x2237
    panel at about 157x504 and blurred every outline; at 700 px horns, fingers and hair strands separate, for 1.0 s and
    3.8 GB instead of 0.5 s and 2.1 GB (1008 px: 5.4 s, barely sharper). A 5 px median then removes the dot pattern the
    model leaves on flat textured backgrounds (True Beauty 4 p12) without moving edges."""
    if res is None:
        res = min(MAX_SHORT, min(img.size)) // 14 * 14  # patch size 14
    with torch.inference_mode():
        pred = model.inference([np.asarray(img.convert("RGB"))], process_res=res, process_res_method=method)
    d = np.asarray(pred.depth[0], dtype=np.float32)
    if d.shape != (img.height, img.width):
        d = np.asarray(Image.fromarray(d).resize(img.size, Image.BILINEAR))
    import cv2
    d = cv2.medianBlur(d.astype(np.float32), 5)
    # nearness linear in depth, not 1/depth: 1/depth gave near objects most of the range and squeezed the background
    # (share of 0..1 spanned by the background's middle half: ToG 228 p6 0.17 with 1/depth, 0.41 linear; TB4 p11
    # 0.14 vs 0.29); with it the table, vase and chair behind a character merged into one dark plane
    keep = ~exclude if exclude is not None and (~exclude).sum() > 500 else np.ones(d.shape, bool)
    keep &= ~non_art(img)
    if keep.sum() < 500:
        keep = np.ones(d.shape, bool)
    lo, hi = np.percentile(d[keep], 1), np.percentile(d[keep], 99)
    return ((hi - d) / max(hi - lo, 1e-6)).astype(np.float32)


def non_art(img: Image.Image, border: float = 0.02, exclude: np.ndarray | None = None) -> np.ndarray:
    """Pixels whose depth means nothing: white gutters and page margins reaching the panel's edge (the model gives
    them blotchy depth, ToG 228 p2), and a thin border where it brightens every panel edge (TB4 p11). `exclude`: pixels
    the white may not spread through (speech bubbles, which are white and often touch the edge)."""
    from scipy.ndimage import binary_dilation, label
    a = np.asarray(img.convert("RGB"))
    white = (a.min(axis=2) >= 245)
    if exclude is not None:
        white &= ~exclude
    lab, _ = label(white)
    edge_ids = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    gutter = np.isin(lab, edge_ids[edge_ids > 0])
    gutter = binary_dilation(gutter, iterations=4)
    b = max(2, int(border * min(img.size)))
    frame = np.zeros(gutter.shape, bool)
    frame[:b], frame[-b:], frame[:, :b], frame[:, -b:] = True, True, True, True
    return gutter | frame


def fill_under(near: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """The depth field with `mask` filled from its surroundings: the background as it continues behind cut-outs."""
    if not mask.any() or (~mask).sum() < 500:  # nothing, or too little background left to fill from
        return near
    # normalised Gaussian convolution, fine to coarse: each hole pixel takes the weighted mean of the known depth
    # around it at the smallest scale that reaches known pixels. Telea inpainting drew streaks and wedges across
    # large holes (captions and bubbles: ToG 228 p6, p20, p30)
    import cv2
    w = (~mask).astype(np.float32)
    v = np.where(mask, 0, near).astype(np.float32)
    out = near.astype(np.float32).copy()
    todo = mask.copy()
    h, wd = near.shape
    for sigma in (4, 12, 32, 80, 200, 500):
        f = max(1, sigma // 8)  # blur large scales on a downsampled copy
        small = (max(1, wd // f), max(1, h // f))
        num = cv2.GaussianBlur(cv2.resize(v * w, small, interpolation=cv2.INTER_AREA), (0, 0), sigma / f)
        den = cv2.GaussianBlur(cv2.resize(w, small, interpolation=cv2.INTER_AREA), (0, 0), sigma / f)
        num, den = (cv2.resize(x, (wd, h), interpolation=cv2.INTER_LINEAR) for x in (num, den))
        ok = todo & (den > 0.02)
        out[ok] = num[ok] / den[ok]
        todo &= ~ok
        if not todo.any():
            break
    if todo.any():
        out[todo] = float(np.median(near[~mask]))
    return out


# ---------- precise depth (docs/research/depth-precision-2026-10.md) ----------
TILE_ASPECT = 1.5   # window height / width; DA3 trained up to 896x504 (aspect 1:1.8): a 700x2400 panel (1:3.4) is not
FLY_RATIO = 1.03    # neighbouring depths differing by more than 3%: a "flying" pixel on an outline


def _infer(model, arr, res):
    with torch.inference_mode():
        pred = model.inference([arr], process_res=res, process_res_method="lower_bound_resize")
    d = np.asarray(pred.depth[0], dtype=np.float32)
    if d.shape != arr.shape[:2]:
        d = np.asarray(Image.fromarray(d).resize((arr.shape[1], arr.shape[0]), Image.BILINEAR))
    return d


PAD_ASPECT = 1.8  # a frame longer than this (long side / short side) is padded to it before its one pass


def frame_infer(model, rgb: np.ndarray) -> np.ndarray:
    """Depth of ONE frame in one pass. A very tall or wide frame is mirror-padded on its short side up to PAD_ASPECT
    (DA3 trained up to 1:1.8), inferred whole, and cropped back. Tiled windows (tiled_depth) lost the figure on a
    160 x 388 px close-up (P&C 39 p24, third frame: a smooth gradient, while one pass on the crop showed her)."""
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


def _robust_fit(x, y, iters=8):
    """y = s x + t, Huber-weighted least squares (iteratively reweighted)."""
    wgt = np.ones_like(x)
    s, t = 1.0, 0.0
    for _ in range(iters):
        (s, t), *_ = np.linalg.lstsq(np.stack([x * wgt, wgt], 1), y * wgt, rcond=None)
        r = np.abs(y - (s * x + t))
        k = 1.345 * max(np.median(r) / 0.6745, 1e-9)
        wgt = np.sqrt(np.where(r <= k, 1.0, k / np.maximum(r, 1e-12)))
    return s, t


def tiled_depth(model, img: Image.Image, align: bool = True, reference: np.ndarray | None = None) -> tuple[np.ndarray, list]:
    """Depth of a tall panel from overlapping windows of TILE_ASPECT, blended with tent weights. Each window's depth
    is scale-shift invariant, so with `align` it is fitted (scale and shift) before blending: to `reference` over the
    whole window when given (metric depth: one shared reference, so errors do not pile up down a tall panel; tile to
    tile alignment left seams of up to 8%), else to the mosaic on the overlap. Seam errors (median relative
    difference to the mosaic on the overlap, after the fit) are returned."""
    arr = np.asarray(img.convert("RGB"))
    h, w = arr.shape[:2]
    res = min(MAX_SHORT, w) // 14 * 14
    if h <= 1.8 * w:
        return _infer(model, arr, res), []
    win = int(TILE_ASPECT * w)
    stride = win // 3  # two-thirds overlap: more shared pixels for each alignment fit
    tops = list(range(0, h - win, stride)) + [h - win]
    acc = np.zeros((h, w), np.float64)
    wsum = np.zeros((h, w), np.float64)
    tent = np.minimum(np.arange(win) + 1, win - np.arange(win)).astype(np.float64)[:, None]
    seams = []
    for top in tops:
        d = _infer(model, arr[top:top + win], res).astype(np.float64)
        have = wsum[top:top + win] > 0
        if align and reference is not None:
            ref = reference[top:top + win].astype(np.float64)
            sub = slice(None, None, max(1, d.size // 40000))
            s, t = _robust_fit(d.ravel()[sub], ref.ravel()[sub])
            d = s * d + t
        elif align and have.any():
            mosaic = acc[top:top + win][have] / wsum[top:top + win][have]
            s, t = _robust_fit(d[have], mosaic)
            d = s * d + t
        if have.any():
            mosaic = acc[top:top + win][have] / wsum[top:top + win][have]
            seams.append(float(np.median(np.abs(d[have] - mosaic) / np.maximum(np.abs(mosaic), 1e-6))))
        acc[top:top + win] += d * tent
        wsum[top:top + win] += tent
    return (acc / wsum).astype(np.float32), seams


def fill_flying(D: np.ndarray, valid: np.ndarray, rgb: np.ndarray, r: int = 3, rounds: int = 3) -> np.ndarray:
    """Give each invalid (flying) pixel the depth of the most similar valid pixel within r px: colour distance first,
    distance as the tie-break. It takes ONE side of the outline (the side it is drawn in), never an average of both,
    so it does not recreate the in-between depth. Repeated while invalid pixels remain (wide edges)."""
    D = D.copy()
    ok = valid.copy()
    lab = rgb.astype(np.float32)
    h, w = D.shape
    for _ in range(rounds):
        todo = ~ok
        if not todo.any():
            break
        best = np.full((h, w), np.inf, np.float32)
        pick = D.copy()
        P = np.pad(D, r, mode="edge")
        V = np.pad(ok, r, mode="constant", constant_values=False)
        C = np.pad(lab, ((r, r), (r, r), (0, 0)), mode="edge")
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dy == 0 and dx == 0:
                    continue
                v = V[r + dy:r + dy + h, r + dx:r + dx + w]
                cost = np.sum((C[r + dy:r + dy + h, r + dx:r + dx + w] - lab) ** 2, axis=2) + 0.5 * (dy * dy + dx * dx)
                better = todo & v & (cost < best)
                best[better] = cost[better]
                pick[better] = P[r + dy:r + dy + h, r + dx:r + dx + w][better]
        got = todo & np.isfinite(best)
        D[got] = pick[got]
        ok |= got
    return D


def add_relief(D: np.ndarray, img: Image.Image, where: np.ndarray, r: int = 8, eps: float = 50.0) -> np.ndarray:
    """Fine relief below DA3's 14 px patches, extrapolated from nearby pixels: a guided filter models depth locally as
    a linear function of the image, so shading and ink detail carry into depth. Applied only inside `where`
    (characters): on ToG 228 p6 / p20 it gave characters 2.3-2.5x more relief but copied wood grain and tiles into
    walls and floors (flatness 0.008 -> 0.023, 0.0066 -> 0.0129), so scene surfaces are left as they are."""
    import cv2
    if not where.any():
        return D
    g = cv2.ximgproc.guidedFilter(np.asarray(img.convert("RGB")).astype(np.float32), D.astype(np.float32), r, eps)
    a = cv2.GaussianBlur(where.astype(np.float32), (0, 0), 2)  # feathered, no seam at the outline
    return (D * (1 - a) + g * a).astype(np.float32)


def depth_like(mono, img: Image.Image, ref: np.ndarray, keep: np.ndarray) -> tuple[np.ndarray, float]:
    """Depth of an edited copy of a panel (a plate with things erased) in the panel's own frame: tiled DA3MONO, its
    scale and shift fitted robustly to the panel's precise depth `ref` where the two images still agree (`keep`),
    then the same median and flying-pixel fill as precise_depth. The metric model is not needed: the fit to `ref`
    already removes the unknown shift. Returns (depth, median relative error on keep)."""
    import cv2
    m, _ = tiled_depth(mono, img, align=True)
    ratio = cv2.dilate(m, np.ones((3, 3), np.uint8)) / np.maximum(cv2.erode(m, np.ones((3, 3), np.uint8)), 1e-6)
    fly = ratio > FLY_RATIO
    use = keep & ~fly
    if use.sum() < 1000:  # the edit covers (almost) the whole box: fit on everything rather than on nothing
        keep = np.ones_like(keep)
        use = ~fly
    sub = np.flatnonzero(use.ravel())[:: max(1, int(use.sum()) // 60000)]
    s, t = _robust_fit(m.ravel()[sub].astype(np.float64), ref.ravel()[sub].astype(np.float64))
    D = np.maximum((s * m + t).astype(np.float32), float(ref[keep].min()) * 0.5)
    D = fill_flying(cv2.medianBlur(D, 3), ~fly, np.asarray(img.convert("RGB")))
    err = float(np.median(np.abs(D[keep] - ref[keep]) / ref[keep]))
    return D.astype(np.float32), err


def align_locally(Dl: np.ndarray, ref: np.ndarray, mask: np.ndarray, valid: np.ndarray, band: int = 16) -> np.ndarray:
    """A plate's depth joined to the box's at the mask's border: outside the mask the box's own depth (the plate shows
    the same scene there), inside it the plate's depth plus a smooth correction in log depth measured in a band along
    the border and carried inward by normalised convolution (fill_under). depth_like's single global scale and shift
    left the hidden surface a few percent off the visible one at the seam (user, 2026-10-25)."""
    from scipy.ndimage import binary_dilation
    ring = binary_dilation(mask, iterations=band) & ~mask & valid
    if ring.sum() < 200:
        return Dl
    r = np.where(ring, np.log(np.maximum(ref, 1e-6)) - np.log(np.maximum(Dl, 1e-6)), 0).astype(np.float32)
    corr = fill_under(r, ~ring)
    out = np.where(mask, Dl * np.exp(corr), np.where(valid, ref, Dl))
    return out.astype(np.float32)


def precise_depth(mono, metric, img: Image.Image, ignore: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, dict]:
    """Depth for back-projection: (depth, valid mask, stats).

    1. DA3MONO, tiled for tall panels (aligned windows).
    2. Its unknown shift removed: DA3MONO predicts scale-shift-invariant depth, and a wrong shift bends flat surfaces
       in 3D. DA3METRIC-LARGE (no shift) on the same windows; mono = s * metric + t fitted robustly (Huber IRLS) on
       valid pixels; depth = (mono - t) / s.
    3. Flying pixels (neighbour ratio over FLY_RATIO) marked invalid: outlines blend object and background depth.
    4. A 3 px median, then each flying pixel takes the depth of the most similar valid pixel nearby (fill_flying).
       An edge-aware weighted median (guided by the panel, flattened or not) put 76-82% of character
       pixels on flat plateaus, so characters looked blocky, and it did not make floors or walls any flatter
       (ToG 228 p6, p20; the flatness gain comes from steps 1-2)."""
    import cv2
    import time
    t0 = time.perf_counter()
    # mono windows aligned to each other (robust fit on the overlap); the metric model gives only the global shift
    # below. Fitting each mono window to the metric windows instead was worse: metric windows disagree with each other
    # (seams up to 36%, ToG 228 p30; floor flatness 0.007 -> 0.23, p20)
    m, seams = tiled_depth(mono, img, align=True)
    M, _ = tiled_depth(metric, img, align=False)
    ratio = cv2.dilate(m, np.ones((3, 3), np.uint8)) / np.maximum(cv2.erode(m, np.ones((3, 3), np.uint8)), 1e-6)
    fly = ratio > FLY_RATIO
    use = ~fly & (ignore is None or ~ignore) if ignore is not None else ~fly
    if use.sum() < 1000:
        use = np.ones_like(fly)
    sub = np.flatnonzero(use.ravel())[:: max(1, int(use.sum()) // 60000)]
    x, y = M.ravel()[sub].astype(np.float64), m.ravel()[sub].astype(np.float64)
    wgt = np.ones_like(x)
    s, t = 1.0, 0.0
    for _ in range(8):  # Huber IRLS for y = s x + t
        A = np.stack([x * wgt, wgt], 1)
        (s, t), *_ = np.linalg.lstsq(A, y * wgt, rcond=None)
        r = np.abs(y - (s * x + t))
        k = 1.345 * max(np.median(r) / 0.6745, 1e-9)
        wgt = np.sqrt(np.where(r <= k, 1.0, k / np.maximum(r, 1e-12)))
    D = ((m - t) / s).astype(np.float32) if s > 1e-9 else M.astype(np.float32)  # no usable fit: the metric depth as is
    D = np.maximum(D, float(np.percentile(D, 0.5)) * 0.5 if np.percentile(D, 0.5) > 0 else 1e-3)
    Ds = fill_flying(cv2.medianBlur(D.astype(np.float32), 3), ~fly, np.asarray(img.convert("RGB")))
    stats = {"seams": [round(x_, 4) for x_ in seams], "shift_t": round(float(t), 4), "scale_s": round(float(s), 4),
             "flying_share": round(float(fly.mean()), 4), "secs": round(time.perf_counter() - t0, 2),
             "metric": M}  # parallax.build judges from it whether the box suits model depth at all
    return Ds.astype(np.float32), ~fly, stats
