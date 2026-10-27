"""The prefill erase (experiments/erase_probe.py "prefill": card interiors painted with the surrounding colour, only a
BAND px strip inside each card's outline erased, one call per box) against the plate the pipeline has, as backdrops and
on a simulated 30 cm lean (shadow_fill.lean: each card slid over the backdrop by its parallax).

    uv run python experiments/prefill_lean.py <episode.zumi> <out dir> <sheet path> --panels 8,14,15,18,24
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import flux_erase as FE  # noqa: E402
import shadow_fill as SF  # noqa: E402

BAND = 40
ROW_H = 260


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
        # today's backdrop: the saved plate under the cards
        kind = "all" if (d / "plate-all.png").exists() else "full"
        old_plate = np.asarray(Image.open(d / f"plate-{kind}.png").convert("RGB").resize(img.shape[1::-1]))
        under = binary_dilation(foot, iterations=2)
        old = np.where(under[..., None], old_plate, img)
        # prefill: interiors painted with the surrounding colour, only the band erased, the box's art alone
        band = foot & (distance_transform_edt(foot) <= BAND)
        fill = SF.membrane(img, ~foot & ~page).clip(0, 255).astype(np.uint8)
        pre = np.where((foot & ~band)[..., None], fill, img)
        ys, xs = np.nonzero(~page)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        plate, got, line = FE.erase_panel(pre[y0:y1, x0:x1].copy(), band[y0:y1, x0:x1])
        new = img.copy()
        new[y0:y1, x0:x1] = plate
        new = np.where(under[..., None], new, img)
        print(f"p{i:03d}: band {band[y0:y1, x0:x1].mean():.0%} of the art (whole mask was {foot.mean():.0%}); {line}")
        cols = [(SF.lean(old, cards), f"p{i:03d} lean 30 cm, backdrop now"), (SF.lean(new, cards), "lean 30 cm, prefill"),
                (old, "backdrop now (cards off)"), (new, "prefill backdrop (cards off)")]
        r = Image.fromarray(np.concatenate([c for c, _ in cols], 1))
        s = ROW_H / r.height
        r = r.resize((round(r.width * s), ROW_H))
        dr = ImageDraw.Draw(r)
        for j, (c, t) in enumerate(cols):
            x = round(j * c.shape[1] * s)
            dr.rectangle([x, 0, x + 220, 13], fill=(0, 0, 0))
            dr.text((x + 3, 1), t, fill=(255, 255, 255))
        rows.append(r)
        Image.fromarray(new).save(sheet.parent / f"prefill-backdrop-p{i:03d}.png")
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sh.save(sheet)
    print(sheet, f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
