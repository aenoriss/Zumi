"""Per-FRAME erase: each frame of a box cropped (its window grown 14 px) and sent alone, flat prefill of the card
interiors, band mask (each card's 30 cm lean shift + 6 px, no ring), FLUX's raw output used under the cards, colour
cast fit and seam tone match as prefill_raw. Both placeholder detectors on every frame. Sheet: source | per box
(prefill_raw's raw1) | per frame. Saved outputs (<name>-raw-pNNN-fK.npz) are reused, so a rerun costs nothing.

    uv run python experiments/prefill_frame.py <name> --panels 10,18,26,23
"""
from __future__ import annotations

import io
import json
import sys
import zipfile

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt as edt

import flux_erase as FE
import ghost_iter as GI
import prefill_tex as PT
import shadow_fill as SF

GROW = 14
ROW_H = 300


def detect(g, m, img):
    """(texture ratio, flat share, colour seen, verdict): a placeholder is a fill with under TEX_MIN of the real
    background's texture, or over 40% one flat colour absent from the scene."""
    g8 = np.clip(g, 0, 255).astype(np.uint8)
    gray = lambda a: cv2.cvtColor(a, cv2.COLOR_RGB2GRAY).astype(np.float32)
    tex = lambda a, mm: float(np.median(np.sqrt(np.maximum(cv2.blur(gray(a) ** 2, (7, 7)) - cv2.blur(gray(a), (7, 7)) ** 2, 0))[mm])) if mm.any() else 0.0
    inner = m & ~binary_dilation(~m, iterations=6)
    ref = ~m & ~binary_dilation(m, iterations=4)
    ratio = tex(g8, inner) / max(tex(img, ref), 1e-6)
    q = (g8[m] // 8).astype(int)
    key = q[:, 0] * 1024 + q[:, 1] * 32 + q[:, 2]
    mode = np.bincount(key).argmax()
    col = np.array([mode // 1024, (mode // 32) % 32, mode % 32]) * 8 + 4
    sd = np.sqrt(np.maximum(cv2.blur(gray(g8) ** 2, (9, 9)) - cv2.blur(gray(g8), (9, 9)) ** 2, 0))
    flat = float(((np.abs(g8.astype(int) - col).max(-1) < 14) & (sd < 3))[m].mean())
    seen = float((np.abs(img.astype(int) - col).max(-1) < 20)[~m].mean())
    bad = ratio < 0.12 or (flat > 0.4 and seen < 0.02)
    return ratio, flat, seen, "FAIL" if bad else "ok"


def main():
    name = sys.argv[1]
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    SF.LEAN = 0.3 / 1.5
    z = zipfile.ZipFile(GI.ZUMI)
    panels = json.loads(z.read("manifest.json"))["panels"]
    rows = []
    for i in picks:
        pid = f"pepper-carrot-39-p{i:03d}"
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        cj = json.loads((GI.OUT / "parallax/mesh" / f"{pid}.cards.json").read_text())
        cards, _ = SF.cards_of(cj, GI.OUT / "parallax/mesh")
        foot = np.logical_or.reduce([c["mask"] for c in cards])
        d = edt(foot)
        band = np.zeros_like(foot)
        for c in cards:
            band |= c["mask"] & (d <= abs(c["shift"]) + 6)
        res = img.astype(np.float32).copy()
        for L in cj["layers"]:
            if L["kind"] != "backdrop":
                continue
            k = L["frame"]
            wa = np.asarray(Image.open(GI.OUT / "parallax/mesh" / L["window"]))[..., 3] > 0
            fa = np.zeros(foot.shape, bool)
            wx0, wy0 = L["window_bbox"][:2]
            fa[wy0:wy0 + wa.shape[0], wx0:wx0 + wa.shape[1]] = wa
            # the crop is the frame's box grown GROW px; the frame area is its window (cut 12 px inside the frame,
            # cards.INSET) grown back out to the same box
            fa = binary_dilation(fa, iterations=GROW + 12)
            bx0, by0, bx1, by1 = L["window_bbox"]
            y0, y1 = max(0, by0 - GROW), min(img.shape[0], by1 + GROW)
            x0, x1 = max(0, bx0 - GROW), min(img.shape[1], bx1 + GROW)
            fa[:y0], fa[y1:], fa[:, :x0], fa[:, x1:] = False, False, False, False
            sl = np.s_[y0:y1, x0:x1]
            fimg, ffoot, fband, ffa = img[sl], foot[sl] & fa[sl], band[sl] & fa[sl], fa[sl]
            if not ffoot.any():
                continue
            raw = GI.R / f"{name}-raw-p{i:03d}-f{k}.npz"
            if raw.exists():
                got, line = np.load(raw)["g"], "reused saved output"
            else:
                fill = SF.membrane(fimg, ffa & ~ffoot).clip(0, 255).astype(np.uint8)
                pre = np.where((ffoot & ~fband)[..., None], fill, fimg)
                _, got, line = FE.erase_panel(pre.copy(), fband)
                np.savez_compressed(raw, g=got, mask=fband)
            ratio, flat, seen, v = detect(got, fband, fimg)
            print(f"p{i:03d} f{k} ({x1 - x0}x{y1 - y0}, mask {fband.mean():.0%}): {line}; texture {ratio:.2f}, flat {flat:.2f}, seen {seen:.3f} -> {v}")
            g = PT.cast_fit(got.astype(np.float32), fimg, ffa & ~binary_dilation(ffoot, iterations=12))
            res[sl] = np.where(ffoot[..., None], g, res[sl])
        page = img.min(-1) >= 245
        reach = max(abs(c["shift"]) + 6 for c in cards)
        res, _ = GI.seam_match(img.astype(np.float32), res, foot, page, d, reach, 30, 200)
        out = res.astype(np.uint8)
        Image.fromarray(out).save(GI.R / f"{name}-p{i:03d}.png")
        pb = GI.R / f"raw1-p{i:03d}.png"
        perbox = np.asarray(Image.open(pb).convert("RGB")) if pb.exists() else np.full_like(img, 40)
        sep = np.full((img.shape[0], 8, 3), 20, np.uint8)
        rr = Image.fromarray(np.concatenate([img, sep, perbox, sep, out], 1))
        s = ROW_H / rr.height
        rr = rr.resize((round(rr.width * s), ROW_H))
        dr = ImageDraw.Draw(rr)
        w3 = rr.width // 3
        for j, t in enumerate([f"p{i:03d} source", "per box (one call)", "per frame (one call each)"]):
            dr.rectangle([j * w3, 0, j * w3 + 200, 13], fill=(0, 0, 0))
            dr.text((j * w3 + 3, 1), t, fill=(255, 255, 255))
        rows.append(rr)
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sh.save(GI.R / f"{name}.png")
    print(GI.R / f"{name}.png", f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
