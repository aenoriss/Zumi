"""How much a panel model's answer varies between calls, and what a two-model vote gives (2026-10-30).

Asks each model REPS more times on the same boxes (frames.ask, uncached, in parallel), adds the answer already in
speakers/bakeoff.json, and scores every sample against the reference (llm_opus5.5) with panel_score's matching.
The vote: one Gemini and one Sonnet answer; equal panel counts -> the Gemini one; else a third call (another Gemini
sample) and the answer whose count two of the three share, Gemini first. Replayed over every pairing of samples.
Raw answers: speakers/panel_repeats.json (asked once; a rerun only scores).

    uv run python experiments/panel_repeat.py <out root> <pid> [...]
"""
from __future__ import annotations

import itertools
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import frames as FR  # noqa: E402
from panel_llm import MODELS  # noqa: E402
from panel_score import bbox, match  # noqa: E402

REPS = 3
CANDS = ["llm_gemini3.1pro", "llm_sonnet5.5"]


def px(boxes, w, h):
    return [(b[0] * w / 1000, b[1] * h / 1000, b[2] * w / 1000, b[3] * h / 1000) for b in boxes]


def score(pred, ref):
    got = match(pred, ref)
    return len(pred) == len(ref), len(got), len(pred), len(ref)


def main() -> None:
    root = Path(sys.argv[1]) / "speakers"; pids = sys.argv[2:]
    bk = json.loads((root / "bakeoff.json").read_text())["methods"]
    path = root / "panel_repeats.json"
    rep = json.loads(path.read_text()) if path.exists() else {}
    imgs = {p: Image.open(root / "boxes" / f"{p}.jpg").convert("RGB") for p in pids}
    jobs = [(m, p, r) for m in CANDS for p in pids for r in range(REPS) if len(rep.get(m, {}).get(p, [])) <= r]

    def ask(job):
        m, p, r = job
        model, reasoning = MODELS[m]
        try:
            return job, FR.ask(imgs[p], model, reasoning, f"panels:repeat-{p}")
        except Exception as e:  # an unreadable answer is a sample with no panels
            print(f"{m} {p} #{r}: {type(e).__name__} {e}")
            return job, []

    with ThreadPoolExecutor(8) as ex:
        for (m, p, r), boxes in ex.map(ask, jobs):
            rep.setdefault(m, {}).setdefault(p, []).append(boxes)
    path.write_text(json.dumps(rep))

    ref = {p: [bbox(e) for e in bk["llm_opus5.5"][p]] for p in pids}
    samples = {}  # model -> pid -> [pixel boxes per sample]; the bake-off answer first
    for m in CANDS:
        for p in pids:
            w, h = imgs[p].size
            samples.setdefault(m, {})[p] = [[bbox(e) for e in bk[m][p]]] + [px(b, w, h) for b in rep[m][p]]
    print(f"reference llm_opus5.5; {len(samples[CANDS[0]][pids[0]])} samples per model and box")
    for m in CANDS:
        tot = [0, 0, 0, 0]
        print(f"\n{m}: panel counts per sample (Opus count)")
        for p in pids:
            ss = samples[m][p]
            for s in ss:
                for k, v in enumerate(score(s, ref[p])):
                    tot[k] += v
            print(f"  {p}: {[len(s) for s in ss]} ({len(ref[p])})  exact {sum(score(s, ref[p])[0] for s in ss)}/{len(ss)}")
        n = len(pids) * len(samples[m][pids[0]])
        prec, rec = tot[1] / tot[2], tot[1] / tot[3]
        print(f"  per call: exact count {tot[0]}/{n}, F1 {2 * prec * rec / (prec + rec):.3f}")

    g, s = samples["llm_gemini3.1pro"], samples["llm_sonnet5.5"]
    exact = n = calls = 0
    for p in pids:
        for (gi, a), b in itertools.product(enumerate(g[p]), s[p]):
            if len(a) == len(b):
                pick, k = a, 2
            else:
                third = g[p][(gi + 1) % len(g[p])]
                counts = [len(a), len(b), len(third)]
                pick = next((x for x in (a, b, third) if counts.count(len(x)) >= 2), a)
                k = 3
            exact += score(pick, ref[p])[0]; n += 1; calls += k
    print(f"\nvote Gemini + Sonnet (third call on disagreement): exact count {exact}/{n} = {exact / n:.3f}, "
          f"{calls / n:.2f} calls per box")


if __name__ == "__main__":
    main()
