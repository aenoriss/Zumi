"""Finer background depth by tiles: DA3MONO on overlapping tiles of a backdrop (n x n, half-overlapping, each at
700 px short side, so the model sees each part larger), every tile fitted (scale and shift, robust) to one pass on
the whole frame and blended with tent weights: the whole-frame pass keeps the broad shape, the tiles add the detail.
No contrast boost. Compared with the relief the pipeline writes now (one pass, detail doubled, cards.backdrop_relief).
Each map normalised over the frame (2-98th pct, white = near), with the edge fit of experiments/backdrop_res.py.

    uv run python experiments/backdrop_tiles.py <mesh dir> <sheet path> pepper-carrot-39-p002:0 ...
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
import cards as CD  # noqa: E402
import depth as DP  # noqa: E402
from backdrop_res import edge_fit, infer, norm  # noqa: E402

ROW_H = 260
RED = (128, 40, 40)


def tiled(model, rgb: np.ndarray, area: np.ndarray, whole: np.ndarray, n: int) -> np.ndarray:
    h, w = rgb.shape[:2]
    th, tw = min(h, int(np.ceil(2 * h / (n + 1)))), min(w, int(np.ceil(2 * w / (n + 1))))
    acc, wsum = np.zeros((h, w), np.float64), np.zeros((h, w), np.float64)
    ramp = lambda k: np.minimum(np.arange(k) + 1, k - np.arange(k)).astype(np.float64)
    tent = ramp(th)[:, None] * ramp(tw)[None, :]
    for y in np.linspace(0, h - th, n).round().astype(int):
        for x in np.linspace(0, w - tw, n).round().astype(int):
            sl = np.s_[y:y + th, x:x + tw]
            d = infer(model, np.ascontiguousarray(rgb[sl]), 700).astype(np.float64)
            v = area[sl]
            if v.sum() < 200:
                d = whole[sl].astype(np.float64)
            else:
                s, t = DP._robust_fit(d[v], whole[sl][v].astype(np.float64))
                d = s * d + t
            acc[sl] += d * tent
            wsum[sl] += tent
    return (acc / np.maximum(wsum, 1e-9)).astype(np.float32)


def relief_like(d: np.ndarray, a: np.ndarray) -> np.ndarray:
    """cards.backdrop_relief without the boost: the small blur, normalised, near = 1."""
    d = cv2.GaussianBlur(d, (0, 0), max(0.5, CD.BACK_BLUR * max(d.shape)))
    return np.clip(norm(d, a), 0, 1)


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
        sl = np.s_[y0:y0 + win.shape[0], x0:x0 + win.shape[1]]
        rgb = np.ascontiguousarray(back[sl])
        grey = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        latest = np.asarray(Image.open(mesh / L["relief"]), np.float32)[sl] / 255
        whole = infer(model, rgb, None)
        maps = [("latest (1 pass, detail x2)", latest, 0.0)]
        for n in (2, 3):
            t = time.time()
            maps.append((f"tiles {n}x{n}, restitched", relief_like(tiled(model, rgb, win, whole, n), win), time.time() - t))
        c0 = rgb.copy()
        c0[~win] = RED
        cols, labels = [c0], [f"{pid[-4:]} f{fk} {rgb.shape[1]}x{rgb.shape[0]}"]
        for name, m, secs in maps:
            ef = edge_fit(m.astype(np.float32), grey, win)
            stats.setdefault(name, []).append(ef)
            c = np.dstack([m * 255] * 3).astype(np.uint8)
            c[~win] = RED
            cols.append(c)
            labels.append(f"{name}  edge fit {ef:.2f}" + (f"  {secs:.1f}s" if secs else ""))
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
    sheet.save(out)
    for k, v in stats.items():
        print(f"{k:28s} edge fit median {np.median(v):.2f}  ({', '.join(f'{x:.2f}' for x in v)})")
    print(out)


if __name__ == "__main__":
    main()
