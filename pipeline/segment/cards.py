"""Steps 4-5 as flat layers (user, 2026-10-25): each box is a few textured rectangles facing the camera, and the depth
model only orders them. It replaced the depth-based surface (legacy_mesh.py): on close-ups DA3MONO gave a ramp with
no figure in it, and where it worked the surface came out as 1-3 M points for what reads as a few planes.

Per frame of the box (frames.py):
  backdrop    the erased plate (characters, lettering and, when erased, the chosen objects removed), alpha = the frame
  cards       one per character and per erased object: the original art, alpha = its mask (with its fringe of
              outline ink, claim_fringe) feathered FEATHER px
Every frame is a window at WINDOW_Z with its layers behind it (depths): the nearest card just behind the window, each
farther level STEP beyond, the backdrop at least BACKDROP_Z deep. DA3MONO, run on each frame alone in one pass (user,
2026-10-26; never on a whole box), only orders the cards by the median inside each mask (at most MAX_STEPS levels;
cards within TIE share a level) and shapes their relief.
A character the erase did not reach (refused, or the daily cap) is still a card, its copy left in the backdrop: a
doubled outline at a head move instead of a hole. The lettering is erased from the backdrop and comes back as cards of the
original bubbles (add_lettering), at the depth lettering_layer.place gives each.

Writes mesh/<pid>.cards.json ({w, h, fov, layers: [{png, bbox, z, kind, name}]}, far to near), mesh/<pid>.card-N.png
(each cropped to its bbox) and mesh/<pid>.json (size and fov, as the viewer and export_zumi.py read it).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

FOV = 55.0
# Depths (user, 2026-10-26: the headset values of docs/research/relief-depth-budget-2026-10.md, which replaced the
# desktop tuning: 2% steps were under 2 px of stereo at 1.5 m) are shares of d, the reading distance, where every
# frame's window stands (WINDOW_Z); everything lies behind it. The depth model only orders the cards.
WINDOW_Z = 1.0
NEAR_GAP = 0.005  # the nearest card's relief peak this far behind the window ("just behind the front of the window")
BACKDROP_Z = 1.20 # every frame's backdrop at least this deep (20% of d: 30 cm at 1.5 m), farther when the cards need it
BACKDROP_MAX = 1.25
BACK_GAP = 0.03   # the backdrop at least this far behind the farthest card plane
STEP = 0.04       # between card levels (6 cm at 1.5 m, ~2 px of stereo), squeezed down to STEP_MIN to fit BACKDROP_MAX
STEP_MIN = 0.025
MAX_STEPS = 4     # card levels per frame
PART_MIN = 50     # px a mask must have inside a frame to be a card there
MARGIN = 0.06     # share of the box's long side each backdrop runs past its frame (backdrop_image): the frame is a window
                  # in front of everything, and a head move must not look past the backdrop (a backdrop at 1.4 shifts
                  # ~66 px of a 1200 px box against the window at a 30 cm head move at 1.5 m)
RELIEF = 0.20     # a card's relief (its peak in front of its plane, shape from our per-frame depth, relief_map) is this
                  # times its short side, in units of d, within RELIEF_MIN..RELIEF_MAX: a fixed share left a face
                  # close-up flat (roundness ~0.13) and a small figure puffy. 0.25 / 10% "a bit" much (user, 2026-10-26)
RELIEF_MIN, RELIEF_MAX = 0.02, 0.08
BACK_RELIEF = 0.13   # the backdrop's relief in units of d, its tilt kept (a floor recedes), its nearest point 1% of d
                     # behind the farthest card plane; only on frames whose background has a depth range of its own
                     # (back_range_ok). 13% of d is 20 cm at 1.5 m, ~6 px of stereo across it and ~15 px of parallax
                     # at a 20 cm head move (user, 2026-10-26: 10% "a bit" more). 1.5-4% did not read; 20% bent the backdrop at small
                     # head moves: every backdrop is stretched over its own depth range, a shallow interior as deep as
                     # a street, and the median map climbs 30% of its range per 100 px (all broad shape, 89% of it
                     # left after a 2% blur). On close-ups the background is a sliver whose depth follows the figure's
                     # hair (P&C 39 p8, p24)
BACK_MIN_SHARE = 0.35   # ... the background (the frame minus the cards) at least this share of the frame
BACK_MIN_SPREAD = 0.5   # ... and its depth spread (2-98th pct) at least this share of the whole frame's
BACKDROP_RELIEF_MAX = 1.38  # a backdrop with relief may go this deep, so its near part stays behind the cards
HEAD_MOVE = 0.2 / 1.5   # the head move a backdrop's breaks are judged at: 20 cm at 1.5 m, in units of d
BREAK_STRETCH = 0.30    # backdrop_layers: a pixel whose texture stretches more than this at HEAD_MOVE is steep
BREAK_MIN_STEEP = 0.01  # ... a backdrop breaks only when this share of its frame is steep
BREAK_VALLEY = 0.5      # ... at a valley of its relief histogram under this share of the lower peak beside it
MAX_BREAKS = 0          # ... into at most this + 1 layers; off (user, 2026-10-26: with breaks, 2 then the backdrop
                        # still "heavily deforming"; backed off to the plain relief)
BACK_CELL = 8        # px of the box between the vertices of a backdrop's relief surface ("relief_cell"): at 24 per side
                     # the cells were 35-66 px (median 35 on P&C 39) and the depth's detail never reached the screen
BACK_EQUALIZE = 0.5  # kept when the detail boost and the breaks were backed off (user, 2026-10-26). The backdrop's
                     # relief blended this much with its histogram-equalised self (same order, values
                     # spread evenly over the range): on a street with sky (P&C 39 p2) the middle half of the pixels
                     # held 15% of the range, the sky and the nearest wall the ends (median over 44 backdrops 36%)
BACK_DETAIL = 0.0    # off (user, 2026-10-26: backed off, the backdrop bent at head moves; was 1.0). The backdrop depth's local detail (what an edge-preserving smoothing over BACK_BASE of the frame's
BACK_BASE = 0.05     # long side removes) is boosted by this much (1.0: doubled) before the relief is normalised: more
                     # depth contrast between neighbouring things (a cupboard off its wall) for the same total range
                     # (user, 2026-10-26); edge-preserving, so a depth jump does not grow a halo. Scaled per pixel by
                     # how drawn the art is there (drawn): the full boost on windows and furniture, none on a plain wall
DRAWN_BLUR = 0.01    # drawn(): the edge strength blurred over this share of the long side
DRAWN_PCT = 80       # drawn(): ... and divided by this percentile of it in the frame (above it: full boost)
BACK_BLUR = 0.003    # the backdrop's depth blurred by this share of its frame's long side before it becomes relief
RELIEF_CELL = 8   # px between the vertices of a character or object card's relief surface ("relief_cell")
RELIEF_DETAIL = 1.0    # a card's relief: detail boost where drawn, as BACK_DETAIL (relief_map)
RELIEF_EQUALIZE = 0.5  # ... and blend with its histogram-equalised self over the mask, as BACK_EQUALIZE
RELIEF_EDGE = 6   # px over which the relief fades to 0 at the card's outline
MERGE_TIE = 0.10  # an object touching a character whose median depth is within this share of the frame's depth spread
                  # of the character's joins the character's card: the couch the characters sit on (P&C 39 p8) split
                  # from them at a head move
TIE = 0.03        # cards whose median depths are within this share of their frame's depth spread share a step
FEATHER = 0.8     # px, Gaussian sigma on a card's alpha edge
PAD = 2           # px around a card's crop, so the feather is not cut
INSET = 0.01      # share of the box's long side each window is cut inside its frame (backdrop_image): the window sits in
                  # front of the cards' planes, and at a head move a card cut at the frame's edge slid its straight cut
                  # inside the frame (P&C 39 p1); a card plane 5% behind the window shifts ~7 px of a 1200 px box at a
                  # 20 cm head move at 1.5 m (12 px covers planes to ~8.5% at that move). Running the cards past the frame by their edge pixels looked
                  # bad (user, 2026-10-26)


TOUCH_PX = 15     # an item joins the object it is "on" only if their masks come this close: a wrong "on", or a link to
                  # a table in another frame, leaves the item a card of its own
HELD_PX = 3       # a held item joins the character whose mask it touches most, within this many px
EXCEPT_PX = 40    # an "except" point marks a character it lies in, or this close to


def join_supported(objects: list[dict]) -> list[dict]:
    """Objects ({"name", "mask", "on", "front", "except", ...}) with each item resting on another listed object merged
    into that object's card, through chains (a cup on a tray on a table), so they move together. "on" must match a
    name exactly, or after dropping a repeat number when that leaves one candidate; and the masks must touch
    (TOUCH_PX). A group takes its base's "front" and "except"."""
    import re
    from scipy.ndimage import binary_dilation
    by = {o["name"]: o for o in objects}
    base_of = lambda s: re.sub(r"\s+\d+$", "", s)

    def support(o):
        on = o.get("on")
        if not on:
            return None
        s = by.get(on)
        if s is None:
            cands = [p for p in objects if base_of(p["name"]) == base_of(on) and p is not o]
            s = cands[0] if len(cands) == 1 else None
        if s is None or s is o or not (binary_dilation(o["mask"], iterations=TOUCH_PX) & s["mask"]).any():
            return None
        return s

    def root(o):
        seen = {id(o)}
        while (s := support(o)) is not None and id(s) not in seen:
            o = s
            seen.add(id(o))
        return o

    groups: dict[int, list] = {}
    for o in objects:
        groups.setdefault(id(root(o)), []).append(o)
    out = []
    for os_ in groups.values():
        r = root(os_[0])
        out.append({**r, "name": " + ".join([r["name"]] + [o["name"] for o in os_ if o is not r]),
                    "mask": np.logical_or.reduce([o["mask"] for o in os_])})
    return out


