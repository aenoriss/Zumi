"""Contact sheets and a stats line for an intake run, for the tune-intake loop.

    uv run python -m zumi.sheets .data/out/<slug>-cuts.png .data/out/<slug>.zumi

Tiles the report PNG into 2400 px tall columns, 13 columns per sheet with a 10 px gap, saved as
`<slug>-sheetN.png` next to the report; prints panel count, height quantiles, gutter distribution
and the sliver / giant counts from the manifest in the .zumi.
"""

from __future__ import annotations

import json
import statistics
import sys
import zipfile
from pathlib import Path

from PIL import Image

Image.MAX_IMAGE_PIXELS = None

COL_H = 2400
COLS = 13
GAP = 10


def tile(report: Path, prefix: str | None = None) -> list[Path]:
    im = Image.open(report).convert("RGB")
    prefix = prefix or report.name.removesuffix("-cuts.png")
    n_cols = (im.height + COL_H - 1) // COL_H
    out: list[Path] = []
    for s in range(0, n_cols, COLS):
        cols = list(range(s, min(s + COLS, n_cols)))
        sheet = Image.new("RGB", (len(cols) * (im.width + GAP) - GAP, COL_H), (40, 40, 40))
        for i, c in enumerate(cols):
            sheet.paste(im.crop((0, c * COL_H, im.width, min((c + 1) * COL_H, im.height))), (i * (im.width + GAP), 0))
        p = report.with_name(f"{prefix}-sheet{s // COLS}.png")
        sheet.save(p)
        out.append(p)
    return out


def stats(zumi: Path) -> str:
    with zipfile.ZipFile(zumi) as z:
        m = json.loads(z.read("manifest.json"))
    hs = [p["strip"]["h"] for p in m["panels"]]
    gs = [p["strip"]["gutterAfter"] for p in m["panels"]][:-1]
    q = lambda xs, f: int(statistics.quantiles(xs, n=4)[f]) if len(xs) > 1 else (xs[0] if xs else 0)
    gutters = (
        f"gutter min/q1/med/q3/max {min(gs)}/{q(gs, 0)}/{int(statistics.median(gs))}/{q(gs, 2)}/{max(gs)}"
        if gs
        else "no gutters"
    )
    return (
        f"panels {len(hs)}  h min/med/max {min(hs)}/{int(statistics.median(hs))}/{max(hs)}  {gutters}  "
        f"<300px {sum(h < 300 for h in hs)}  >5000px {sum(h > 5000 for h in hs)}"
    )


if __name__ == "__main__":
    report, zumi = Path(sys.argv[1]), Path(sys.argv[2])
    for p in tile(report):
        print(p)
    print(stats(zumi))
