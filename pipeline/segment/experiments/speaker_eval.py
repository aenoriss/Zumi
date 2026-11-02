"""Scores the speaker rules (speakers.assign, re-run now on the saved layers) against the user's labels.

Split by episode (user, 2026-10-27): the rules are tuned on TUNE and scored on TEST only once, at the end. A bubble is
right when the kind matches and, for kind "card", the answer names every labelled speaker (a chorus must name all) and
nothing outside their speaking groups (speakers.groups: touching cards answer together).
Prints accuracy overall, per labelled kind and per rule that decided, and writes a sheet of the failures.

    uv run python experiments/speaker_eval.py <out root> [tune|test] [--sheet path]
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import speakers as SP  # noqa: E402
from boxstore import Box  # noqa: E402
from workers import pmap  # noqa: E402

TUNE = {"pepper-carrot-37", "pepper-carrot-39"}
TEST = {"pepper-carrot-36", "pepper-carrot-38"}


def evaluate(root: Path, split: str = "tune", sheet: Path | None = None) -> dict:
    eps = TUNE if split == "tune" else TEST
    labels = json.loads((root / "speakers" / "labels.json").read_text())
    data = json.loads((root / "speakers" / "dataset.json").read_text())
    n, ok = 0, 0
    by_kind, by_rule, fails = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), []
    boxes = [box for box in data["boxes"] if box["episode"] in eps]
    for box, got in zip(boxes, pmap(SP.answers_of, [Box(root / "dataset" / b["episode"], b["pid"]) for b in boxes])):
        if got is None:
            continue
        gs = got["groups"]
        for b, a in zip(got["bubbles"], got["answers"]):
            lab = labels.get(f"{box['pid']}#{b['id']}")
            if not lab or lab.get("skip"):
                continue
            if lab["kind"] in ("missing", "off_panel"):  # no card to find (a segmentation miss, or a speaker not
                by_kind[lab["kind"] + " (not scored)"][1] += 1  # drawn in the box; user 2026-10-29): not scored
                continue
            # right: the kind matches and, for a card, the answer holds every labelled speaker and nothing outside
            # their groups (a group answer, Pepper with Carrot in her arms, is right for a label on Pepper)
            if lab["kind"] == "card":
                allowed = {i for g in gs if any(s in g for s in lab["speakers"]) for i in g}
                right = a["speaker_kind"] == "card" and set(lab["speakers"]) <= set(a["speakers"]) <= allowed
            else:
                right = a["speaker_kind"] == lab["kind"]
            n += 1
            ok += right
            by_kind[lab["kind"] + ("_chorus" if len(lab["speakers"]) > 1 else "")][0] += right
            by_kind[lab["kind"] + ("_chorus" if len(lab["speakers"]) > 1 else "")][1] += 1
            by_rule[a["rule"]][0] += right
            by_rule[a["rule"]][1] += 1
            if not right:
                fails.append((box, b, a, lab))
    res = {"n": n, "acc": ok / max(n, 1), "by_kind": dict(by_kind), "by_rule": dict(by_rule), "fails": len(fails)}
    print(f"{split}: {ok}/{n} = {100 * ok / max(n, 1):.1f}%")
    for k, (r, t) in sorted(by_kind.items(), key=lambda x: -x[1][1]):
        print(f"  label {k:14s} {r:3d}/{t:3d} = {100 * r / t:5.1f}%")
    for k, (r, t) in sorted(by_rule.items(), key=lambda x: -x[1][1]):
        print(f"  rule  {k:20s} {r:3d}/{t:3d} = {100 * r / t:5.1f}%")
    if sheet and fails:
        tiles = []
        for box, b, a, lab in fails[:40]:
            im = Image.open(root / "speakers" / box["img"]).convert("RGB")
            d = ImageDraw.Draw(im)
            for c in box["cards"]:
                col = (61, 220, 132) if c["i"] in lab["speakers"] else (74, 163, 255) if c["i"] in a["speakers"] else (120, 120, 120)
                for p in c["outline"]:
                    d.line([tuple(q) for q in p] + [tuple(p[0])], fill=col, width=4 if col != (120, 120, 120) else 1)
            d.rectangle(list(b["bbox"]), outline=(255, 216, 74), width=4)
            if b["tail_tip"]:
                tx, ty = b["tail_tip"]
                d.ellipse([tx - 6, ty - 6, tx + 6, ty + 6], fill=(255, 216, 74))
            d.rectangle([0, 0, im.width, 18], fill=(0, 0, 0))
            d.text((4, 3), f"{box['pid']} #{b['id']}: label {lab['kind']} {lab['speakers']} | got {a['speaker_kind']} "
                           f"{a['speakers']} ({a['rule']})", fill=(255, 255, 255))
            im.thumbnail((700, 400))
            tiles.append(im)
        W = 1420
        rows = [tiles[i:i + 2] for i in range(0, len(tiles), 2)]
        H = sum(max(t.height for t in r) + 6 for r in rows)
        sh = Image.new("RGB", (W, H), (20, 20, 20))
        y = 0
        for r in rows:
            x = 0
            for t in r:
                sh.paste(t, (x, y))
                x += t.width + 10
            y += max(t.height for t in r) + 6
        sh.save(sheet)
        print(f"failures sheet: {sheet}")
    return res


if __name__ == "__main__":
    root = Path(sys.argv[1])
    split = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "tune"
    sheet = Path(sys.argv[sys.argv.index("--sheet") + 1]) if "--sheet" in sys.argv else None
    evaluate(root, split, sheet)
