"""Dialog-character association, card level (user, 2026-10-27): every bubble card of a box linked to the character
card(s) that speak it, as the groundwork for the LLM-led animation (cards moved across the scene, each bubble shown
once its speaker's move ends). Identity across boxes is not decided here.

Per bubble, from the box's flat layers (mesh/<pid>.cards.json, .bubbles.json) and its lettering mask:
  frame     the frame holding most of the bubble (cards.json windows)
  tail      the bubble's tail, if it has one: the part of the mask a large opening removes, its tip the point farthest
            from the bubble's body; the direction body -> tip points at the speaker
  anchor    Understand's point on the speaker (bubbles.json), when Understand has run
Candidates are every character card in the box (any frame, a penalty across frames). The rules (assign) are tuned on
a labelled dataset (experiments/speaker_dataset.py, speaker_eval.py); what they leave undecided goes to an LLM with
the candidates numbered (TODO).

Writes into each lettering layer of cards.json: "speakers" (card png names, a chorus has several), "speaker_kind"
(card | off_panel | narrator | sfx), "confidence" (0-1), "rule" (which rule decided) and "order" (reading order in
the box).

    uv run python speakers.py <episode.zumi> <out dir> [--panels 3,7]
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_opening, distance_transform_edt as edt, label

TAIL_OPEN = 0.18      # the opening radius that strips a tail, as a share of the bubble's short side
TAIL_MIN_PX = 60      # a tail has at least this many pixels...
TAIL_MIN_LEN = 10     # ...and its tip lies at least this far out of the bubble's body
GROUP_PX = 4          # groups: a card's outline within this many px of another counts as touching it...
GROUP_SHARE = 0.30    # ...and this share of the smaller card's outline touching the bigger makes them one group
SPEAKING = {"speech", "shout", "thought", "whisper", "bubble", None}
NARRATION = {"caption", "narration"}
SFX = {"sfx", "sound"}


@dataclass
class Card:
    key: str                 # the card's png name in cards.json
    kind: str
    frame: int | None
    mask: np.ndarray
    centroid: tuple[float, float] = (0.0, 0.0)
    area: int = 0


@dataclass
class Bubble:
    id: int
    key: str                 # its card's png name
    kind: str | None
    text: str
    mask: np.ndarray
    frame: int | None
    centroid: tuple[float, float]
    tail_tip: tuple[float, float] | None = None
    tail_dir: tuple[float, float] | None = None
    anchor: tuple[float, float] | None = None
    understand: str | None = None
    order: int = 0
    feats: dict = field(default_factory=dict)


def _mask_of(png: Path, bbox, w: int, h: int) -> np.ndarray:
    a = np.asarray(Image.open(png).convert("RGBA"))[..., 3] > 127
    x0, y0, x1, y1 = bbox
    m = np.zeros((h, w), bool)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    m[sy0:sy1, sx0:sx1] = a[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
    return m


def _centroid(m: np.ndarray) -> tuple[float, float]:
    ys, xs = np.nonzero(m)
    return (float(xs.mean()), float(ys.mean())) if len(xs) else (0.0, 0.0)


def tail(mask: np.ndarray) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """(tip, unit direction from the body to the tip) of the bubble's tail, or (None, None)."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 200:
        return None, None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    m = mask[y0:y1, x0:x1]
    r = max(3, int(TAIL_OPEN * min(m.shape)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    body = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k) > 0
    if not body.any():
        return None, None
    rest = m & ~binary_dilation(body, iterations=2)
    lab, n = label(rest)
    if not n:
        return None, None
    d = edt(~body)
    best = None
    for i in range(1, n + 1):
        part = lab == i
        if part.sum() < TAIL_MIN_PX:
            continue
        py, px = np.unravel_index(np.argmax(np.where(part, d, -1)), d.shape)
        if d[py, px] < TAIL_MIN_LEN:
            continue
        if best is None or d[py, px] > best[0]:
            best = (d[py, px], px, py, part)
    if best is None:
        return None, None
    _, px, py, part = best
    # the direction: from where the tail leaves the body to its tip
    by, bx = np.nonzero(part & (d <= 3))
    base = (float(bx.mean()), float(by.mean())) if len(bx) else _centroid(body)
    v = np.array([px - base[0], py - base[1]], float)
    n_ = np.linalg.norm(v)
    if n_ < 1e-6:
        return None, None
    return (float(px + x0), float(py + y0)), (float(v[0] / n_), float(v[1] / n_))


def frames_of(cj: dict, mesh: Path) -> list[np.ndarray]:
    w, h = cj["w"], cj["h"]
    out = {}
    for l in cj["layers"]:
        if l["kind"] == "backdrop":
            wa = np.asarray(Image.open(mesh / l["window"]))[..., 3] > 0
            fa = np.zeros((h, w), bool)
            x0, y0 = l["window_bbox"][:2]
            fa[y0:y0 + wa.shape[0], x0:x0 + wa.shape[1]] = wa
            out[l["frame"]] = binary_dilation(fa, iterations=13)
    return [out[k] for k in sorted(out)]


_UND: dict = {}


def _understand(path: Path) -> dict:
    """understand.json's panels, once per episode."""
    if path not in _UND:
        _UND[path] = json.loads(path.read_text(encoding="utf-8")).get("panels", {}) if path.exists() else {}
    return _UND[path]


def load_box(pid: str, mesh: Path) -> tuple[list[Card], list[Bubble], list[np.ndarray], tuple[int, int]] | None:
    """The box's character cards, bubbles (with their features) and frames, or None without cards."""
    cjp, bjp = mesh / f"{pid}.cards.json", mesh / f"{pid}.bubbles.json"
    if not cjp.exists():
        return None
    cj = json.loads(cjp.read_text())
    w, h = cj["w"], cj["h"]
    frames = frames_of(cj, mesh)
    bub = {b["id"]: b for b in json.loads(bjp.read_text(encoding="utf-8")).get("bubbles", [])} if bjp.exists() else {}
    # Understand runs after the layers (step 5), so bubbles.json holds its text, kind and anchor only when an earlier
    # run left them: read them from understand.json (its element ids are the bubble ids)
    und = _understand(mesh.parent.parent / "understand.json").get(str(int(pid.rsplit("-p", 1)[1])), {})
    for e in und.get("elements", []):
        b = bub.setdefault(e.get("id"), {})
        for k in ("text", "kind", "speaker", "anchor"):
            # the segmentation's kind is only "bubble" for any balloon: Understand's (speech, caption, shout) is finer
            generic = k == "kind" and b.get(k) in (None, "bubble")
            if (not b.get(k) or generic) and e.get(k) is not None:
                b[k] = e[k]
    cards, bubbles = [], []
    for l in cj["layers"]:
        if l["kind"] == "character":
            m = _mask_of(mesh / l["png"], l["bbox"], w, h)
            cards.append(Card(l["png"], l["kind"], l.get("frame"), m, _centroid(m), int(m.sum())))
        elif l["kind"] == "lettering":
            m = _mask_of(mesh / l["png"], l["bbox"], w, h)
            b = bub.get(l.get("bubble"), {})
            share = [int((m & f).sum()) for f in frames]
            fr = int(np.argmax(share)) if share and max(share) > 0 else None
            tip, dirn = tail(m)
            anc = b.get("anchor")
            bubbles.append(Bubble(l.get("bubble", -1), l["png"], b.get("kind"), b.get("text", ""), m, fr, _centroid(m),
                                  tip, dirn, (anc[0] * w, anc[1] * h) if anc else None, b.get("speaker")))
    # reading order: frames in order, then rows top to bottom, left to right (western, as Pepper&Carrot)
    row = max(1, h // 12)
    for k, b in enumerate(sorted(bubbles, key=lambda b: (b.frame if b.frame is not None else 99,
                                                         int(b.centroid[1] // row), b.centroid[0]))):
        b.order = k
    return cards, bubbles, frames, (w, h)


def groups(cards: list[Card]) -> list[list[int]]:
    """Speaking groups (user, 2026-10-27): two cards of one frame where the smaller is held or embraced by the bigger
    (at least GROUP_SHARE of its outline within GROUP_PX of the bigger card) answer together: Pepper with Carrot in her
    arms is one target, so a tail aimed at the cat names her too, and the pair moves together in the animation. Pairs
    only, each card in at most one (its strongest): mere contact chained a crowd into groups of up to 7 (P&C 38). No
    rule singles out animals."""
    n = len(cards)
    grown = [binary_dilation(c.mask, iterations=GROUP_PX) for c in cards]
    rim = [c.mask & ~binary_opening(c.mask, iterations=1) for c in cards]  # each card's outline
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if cards[i].frame != cards[j].frame:
                continue
            s, b = (i, j) if cards[i].area <= cards[j].area else (j, i)
            if not rim[s].any():
                continue
            share = (rim[s] & grown[b]).sum() / rim[s].sum()
            if share >= GROUP_SHARE:
                pairs.append((share, s, b))
    taken, out = set(), []
    for _, s, b in sorted(pairs, reverse=True):
        if s not in taken and b not in taken:
            taken |= {s, b}
            out.append(sorted([s, b]))
    return out + [[i] for i in range(n) if i not in taken]


def as_groups(cards: list[Card]) -> tuple[list[Card], list[list[int]]]:
    """One merged Card per group (mask union, frame of its members) and the member indices of each."""
    gs = groups(cards)
    merged = []
    for g in gs:
        m = np.logical_or.reduce([cards[i].mask for i in g])
        merged.append(Card("+".join(cards[i].key for i in g), "group", cards[g[0]].frame, m, _centroid(m), int(m.sum())))
    return merged, gs


def features(b: Bubble, cards: list[Card], frames: list[np.ndarray]) -> list[dict]:
    """Per candidate card: distance from the bubble (and from its tail tip), the tail's aim at it (cosine), same
    frame, the anchor inside it."""
    out = []
    for i, c in enumerate(cards):
        if not hasattr(c, "_dist"):  # the distance map to a card, once per box
            c._dist = edt(~c.mask)
        dist_c = c._dist
        bd = float(dist_c[b.mask].min()) if b.mask.any() else 1e9
        f = {"card": i, "same_frame": c.frame == b.frame, "dist": bd, "area": c.area}
        if b.tail_tip is not None:
            tx, ty = b.tail_tip
            f["tip_dist"] = float(dist_c[int(min(max(ty, 0), c.mask.shape[0] - 1)), int(min(max(tx, 0), c.mask.shape[1] - 1))])
            # aim: the cosine between the tail's direction and the way to the card (95th pct over its pixels)
            ys, xs = np.nonzero(c.mask)
            dx, dy = xs - tx, ys - ty
            dd = np.hypot(dx, dy) + 1e-6
            cos = (dx * b.tail_dir[0] + dy * b.tail_dir[1]) / dd
            f["aim"] = float(np.percentile(cos, 95))
        if b.anchor is not None:
            ax, ay = int(min(max(b.anchor[0], 0), c.mask.shape[1] - 1)), int(min(max(b.anchor[1], 0), c.mask.shape[0] - 1))
            f["anchor_dist"] = float(dist_c[ay, ax])
        out.append(f)
    return out


_GROUPS: dict = {}


def assign(b: Bubble, cards: list[Card], frames: list[np.ndarray]) -> dict:
    """The rule cascade run on speaking groups (as_groups), its answer given back as the member cards. Returns
    {"speakers": [card index], "speaker_kind", "confidence", "rule"}."""
    key = id(cards)
    if key not in _GROUPS or _GROUPS[key][0] is not cards:
        _GROUPS.clear()
        _GROUPS[key] = (cards, *as_groups(cards))
    _, merged, gs = _GROUPS[key]
    a = _assign(b, merged, frames)
    a["speakers"] = sorted(i for g in a["speakers"] for i in gs[g])
    return a


def _assign(b: Bubble, cards: list[Card], frames: list[np.ndarray]) -> dict:
    """The rule cascade (v0) over candidate cards (groups)."""
    if b.kind in SFX:
        return {"speakers": [], "speaker_kind": "sfx", "confidence": 0.9, "rule": "kind_sfx"}
    if b.kind in NARRATION:
        return {"speakers": [], "speaker_kind": "narrator", "confidence": 0.9, "rule": "kind_caption"}
    feats = features(b, cards, frames)
    b.feats = {"cands": feats, "tail": b.tail_tip is not None}
    if not feats:
        return {"speakers": [], "speaker_kind": "off_panel", "confidence": 0.5, "rule": "no_cards"}
    same = [f for f in feats if f["same_frame"]]
    if b.tail_tip is not None:
        aimed = [f for f in feats if f.get("aim", -1) > 0.85]
        if aimed:
            best = min(aimed, key=lambda f: f["tip_dist"] + (0 if f["same_frame"] else 200))
            return {"speakers": [best["card"]], "speaker_kind": "card", "confidence": 0.85, "rule": "tail"}
    if len(same) == 1:
        return {"speakers": [same[0]["card"]], "speaker_kind": "card", "confidence": 0.75, "rule": "single_in_frame"}
    if same:
        best = min(same, key=lambda f: f["dist"])
        return {"speakers": [best["card"]], "speaker_kind": "card", "confidence": 0.45, "rule": "nearest_in_frame"}
    best = min(feats, key=lambda f: f["dist"])
    return {"speakers": [best["card"]], "speaker_kind": "card", "confidence": 0.3, "rule": "nearest_other_frame"}


def run_box(pid: str, mesh: Path, write: bool = True) -> list[dict]:
    """Assign every bubble of a box; written into its cards.json when write. Returns one record per bubble."""
    got = load_box(pid, mesh)
    if got is None:
        return []
    cards, bubbles, frames, _ = got
    recs = []
    for b in bubbles:
        a = assign(b, cards, frames)
        recs.append({"pid": pid, "bubble": b.id, "key": b.key, "order": b.order, "kind": b.kind, "text": b.text,
                     "speakers": [cards[k].key for k in a["speakers"]], "speaker_kind": a["speaker_kind"],
                     "confidence": a["confidence"], "rule": a["rule"]})
    if write:
        cjp = mesh / f"{pid}.cards.json"
        cj = json.loads(cjp.read_text())
        by = {r["key"]: r for r in recs}
        for l in cj["layers"]:
            r = by.get(l["png"])
            if r:
                l.update({k: r[k] for k in ("speakers", "speaker_kind", "confidence", "rule", "order")})
        cjp.write_text(json.dumps(cj, indent=1))
    return recs


def main():
    import zipfile
    zumi, out = Path(sys.argv[1]), Path(sys.argv[2])
    n = len(json.loads(zipfile.ZipFile(zumi).read("manifest.json"))["panels"])
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")] if "--panels" in sys.argv else range(n)
    mesh = out / "parallax" / "mesh"
    for i in picks:
        for r in run_box(f"{zumi.stem}-p{i:03d}", mesh):
            print(f"{r['pid']} #{r['bubble']} [{r['rule']}] -> {r['speaker_kind']} {r['speakers']}  {r['text'][:40]!r}")


if __name__ == "__main__":
    main()
