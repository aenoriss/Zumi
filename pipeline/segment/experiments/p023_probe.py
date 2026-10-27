"""Two decisive probes on P&C 39 p23 (FLUX Erase answered a flat placeholder in 7 of 10 runs, and no input variable
separated the runs that worked): (a) the exact saved input of a run that worked (tex4: pre + mask) sent again, byte
for byte: a failure means the model is unstable on this box; (b) each frame sent alone: a failure of one frame only
means the scene content drives it. Prints the placeholder check for each.

    uv run python experiments/p023_probe.py resend | frames
"""
from __future__ import annotations

import io
import json
import sys
import zipfile

import cv2
import numpy as np
from PIL import Image

import flux_erase as FE
import ghost_iter as GI


def check(g, m, img):
    g = g.clip(0, 255).astype(np.uint8)
    q = (g[m] // 8).astype(int)
    key = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    mode = np.bincount(key).argmax()
    col = np.array([mode // 1024, (mode // 32) % 32, mode % 32]) * 8 + 4
    gr = cv2.cvtColor(g, cv2.COLOR_RGB2GRAY).astype(np.float32)
    sd = np.sqrt(np.maximum(cv2.blur(gr * gr, (9, 9)) - cv2.blur(gr, (9, 9)) ** 2, 0))
    flat = float(((np.abs(g.astype(int) - col).max(-1) < 14) & (sd < 3))[m].mean())
    seen = float((np.abs(img.astype(int) - col).max(-1) < 20)[~m].mean())
    return flat, seen, col, ("FAIL" if flat > 0.4 and seen < 0.02 else "ok")


def main():
    mode = sys.argv[1]
    z = zipfile.ZipFile(GI.ZUMI)
    panels = json.loads(z.read("manifest.json"))["panels"]
    img = np.asarray(Image.open(io.BytesIO(z.read(panels[23]["layers"][0]["image"]))).convert("RGB"))
    c = np.load(GI.R / "tex4-raw-p023.npz")
    pre, mask = c["pre"], c["mask"]
    page = img.min(-1) >= 245
    ys, xs = np.nonzero(~page)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    if mode == "resend":
        _, got, line = FE.erase_panel(pre[y0:y1, x0:x1].copy(), mask[y0:y1, x0:x1])
        fl, se, col, v = check(got, mask[y0:y1, x0:x1], img[y0:y1, x0:x1])
        print(f"resend of tex4 input: {line}\n  flat {fl:.2f}, colour seen {se:.3f}, {col} -> {v}")
        Image.fromarray(got.clip(0, 255).astype(np.uint8)).save(GI.R / "p023-resend.png")
    else:
        cj = json.loads((GI.OUT / "parallax/mesh/pepper-carrot-39-p023.cards.json").read_text())
        outs = []
        for L in cj["layers"]:
            if L["kind"] != "backdrop":
                continue
            fx0, fy0, fx1, fy1 = L["window_bbox"]
            fx0, fy0, fx1, fy1 = max(0, fx0 - 14), max(0, fy0 - 14), min(img.shape[1], fx1 + 14), min(img.shape[0], fy1 + 14)
            sub, sm = pre[fy0:fy1, fx0:fx1].copy(), mask[fy0:fy1, fx0:fx1]
            _, got, line = FE.erase_panel(sub, sm)
            fl, se, col, v = check(got, sm, img[fy0:fy1, fx0:fx1])
            print(f"frame {L['frame']} alone ({sub.shape[1]}x{sub.shape[0]}, mask {sm.mean():.0%}): {line}\n  flat {fl:.2f}, colour seen {se:.3f}, {col} -> {v}")
            outs.append(np.concatenate([img[fy0:fy1, fx0:fx1], np.full((fy1 - fy0, 6, 3), 20, np.uint8), got.clip(0, 255).astype(np.uint8)], 1))
        h = max(o.shape[0] for o in outs)
        sheet = np.full((h, sum(o.shape[1] + 10 for o in outs), 3), 20, np.uint8)
        x = 0
        for o in outs:
            sheet[:o.shape[0], x:x + o.shape[1]] = o
            x += o.shape[1] + 10
        Image.fromarray(sheet).save(GI.R / "p023-frames.png")
    print(f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
