"""Finer background depth: DA3MONO on a backdrop at the frame's own short side (frame_infer today), upscaled to 700 and
1008 px, and 700 px followed by a guided filter on the backdrop image (depth edges snapped to the art's edges). One
row per frame, each depth normalised over the frame (2-98th pct, white = near), with its time. Also prints how
well depth edges sit on image edges: the mean depth gradient on the image's strongest 5% of edges over the mean
elsewhere (higher = depth changes where the drawing does).

    uv run python experiments/backdrop_res.py <mesh dir> <sheet path> pepper-carrot-39-p002:0 pepper-carrot-39-p004:0 ...
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import depth as DP  # noqa: E402

ROW_H = 260
RED = (128, 40, 40)


def infer(model, rgb: np.ndarray, short: int | None) -> np.ndarray:
    """frame_infer with the model's short side set: None = the frame's own (today), else that many px."""
    h, w = rgb.shape[:2]
    if max(h, w) > DP.PAD_ASPECT * min(h, w):
        if h > w:
            p = int(np.ceil(h / DP.PAD_ASPECT)) - w
            pads = ((0, 0), (p // 2, p - p // 2), (0, 0))
        else:
            p = int(np.ceil(w / DP.PAD_ASPECT)) - h
            pads = ((p // 2, p - p // 2), (0, 0), (0, 0))
        big = np.pad(rgb, pads, mode="reflect" if max(pads[0][1], pads[1][1]) < min(h, w) else "edge")
    else:
        pads, big = ((0, 0), (0, 0), (0, 0)), rgb
    bh, bw = big.shape[:2]
    res = (min(DP.MAX_SHORT, bh, bw) if short is None else short) // 14 * 14
    d = DP._infer(model, np.ascontiguousarray(big), res)
    return d[pads[0][0]:pads[0][0] + h, pads[1][0]:pads[1][0] + w].astype(np.float32)


def guided(I: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    """He et al.'s guided filter, grey guide: p smoothed except where I has edges."""
    box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mI, mp = box(I), box(p)
    a = (box(I * p) - mI * mp) / (box(I * I) - mI * mI + eps)
    b = mp - a * mI
    return box(a) * I + box(b)


def norm(d: np.ndarray, a: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(d[a], [2, 98])
    return np.clip((hi - d) / max(hi - lo, 1e-6), 0, 1)  # near = 1


def edge_fit(n: np.ndarray, grey: np.ndarray, a: np.ndarray) -> float:
    gi = np.hypot(cv2.Sobel(grey, cv2.CV_32F, 1, 0), cv2.Sobel(grey, cv2.CV_32F, 0, 1))
    gd = np.hypot(cv2.Sobel(n, cv2.CV_32F, 1, 0), cv2.Sobel(n, cv2.CV_32F, 0, 1))
    strong = a & (gi >= np.percentile(gi[a], 95))
    return float(gd[strong].mean() / max(gd[a & ~strong].mean(), 1e-6))


def main():
    mesh, out = Path(sys.argv[1]), Path(sys.argv[2])
    model = DP.load()
    rows, stats = [], {}
    for spec in sys.argv[3:]:
        pid, fk = spec.split(":")
        L = next(l for l in json.loads((mesh / f"{pid}.cards.json").read_text())["layers"]
                 if l["kind"] == "backdrop" and l["frame"] == int(fk))
        back = np.asarray(Image.open(mesh / L["png"]).convert("RGB"))
        win = np.asarray(Image.open(mesh / L["window"]))[..., 3] > 0
        x0, y0 = L["window_bbox"][0] - L["bbox"][0], L["window_bbox"][1] - L["bbox"][1]
        rgb = np.ascontiguousarray(back[y0:y0 + win.shape[0], x0:x0 + win.shape[1]])
        grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        cols, labels = [rgb.copy()], [f"{pid[-4:]} f{fk} {rgb.shape[1]}x{rgb.shape[0]}"]
        cols[0][~win] = RED
        variants = []
        for name, short in (("native", None), ("700", 700), ("1008", 1008)):
            t = time.time()
            d = infer(model, rgb, short)
            variants.append((name, d, time.time() - t))
        d700 = variants[1][1]
        t = time.time()
        n700 = norm(d700, win)
        g = guided(grey, n700.astype(np.float32), r=max(4, round(0.01 * max(rgb.shape))), eps=1e-3)
        variants.append(("700+guided", None, variants[1][2] + time.time() - t))
        for name, d, secs in variants:
            n = g if d is None else norm(d, win)
            ef = edge_fit(n.astype(np.float32), grey, win)
            stats.setdefault(name, []).append(ef)
            c = np.dstack([n * 255] * 3).astype(np.uint8)
            c[~win] = RED
            cols.append(c)
            labels.append(f"{name}  {secs:.1f}s  edge fit {ef:.2f}")
        row = Image.fromarray(np.concatenate(cols, 1))
        s = ROW_H / row.height
        row = row.resize((round(row.width * s), ROW_H))
        dr = ImageDraw.Draw(row)
        x = 0
        for c, lab in zip(cols, labels):
            dr.rectangle([x, 0, x + round(c.shape[1] * s) - 1, 13], fill=(0, 0, 0))
            dr.text((x + 3, 1), lab, fill=(255, 255, 255))
            x += round(c.shape[1] * s)
        rows.append(row)
    W = max(r.width for r in rows)
    sheet = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sheet.paste(r, (0, j * (ROW_H + 6)))
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out)
    for k, v in stats.items():
        print(f"{k:12s} edge fit median {np.median(v):.2f}  ({', '.join(f'{x:.2f}' for x in v)})")
    print(out)


if __name__ == "__main__":
    main()
