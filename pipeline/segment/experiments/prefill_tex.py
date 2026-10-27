"""One FLUX Erase call per box, no seam between its fill and ours: the card interiors are prefilled to look like the
background before the call (tone from shadow_fill.membrane, brush texture from random real-background patches away
from every outline), so FLUX blends its band between real background and a textured prefill instead of drawing a
transition line against a smooth one. Then: FLUX's pixels kept only in the band and the ring (colour cast removed by a
per-channel fit outside the cards), the prefill everywhere else under the cards, the seam tone matched
(ghost_iter.seam_match), cards grown 3 px. Scores: halo (dE band vs real background), blob step (dE across the
band/interior edge) and contour (edge strength along that edge over the band's median edge strength; 1 = invisible).

    uv run python experiments/prefill_tex.py <sheet name> --panels 9,10,19,21,26
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt as edt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flux_erase as FE  # noqa: E402
import ghost_iter as GI  # noqa: E402
import shadow_fill as SF  # noqa: E402

RING = 3
PATCH, STEP = 48, 24   # texture patches and their spacing
TEX_GAIN = 0.5         # the borrowed texture's strength
CALM_PCT = 50          # sources only where the art's edge strength (blurred) is under this percentile: grain, not lines
FAR = 10               # px a texture source stays away from every card
NEAR = 200             # px: a patch comes from real background within this distance of where it goes
TEX_SIGMA = 3.0
TARGET = float(next((a.split("=")[1] for a in sys.argv if a.startswith("target=")), 0.55))  # FLUX mask share of the art
FEATHER = float(next((a.split("=")[1] for a in sys.argv if a.startswith("feather=")), 8))   # px of hand-over
ROW_H = 300


def textured_prefill(img, foot, page, rng):
    """Under the cards: the membrane fill's tone plus high-pass texture from random background patches nearby."""
    known = ~binary_dilation(foot, iterations=RING) & ~page
    base = SF.membrane(img, known)
    f = img.astype(np.float32)
    hp = f - cv2.GaussianBlur(f, (0, 0), TEX_SIGMA)
    src = known & ~binary_dilation(foot, iterations=FAR)
    gry = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    em = cv2.GaussianBlur(np.hypot(cv2.Sobel(gry, cv2.CV_32F, 1, 0), cv2.Sobel(gry, cv2.CV_32F, 0, 1)), (0, 0), 6)
    if src.any():
        src &= em < np.percentile(em[src], CALM_PCT)
    h, w = foot.shape
    r = PATCH // 2
    src[:r], src[-r:], src[:, :r], src[:, -r:] = False, False, False, False
    sy, sx = np.nonzero(src)
    acc = np.zeros_like(f)
    wsum = np.zeros((h, w), np.float32)
    win = np.outer(np.hanning(PATCH), np.hanning(PATCH)).astype(np.float32) + 1e-3
    if len(sy) == 0:
        return base
    for y in range(0, h, STEP):
        for x in range(0, w, STEP):
            y0, x0 = max(0, y - r), max(0, x - r)
            y1, x1 = min(h, y + r), min(w, x + r)
            if not foot[y0:y1, x0:x1].any():
                continue
            near = (np.abs(sy - y) < NEAR) & (np.abs(sx - x) < NEAR)
            k = rng.choice(np.flatnonzero(near)) if near.any() else rng.integers(len(sy))
            cy, cx = sy[k], sx[k]
            p = hp[cy - r:cy + r, cx - r:cx + r]
            if rng.random() < 0.5:  # random flips: repeated patches do not line up in blocks
                p = p[:, ::-1]
            if rng.random() < 0.5:
                p = p[::-1]
            wy0, wx0 = y0 - (y - r), x0 - (x - r)
            ww = win[wy0:wy0 + (y1 - y0), wx0:wx0 + (x1 - x0)]
            acc[y0:y1, x0:x1] += p[wy0:wy0 + (y1 - y0), wx0:wx0 + (x1 - x0)] * ww[..., None]
            wsum[y0:y1, x0:x1] += ww
    tex = acc / np.maximum(wsum, 1e-6)[..., None]
    return np.clip(base + TEX_GAIN * tex, 0, 255)


def cast_fit(got, ref, m):
    """Per channel, got -> ref by least squares on the pixels m (FLUX's colour cast)."""
    out = got.astype(np.float32).copy()
    for c in range(3):
        A = np.c_[got[m][:, c], np.ones(int(m.sum()))]
        k, *_ = np.linalg.lstsq(A, ref[m][:, c].astype(np.float64), rcond=None)
        out[..., c] = got[..., c] * k[0] + k[1]
    return out


