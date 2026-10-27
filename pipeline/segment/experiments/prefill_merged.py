"""The prefill erase merged with docs/research/disocclusion-established-2026-10.md, against the plate the pipeline has:
- card interiors painted with the smooth fill of the background only (shadow_fill.membrane), its source pixels not
  within RING px of any card (the outline's mixed pixels are dropped, not copied);
- the erase mask a band per card, its 30 cm lean shift + 6 px wide, plus the RING px outside the outline; one FLUX
  Erase call per box, alone;
- cards grown GROW px, fully opaque inside (the 0.8 px feather let the fill show through at rest);
- a faint contact darkening AO along each card's outline in the band.
Shows each box at rest and on a 30 cm lean, now against merged, and prints the rest-view difference from the art.

    uv run python experiments/prefill_merged.py <episode.zumi> <out dir> <sheet path> --panels 9,10,19,21,26
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
from scipy.ndimage import binary_dilation, distance_transform_edt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flux_erase as FE  # noqa: E402
import shadow_fill as SF  # noqa: E402

RING = 3     # px around every card dropped from the fill's sources and added to the erase mask
GROW = 2     # px each card is grown, opaque
AO = 0.08    # contact darkening at the outline, fading over the band
ROW_H = 280


def grown_cards(img: np.ndarray, cards: list[dict]) -> list[dict]:
    """Each card grown GROW px (opaque, the art's own pixels in the ring), a 1 px soft edge outside."""
    out = []
    for c in cards:
        m = binary_dilation(c["mask"], iterations=GROW)
        a = np.clip(cv2.GaussianBlur(binary_dilation(m, iterations=1).astype(np.float32), (0, 0), 0.6), 0, 1)
        a[m] = 1.0
        ys, xs = np.nonzero(a > 0.01)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        rgba = np.dstack([img[y0:y1, x0:x1], (a[y0:y1, x0:x1] * 255).astype(np.uint8)])
        out.append({**c, "mask": m, "rgba": rgba, "bbox": [x0, y0, x1, y1]})
    return out


def lean_raw(back: np.ndarray, cards: list[dict], scale: float) -> np.ndarray:
    keep = SF.LEAN
    SF.LEAN *= scale
    try:
        if scale == 0:
            for c in cards:
                c["_s"], c["shift"] = c["shift"], 0.0
        return SF.lean(back, cards)
    finally:
        SF.LEAN = keep
        for c in cards:
            if "_s" in c:
                c["shift"] = c.pop("_s")


def main():
    zumi, out, sheet = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    z = zipfile.ZipFile(zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    SF.LEAN = 0.3 / 1.5
    rows = []
    for i in picks:
        pid = f"{zumi.stem}-p{i:03d}"
        d, mesh = out / "parallax" / "plates" / pid, out / "parallax" / "mesh"
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        cards, _ = SF.cards_of(json.loads((mesh / f"{pid}.cards.json").read_text()), mesh)
        foot = np.logical_or.reduce([c["mask"] for c in cards])
        page = img.min(-1) >= 245
        # today: the saved plate under the cards, the cards as they are
        kind = "all" if (d / "plate-all.png").exists() else "full"
        old_plate = np.asarray(Image.open(d / f"plate-{kind}.png").convert("RGB").resize(img.shape[1::-1]))
        old = np.where(binary_dilation(foot, iterations=2)[..., None], old_plate, img)
        # merged
        dist = distance_transform_edt(foot)
        band = np.zeros_like(foot)
        for c in cards:
            band |= c["mask"] & (dist <= abs(c["shift"]) + 6)
        ring = binary_dilation(foot, iterations=RING) & ~foot & ~page
        fill = SF.membrane(img, ~foot & ~ring & ~page).clip(0, 255).astype(np.uint8)
        pre = np.where((foot & ~band)[..., None], fill, img)
        mask = band | ring
        ys, xs = np.nonzero(~page)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        plate, got, line = FE.erase_panel(pre[y0:y1, x0:x1].copy(), mask[y0:y1, x0:x1])
        new = img.copy()
        new[y0:y1, x0:x1] = plate
        under = binary_dilation(foot, iterations=RING + GROW)
        new = np.where(under[..., None], new, img)
        # faint contact darkening: strongest at the outline, gone at the band's inner edge
        ao = np.where(band, AO * np.clip(1 - dist / np.maximum(dist[band].max() if band.any() else 1, 1), 0, 1), 0)
        new = (new.astype(np.float32) * (1 - ao[..., None])).astype(np.uint8)
        gcards = grown_cards(img, cards)
        rest_old = lean_raw(old, cards, 0)
        rest_new = lean_raw(new, gcards, 0)
        art = ~page
        d_old = np.abs(rest_old.astype(int) - img).max(-1)[art]
        d_new = np.abs(rest_new.astype(int) - img).max(-1)[art]
        print(f"p{i:03d}: mask {mask[y0:y1, x0:x1].mean():.0%} (whole was {foot.mean():.0%}); {line}")
        print(f"  at rest vs the art: now max {d_old.max()} on {(d_old > 20).sum()} px, merged max {d_new.max()} on "
              f"{(d_new > 20).sum()} px")
        cols = [(SF.lean(old, cards), f"p{i:03d} lean 30 cm, now"), (SF.lean(new, gcards), "lean 30 cm, merged"),
                (old, "backdrop now"), (new, "backdrop merged")]
        r = Image.fromarray(np.concatenate([c for c, _ in cols], 1))
        s = ROW_H / r.height
        r = r.resize((round(r.width * s), ROW_H))
        dr = ImageDraw.Draw(r)
        for j, (c, t) in enumerate(cols):
            x = round(j * c.shape[1] * s)
            dr.rectangle([x, 0, x + 200, 13], fill=(0, 0, 0))
            dr.text((x + 3, 1), t, fill=(255, 255, 255))
        rows.append(r)
        Image.fromarray(new).save(sheet.parent / f"merged-backdrop-p{i:03d}.png")
        Image.fromarray(SF.lean(new, gcards)).save(sheet.parent / f"merged-lean-p{i:03d}.png")
        Image.fromarray(SF.lean(old, cards)).save(sheet.parent / f"now-lean-p{i:03d}.png")
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sh.save(sheet)
    print(sheet, f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
