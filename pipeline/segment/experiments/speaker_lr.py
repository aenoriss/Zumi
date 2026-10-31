"""Hardcoded cascade vs a logistic regression over the same heuristics, as candidate features, scored
leave-one-episode-out on the card-labelled bubbles (single speaker and chorus, same criterion as speaker_eval)."""
import json, re, sys
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import speakers as SP
from boxstore import Box
root = Path(__file__).resolve().parents[2] / ".data" / "out"
labels = json.loads((root / "speakers" / "labels.json").read_text()); data = json.loads((root / "speakers" / "dataset.json").read_text())
KINDS = ["speech", "shout", "thought", "bubble", "caption", "whisper"]
rows = []   # one per (bubble, candidate group)
bubs = []   # one per bubble: (episode, key, want, allowed, candidate row indices, cascade answer)
for box in data["boxes"]:
    cards, bubbles, frames, (w, h) = SP.load_box(Box(root / "dataset" / box["episode"], box["pid"]))
    merged, gs = SP.as_groups(cards); L = max(w, h)
    for b in bubbles:
        k = f"{box['pid']}#{b.id}"; lab = labels.get(k)
        if not lab or lab.get("skip") or lab["kind"] != "card": continue
        feats = SP.features(b, merged)
        if not feats: continue
        want = set(lab["speakers"]); allowed = {i for g in gs if g and any(s in g for s in want) for i in g}
        a = SP.assign(b, cards, frames)
        idx = []
        tail = b.tail_tip is not None
        for f in feats:
            x = [1.0, float(f["same_frame"]), f["dist"] / L, float(tail), (f.get("tip_dist", L) / L) if tail else 0.0,
                 (f.get("aim", -1.0)) if tail else 0.0, float(tail and f.get("aim", -1) > 0.85), float(tail and f.get("aim", -1) > 0.85) * (f.get("tip_dist", L) / L),
                 (f.get("anchor_dist", L) / L) if "anchor_dist" in f else 1.0, float("anchor_dist" in f), np.log1p(f["area"] / (w * h)) ,
                 float(f["same_frame"]) * f["dist"] / L] + [float(b.kind == kd) for kd in KINDS]
            y = 1.0 if set(gs[f["card"]]) & want else 0.0
            rows.append((x, y)); idx.append((len(rows) - 1, f["card"]))
        bubs.append((box["episode"], k, want, allowed, idx, a, gs))
X = np.array([r[0] for r in rows]); Y = np.array([r[1] for r in rows])
mu, sd = X.mean(0), X.std(0) + 1e-9; mu[0], sd[0] = 0, 1
Xn = (X - mu) / sd

def fit(Xt, Yt, l2=1.0, iters=3000, lr=0.1):
    w = np.zeros(Xt.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-Xt @ w)); g = Xt.T @ (p - Yt) / len(Yt) + l2 * w / len(Yt); w -= lr * g
    return w

def right(answer, want, allowed): return want <= set(answer) <= allowed
eps = sorted({b[0] for b in bubs})
tot = {"cascade": 0, "lr": 0, "n": 0}; per = {}
for hold in eps:
    tr = [i for i, b in enumerate(bubs) if b[0] != hold]; te = [i for i, b in enumerate(bubs) if b[0] == hold]
    tr_rows = [r for i in tr for r, _ in bubs[i][4]]
    w = fit(Xn[tr_rows], Y[tr_rows])
    c = l = 0
    for i in te:
        ep, k, want, allowed, idx, a, gs = bubs[i]
        scores = [(Xn[r] @ w, g) for r, g in idx]; best = max(scores)[1]
        l += right(gs[best], want, allowed); c += right(a["speakers"], want, allowed) and a["speaker_kind"] == "card"
    per[hold] = (c, l, len(te)); tot["cascade"] += c; tot["lr"] += l; tot["n"] += len(te)
for ep, (c, l, n) in per.items(): print(f"{ep}: cascade {c}/{n}  regression {l}/{n}")
print(f"ALL (leave-one-episode-out): cascade {tot['cascade']}/{tot['n']} = {100*tot['cascade']/tot['n']:.1f}%   regression {tot['lr']}/{tot['n']} = {100*tot['lr']/tot['n']:.1f}%")
w = fit(Xn, Y); names = ["bias", "same_frame", "dist", "has_tail", "tip_dist", "aim", "aimed", "aimed*tip", "anchor_dist", "has_anchor", "log_area", "same*dist"] + ["kind_" + kd for kd in KINDS]
print("weights (standardised, all data):", ", ".join(f"{n} {v:+.2f}" for n, v in sorted(zip(names, w), key=lambda t: -abs(t[1]))))
