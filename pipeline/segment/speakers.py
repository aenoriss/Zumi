"""Dialog-character association, card level (user, 2026-10-27): every bubble card of a box linked to the character
card(s) that speak it, as the groundwork for the LLM-led animation (cards moved across the scene, each bubble shown
once its speaker's move ends). Identity across boxes is not decided here.

Per bubble, from the box's flat layers (mesh/<pid>.cards.json, .bubbles.json) and its lettering mask:
  frame     the frame its stack is read in (home_frame, on the frame step's frames)
  tail      the bubble's tail, if it has one: the part of the mask a large opening removes, its tip the point farthest
            from the bubble's body; the direction body -> tip points at the speaker
  anchor    Understand's point on the speaker (bubbles.json), when Understand has run
Candidates are every character card in the box (any frame, a penalty across frames). The rules (assign) are tuned on
a labelled dataset (experiments/speaker_dataset.py, speaker_eval.py); what they leave undecided goes to an LLM with
the candidates numbered (TODO). A logistic regression over the same features, scored leave-one-episode-out on the
card-labelled bubbles (2026-10-30, speaker_lr.py, now only in the git history), got 255/278 (91.7%) where these
rules got 263/278 (94.6%), so the rules stay hand-written.

Writes the box's speakers.json (Box.save_speakers), one record per bubble: its lettering card ("key"), "speakers"
(character card png names, a chorus has several), "speaker_kind" (card | off_panel | narrator | sfx), "confidence"
(0-1), "rule" (which rule decided) and "order" (reading order in the box).

    uv run python speakers.py <episode.zumi> <out dir> [--panels 3,7]
"""
from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np
from scipy.ndimage import binary_dilation, binary_opening, distance_transform_edt as edt, label

import lettering_layer as LL
from boxstore import Box

TAIL_OPEN = 0.18      # the opening radius that strips a tail, as a share of the bubble's short side
TAIL_MIN_PX = 60      # a tail has at least this many pixels...
TAIL_MIN_LEN = 10     # ...and its tip lies at least this far out of the bubble's body
GROUP_PX = 4          # groups: a card's outline within this many px of another counts as touching it...
GROUP_SHARE = 0.30    # ...and this share of the smaller card's outline touching the bigger makes them one group
OTHER_FRAME_PENALTY = 1 / 6  # tail rule: an other-frame card is handicapped by this share of the box's long side (200 px at 1200)
CLUSTER_PX = 8        # reading order: bubbles this close (a stack) are read together...
STACK_MAX = 0.10      # ...unless one is a sound effect or covers this share of the box
TAU_CUT = 0.15        # reading order: a frame or bubble may cross a cut line by this share of its area
INSET_GAP = 6         # ...a frame ringed by a bigger one (this gutter, px)...
INSET_RING = 0.6      # ...on this share of its ring is an inset, read right after it
HOME_SHARE = 0.65     # a bubble cluster with this share in one frame is read there; less: its tail decides
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


def _centroid(m: np.ndarray) -> tuple[float, float]:
    ys, xs = np.nonzero(m)
    return (float(xs.mean()), float(ys.mean())) if len(xs) else (0.0, 0.0)


