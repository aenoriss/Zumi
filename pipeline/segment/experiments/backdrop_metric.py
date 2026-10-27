"""DA3METRIC vs DA3MONO on the backdrop, for the frames whose backdrop gets relief. One row per frame: the backdrop
(erased under the cards and lettering), DA3METRIC on it (what its relief comes from) and DA3MONO on it, each
normalised over the frame, 2-98th percentiles, white = near. Runs the normal layers step (--from-masks) and records
what cards sees. Written while episode.py passed DA3METRIC for the backdrop (2026-10-26); that was reverted (metric
added specks, seams and erased-figure ghosts on P&C 39 p4, p7, p12, p16), so the "metric" column now needs it back.

    uv run python experiments/backdrop_metric.py <episode.zumi> <out dir> <sheet path> --panels 2,4,7,13
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cards as CD  # noqa: E402
import episode  # noqa: E402

RED = (128, 40, 40)
ROW_H = 300


def grey(v: np.ndarray, valid: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(v[valid], [2, 98])
    g = np.clip((hi - v) / max(hi - lo, 1e-6), 0, 1)  # near = white (depth grows away from the camera)
    out = np.dstack([g * 255] * 3).astype(np.uint8)
    out[~valid] = RED
    return out


def main():
    zumi, out, path = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    z = zipfile.ZipFile(zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    seen, mono_fn = [], []
    order, image, relief, frame_depth = CD.order, CD.backdrop_image, CD.backdrop_relief, CD.frame_depth

    def spy_depth(fn, rgb, areas):
        if not mono_fn:  # build's first call is DA3MONO on the base
            mono_fn.append(fn)
        return frame_depth(fn, rgb, areas)

    def spy_order(M, masks, area, behind=(), Mo=None):
        seen.append({"mono": (M if Mo is None else Mo).copy(), "area": area.copy()})
        return order(M, masks, area, behind, Mo)

    def spy_image(rgb, area, m, inset=0):
        seen[-1]["back"] = rgb.copy()
        return image(rgb, area, m, inset)

    def spy_relief(area, Mb, eb, *rest):
        seen[-1]["metric"] = Mb.copy()
        seen[-1]["mono_back"] = frame_depth(mono_fn[0], seen[-1]["back"], [area])
        return relief(area, Mb, eb, *rest)

    CD.order, CD.backdrop_image, CD.backdrop_relief, CD.frame_depth = spy_order, spy_image, spy_relief, spy_depth
    rows = []
    for p in picks:
        seen.clear()
        sys.argv = ["episode.py", str(zumi), str(out), "--from-masks", "--panels", str(p)]
        episode.main()
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[p]["layers"][0]["image"]))).convert("RGB"))
        for k, s in enumerate(seen):
            if "metric" not in s:
                continue
            a = s["area"]
            ys, xs = np.nonzero(a)
            sl = np.s_[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
            ac = a[sl]
            c = s["back"][sl].copy()
            c[~ac] = RED
            cols = [c, grey(s["metric"][sl], ac), grey(s["mono_back"][sl], ac)]
            row = Image.fromarray(np.concatenate(cols, 1))
            row = row.resize((round(row.width * ROW_H / row.height), ROW_H))
            d = ImageDraw.Draw(row)
            d.rectangle([0, 0, row.width, 14], fill=(0, 0, 0))
            d.text((4, 1), f"p{p:03d} f{k}   backdrop (erased) | DA3METRIC on backdrop | DA3MONO on backdrop",
                   fill=(255, 255, 255))
            rows.append(row)
    W = max(r.width for r in rows)
    sheet = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sheet.paste(r, (0, j * (ROW_H + 6)))
    path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(path)
    print(f"{len(rows)} frames -> {path}")


if __name__ == "__main__":
    main()
