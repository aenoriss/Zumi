"""Score Transcribe results against hand-written labels.

    uv run python experiments/score_transcribe.py <labels.json> <result.json> [<result.json> ...]

Labels: {"panels": {"<panel>": {"<element number>": {"keep": bool, "text": str}}}} (a label's "speaker", from the
Understand days, is ignored). Per result file: keep accuracy (all labelled elements); text accuracy, 1 - character
error rate on elements both sides keep.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[‘’`]", "'", str(t or "")).upper()).strip()


def cer(a: str, b: str) -> float:
    a, b = norm(a), norm(b)
    if not b:
        return 0.0 if not a else 1.0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return min(1.0, prev[-1] / len(b))


def score(labels: dict, result: dict) -> dict:
    keep_ok, keep_n, cers, misses = 0, 0, [], []
    for p, elems in labels["panels"].items():
        got = {str(e.get("id")): e for e in result["panels"].get(p, {}).get("elements", [])}
        for k, lab in elems.items():
            e = got.get(k, {})
            keep_n += 1
            keep_ok += bool(e.get("keep")) == lab["keep"]
            if lab["keep"] and e.get("keep"):
                c = cer(e.get("text", ""), lab["text"])
                cers.append(c)
                if c > 0.1:
                    misses.append(f"p{p}#{k} text {e.get('text')!r} vs {lab['text']!r}")
    return {
        "keep": f"{keep_ok}/{keep_n}",
        "text": f"{1 - sum(cers) / len(cers):.3f} on {len(cers)}" if cers else "-",
        "misses": misses,
    }


if __name__ == "__main__":
    labels = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    for f in sys.argv[2:]:
        episode = Path(f).stem
        lab = labels[episode] if episode in labels else labels
        s = score(lab, json.loads(Path(f).read_text(encoding="utf-8")))
        print(f"== {f}\n   keep {s['keep']}  text {s['text']}")
        for m in s["misses"]:
            print("   -", m)
