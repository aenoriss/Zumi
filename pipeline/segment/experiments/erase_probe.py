"""Why FLUX Erase fails on crowded boxes: the same box sent alone (no second copy packed beside it) with the whole mask,
and with a band mask (only BAND px inside each card's outline, what a head move uncovers). Shows each raw output, the
share of green in it (the model's blank output on p20 and p23) and the plate.

    uv run python experiments/erase_probe.py <episode.zumi> <out dir> <sheet path> 20:whole 20:band 7:band 23:band
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import distance_transform_edt

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import flux_erase as FE  # noqa: E402

BAND = 40
ROW_H = 300


def green(a: np.ndarray) -> np.ndarray:
    a = a.astype(int)
    return (a[..., 1] > a[..., 0] + 60) & (a[..., 1] > a[..., 2] + 60)


def main():
    zumi, out, sheet = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    z = zipfile.ZipFile(zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    rows = []
    for spec in sys.argv[4:]:
        i, how = spec.split(":")
        i = int(i)
        pid = f"{zumi.stem}-p{i:03d}"
        d = out / "parallax" / "plates" / pid
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        kind = "all" if (d / "plate-all.png").exists() else "full"
        whole = np.asarray(Image.open(d / f"mask-{kind}.png")) > 0
        # the mask is on the art's crop: the box minus its white page border
        ys, xs = np.nonzero(img.min(-1) < 245)
        y0, x0 = ys.min(), xs.min()
        crop = img[y0:y0 + whole.shape[0], x0:x0 + whole.shape[1]].copy()
        if how in ("band", "prefill"):
            cj = json.loads((out / "parallax" / "mesh" / f"{pid}.cards.json").read_text())
            foot = np.zeros(img.shape[:2], bool)
            for l in cj["layers"]:
                if l["kind"] == "backdrop":
                    continue
                a = np.asarray(Image.open(out / "parallax" / "mesh" / l["png"]))[..., 3] > 127
                bx0, by0, bx1, by1 = l["bbox"]
                sl = (slice(max(0, by0), min(img.shape[0], by1)), slice(max(0, bx0), min(img.shape[1], bx1)))
                foot[sl] |= a[sl[0].start - by0:sl[0].stop - by0, sl[1].start - bx0:sl[1].stop - bx0]
            band = foot & (distance_transform_edt(foot) <= BAND)
            m = band[y0:y0 + whole.shape[0], x0:x0 + whole.shape[1]]
            if how == "prefill":  # inside the band the cards' interiors painted over with the surrounding colour
                import shadow_fill as SF
                fill = SF.membrane(img, ~foot & (img.min(-1) < 245)).clip(0, 255).astype(np.uint8)
                inner = (foot & ~band)[y0:y0 + whole.shape[0], x0:x0 + whole.shape[1]]
                crop[inner] = fill[y0:y0 + whole.shape[0], x0:x0 + whole.shape[1]][inner]
        else:
            m = whole
        plate, got, line = FE.erase_panel(crop, m)
        print(f"p{i:03d} {how}: mask {m.mean():.0%}; {line}; green in holes {green(got)[m].mean():.0%}, "
              f"outside {green(got)[~m].mean():.0%}")
        vis = crop.copy()
        vis[m] = (0.4 * vis[m] + 0.6 * np.array([230, 30, 30])).astype(np.uint8)
        cols = [(vis, f"p{i:03d} {how} mask {m.mean():.0%}"), (got, f"raw (green {green(got)[m].mean():.0%} of holes)"),
                (plate, "plate")]
        r = Image.fromarray(np.concatenate([c for c, _ in cols], 1))
        s = ROW_H / r.height
        r = r.resize((round(r.width * s), ROW_H))
        dr = ImageDraw.Draw(r)
        for j, (c, t) in enumerate(cols):
            x = round(j * c.shape[1] * s)
            dr.rectangle([x, 0, x + 230, 13], fill=(0, 0, 0))
            dr.text((x + 3, 1), t, fill=(255, 255, 255))
        rows.append(r)
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sh.save(sheet)
    print(sheet, f"BFL spend today {FE.spent_today():.2f} USD")


if __name__ == "__main__":
    main()