def tail_parts(mask: np.ndarray) -> dict | None:
    """What tail() sees, cropped to the bubble at (x0, y0): the opening radius r, the body (the bubble opened by r),
    and each part the opening strips, with its size, its reach out of the body and whether it can be a tail."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 200:
        return None
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    m = mask[y0:y1, x0:x1]
    r = max(3, int(TAIL_OPEN * min(m.shape)))
    k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))
    body = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, k) > 0
    out = {"x0": int(x0), "y0": int(y0), "r": r, "body": body, "parts": [], "d": None}
    if not body.any():
        return out
    rest = m & ~binary_dilation(body, iterations=2)
    lab, n = label(rest)
    d = out["d"] = edt(~body)
    for i in range(1, n + 1):
        part = lab == i
        py, px = np.unravel_index(np.argmax(np.where(part, d, -1)), d.shape)
        size, reach = int(part.sum()), float(d[py, px])
        out["parts"].append({"mask": part, "px": size, "reach": reach, "tip": (int(px), int(py)),
                             "kept": size >= TAIL_MIN_PX and reach >= TAIL_MIN_LEN})
    return out


def tail(mask: np.ndarray) -> tuple[tuple[float, float] | None, tuple[float, float] | None]:
    """(tip, unit direction from the body to the tip) of the bubble's tail, or (None, None): the kept part reaching
    furthest out of the body (tail_parts)."""
    t = tail_parts(mask)
    if t is None or not t["parts"]:
        return None, None
    kept = [p for p in t["parts"] if p["kept"]]
    if not kept:
        return None, None
    best = max(kept, key=lambda p: p["reach"])
    (px, py), part, d, body, x0, y0 = best["tip"], best["mask"], t["d"], t["body"], t["x0"], t["y0"]
    # the direction: from where the tail leaves the body to its tip
    by, bx = np.nonzero(part & (d <= 3))
    base = (float(bx.mean()), float(by.mean())) if len(bx) else _centroid(body)
    v = np.array([px - base[0], py - base[1]], float)
    n_ = np.linalg.norm(v)
    if n_ < 1e-6:
        return None, None
    return (float(px + x0), float(py + y0)), (float(v[0] / n_), float(v[1] / n_))


def home_frame(m: np.ndarray, tips: list, frames: list[np.ndarray], rank: list[int], flags: list[str] | None = None,
               name: str = "", nearest: bool = True) -> int | None:
    """The frame a bubble (or a stack of bubbles: m their union, tips their tail tips) belongs to: the frame holding
    HOME_SHARE of it, or the only one it touches; straddling frames, the one a tail tip lands in (the committee on
    frames, 2026-10-30: a crossing bubble ties a shot to its reverse shot, and its tail says which holds the
    speaker); with no tail there, the earlier in reading order (flagged); touching none, the nearest (nearest=False:
    none). The one rule for reading order (per stack) and the speaker rules' "same frame" (per bubble, no nearest
    frame: measured 2026-10-30 on the 333 labelled bubbles, homing a bubble with its stack lost 1-3, giving a bubble
    off every frame the nearest one lost 1)."""
    if not frames:
        return None
    share = np.array([(m & f).sum() for f in frames], float) / max(1, int(m.sum()))
    touched = [int(f) for f in np.argsort(-share) if share[f] > 0]
    if touched and (share[touched[0]] >= HOME_SHARE or len(touched) == 1):
        return touched[0]
    for t in tips:
        if t is not None:
            y, x = min(int(t[1]), m.shape[0] - 1), min(int(t[0]), m.shape[1] - 1)
            for f in touched:
                if frames[f][y, x]:
                    return f
    if touched:
        if flags is not None:
            flags.append(f"{name} straddles frames, no tail to decide")
        return min(touched, key=lambda f: rank[f])
    if not nearest:
        return None
    ys, xs = np.nonzero(m)
    c = (int(ys.mean()), int(xs.mean()))
    return int(np.argmin([edt(~f)[c] for f in frames]))


def load_box(box: Box) -> tuple[list[Card], list[Bubble], list[np.ndarray], tuple[int, int]] | None:
    """The box's character cards, bubbles (with their features and reading order) and frames (the frame step's,
    which its layers were built on), or None without cards."""
    cj = box.cards()
    if cj is None:
        return None
    w, h = cj["w"], cj["h"]
    fr = box.frames()
    frames = fr.masks if fr else []  # flat frames (credits) included: their mascots speak, and those bubbles are labelled
    bub = {b["id"]: b for b in (box.bubbles() or {}).get("bubbles", [])}
    # Understand's text, kind, speaker and anchor, joined as the layers join them (lettering_layer.understood): its
    # element ids are the bubble ids
    for e in box.understanding().get("elements", []):
        if "id" in e:
            b = bub.setdefault(int(e["id"]), {})
            b.update(LL.understood(e, b.get("kind")))
    cards, bubbles = [], []
    for l in cj["layers"]:
        if l["kind"] == "character":
            m = box.layer_mask(l, (h, w))
            cards.append(Card(l["png"], l["kind"], l.get("frame"), m, _centroid(m), int(m.sum())))
        elif l["kind"] == "lettering":
            m = box.layer_mask(l, (h, w))
            b = bub.get(l.get("bubble"), {})
            tip, dirn = tail(m)
            anc = b.get("anchor")
            bubbles.append(Bubble(l.get("bubble", -1), l["png"], b.get("kind"), b.get("text", ""), m, None, _centroid(m),
                                  tip, dirn, (anc[0] * w, anc[1] * h) if anc else None, b.get("speaker")))
    order_bubbles(bubbles, frames)  # also homes each bubble in its frame
    return cards, bubbles, frames, (w, h)


def order_bubbles(bubbles: list[Bubble], frames: list[np.ndarray]) -> list[str]:
    """Reading order (user, 2026-10-27; docs/research/panel-reading-order-2026-10.md): frames by a recursive cut
    (reading_order), each bubble cluster (a stack within CLUSTER_PX, read as a unit) in one frame (home_frame, which
    also sets each bubble's .frame), the clusters of a frame by the same cut, and the parts of a stack by it too.
    Sets .order and .frame on the bubbles; returns the flags of the decisions geometry is unsure of (an uncut group, a
    bubble straddling frames without a tail to decide it)."""
    flags: list[str] = []
    rank = [0] * len(frames)
    for k, i in enumerate(reading_order(frames, flags, insets=True)):
        rank[i] = k
    n = len(bubbles)
    parent = list(range(n))

    def root(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    # touching joins a stack only between balloons: a sound effect is read where it sits, and nothing as big as STACK_MAX
    # of the box is a balloon (36-p012: a 387k px "caption" over a whole panel touched a bubble of the next frame and
    # pulled it to the front). A container (it holds 90 % of the other) always joins its parts (38-p009: 18 % of a box).
    area = [int(b.mask.sum()) for b in bubbles]
    stackable = [b.kind != "sfx" and a < STACK_MAX * b.mask.size for b, a in zip(bubbles, area)]
    grown = [binary_dilation(b.mask, iterations=CLUSTER_PX) for b in bubbles]
    for i in range(n):
        for j in range(i + 1, n):
            inner = (bubbles[i].mask & bubbles[j].mask).sum() >= 0.9 * min(area[i], area[j])
            if inner or (stackable[i] and stackable[j] and (grown[i] & bubbles[j].mask).any()):
                parent[root(i)] = root(j)
    clusters: dict[int, list[int]] = {}
    for i in range(n):
        clusters.setdefault(root(i), []).append(i)
    units = list(clusters.values())
    masks = [np.logical_or.reduce([bubbles[i].mask for i in u]) for u in units]

    by_frame: dict[int, list[int]] = {}
    for k, (u, m) in enumerate(zip(units, masks)):
        f = home_frame(m, [bubbles[i].tail_tip for i in u], frames, rank, flags, f"bubble {bubbles[u[0]].id}")
        for i in u:  # each bubble's own frame, by the same rule on itself: the speaker rules' "same frame"
            bubbles[i].frame = home_frame(bubbles[i].mask, [bubbles[i].tail_tip], frames, rank, nearest=False)
        by_frame.setdefault(rank[f] if f is not None else 0, []).append(k)
    k = 0
    for fr in sorted(by_frame):
        idx = by_frame[fr]
        for q in reading_order([masks[c] for c in idx], flags):
            u = units[idx[q]]
            # a stack segmented once more as a whole (a container: 22 of 81 boxes) would span all its parts;
            # read the parts, the container just before its first
            area = {i: int(bubbles[i].mask.sum()) for i in u}
            holds = {i: [j for j in u if j != i and area[i] > area[j]
                         and (bubbles[i].mask & bubbles[j].mask).sum() >= 0.9 * area[j]] for i in u}
            parts = [i for i in u if not holds[i]]
            seq: list[int] = []
            for q2 in reading_order([bubbles[i].mask for i in parts], flags):
                seq += [i for i in u if parts[q2] in holds[i] and i not in seq] + [parts[q2]]
            for i in seq + [i for i in u if i not in seq]:
                bubbles[i].order = k
                k += 1
    return flags


def reading_order(masks: list[np.ndarray], flags: list[str] | None = None, insets: bool = False) -> list[int]:
    """Indices of the masks in Western reading order, by a recursive guillotine cut, horizontal cuts first (Tanaka 2007;
    Kovanen & Aizawa 2015 as in Manga109's estimator; Hinami 2021: 91.9 % of 258 pages): a cut line splits the set when
    every mask lies on one side, crossing it by at most TAU_CUT of its area; the halves are read top (or left) first.
    Two panels stacked beside a tall one read as a column first, as most readers do (Cohn 2013: 91 of 145). The row
    rule it replaced read top-left, tall, bottom-left. A set no cut splits (overlaps, pinwheels) is ranked by pairwise
    precedence (Magi's idea, on masks) and flagged. insets: a mask mostly ringed by one at least twice its size reads
    right after it."""
    n = len(masks)
    if n <= 1:
        return list(range(n))
    rows = [m.sum(1).cumsum() for m in masks]
    cols = [m.sum(0).cumsum() for m in masks]
    area = [max(1, int(r[-1])) for r in rows]
    parent: dict[int, int | None] = {i: None for i in range(n)}
    if insets:
        for i in range(n):
            ring = binary_dilation(masks[i], iterations=INSET_GAP + 3) & ~binary_dilation(masks[i], iterations=2)
            for j in range(n):
                if j != i and area[j] >= 2 * area[i] and (ring & masks[j]).sum() >= INSET_RING * max(1, ring.sum()):
                    parent[i] = j

    def cut(idx: list[int]) -> tuple[list[int], list[int]] | None:
        for cum in (rows, cols):  # horizontal cut lines first: rows top to bottom, the Z-path in grids
            cands = set()
            for i in idx:
                nz = np.nonzero(np.diff(np.concatenate([[0], cum[i]])))[0]
                if len(nz):
                    cands |= {int(nz[0]), int(nz[-1]) + 1}
            for pos in sorted(cands):
                a, b = [], []
                for i in idx:
                    f = cum[i][pos - 1] / area[i] if pos > 0 else 0.0
                    if f >= 1 - TAU_CUT:
                        a.append(i)
                    elif f <= TAU_CUT:
                        b.append(i)
                    else:
                        break
                else:
                    if a and b:
                        return a, b
        return None

    def first(a: int, b: int) -> bool:
        A, B = masks[a], masks[b]
        ca, ra = A.any(0) & B.any(0), A.any(1) & B.any(1)
        sc = ca.sum() / max(1, min(A.any(0).sum(), B.any(0).sum()))
        sr = ra.sum() / max(1, min(A.any(1).sum(), B.any(1).sum()))
        if sc == 0 and sr == 0:
            ta, tb = np.nonzero(A.any(1))[0][0], np.nonzero(B.any(1))[0][0]
            if abs(ta - tb) > 0.5 * min(A.any(1).sum(), B.any(1).sum()):
                return ta < tb
            return np.nonzero(A.any(0))[0][0] < np.nonzero(B.any(0))[0][0]
        if sc >= sr:  # one above the other: the higher first
            return np.nonzero(A[:, ca])[0].mean() < np.nonzero(B[:, ca])[0].mean()
        return np.nonzero(A[ra, :])[1].mean() < np.nonzero(B[ra, :])[1].mean()

    def top_left(i: int) -> tuple[int, int]:
        return int(np.searchsorted(rows[i], 1)), int(np.searchsorted(cols[i], 1))

    def xy(idx: list[int]) -> list[int]:
        if len(idx) <= 1:
            return list(idx)
        s = cut(idx)
        if s:
            return xy(s[0]) + xy(s[1])
        if flags is not None:
            flags.append(f"{len(idx)} {'frames' if insets else 'items'} no cut splits: ranked pairwise")
        wins = {i: sum(first(i, j) for j in idx if j != i) for i in idx}
        return sorted(idx, key=lambda i: (-wins[i], *top_left(i)))

    out: list[int] = []
    for i in xy([i for i in range(n) if parent[i] is None]):
        out += [i] + xy([k for k in range(n) if parent[k] == i])
    return out + [i for i in range(n) if i not in out]


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


def features(b: Bubble, cards: list[Card]) -> list[dict]:
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
    """The rule cascade (v1) over candidate cards (groups). Measured 2026-10-29 on all four P&C episodes (336 labelled
    bubbles; the tune/test split of speaker_eval.py was spent that day): a tail with an aimed card is right 209/212;
    the errors sit where no tail aims at a card. Tried and out: aim before tip distance (-2), sfx to the touching
    card (-7 to -19), chorus by touching cards (+1/-2), off-panel when no card is aimed (-6: the tail's direction is
    wrong on spiky shouts), Understand's speaker anchor as arbiter (0/40 against the tail)."""
    # a balloon of punctuation alone ("!!!", "???", "...") WITH a tail is a character's reaction, not a sound effect,
    # whatever Understand called it (8 of 8 in P&C 36-39, all tailed); without a tail it stays lettering
    reaction = b.tail_tip is not None and re.fullmatch(r"[!?.… ]+", (b.text or "").strip() or "x") is not None
    if b.kind in SFX and not reaction:
        return {"speakers": [], "speaker_kind": "sfx", "confidence": 0.9, "rule": "kind_sfx"}
    feats = features(b, cards)
    b.feats = {"cands": feats, "tail": b.tail_tip is not None}
    if b.kind in NARRATION:
        # a "caption" with a tail aimed at a card of its frame is speech in a box (P&C 39-p013: the song's lyrics)
        if not any(f["same_frame"] and f.get("aim", -1) > 0.85 for f in feats):
            return {"speakers": [], "speaker_kind": "narrator", "confidence": 0.9, "rule": "kind_caption"}
    if not feats:
        return {"speakers": [], "speaker_kind": "off_panel", "confidence": 0.5, "rule": "no_cards"}
    same = [f for f in feats if f["same_frame"]]
    # no chorus rule: "a shout touched by two cards" won "CHEERS! CHEERS! CHEERS!" (39-p008) and lost two laughing
    # single speakers in 38-p018 (2026-10-29, all four episodes). A chorus needs its own evidence (several tails)
    if b.tail_tip is not None:
        aimed = [f for f in feats if f.get("aim", -1) > 0.85]
        if aimed:
            # a card in another frame must be this much nearer the tip than one in the bubble's own frame to win:
            # a share of the box's long side, not pixels, so it holds at any page resolution
            penalty = OTHER_FRAME_PENALTY * max(b.mask.shape)
            best = min(aimed, key=lambda f: f["tip_dist"] + (0 if f["same_frame"] else penalty))
            return {"speakers": [best["card"]], "speaker_kind": "card", "confidence": 0.85, "rule": "tail"}
    if len(same) == 1:
        return {"speakers": [same[0]["card"]], "speaker_kind": "card", "confidence": 0.75, "rule": "single_in_frame"}
    if same:
        best = min(same, key=lambda f: f["dist"])
        return {"speakers": [best["card"]], "speaker_kind": "card", "confidence": 0.45, "rule": "nearest_in_frame"}
    best = min(feats, key=lambda f: f["dist"])
    return {"speakers": [best["card"]], "speaker_kind": "card", "confidence": 0.3, "rule": "nearest_other_frame"}


def run_box(box: Box, write: bool = True) -> list[dict]:
    """Assign every bubble of a box; saved as its speakers.json when write (Box.save_speakers: the layers can be
    rebuilt without losing it). Returns one record per bubble."""
    got = load_box(box)
    if got is None:
        return []
    cards, bubbles, frames, _ = got
    recs = []
    for b in bubbles:
        a = assign(b, cards, frames)
        recs.append({"pid": box.pid, "bubble": b.id, "key": b.key, "order": b.order, "kind": b.kind, "text": b.text,
                     "speakers": [cards[k].key for k in a["speakers"]], "speaker_kind": a["speaker_kind"],
                     "confidence": a["confidence"], "rule": a["rule"]})
    if write:
        box.save_speakers(recs)
    return recs


def main():
    from chapter import Chapter
    ch, out = Chapter(Path(sys.argv[1])), Path(sys.argv[2])
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")] if "--panels" in sys.argv else range(len(ch))
    for i in picks:
        for r in run_box(Box(out, ch.pid(i))):
            print(f"{r['pid']} #{r['bubble']} [{r['rule']}] -> {r['speaker_kind']} {r['speakers']}  {r['text'][:40]!r}")


if __name__ == "__main__":
    main()