def join_held(chars: list[np.ndarray], objects: list[dict]) -> tuple[list[np.ndarray], list[dict]]:
    """A held item joins the card of the character whose mask it touches most (within HELD_PX): drawn as painted, it
    can never be on the wrong side of its holder. With no character touching it, it stays an object."""
    from scipy.ndimage import binary_dilation
    chars, rest = [c.copy() for c in chars], []
    for o in objects:
        if o.get("held") and chars:
            grown = binary_dilation(o["mask"], iterations=HELD_PX)
            touch = [int((grown & c).sum()) for c in chars]
            if max(touch) > 0:
                chars[int(np.argmax(touch))] |= o["mask"]
                continue
        rest.append(o)
    return chars, rest


LETTER_GROW = 3   # px around a bubble's mask kept on its card: its drawn outline sits just outside the mask


def add_lettering(pid: str, img: np.ndarray, letter_masks: list[np.ndarray], bubbles: dict, mesh_dir: Path) -> int:
    """The lettering as cards of the ORIGINAL art (user, 2026-10-25: the redrawn bubbles looked off): each bubble's
    pixels, alpha = its mask grown LETTER_GROW px and feathered, at the depth lettering_layer.place chose for it
    (just in front of whatever is behind it). Appended to mesh/<pid>.cards.json, nearest last. Returns the count."""
    import cv2
    from scipy.ndimage import binary_dilation
    cj = mesh_dir / f"{pid}.cards.json"
    c = json.loads(cj.read_text())
    c["layers"] = [l for l in c["layers"] if l["kind"] != "lettering"]
    n = 1 + max((int(l["png"].rsplit("-", 1)[1].split(".")[0]) for l in c["layers"]), default=-1)
    added = []
    for b in bubbles.get("bubbles", []):
        k = b["id"] - 1
        if not (0 <= k < len(letter_masks)) or not letter_masks[k].any():
            continue
        m = binary_dilation(letter_masks[k], iterations=LETTER_GROW)
        alpha = cv2.GaussianBlur(m.astype(np.float32), (0, 0), FEATHER) if FEATHER else m.astype(np.float32)
        bb = _bbox(m, PAD)
        png = f"{pid}.card-{n}.png"
        _rgba(img, alpha, bb).save(mesh_dir / png)
        text = (b.get("text") or "").strip()
        added.append({"png": png, "bbox": bb, "z": b["depth"], "kind": "lettering",
                      "name": (text[:24] + "…") if len(text) > 24 else (text or f"lettering {b['id']}")})
        n += 1
    c["layers"] += sorted(added, key=lambda l: -l["z"])  # far to near among themselves, after the scene
    cj.write_text(json.dumps(c, indent=1))
    return len(added)


