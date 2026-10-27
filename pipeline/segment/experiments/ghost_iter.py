"""Local rounds on the merged backdrops (experiments/prefill_merged.py, FLUX already baked in, no API): remove the soft
ghosts. The 8% contact darkening is divided back out first. Per round:
- seam tone match: at the outline, the real background just outside minus the fill just inside (robust: bright or
  saturated pixels and outliers left out, offsets capped at CAP), spread smoothly inward and faded over the band;
- blob: the hidden interior refilled from the (matched) band and the background (membrane, so its tone continues the
  band's), with the band's brush texture (high-pass) mirrored in, fading over TEX px.
Scores: halo = local dE band vs real background; blotches = px the correction moved > 25 levels; blob step = dE across
the blob's edge; texture ratio = high-pass std in the blob near its edge over the band's (1 = same).

    uv run python experiments/ghost_iter.py <round name> [CAP] [TEX] [SAT]
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
from scipy.ndimage import binary_dilation, distance_transform_edt as edt

sys.path.insert(0, str(Path(__file__).resolve().parent))
import prefill_merged as PM  # noqa: E402
import shadow_fill as SF  # noqa: E402

ZUMI = Path("../../.data/out/chapters/pepper-carrot-39.zumi")
OUT = Path("../../.data/out/dataset/pepper-carrot-39")
R = Path("../../.data/out/dataset/erase_review")
BOXES = [9, 10, 19, 21, 26]
CLIP_PCT = float(sys.argv[5]) if len(sys.argv) > 5 else 0  # per-channel outlier clip of the seam offsets (0 = off)
RIM = 4  # px of band next to the blob the refill blends over (FLUX's dark contour there)
FLAT_LO, FLAT_HI = 2.0, 6.0  # local grey std (sigma 4 px): under LO the blob is our prefill (refilled), over HI FLUX's


def lab(a):
    return cv2.cvtColor(np.clip(a, 0, 255).astype(np.uint8)[None], cv2.COLOR_RGB2LAB)[0].astype(np.float32) * [100 / 255, 1, 1] - [0, 128, 128]


def seam_match(img, base, foot, page, d, reach, cap, sat_max, S=8.0):
    """base with the seam's tone offset spread inward. Returns (result, offset magnitude per px)."""
    hsv = cv2.cvtColor(img.astype(np.uint8), cv2.COLOR_RGB2HSV)
    ok = (img.max(-1) < 235) & (hsv[..., 1] < sat_max)  # no bright spots, no saturated accents in the measure
    src = ~binary_dilation(foot, iterations=4) & binary_dilation(foot, iterations=12) & ~page & ok
    inn = foot & (d >= 2) & (d <= 8) & (base.max(-1) < 235)

    def avg(a, m):
        w = cv2.GaussianBlur(m.astype(np.float32), (0, 0), S)
        return cv2.GaussianBlur(np.where(m[..., None], a, 0), (0, 0), S) / np.maximum(w, 1e-6)[..., None], w

    ro, wo = avg(img, src)
    ri, wi = avg(base, inn)
    seam = foot & (d <= 8) & (wo > 0.05) & (wi > 0.05)
    off = np.where(seam[..., None], ro - ri, 0).astype(np.float32)
    # outliers out: per-channel offsets beyond the seam's own 10-90 pct range are clipped to it, then capped
    if seam.any() and CLIP_PCT:
        lo, hi = np.percentile(off[seam], [CLIP_PCT, 100 - CLIP_PCT], axis=0)
        off = np.where(seam[..., None], np.clip(off, lo, hi), 0)
    off = np.clip(off, -cap, cap)
    w = cv2.GaussianBlur(seam.astype(np.float32), (0, 0), 2 * S)
    offs = cv2.GaussianBlur(off, (0, 0), 2 * S) / np.maximum(w, 1e-6)[..., None]
    fade = np.clip(1 - d / reach, 0, 1)[..., None]
    corr = offs * fade * foot[..., None]
    return np.clip(base + corr, 0, 255), np.abs(corr).max(-1)


