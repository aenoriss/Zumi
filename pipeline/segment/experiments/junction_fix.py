"""Local, no API: remove the contour FLUX draws where its band meets our prefill (it reads the meeting as an object edge
and outlines it). On a saved FLUX output (prefill_tex.py's <name>-raw-pNNN.npz): FLUX's pixels are dropped within
DROP px of the interior, and the interior plus that strip are refilled from FLUX's own band: tone by membrane
interpolation, texture by random patches of the band's high-pass (no mirroring, so no echoed outlines).

    uv run python experiments/junction_fix.py <name> 9,10,19
"""
from __future__ import annotations

import io
import json
import sys
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt as edt

import ghost_iter as GI
import prefill_tex as PT
import shadow_fill as SF

DROP = 14


GRAIN = (0.8, 2.0)  # band-pass sigmas: paper and brush grain only, no strokes (a plain high-pass copied FLUX's
                    # cracked-plaster strokes into every interior, P&C 39 p7, p18, p23)
GAIN = 0.35
LIGHT_FRAC = 0.9    # a fill source brighter than this (bubble white, the page) is not background


def band_texture(res, src, hole, rng, patch=40, step=20, gain=GAIN):
    """Grain over `hole` from random patches of `res` inside `src` (no mirroring)."""
    f = res.astype(np.float32)
    hp = cv2.GaussianBlur(f, (0, 0), GRAIN[0]) - cv2.GaussianBlur(f, (0, 0), GRAIN[1])
    h, w = hole.shape
    r = patch // 2
    s = src.copy()
    s[:r], s[-r:], s[:, :r], s[:, -r:] = False, False, False, False
    s &= binary_erosion(src, iterations=r // 2)
    # grain only: sources where the band's edge strength is low (no strokes, no marks to repeat)
    gry = cv2.cvtColor(np.clip(res, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    em = cv2.GaussianBlur(np.hypot(cv2.Sobel(gry, cv2.CV_32F, 1, 0), cv2.Sobel(gry, cv2.CV_32F, 0, 1)), (0, 0), 8)
    if s.any():
        s &= em < np.percentile(em[s], 40)
    sy, sx = np.nonzero(s)
    if len(sy) == 0:
        return np.zeros_like(f)
    win = np.outer(np.hanning(patch), np.hanning(patch)).astype(np.float32) + 1e-3
    acc, ws = np.zeros_like(f), np.zeros((h, w), np.float32)
    for y in range(0, h, step):
        for x in range(0, w, step):
            y0, x0, y1, x1 = max(0, y - r), max(0, x - r), min(h, y + r), min(w, x + r)
            if not hole[y0:y1, x0:x1].any():
                continue
            near = (np.abs(sy - y) < 200) & (np.abs(sx - x) < 200)
            k = rng.choice(np.flatnonzero(near)) if near.any() else rng.integers(len(sy))
            p = hp[sy[k] - r:sy[k] + r, sx[k] - r:sx[k] + r]
            if rng.random() < 0.5:
                p = p[:, ::-1]
            wy0, wx0 = y0 - (y - r), x0 - (x - r)
            ww = win[wy0:wy0 + y1 - y0, wx0:wx0 + x1 - x0]
            acc[y0:y1, x0:x1] += p[wy0:wy0 + y1 - y0, wx0:wx0 + x1 - x0] * ww[..., None]
            ws[y0:y1, x0:x1] += ww
    return gain * acc / np.maximum(ws, 1e-6)[..., None]


def main():
    name, picks = sys.argv[1], [int(v) for v in sys.argv[2].split(",")]
    SF.LEAN = 0.3 / 1.5
    z = zipfile.ZipFile(GI.ZUMI)
    panels = json.loads(z.read("manifest.json"))["panels"]
    rng = np.random.default_rng(1)
    rows = []
    for i in picks:
        pid = f"pepper-carrot-39-p{i:03d}"
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        cards, _ = SF.cards_of(json.loads((GI.OUT / "parallax/mesh" / f"{pid}.cards.json").read_text()), GI.OUT / "parallax/mesh")
        foot = np.logical_or.reduce([c["mask"] for c in cards])
        page = img.min(-1) >= 245
        c = np.load(GI.R / f"{name}-raw-p{i:03d}.npz")
        mask, g = c["mask"], c["g"].astype(np.float32)
        g = PT.cast_fit(g, img, ~binary_dilation(foot, iterations=12) & ~page)
        blob = foot & ~mask
        hole = foot & (blob | (edt(~blob) <= DROP)) if blob.any() else np.zeros_like(foot)
        res = np.where(mask[..., None], g, img.astype(np.float32))
        # bubble white stays out of every fill source: the lettering cards' own pixels, and anything near-white
        letters = np.logical_or.reduce([cc["mask"] for cc in cards if cc["kind"] == "lettering"] or [np.zeros_like(foot)])
        light = res.min(-1) > 255 * LIGHT_FRAC
        clean = ~page & ~binary_dilation(letters, iterations=4) & ~light
        # under a bubble the fill is the background's, never its white: the bubble region joins the hole
        hole = hole | (letters & foot)
        good = ~hole & clean & (mask | ~foot)  # FLUX's band away from the meeting, and real background
        if hole.any():
            base = SF.membrane(res, good)
            tex = band_texture(res, mask & ~hole & clean, hole, rng)
            res = np.where(hole[..., None], np.clip(base + tex, 0, 255), res)
        d = edt(foot)
        reach = max(abs(cc["shift"]) + 6 for cc in cards)
        res, _ = GI.seam_match(img.astype(np.float32), res, foot, page, d, reach, 30, 200)
        band = mask & foot
        halo, _, step, _ = GI.score(img.astype(np.float32), res, res, foot, band, blob, page, d)
        ct = PT.contour(res, band & ~hole, hole) if hole.any() else 1.0
        print(f"p{i:03d} ({name}): halo {halo:.1f}, contour {ct:.2f}")
        out = res.astype(np.uint8)
        Image.fromarray(out).save(GI.R / f"{name}-fixed-p{i:03d}.png")
        rr = Image.fromarray(out)
        rr = rr.resize((round(rr.width * 300 / rr.height), 300))
        ImageDraw.Draw(rr).text((4, 2), f"p{i:03d} {name} + junction fix", fill=(255, 255, 255))
        rows.append(rr)
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * 306), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * 306))
    sh.save(GI.R / f"{name}-fixed.png")


if __name__ == "__main__":
    main()