def order(M: np.ndarray, masks: list[np.ndarray], area: np.ndarray, behind: list[tuple[int, int]] = (),
          Mo: np.ndarray | None = None) -> list[int]:
    """The level of each mask, 0 = nearest (at most MAX_STEPS levels): M (or Mo, a second depth, when given) only
    ORDERS the cards, depths() spaces the levels. Cards whose median
    depths differ by less than TIE of the frame's depth spread share a step. behind: pairs (i, j) where mask i must be
    farther than mask j (an object the picker put behind the character it touches: the armchair's visible slivers
    around a seated man read nearer than him in DA3METRIC, ToG 228 p6)."""
    Mo = M if Mo is None else Mo
    lo, hi = np.percentile(Mo[area], [2, 98])
    tie = TIE * max(float(hi - lo), 1e-6)
    meds = [float(np.median(Mo[m])) for m in masks]
    for _ in range(len(masks)):  # push each constrained mask just past the one it must be behind, until none moves
        moved = False
        for i, j in behind:
            if meds[i] <= meds[j] + tie:
                meds[i] = meds[j] + 2 * tie
                moved = True
        if not moved:
            break
    steps = [0] * len(masks)
    step, prev = 0, None
    for k in sorted(range(len(masks)), key=lambda k: -meds[k]):  # far to near
        if prev is None or meds[k] < prev - tie:
            step, prev = min(step + 1, MAX_STEPS), meds[k]
        steps[k] = step
    return [max(steps) - s for s in steps]


def card_relief(m: np.ndarray, f: float) -> float:
    """A card's relief in units of d: RELIEF times its short side (the mask's box, px / f at the window's depth)."""
    ys, xs = np.nonzero(m)
    short = min(xs.max() - xs.min(), ys.max() - ys.min()) + 1
    return float(np.clip(RELIEF * short / f, RELIEF_MIN, RELIEF_MAX))


def depths(levels: list[int], reliefs: list[float], back: float = 0.0) -> tuple[float, float, list[float], list[float]]:
    """(backdrop depth, backdrop relief_amp, plane depth per card, relief_amp per card) from each card's level (0 =
    nearest), relief (units of d) and the backdrop's relief `back` (units of d, 0 for none): the nearest level's
    biggest relief peaks NEAR_GAP behind the window, each farther level's plane STEP beyond (squeezed to fit
    BACKDROP_MAX), no card peaking nearer than that; the backdrop BACK_GAP beyond the farthest plane and at least
    BACKDROP_Z deep, with relief deep enough (to BACKDROP_RELIEF_MAX) that its nearest point stays 1% of d behind that
    plane. A relief_amp is a share of the layer's own depth (the reader puts the peak at z * (1 - relief_amp))."""
    if not levels:
        return BACKDROP_Z + back / 2, back / (BACKDROP_Z + back / 2), [], []
    nl = max(levels) + 1
    p0 = WINDOW_Z + NEAR_GAP + max(r for l, r in zip(levels, reliefs) if l == 0)
    step = STEP if nl == 1 else max(STEP_MIN, min(STEP, (BACKDROP_MAX - BACK_GAP - p0) / (nl - 1)))
    planes = [p0 + step * l for l in levels]
    far = max(planes)
    cap = BACKDROP_RELIEF_MAX if back else BACKDROP_MAX
    zb = max(far + 0.01, min(cap, max(BACKDROP_Z, far + BACK_GAP, far + 0.01 + back)))
    amps = [min(r, p - WINDOW_Z - NEAR_GAP) / p for p, r in zip(planes, reliefs)]
    return zb, max(0.0, min(back, zb - far - 0.01)) / zb, planes, amps


def back_range_ok(M: np.ndarray, area: np.ndarray, covered: np.ndarray) -> bool:
    """Whether a frame's background has a depth range of its own: it covers BACK_MIN_SHARE of the frame (the cards
    grown 4 px, their feathered outlines are not background) and spans BACK_MIN_SPREAD of the frame's depth spread.
    Thresholds from P&C 39 p2, p8, p13, p24 (experiments/backdrop_depth.py): the street and the tavern 88% / 59% of
    the frame and 100% / 93% of its spread, the close-ups 5-41% and 30-65%."""
    from scipy.ndimage import binary_dilation
    bg = area & ~binary_dilation(covered, iterations=4)
    if bg.sum() < BACK_MIN_SHARE * area.sum():
        return False
    fl, fh = np.percentile(M[area], [2, 98])
    bl, bh = np.percentile(M[bg], [2, 98])
    return (bh - bl) >= BACK_MIN_SPREAD * (fh - fl)