def blob_refill(res, band, blob, page, tex):
    """The blob refilled: membrane from everything not blob (band included), plus the band's texture mirrored in."""
    if not blob.any() or tex <= 0:
        return res
    base = SF.membrane(res, ~blob & ~page)
    hp = res - cv2.GaussianBlur(res, (0, 0), 2.5)
    srcm = band & ~page
    dist, (iy, ix) = edt(~srcm, return_indices=True)
    Y, X = np.indices(blob.shape)
    ry, rx = np.clip(2 * iy - Y, 0, blob.shape[0] - 1), np.clip(2 * ix - X, 0, blob.shape[1] - 1)
    t = np.where(srcm[ry, rx][..., None], hp[ry, rx], hp[iy, ix])
    t *= np.clip(1 - dist / tex, 0, 1)[..., None]
    # only where the blob is still our flat prefill: where FLUX repainted it (textured) its work is kept
    # a 7 px median first: a thin line (FLUX's dark rim along its mask edge) is not texture to keep
    g = cv2.medianBlur(cv2.cvtColor(np.clip(res, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY), 7).astype(np.float32)
    sd = np.sqrt(np.maximum(cv2.GaussianBlur(g * g, (0, 0), 4) - cv2.GaussianBlur(g, (0, 0), 4) ** 2, 0))
    w = np.clip((FLAT_HI - sd) / (FLAT_HI - FLAT_LO), 0, 1) * blob
    # FLUX darkens the inner edge of what it fills (a thin dark contour on the band's side of the blob): the refill
    # also blends over RIM px of band next to the blob, fading out
    rim = band & (edt(~blob) <= RIM)
    w = np.maximum(w, rim * np.clip(1 - edt(~blob) / (RIM + 1), 0, 1) * (blob.any()))
    w = w[..., None]
    return res * (1 - w) + np.clip(base + t, 0, 255) * w


def score(img, res, before, foot, band, blob, page, d):
    blur = lambda a: cv2.GaussianBlur(a.astype(np.float32), (0, 0), 3)
    sel = band & (d >= 4) & (d <= 10)
    _, (iy, ix) = edt(~(~binary_dilation(foot, iterations=5) & ~page), return_indices=True)
    halo = float(np.median(np.linalg.norm(lab(blur(res)[sel]) - lab(blur(img)[iy[sel], ix[sel]]), axis=1)))
    blot = int((np.abs(res - before).max(-1)[foot] > 25).sum())
    inner, outer = blob & (edt(~band) <= 6), band & (edt(~blob) <= 6)
    step = float(np.linalg.norm(lab(res[inner]).mean(0) - lab(res[outer]).mean(0))) if inner.any() else 0.0
    hp = res - cv2.GaussianBlur(res.astype(np.float32), (0, 0), 2.5)
    tr = float(hp[inner].std() / max(hp[outer].std(), 1e-6)) if inner.any() else 1.0
    return halo, blot, step, tr


def main():
    name = sys.argv[1]
    cap = float(sys.argv[2]) if len(sys.argv) > 2 else 20
    tex = float(sys.argv[3]) if len(sys.argv) > 3 else 40
    sat = float(sys.argv[4]) if len(sys.argv) > 4 else 170
    SF.LEAN = 0.3 / 1.5
    z = zipfile.ZipFile(ZUMI)
    panels = json.loads(z.read("manifest.json"))["panels"]
    rows, tot = [], []
    for i in BOXES:
        pid = f"pepper-carrot-39-p{i:03d}"
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")).astype(np.float32)
        new = np.asarray(Image.open(R / f"merged-backdrop-p{i:03d}.png").convert("RGB")).astype(np.float32)
        cards, _ = SF.cards_of(json.loads((OUT / "parallax/mesh" / f"{pid}.cards.json").read_text()), OUT / "parallax/mesh")
        foot = np.logical_or.reduce([c["mask"] for c in cards])
        page = img.min(-1) >= 245
        d = edt(foot)
        band = np.zeros_like(foot)
        for c in cards:
            band |= c["mask"] & (d <= abs(c["shift"]) + 6)
        blob = foot & ~band
        ao = np.where(band, PM.AO * np.clip(1 - d / max(d[band].max(), 1), 0, 1), 0)
        base = np.where(foot[..., None], new / (1 - ao[..., None]), new)
        reach = max(abs(c["shift"]) + 6 for c in cards)
        res, mag = seam_match(img, base, foot, page, d, reach, cap, sat)
        seamed = res.copy()
        res = blob_refill(res, band, blob, page, tex)
        s0 = score(img, new, new, foot, band, blob, page, d)
        s1 = score(img, res, seamed, foot, band, blob, page, d)
        # blotches: where the seam correction itself moved a pixel more than 25 levels
        s1 = (s1[0], int((mag[foot] > 25).sum()), s1[2], s1[3])
        tot.append(s1)
        print(f"p{i:03d}: halo {s0[0]:.1f} -> {s1[0]:.1f}, blotches {s1[1]} px, blob step {s0[2]:.1f} -> {s1[2]:.1f}, "
              f"texture ratio {s0[3]:.2f} -> {s1[3]:.2f}")
        Image.fromarray(res.astype(np.uint8)).save(R / f"iter-{name}-p{i:03d}.png")
        rr = Image.fromarray(np.concatenate([new.astype(np.uint8), np.full((new.shape[0], 8, 3), 20, np.uint8),
                                             res.astype(np.uint8)], 1))
        s = 300 / rr.height
        rr = rr.resize((round(rr.width * s), 300))
        dr = ImageDraw.Draw(rr)
        dr.rectangle([0, 0, 200, 13], fill=(0, 0, 0))
        dr.text((3, 1), f"p{i:03d} merged", fill=(255, 255, 255))
        x = rr.width // 2 + 4
        dr.rectangle([x, 0, x + 260, 13], fill=(0, 0, 0))
        dr.text((x + 3, 1), f"round {name}", fill=(255, 255, 255))
        rows.append(rr)
    t = np.array(tot)
    print(f"round {name} (cap {cap}, tex {tex}, sat {sat}): median halo {np.median(t[:, 0]):.1f}, blotches "
          f"{int(t[:, 1].sum())} px, blob step {np.median(t[:, 2]):.1f}, texture ratio {np.median(t[:, 3]):.2f}")
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * 306), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * 306))
    sh.save(R / f"iter-{name}.png")


if __name__ == "__main__":
    main()
