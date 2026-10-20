"""Maverick per box vs Magiv3 on superframes, on the same labelled lines.

    uv run --group magi python compare_understand.py

Lines: every labelled element kept by the label whose speaker is known (not "?"), in the 38 labelled boxes.
- coverage: share of lines the system gives a speaker (Maverick: not unknown; Magiv3: a linked character).
- accuracy: right speakers over all lines (no answer counts as wrong), after mapping each system id to the
  label it most often has (Maverick ids span an episode, Magiv3 identities a run).
- pairwise: for pairs of lines in the same run, "same speaker" predicted vs labelled; precision, recall, F1.
  Needs no id mapping, so neither system gains from having more ids.
- text: 1 - character error rate on lines both the label and the system keep; Magiv3 OCR runs per box at full
  resolution, each OCR line assigned to the mask that contains its centre pixel.
Narrator and environment lines are reported apart: Magiv3 has no such classes.
"""

from __future__ import annotations

import io
import json
import zipfile
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

import torch
from PIL import Image
from transformers import AutoModelForCausalLM, AutoProcessor

from bubbles import load_masks
from magi_run import MODEL, pad
from magi_superframe import RUNS
from score_understand import FIXED, cer

ROOT = Path(__file__).resolve().parent.parent
LAB = json.loads((ROOT / ".data/out/understand/labels.json").read_text(encoding="utf-8"))
MAV = ROOT / ".data/out/understand/m3/meta-llama_llama-4-maverick"
SF = json.loads((ROOT / ".data/out/magi/superframe/records.json").read_text())["rtl"]
OCR_CACHE = ROOT / ".data/out/magi/ocr-38.json"


def magi_ocr() -> dict:
    if OCR_CACHE.exists():
        return json.loads(OCR_CACHE.read_text(encoding="utf-8"))
    model = AutoModelForCausalLM.from_pretrained(str(MODEL), torch_dtype=torch.float16, trust_remote_code=True).cuda().eval()
    proc = AutoProcessor.from_pretrained(str(MODEL), trust_remote_code=True)
    out = {}
    for ep, runs in RUNS.items():
        z = zipfile.ZipFile(ROOT / ".data/out/chapters" / f"{ep}.zumi")
        panels = json.loads(z.read("manifest.json"))["panels"]
        for b in [b for r in runs for b in r]:
            img = Image.open(io.BytesIO(z.read(panels[b]["layers"][0]["image"]))).convert("RGB")
            padded, left = pad(img)
            with torch.no_grad():
                r = model.predict_ocr([padded], proc)[0]
            out[f"{ep}:{b}"] = [(t.strip(), [x[0] - left, x[1], x[2] - left, x[3]]) for t, x in zip(r["ocr_texts"], r["bboxes"])]
    OCR_CACHE.write_text(json.dumps(out, ensure_ascii=False))
    return out


def lines() -> list[dict]:
    out = []
    for ep, runs in RUNS.items():
        for ri, run in enumerate(runs):
            for b in run:
                for e, l in LAB[ep]["panels"].get(str(b), {}).items():
                    if l["keep"]:
                        out.append({"ep": ep, "run": ri, "box": b, "el": e, "label": l["speaker"], "text": l["text"]})
    return out


def accuracy(rows, key) -> tuple[int, int]:
    votes = defaultdict(Counter)
    for r in rows:
        if r[key] is not None and r[key] not in FIXED:
            votes[(r["ep"], r[key])][r["label"]] += 1
    mp = {k: v.most_common(1)[0][0] for k, v in votes.items()}
    right = sum(1 for r in rows if r[key] is not None and (r[key] if r[key] in FIXED else mp.get((r["ep"], r[key]))) == r["label"])
    return right, len(rows)


def pairwise(rows, key) -> tuple[float, float, float]:
    tp = fp = fn = 0
    groups = defaultdict(list)
    for r in rows:
        groups[(r["ep"], r["run"])].append(r)
    for g in groups.values():
        for a, b in combinations(g, 2):
            same = a["label"] == b["label"]
            pred = a[key] is not None and a[key] == b[key] and a[key] not in ("unknown",)
            tp += same and pred
            fp += pred and not same
            fn += same and not pred
    p = tp / (tp + fp) if tp + fp else 0.0
    rc = tp / (tp + fn) if tp + fn else 0.0
    return p, rc, (2 * p * rc / (p + rc) if p + rc else 0.0)


def main() -> None:
    ocr = magi_ocr()
    rows = lines()
    mav = {ep: json.loads((MAV / f"{ep}.json").read_text(encoding="utf-8")) for ep in RUNS}
    sf = {(r["ep"], r["box"], r["el"]): r for r in SF}
    mav_text, magi_text = [], []
    for r in rows:
        e = {str(x.get("id")): x for x in mav[r["ep"]]["panels"].get(str(r["box"]), {}).get("elements", [])}.get(r["el"], {})
        sp = e.get("speaker")
        r["mav"] = None if sp in (None, "", "unknown") else str(sp)
        if e.get("keep"):
            mav_text.append(cer(e.get("text", ""), r["text"]))
        s = sf.get((r["ep"], r["box"], r["el"]))
        r["magi08"] = s["ident"] if s and s["ident"] and s["score"] >= 0.8 else None
        r["magitop"] = s["ident"] if s and s["ident"] else None
        mask = load_masks(ROOT / f".data/out/understand/seg2/masks/{r['ep']}-p{r['box']:03d}.npz")[int(r["el"]) - 1].mask
        got = []
        for t, bb in ocr.get(f"{r['ep']}:{r['box']}", []):
            cx, cy = int((bb[0] + bb[2]) / 2), int((bb[1] + bb[3]) / 2)
            if 0 <= cy < mask.shape[0] and 0 <= cx < mask.shape[1] and mask[cy, cx]:
                got.append((bb[1], t))
        magi_text.append(cer(" ".join(t for _, t in sorted(got)), r["text"]))
    known = [r for r in rows if r["label"] != "?"]
    chars = [r for r in known if r["label"] not in FIXED]
    print(f"{len(rows)} kept lines; {len(known)} with a known speaker, {len(chars)} of them characters (not narrator/environment)\n")
    print(f"{'':28s}{'coverage':>10s}{'accuracy':>12s}{'acc. chars':>12s}{'pair P/R/F1':>20s}")
    for name, key in (("Maverick per box", "mav"), ("Magiv3 superframe, cut 0.8", "magi08"), ("Magiv3 superframe, top", "magitop")):
        cov = sum(r[key] is not None for r in known) / len(known)
        a, n = accuracy(known, key)
        ac, nc = accuracy(chars, key)
        p, rc, f1 = pairwise(known, key)
        print(f"{name:28s}{cov:>10.0%}{f'{a}/{n}':>12s}{f'{ac}/{nc}':>12s}{f'{p:.2f}/{rc:.2f}/{f1:.2f}':>20s}")
    print(f"\ntext: Maverick {1 - sum(mav_text) / len(mav_text):.3f} on {len(mav_text)} lines it kept; "
          f"Magiv3 OCR {1 - sum(magi_text) / len(magi_text):.3f} on all {len(magi_text)}")


if __name__ == "__main__":
    main()