def merge_level(segs: list[tuple], M: np.ndarray, area: np.ndarray) -> list[tuple]:
    """Objects that touch a character (within 3 px) at the character's depth (median within MERGE_TIE of the frame's
    depth spread) join that character's card: the couch the characters sit on, the chair under a seated man. As two
    cards a step apart they split at a head move (P&C 39 p8). Each goes to the touching character nearest in depth."""
    from scipy.ndimage import binary_dilation
    lo, hi = np.percentile(M[area], [2, 98])
    tie = MERGE_TIE * max(float(hi - lo), 1e-6)
    med = lambda m: float(np.median(M[m & area])) if (m & area).any() else float("nan")
    chars = [list(s) for s in segs if s[0] == "character"]
    cmed = [med(c[2]) for c in chars]
    out = []
    for s in segs:
        if s[0] != "object" or not chars:
            continue
        grown = binary_dilation(s[2], iterations=3)
        om = med(s[2])
        best = min((abs(om - cmed[k]), k) for k, c in enumerate(chars) if (grown & c[2]).any()) if any(
            (grown & c[2]).any() for c in chars) else None
        if best is not None and best[0] <= tie:
            chars[best[1]][2] = chars[best[1]][2] | s[2]
            chars[best[1]][1] = f"{chars[best[1]][1]} + {s[1]}"
        else:
            out.append(s)
    return [tuple(c) for c in chars] + out


def exclusive(segs: list[tuple]) -> list[tuple]:
    """Every pixel on one card only, the smaller (more specific) mask keeping what two share; a card left under
    PART_MIN px is dropped. Two cards holding the same pixels each bent them by their own relief and they slid apart
    at a head move, a doubled face (pin 261026-045646: P&C 39 p3's "character 1" was Pepper with the dress she holds,
    "character 4" Pepper alone, 37,146 px shared; on p2 one mask held 89-96% of three others)."""
    claimed, out = None, {}
    for i in sorted(range(len(segs)), key=lambda i: int(segs[i][2].sum())):
        m = segs[i][2] if claimed is None else segs[i][2] & ~claimed
        claimed = m.copy() if claimed is None else claimed | m
        if m.sum() >= PART_MIN:
            out[i] = (segs[i][0], segs[i][1], m, segs[i][3])
    return [out[i] for i in sorted(out)]


def padded(a: np.ndarray, bb, fill=0) -> np.ndarray:
    """a[y0:y1, x0:x1] for a box that may reach past the image (a backdrop's margin), filled with `fill` outside."""
    x0, y0, x1, y1 = bb
    h, w = a.shape[:2]
    out = np.full((y1 - y0, x1 - x0) + a.shape[2:], fill, a.dtype)
    sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
    out[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0] = a[sy0:sy1, sx0:sx1]
    return out


def backdrop_image(rgb: np.ndarray, area: np.ndarray, m: int, inset: int = 0) -> tuple[Image.Image, tuple, Image.Image, tuple]:
    """(backdrop RGBA, its box, window RGBA, its box). The backdrop runs m px past its frame, so a head move through
    the window in front never looks past it: each pixel out there takes the colour of the frame pixel mirrored across
    the nearest edge point (the nearest frame pixel itself where the mirror falls outside the frame). The nearest
    frame pixel's colour alone streaked the edge outward, and with the backdrop 20-38% behind the window a head move
    showed the streaks (user, 2026-10-26); the reader stretching the texture's edge made a vignette's brush stroke at
    its box edge a line (P&C 39 p5). The window is the frame's shape cut inset px inside it (alpha), on the frame's
    box."""
    from scipy.ndimage import distance_transform_edt
    fb = _bbox(area, 0)
    eb = (fb[0] - m, fb[1] - m, fb[2] + m, fb[3] + m)
    a = padded(area, eb, False)
    col, dist = mirror_fill(padded(rgb, eb, 0), a)
    alpha = (dist <= m).astype(np.uint8) * 255
    back = Image.fromarray(np.dstack([col, alpha]), "RGBA")
    inner = distance_transform_edt(a)[m:m + fb[3] - fb[1], m:m + fb[2] - fb[0]] > inset
    win = Image.fromarray(np.dstack([rgb[fb[1]:fb[3], fb[0]:fb[2]], (inner * 255).astype(np.uint8)]), "RGBA")
    return back, eb, win, fb


