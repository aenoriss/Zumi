"""Scores every panel method in speakers/bakeoff.json against a reference method (default llm_opus5.5) on the boxes the
reference answered: panels matched one to one by box IoU (Hungarian), a match counted at IoU >= MATCH_IOU.
Per method: exact count, precision, recall, F1, mean IoU of the matches, and the logged OpenRouter cost per box.

    uv run python experiments/panel_score.py <out root> [reference]
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

sys.path.insert(0, str(Path(__file__).resolve().parent))
from panel_llm import MODELS  # noqa: E402

MATCH_IOU = 0.5
LEDGER = Path(__file__).resolve().parents[2] / ".data/spend/openrouter.jsonl"


def bbox(entry) -> tuple[float, float, float, float]:
    pts = np.array([p for ring in entry["rings"] for p in ring], float)
    return pts[:, 0].min(), pts[:, 1].min(), pts[:, 0].max(), pts[:, 1].max()


def iou(a, b) -> float:
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0])); iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def match(pred, ref) -> list[float]:
    """IoUs of the matched pairs at or above MATCH_IOU."""
    if not pred or not ref:
        return []
    m = np.array([[iou(p, r) for r in ref] for p in pred])
    rows, cols = linear_sum_assignment(-m)
    return [m[i, j] for i, j in zip(rows, cols) if m[i, j] >= MATCH_IOU]


def cost_per_box() -> dict[str, float]:
    cost = defaultdict(list)
    if LEDGER.exists():
        for e in map(json.loads, LEDGER.read_text().splitlines()):
            if e.get("tag", "").startswith("panels:"):
                cost[e["model"]].append(e["cost"])
    return {m: sum(c) / len(c) for m, c in cost.items()}


def main() -> None:
    root = Path(sys.argv[1]); refname = sys.argv[2] if len(sys.argv) > 2 else "llm_opus5.5"
    methods = json.loads((root / "speakers" / "bakeoff.json").read_text())["methods"]
    ref = methods[refname]
    pids = sorted(ref)
    usd = cost_per_box()
    rows = []
    for name, per in methods.items():
        if name == refname or not all(pid in per for pid in pids):
            continue
        tp = npred = nref = exact = 0; ious = []
        for pid in pids:
            p = [bbox(e) for e in per[pid]]; r = [bbox(e) for e in ref[pid]]
            got = match(p, r)
            tp += len(got); npred += len(p); nref += len(r); exact += len(p) == len(r); ious += got
        prec = tp / npred if npred else 0.0; rec = tp / nref if nref else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        model = MODELS.get(name, (None,))[0]
        rows.append((f1, name, exact, prec, rec, float(np.mean(ious)) if ious else 0.0, usd.get(model)))
    print(f"reference {refname}, {len(pids)} boxes, {sum(len(ref[p]) for p in pids)} panels; match at IoU >= {MATCH_IOU}")
    print(f"{'method':20s} {'F1':>5s} {'exact':>6s} {'prec':>5s} {'rec':>5s} {'mIoU':>5s} {'USD/box':>8s}")
    for f1, name, exact, prec, rec, miou, c in sorted(rows, reverse=True):
        print(f"{name:20s} {f1:5.2f} {exact:3d}/{len(pids):<2d} {prec:5.2f} {rec:5.2f} {miou:5.2f} {('%.4f' % c) if c is not None else 'local':>8s}")


if __name__ == "__main__":
    main()