def contour(res, band, blob):
    """Edge strength along the band/interior boundary over the band's median edge strength."""
    g = cv2.cvtColor(np.clip(res, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32)
    gm = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    edge = blob & ~binary_erosion(blob, iterations=2)
    inner_band = band & (edt(~blob) > 6) & (edt(~blob) < 20)
    if not edge.any() or not inner_band.any():
        return 1.0
    return float(np.median(gm[edge]) / max(np.median(gm[inner_band]), 1e-6))


def main():
    name = sys.argv[1]
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    SF.LEAN = 0.3 / 1.5
    z = zipfile.ZipFile(GI.ZUMI)
    panels = json.loads(z.read("manifest.json"))["panels"]
    rng = np.random.default_rng(0)
    rows = []
    for i in picks:
        pid = f"pepper-carrot-39-p{i:03d}"
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        cards, _ = SF.cards_of(json.loads((GI.OUT / "parallax/mesh" / f"{pid}.cards.json").read_text()), GI.OUT / "parallax/mesh")
        foot = np.logical_or.reduce([c["mask"] for c in cards])
        page = img.min(-1) >= 245
        d = edt(foot)
        band = np.zeros_like(foot)
        for c in cards:
            band |= c["mask"] & (d <= abs(c["shift"]) + 6)
        ring = binary_dilation(foot, iterations=RING) & ~foot & ~page
        ys, xs = np.nonzero(~page)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        # the band grown, frame by frame, while FLUX's mask stays under TARGET of that frame: structure comes from
        # FLUX in wide shots; a close-up (cards nearly filling it) keeps the minimum band and the textured prefill. The
        # whole box's share let close-up frames be masked whole: FLUX blanked one and invented a mountain in another
        cj = json.loads((GI.OUT / "parallax/mesh" / f"{pid}.cards.json").read_text())
        for L in cj["layers"]:
            if L["kind"] != "backdrop":
                continue
            fa = np.zeros_like(foot)
            wa = np.asarray(Image.open(GI.OUT / "parallax/mesh" / L["window"]))[..., 3] > 0
            wx0, wy0 = L["window_bbox"][:2]
            fa[wy0:wy0 + wa.shape[0], wx0:wx0 + wa.shape[1]] = wa
            fa &= ~page
            if not fa.any():
                continue
            share = lambda e: ((band | ring | (foot & (d <= e))) & fa).sum() / fa.sum()
            extra = 0
            while extra < 200 and share(extra + 8) < TARGET:
                extra += 8
            band |= foot & fa & (d <= extra)
        blob = foot & ~band
        raw = GI.R / f"{name}-raw-p{i:03d}.npz"
        if raw.exists():  # FLUX already paid for with this very mask: reuse
            cached = np.load(raw)
            pre, mask, g = cached["pre"], cached["mask"], cached["g"]
            line = "reused saved FLUX output"
        else:
            pre = np.where(blob[..., None], textured_prefill(img, foot, page, rng), img).astype(np.uint8)
            mask = band | ring
            _, got, line = FE.erase_panel(pre[y0:y1, x0:x1].copy(), mask[y0:y1, x0:x1])
            g = np.zeros_like(img, dtype=np.float32)
            g[y0:y1, x0:x1] = got
            np.savez_compressed(raw, pre=pre, mask=mask, g=g)
        fit_px = ~binary_dilation(foot, iterations=12) & ~page
        g = cast_fit(g, img, fit_px)
        # FLUX's pixels in the band, handed over to the prefill over FEATHER px at the band's inner edge
        db = edt(~blob)
        wt = np.where(mask, np.clip(db / FEATHER, 0, 1), 0)[..., None] if blob.any() else mask[..., None].astype(np.float32)
        res = g * wt + pre.astype(np.float32) * (1 - wt)
        res = np.where(foot[..., None] | ring[..., None], res, img.astype(np.float32))
        reach = max(abs(c["shift"]) + 6 for c in cards)
        res, _ = GI.seam_match(img.astype(np.float32), res, foot, page, d, reach, 30, 200)
        halo, _, step, _ = GI.score(img.astype(np.float32), res, res, foot, band, blob, page, d)
        ct = contour(res, band, blob)
        print(f"p{i:03d}: {line}\n  halo {halo:.1f}, blob step {step:.1f}, contour {ct:.2f}")
        Image.fromarray(res.astype(np.uint8)).save(GI.R / f"{name}-p{i:03d}.png")
        pf = GI.R / f"iter-r3-p{i:03d}.png"
        prev = np.asarray(Image.open(pf).convert("RGB")) if pf.exists() else img
        rr = Image.fromarray(np.concatenate([prev, np.full((img.shape[0], 8, 3), 20, np.uint8), res.astype(np.uint8)], 1))
        s = ROW_H / rr.height
        rr = rr.resize((round(rr.width * s), ROW_H))
        dr = ImageDraw.Draw(rr)
        dr.rectangle([0, 0, 200, 13], fill=(0, 0, 0))
        dr.text((3, 1), f"p{i:03d} round 3", fill=(255, 255, 255))
        x = rr.width // 2 + 4
        dr.rectangle([x, 0, x + 260, 13], fill=(0, 0, 0))
        dr.text((x + 3, 1), "textured prefill, one call", fill=(255, 255, 255))
        rows.append(rr)
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sh.save(GI.R / f"{name}.png")
    print(GI.R / f"{name}.png", f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