def mirror_fill(rgb: np.ndarray, own: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(rgb with every pixel outside `own` taking the own pixel mirrored across the nearest own point, or that nearest
    own pixel where the mirror falls outside `own`; the distance to `own`). Continues the texture instead of streaking
    its edge pixel outward."""
    from scipy.ndimage import distance_transform_edt
    dist, (iy, ix) = distance_transform_edt(~own, return_indices=True)
    Y, X = np.indices(own.shape)
    ry, rx = np.clip(2 * iy - Y, 0, own.shape[0] - 1), np.clip(2 * ix - X, 0, own.shape[1] - 1)
    return np.where(own[ry, rx][..., None], rgb[ry, rx], rgb[iy, ix]), dist


def backdrop_relief(area: np.ndarray, Mb: np.ndarray, eb, rgb: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """The backdrop's relief over its box eb (the frame and its margin), at full resolution: Mb is DA3MONO on the
    backdrop itself (rgb), the erased plate under the cards, so it is the
    background's depth there and not a fill; in the margin the depth of the nearest frame pixel. Its tilt kept (a
    floor recedes), normalised over the frame (2nd-98th percentile), white = nearest. A nearest-background fill under
    the cards on the original's depth left flat plateaus in the characters' shapes (P&C 39 p5). Returns (relief,
    the relief before the even spread: its histogram keeps the valleys backdrop_layers splits at), 0..1 floats."""
    import cv2
    from scipy.ndimage import distance_transform_edt
    a = padded(area, eb, False)
    _, (iy, ix) = distance_transform_edt(~a, return_indices=True)
    d = padded(Mb.astype(np.float32), eb, 0)[iy, ix]
    d = cv2.GaussianBlur(d, (0, 0), max(0.5, BACK_BLUR * max(d.shape)))
    norm = lambda v: (v - np.percentile(v[a], 2)) / max(float(np.subtract(*np.percentile(v[a], [98, 2]))), 1e-6)
    h = norm(-d).astype(np.float32)
    if BACK_DETAIL:  # depth contrast: the detail over an edge-preserving base boosted where the art is drawn
        base = guided_filter(h, h, max(2, round(BACK_BASE * max(d.shape))), 0.01)
        h = norm(base + (1 + BACK_DETAIL * drawn(padded(rgb, eb, 0)[iy, ix], a)) * (h - base))
    h = pre = np.clip(h, 0, 1)
    if BACK_EQUALIZE:  # each value's rank among the frame's pixels: an even spread, the order kept
        ranks = np.sort(h[a][:: max(1, int(a.sum()) // 200000)])
        h = (1 - BACK_EQUALIZE) * h + BACK_EQUALIZE * np.interp(h, ranks, np.linspace(0, 1, len(ranks)))
    return h.astype(np.float32), pre.astype(np.float32)


def backdrop_layers(h: np.ndarray, pre: np.ndarray, a: np.ndarray, rgb: np.ndarray,
                    stretch: float) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """The backdrop broken at its big depth edges (user, 2026-10-26): as one surface, a roof against the sky or a
    cupboard against its wall was a steep ramp whose texture stretched at a head move (over 30% on 5-7% of P&C 39 p2,
    p4, p28). h: the relief over the backdrop's box, pre: before the even spread, a: the frame on that box, rgb: the
    backdrop's colours there, stretch: the texture stretch at a HEAD_MOVE per unit of relief slope (per px).

    Where over BREAK_MIN_STEEP of the frame stretches more than BREAK_STRETCH, the relief values are cut at up to
    MAX_BREAKS valleys of pre's histogram (few pixels sit between a roof and the sky) that the steep pixels cross.
    Returns [(mask, relief, rgb)] far to near over the box: layer k covers every pixel at its depth or nearer (it goes
    on under the nearer layers), its relief there its own, its steep pixels and the pixels under nearer layers taking
    the nearest of its own flat ones (no ramp left at a break), its colours under nearer layers mirrored from its own
    (what a head move uncovers continues its texture). One layer, the relief whole, when nothing needs breaking."""
    from scipy.ndimage import distance_transform_edt, gaussian_filter1d
    gy, gx = np.gradient(h)
    steep = a & (stretch * np.hypot(gx, gy) > BREAK_STRETCH)
    whole = [(np.ones_like(a), h, rgb)]
    if steep.sum() < BREAK_MIN_STEEP * a.sum():
        return whole
    bins = 64
    hist = gaussian_filter1d(np.histogram(pre[a], bins, (0, 1))[0].astype(np.float64), 1.5)
    shist = np.histogram(pre[steep], bins, (0, 1))[0]
    cuts = []
    for b in range(3, bins - 3):
        if hist[b] > hist[b - 1] or hist[b] > hist[b + 1]:
            continue
        if hist[b] > BREAK_VALLEY * min(hist[:b].max(), hist[b + 1:].max()):
            continue
        cuts.append((shist[max(0, b - 2):b + 3].sum(), (b + 0.5) / bins))
    cuts = sorted(t for s, t in sorted(cuts, reverse=True)[:MAX_BREAKS] if s >= BREAK_MIN_STEEP * a.sum() / 4)
    if not cuts:
        return whole
    lab = np.digitize(pre, cuts)  # 0 = farthest
    out = []
    for k in range(len(cuts) + 1):
        own = lab == k
        flat = own & ~steep
        if flat.sum() < 50:
            flat = own
        if not own.any():
            continue
        _, (iy, ix) = distance_transform_edt(~flat, return_indices=True)
        rel = np.where(flat, h, h[iy, ix])
        col, _ = mirror_fill(rgb, own)
        out.append((lab >= k, rel.astype(np.float32), col))
    out[0] = (np.ones_like(a), out[0][1], out[0][2])  # the farthest layer is the whole backdrop
    return out


def drawn(rgb: np.ndarray, a: np.ndarray) -> np.ndarray:
    """0..1 per pixel, how much the art is drawn around it: the image's edge strength (Sobel), blurred over
    DRAWN_BLUR of the long side, over its DRAWN_PCT percentile in the frame. Where it is 0 (a plain wall) the depth's
    detail is the model's wobble, not a shape: at a flat boost it became dark bands at a head move (P&C 39 p16)."""
    import cv2
    g = cv2.cvtColor(rgb.astype(np.uint8), cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
    e = np.hypot(cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1))
    e = cv2.GaussianBlur(e, (0, 0), max(1.0, DRAWN_BLUR * max(g.shape)))
    return np.clip(e / max(float(np.percentile(e[a], DRAWN_PCT)), 1e-6), 0, 1)


def guided_filter(I: np.ndarray, p: np.ndarray, r: int, eps: float) -> np.ndarray:
    """He et al.'s guided filter (grey guide I): p smoothed over a (2r+1) box except where I varies by more than eps
    (variance); with I = p it is an edge-preserving smoothing."""
    import cv2
    box = lambda x: cv2.boxFilter(x, -1, (2 * r + 1, 2 * r + 1))
    mI, mp = box(I), box(p)
    A = (box(I * p) - mI * mp) / (box(I * I) - mI * mI + eps)
    return box(A) * I + box(mp - A * mI)


