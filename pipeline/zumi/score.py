"""Boundary recall / precision of an intake run against hand-judged cut labels (tune-intake step 5).

    uv run python -m zumi.score .data/out/<slug>.zumi .data/labels/<slug>.json [--write FLOATERS]

Labels are `{"cuts": [y, ...], "ambiguous": [y, ...]}`: strip rows at gutter centres a reader agrees with, and
rows where a cut is a pacing choice either way (optional). A predicted cut
(the blank run between two consecutive panels) matches a label lying inside it, ±20 px.
`--write a,b,c` builds the label file from the run instead: every gutter centre except, for each
listed slab index (a floater: text-only slab), the smaller of its two gaps, which is the one the
floater should merge across.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

TOL = 20


def cuts_of(zumi: Path) -> list[tuple[int, int, int]]:
    """(centre, gap, slab index above) for each gutter between consecutive panels."""
    with zipfile.ZipFile(zumi) as z:
        panels = json.loads(z.read("manifest.json"))["panels"]
    out = []
    for i, p in enumerate(panels[:-1]):
        s = p["strip"]
        out.append((s["y"] + s["h"] + s["gutterAfter"] // 2, s["gutterAfter"], i))
    return out


def write_labels(zumi: Path, labels: Path, floaters: set[int]) -> None:
    cuts = cuts_of(zumi)
    drop = set()
    for i in floaters:
        above = next((c for c in cuts if c[2] == i - 1), None)
        below = next((c for c in cuts if c[2] == i), None)
        if above and below:
            drop.add(min(above, below, key=lambda c: c[1])[0])
        elif above or below:
            drop.add((above or below)[0])
    labels.parent.mkdir(parents=True, exist_ok=True)
    labels.write_text(json.dumps({"cuts": [c[0] for c in cuts if c[0] not in drop]}))
    print(f"{labels}: {len(cuts) - len(drop)} cuts ({len(drop)} dropped)")


def score(zumi: Path, labels: Path) -> str:
    data = json.loads(labels.read_text())
    truth = data["cuts"]
    # pacing calls the reviewers split on (spaced balloons, a CLICK crescendo): a cut there is neither required
    # nor counted as extra
    ambiguous = data.get("ambiguous", [])
    truth = [t for t in truth if t not in ambiguous]
    cuts = [c for c in cuts_of(zumi) if not any(c[0] - c[1] // 2 - TOL <= a <= c[0] + c[1] // 2 + TOL for a in ambiguous)]
    pred = [c[0] for c in cuts]
    # a label matches a predicted gutter when it lies inside that blank run (±TOL): a gutter that grew
    # by a faded panel edge moves its centre by more than TOL without being a different cut
    run = {c: (c - g // 2 - TOL, c + (g - g // 2) + TOL) for c, g, _ in cuts}
    near = lambda t, p: run[p][0] <= t <= run[p][1]
    hit = [t for t in truth if any(near(t, p) for p in pred)]
    ok = [p for p in pred if any(near(t, p) for t in truth)]
    missed = [t for t in truth if t not in hit]
    extra = [p for p in pred if p not in ok]
    rec = len(hit) / len(truth) if truth else 1.0
    prec = len(ok) / len(pred) if pred else 1.0
    return (
        f"recall {rec:.3f} ({len(hit)}/{len(truth)})  precision {prec:.3f} ({len(ok)}/{len(pred)})\n"
        f"  missed labels at: {missed}\n  extra cuts at: {extra}"
    )


if __name__ == "__main__":
    zumi, labels = Path(sys.argv[1]), Path(sys.argv[2])
    if "--write" in sys.argv:
        fl = sys.argv[sys.argv.index("--write") + 1]
        write_labels(zumi, labels, {int(x) for x in fl.split(",") if x})
    else:
        print(score(zumi, labels))