def relief_map(m: np.ndarray, M: np.ndarray, rgb: np.ndarray) -> Image.Image:
    """A card's relief, grey, white = nearest, at the card's resolution, from OUR depth (user, 2026-10-26): the
    frame's DA3MONO depth inside the mask, its tilt removed (a plane fitted over the mask: the figure as a whole stays on
    its card), normalised over the mask (5th-95th percentile); then, as the backdrop's (backdrop_relief), its detail
    over an edge-preserving base boosted by RELIEF_DETAIL where the card's art (rgb) is drawn, and blended
    RELIEF_EQUALIZE with its histogram-equalised self over the mask; last faded to 0 over RELIEF_EDGE px at the
    outline so the card keeps its edge on its plane. The reader bulges the card by relief_amp of its depth times this
    value, each point along its own camera ray (no change at rest). A mask-shape dome replaced: every card had the same
    round bulge. At 48 px on its long side (drawn on a 24 x 24 grid) a face close-up had no features in depth."""
    from scipy.ndimage import distance_transform_edt
    h = np.zeros(m.shape, np.float32)
    if m.sum() >= 30:
        v, u = np.nonzero(m)
        A = np.stack([u, v, np.ones_like(u)], 1).astype(np.float64)
        coef, *_ = np.linalg.lstsq(A, M[m].astype(np.float64), rcond=None)
        near = -(M[m] - A @ coef)  # depth grows away from the camera: nearer is the negative residual
        lo, hi = np.percentile(near, [5, 95])
        h[m] = (near - lo) / max(float(hi - lo), 1e-6)
        # outside the mask the nearest inside value, so the filters see no false edge at the outline
        _, (iy, ix) = distance_transform_edt(~m, return_indices=True)
        h = h[iy, ix]
        if RELIEF_DETAIL:
            base = guided_filter(h, h, max(2, round(BACK_BASE * max(m.shape))), 0.01)
            h = base + (1 + RELIEF_DETAIL * drawn(rgb, m)) * (h - base)
            lo, hi = np.percentile(h[m], [5, 95])
            h = (h - lo) / max(float(hi - lo), 1e-6)
        h = np.clip(h, 0, 1)
        if RELIEF_EQUALIZE:
            ranks = np.sort(h[m][:: max(1, int(m.sum()) // 200000)])
            h = (1 - RELIEF_EQUALIZE) * h + RELIEF_EQUALIZE * np.interp(h, ranks, np.linspace(0, 1, len(ranks)))
        h = np.where(m, h, 0) * np.clip(distance_transform_edt(m) / RELIEF_EDGE, 0, 1)
    return Image.fromarray((h * 255).astype(np.uint8))


def depth_view(M: np.ndarray, areas: list[np.ndarray], path: Path) -> None:
    """The depth the cards were ordered by, each frame normalised on its own (2nd-98th percentile), bright = near,
    the page black: the viewer's "depth" view."""
    vis = np.zeros(M.shape, np.float32)
    for a in areas:
        if a.sum() < 100:
            continue
        lo, hi = np.percentile(M[a], [2, 98])
        vis[a] = np.clip((hi - M[a]) / max(float(hi - lo), 1e-6), 0, 1)
    Image.fromarray((vis * 255).astype(np.uint8)).save(path)


SEG_COL = {"character": [(230, 60, 60), (240, 130, 40), (220, 50, 160), (200, 90, 90)],
           "object": [(40, 120, 230), (40, 190, 210), (110, 90, 230), (60, 160, 120)],
           "lettering": [(60, 200, 80)]}


def seg_view(img: np.ndarray, chars: list[np.ndarray], objects: list[tuple[str, np.ndarray]],
             letters: list[np.ndarray], frames: list[np.ndarray], path: Path) -> None:
    """The box with every mask tinted (characters warm, objects cool, lettering green) and each frame outlined in
    magenta: the viewer's "segmentation" view."""
    from PIL import ImageDraw
    from scipy.ndimage import binary_dilation
    out = img.astype(np.float32).copy()
    for kind, ms in (("lettering", letters), ("object", [m for _, m in objects]), ("character", chars)):
        for k, m in enumerate(ms):
            c = np.array(SEG_COL[kind][k % len(SEG_COL[kind])], np.float32)
            out[m] = out[m] * 0.45 + c * 0.55
            edge = binary_dilation(m, iterations=2) & ~m
            out[edge] = c
    pic = Image.fromarray(out.astype(np.uint8))
    d = ImageDraw.Draw(pic)
    for f in frames if len(frames) > 1 else []:
        ys, xs = np.nonzero(f)
        d.rectangle([int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())], outline=(255, 0, 255), width=4)
    pic.save(path)


def frame_depth(depth_fn, rgb: np.ndarray, areas: list[np.ndarray]) -> np.ndarray:
    """Relative depth with each frame inferred on its own crop: on a box of a wide shot beside two close-ups the
    models saw one blurred scene and the characters vanished (P&C 39 p24: figure-ground separation +2.18 / +18.30 /
    +3.28 per frame with DA3MONO per frame, -0.08 / +0.64 / +0.97 with DA3METRIC on the whole box)."""
    D = np.zeros(rgb.shape[:2], np.float32)
    for a in areas:
        if not a.any():
            continue
        ys, xs = np.nonzero(a)
        y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
        D[y0:y1, x0:x1] = np.where(a[y0:y1, x0:x1], depth_fn(rgb[y0:y1, x0:x1]), D[y0:y1, x0:x1])
    return D


def _rgba(rgb: np.ndarray, alpha: np.ndarray, bbox) -> Image.Image:
    x0, y0, x1, y1 = bbox
    a = (np.clip(alpha[y0:y1, x0:x1], 0, 1) * 255).astype(np.uint8)
    return Image.fromarray(np.dstack([rgb[y0:y1, x0:x1], a]), "RGBA")


def _bbox(m: np.ndarray, pad: int) -> tuple[int, int, int, int]:
    ys, xs = np.nonzero(m)
    h, w = m.shape
    return (max(0, int(xs.min()) - pad), max(0, int(ys.min()) - pad), min(w, int(xs.max()) + 1 + pad),
            min(h, int(ys.max()) + 1 + pad))


def build(pid: str, img: np.ndarray, chars: list[np.ndarray], objects: list[dict],
          plate: np.ndarray, g: np.ndarray, M: np.ndarray, mesh_dir: Path,
          fringe: np.ndarray | None = None, lettering: np.ndarray | None = None, order_fn=None,
          depth_img: np.ndarray | None = None, depth_fn=None,
          frames: list[np.ndarray] | None = None) -> tuple[dict, np.ndarray]:
    """img: the original box (RGB). chars: one mask per character. objects: the picker's objects erased from the
    plate ({"name", "mask", "on", "held", "front", "except"}; empty when the objects were not erased: they stay
    painted on it); held ones join their holder, supported ones their support. plate: the erased plate. g: the page
    around the art. M: a depth map of the box, or None with depth_fn: rgb crop -> depth, run on each frame alone
    (frame_depth) on depth_img (the lettering-free image when there is one); it gives the backdrops' distance and
    orders the cards. order_fn (optional): a second per-frame depth that only orders the cards.
    lettering: the erased lettering (redrawn by the reader).
    Returns (log info, depth per pixel of the nearest layer, 0 on the page: what the lettering is placed against).
    The backdrop is the original art except under the cards and the lettering, where it is the plate: the erase
    model also removes cast shadows and redraws outlines in the band its mask is grown by, and showing the plate
    there put a lighter floor where the character's shadow was (3.2% of ToG 228 p6's art off by more than 40)."""
    import cv2
    import frames as FR
    from scipy.ndimage import binary_dilation, distance_transform_edt
    h, w = g.shape
    art = ~g
    # the fringe (outline ink just outside a mask) goes to the nearest character's card
    chars = [c & art for c in chars if c.any()]
    if fringe is not None and fringe.any() and chars:
        lab = np.zeros((h, w), np.int32)
        for k, c in enumerate(chars, 1):
            lab[c] = k
        _, (iy, ix) = distance_transform_edt(lab == 0, return_indices=True)
        near = lab[iy, ix]
        chars = [c | (fringe & art & (near == k)) for k, c in enumerate(chars, 1)]
    chars, objects = join_held(chars, objects)
    objects = join_supported(objects)
    segs = [("character", f"character {k + 1}", c, None) for k, c in enumerate(chars)]
    segs += [("object", o["name"], o["mask"] & art, o) for o in objects if (o["mask"] & art).any()]
    under = binary_dilation(np.logical_or.reduce([s[2] for s in segs]), iterations=PAD) if segs else np.zeros((h, w), bool)
    if lettering is not None:
        under |= lettering
    backdrop = np.where(under[..., None], plate, img)
    # the frames of step 1 (episode.box_frames) when given, else found here
    fr = frames if frames is not None else FR.frames(Image.fromarray(img), g)
    areas = [f & art for f in fr] if len(fr) > 1 else [art]
    # depth only ever per frame (user, 2026-10-26)
    dimg = img if depth_img is None else depth_img
    if depth_fn is not None:
        M = frame_depth(depth_fn, dimg, areas)
    Mo = frame_depth(order_fn, dimg, areas) if order_fn is not None else None
    mesh_dir.mkdir(parents=True, exist_ok=True)
    depth_view(M if Mo is None else Mo, areas, mesh_dir / f"{pid}.depth.png")
    # this box's earlier output, cards and the legacy surface's files (legacy_mesh.py), so nothing reads a stale one
    for pat in (f"{pid}.card-*.png", f"{pid}.f32", f"{pid}.png", f"{pid}.ldi.*", f"{pid}.fig.*", f"{pid}.bg*",
                f"{pid}.fgclean.*", f"{pid}.seg.u8", f"{pid}.layers.json"):
        for old in mesh_dir.glob(pat):
            old.unlink()
    mesh_dir.mkdir(parents=True, exist_ok=True)
    layers, D = [], np.zeros((h, w), np.float32)
    n = 0
    for fk, area in enumerate(areas):
        if area.sum() < 1000:
            continue
        # every card the plate was erased under is kept, however small (dropped, an erased vase left only its outline
        # in the backdrop); a mask spanning several frames is a card in each, its part there: the review merges copies
        # of one character across frames into one mask, and given whole to the frame holding most of it, P&C 39 p10's
        # Pepper vanished from the wide frame (erased from the backdrop, on no card)
        mine = [(s[0], s[1], s[2] & area, s[3]) for s in segs if (s[2] & area).sum() >= PART_MIN]
        mine = merge_level(mine, M if Mo is None else Mo, area)
        mine = exclusive(mine)
        # the picker's front/behind for each object against every character it touches (within 3 px), reversed for
        # the characters its "except" points mark (a counter in front of the barkeeper, behind the customer)
        behind = []
        for a_, (ka, _, ma, o) in enumerate(mine):
            if ka != "object":
                continue
            grown = binary_dilation(ma, iterations=3)
            for c_, (kc, _, mc, _) in enumerate(mine):
                if kc == "character" and (grown & mc).any():
                    near = binary_dilation(mc, iterations=EXCEPT_PX)
                    flip = any(0 <= y < h and 0 <= x < w and near[y, x] for x, y in o.get("except") or [])
                    behind.append((c_, a_) if bool(o.get("front")) != flip else (a_, c_))
        f = max(w, h) / (2 * np.tan(np.radians(FOV / 2)))
        covered = np.logical_or.reduce([s[2] for s in mine]) if mine else np.zeros_like(area)
        relief_on = BACK_RELIEF > 0 and back_range_ok(M if Mo is None else Mo, area, covered)
        zb, ampb, zs, amps = depths(order(M, [s[2] & area for s in mine], area, behind, Mo),
                                    [card_relief(s[2] & area, f) for s in mine], BACK_RELIEF if relief_on else 0.0)
        back, eb, win, fb = backdrop_image(backdrop, area, round(MARGIN * max(w, h)), round(INSET * max(w, h)))
        win.save(mesh_dir / f"{pid}.card-{n}.window.png")
        # "frame": the reader shows each frame's layers through a window of the frame's shape ("window", on
        # "window_bbox", at depth "window_z") in front of them (user, 2026-10-26); lettering is not clipped. The
        # backdrop's box runs past the frame by its margin and may reach past the image
        layers.append({"png": f"{pid}.card-{n}.png", "bbox": [int(v) for v in eb], "z": round(zb, 5),
                       "kind": "backdrop", "name": f"backdrop {fk + 1}", "frame": fk,
                       "window": f"{pid}.card-{n}.window.png", "window_bbox": [int(v) for v in fb],
                       "window_z": WINDOW_Z})
        parts = []
        if ampb > 0:
            # depth on the backdrop's own frame (the erased plate under the cards), only for a frame with relief;
            # broken at its big depth edges into layers far to near (backdrop_layers), the first the backdrop itself
            rel, pre = backdrop_relief(area, frame_depth(depth_fn, backdrop, [area]) if depth_fn is not None else M,
                                       eb, backdrop)
            ba = np.asarray(back)
            parts = backdrop_layers(rel, pre, padded(area, eb, False), ba[..., :3].copy(),
                                    f * HEAD_MOVE * ampb / zb)
            back = Image.fromarray(np.dstack([parts[0][2], ba[..., 3]]), "RGBA")
            Image.fromarray((parts[0][1] * 255).astype(np.uint8)).save(mesh_dir / f"{pid}.card-{n}.relief.png")
            layers[-1].update({"relief": f"{pid}.card-{n}.relief.png", "relief_amp": round(ampb, 5),
                               "relief_cell": BACK_CELL})
        back.save(mesh_dir / f"{pid}.card-{n}.png")
        D[area] = zb * (1 - ampb)  # the nearest each layer gets: the lettering is placed in front of it
        n += 1
        for k, (pm, prel, pcol) in enumerate(parts[1:], 2):
            # a nearer layer of the backdrop: a card on the backdrop's plane and relief scale, cut at its break
            alpha = cv2.GaussianBlur(pm.astype(np.float32), (0, 0), FEATHER) * (np.asarray(back)[..., 3] / 255)
            cb = _bbox(pm, PAD)
            sl = np.s_[cb[1]:cb[3], cb[0]:cb[2]]
            Image.fromarray(np.dstack([pcol[sl], (np.clip(alpha[sl], 0, 1) * 255).astype(np.uint8)]), "RGBA").save(
                mesh_dir / f"{pid}.card-{n}.png")
            Image.fromarray((prel[sl] * 255).astype(np.uint8)).save(mesh_dir / f"{pid}.card-{n}.relief.png")
            layers.append({"png": f"{pid}.card-{n}.png",
                           "bbox": [int(eb[0] + cb[0]), int(eb[1] + cb[1]), int(eb[0] + cb[2]), int(eb[1] + cb[3])],
                           "z": round(zb, 5), "kind": "scenery", "name": f"backdrop {fk + 1} layer {k}", "frame": fk,
                           "relief": f"{pid}.card-{n}.relief.png", "relief_amp": round(ampb, 5),
                           "relief_cell": BACK_CELL})
            n += 1
        for (kind, name, m, _), z, amp in sorted(zip(mine, zs, amps), key=lambda c: -c[1]):
            m = m & area
            alpha = cv2.GaussianBlur(m.astype(np.float32), (0, 0), FEATHER) if FEATHER else m.astype(np.float32)
            alpha *= art
            bb = _bbox(m, PAD)
            _rgba(img, alpha, bb).save(mesh_dir / f"{pid}.card-{n}.png")
            relief_map(m[bb[1]:bb[3], bb[0]:bb[2]], (M if Mo is None else Mo)[bb[1]:bb[3], bb[0]:bb[2]],
                       img[bb[1]:bb[3], bb[0]:bb[2]]).save(mesh_dir / f"{pid}.card-{n}.relief.png")
            layers.append({"png": f"{pid}.card-{n}.png", "bbox": bb, "z": round(z, 5), "kind": kind, "name": name,
                           "frame": fk, "relief": f"{pid}.card-{n}.relief.png", "relief_amp": round(amp, 5),
                           "relief_cell": RELIEF_CELL})
            D[m] = z * (1 - amp)  # far to near: the nearest card is written last
            n += 1
    (mesh_dir / f"{pid}.cards.json").write_text(json.dumps({"w": w, "h": h, "fov": FOV, "layers": layers}, indent=1))
    (mesh_dir / f"{pid}.json").write_text(json.dumps({"w": w, "h": h, "fov": FOV, "cards": True}))
    info = {"frames": len(areas), "cards": sum(1 for l in layers if l["kind"] != "backdrop"),
            "z": [f"{l['kind'][0]}{l['z']:.3f}" for l in layers]}
    return info, D
