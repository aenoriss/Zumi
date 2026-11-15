"""Step 9, motion: the accents an episode plays, decided by rules on its clock (docs/architecture/decisions.md,
"Reader catch-up, decided 2026-11-15": rule-based accents only; no model call, nothing paid).

At most one accent per balloon, decided over the whole episode in clock order (decide), from what the steps before
saved: the scene (each card's frame, box and share of the panel, how many characters its frame holds), the speakers
(which card of the box says the line), the clock (when each balloon starts and ends, which frame is lit) and the
recorded lines (whether the balloon has audio). Three tricks:

    pop     a speech line whose speaker changed: the speaking card swells about the middle of its base and settles
            back (scale 1 -> peak at POP_RISE_S, back to 1 by POP_S, each way an ease-out)
    cut     the first shout of a run: the speaking card is a little bigger for CUT_S, then back; two states, no glide
    impact  a stretch of sound effects: what the frame's window shows shakes sideways and dies out (IMPACT_PX at a
            REF_W-px panel, IMPACT_HZ, gone by IMPACT_S), at most one every RULES["impact_every"] seconds. A card
            that touches a side of its frame's visible window never moves away from that side (it would show the
            unpainted strip behind it: only a narrow band is painted behind a card), so it takes only the half of
            the shake toward that side (touching, pins)

Every accent starts STAGGER_S after its balloon appears. Three presets (the committee's reading, a sparser one and
the one tuned on the demo, pipeline/.data/out/motion_demo, which imports these rules), picked by name, else
ZUMI_MOTION, else "tuned":

    committee   the rules as written, pop and cut at FIXED_SCALE, only on a card covering at most share_max of the
                panel
    sparse      and a speech line pops only after a gap of sparse_gap seconds since the line before ended
    tuned       sparse, without the size gate: the scale is set per card so its top rises `rise` px at a REF_W-px
                panel (clamped to scale_min..scale_max), and a run of shouts starts again at each new panel

    lines(ep, clk, voiced)             every balloon of the episode in clock order with what the rules look at
    decide(lines, preset)              [(trick or None, why not)] aligned with lines
    fired(lines, preset)               the accents that fire: [{"panel", "bubble", "trick", "t", "target", ...}]
    accents(ep, clk, voiced, preset)   fired, on an episode's own lines
    tracks(accents, clk)               {panel id: [the format's animation tracks]} for the export
    motion_step(ep, n_boxes)           the chosen preset's accents and every preset's counts, motion/motion.json

    python motion.py <chapter.zumi> <episode out dir> [--table]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

from boxstore import Episode, Layer

# the thresholds of the per-balloon decision
RULES = {"share_max": 0.25, "min_chars": 2, "shout_rearm": 8.0, "impact_every": 8.0, "sparse_gap": 1.0,
         # tuned: pop and cut raise the top of the speaking card by `rise` px (at a REF_W-px panel), scale clamped
         "rise": 9.0, "scale_min": 1.015, "scale_max": 1.06}
FIXED_SCALE = 1.03   # committee and sparse: the pop's peak and the cut's scale
REF_W = 1200         # the panel width the pixel sizes here are stated at
PRESETS = ("tuned", "sparse", "committee")
SPOKEN = ("speech", "shout")
TOUCH = 2            # px: a card within this of its frame's visible edge, or past it, touches that side
STAGGER_S = 0.06     # an accent starts this long after its balloon appears
POP_RISE_S, POP_S = 0.07, 0.45
CUT_S = 0.09
IMPACT_PX, IMPACT_HZ, IMPACT_S, IMPACT_DECAY = 4.0, 13.0, 0.35, 2
BASE = {"x": 0.5, "y": 1.0}  # pop and cut scale about the middle of the card's base


def preset(name: str | None = None) -> str:
    """The preset named, else ZUMI_MOTION's, else tuned."""
    name = name or os.environ.get("ZUMI_MOTION") or PRESETS[0]
    if name not in PRESETS:
        raise ValueError(f"motion preset {name!r}: one of {', '.join(PRESETS)}")
    return name


def visible(backdrop: Layer) -> tuple[int, int, int, int] | None:
    """The opaque box of a frame's window in panel pixels (the window's mask is transparent for about 12 px inside
    its box, where the drawn border sits); None for a layer without a window."""
    win = backdrop.window()
    if win is None or backdrop.window_bbox is None:
        return None
    a = np.asarray(win)[..., 3] > 128
    ys, xs = np.where(a.any(1))[0], np.where(a.any(0))[0]
    if not len(ys) or not len(xs):
        return None
    x0, y0 = backdrop.window_bbox[:2]
    return int(x0 + xs[0]), int(y0 + ys[0]), int(x0 + xs[-1] + 1), int(y0 + ys[-1] + 1)


def touching(bbox, vis) -> dict:
    """{"touch": which sides of its frame's visible window a card's box touches (l, t, r, b), "margin": px to each}."""
    m = {"l": bbox[0] - vis[0], "t": bbox[1] - vis[1], "r": vis[2] - bbox[2], "b": vis[3] - bbox[3]}
    return {"touch": {k: v <= TOUCH for k, v in m.items()}, "margin": m}


def pins(layers: list[Layer], frame: int) -> dict[str, str]:
    """{card: "l" | "r" | "lr"} for the character and object cards of a frame that touch its visible window's left
    or right side: where an impact's shake may not pull them away from."""
    vis = next((v for l in layers if l.kind == "backdrop" and l.frame == frame and (v := visible(l))), None)
    out = {}
    if vis is None:
        return out
    for l in layers:
        if l.kind in ("character", "object") and l.frame == frame:
            t = touching(l.bbox, vis)["touch"]
            if t["l"] or t["r"]:
                out[l.card] = ("l" if t["l"] else "") + ("r" if t["r"] else "")
    return out


def lines(ep: Episode, clk: dict, voiced: set[tuple[str, int]]) -> list[dict]:
    """Every balloon of the episode in clock order with what the rules look at: {"panel", "id", "t", "end", "kind",
    "card" (the speaking card of its own box, else None), "frame" (the card's; without a card, the frame lit when
    the balloon starts), "share" (the card's box over the panel's area), "chars" (characters in the card's frame),
    "height", "w" (the card's height and the panel's width, px), "audio", "pins" (for a sound effect, pins of its
    frame)}. clk: the episode clock; voiced: the (box pid, bubble id) that have a recorded line."""
    out = []
    for pi, cp in enumerate(clk["panels"]):
        if not cp["bubbles"]:
            continue
        box = ep.box(cp["index"])
        sc = box.scene()
        if sc is None:
            continue
        recs = {r["bubble"]: r for r in box.speakers() or []}
        by_key = {l.key: l for l in sc.layers}
        frames = sorted(cp.get("frames") or [], key=lambda f: f["startOffset"])
        for bi, cb in enumerate(cp["bubbles"]):
            n = int(cb["id"][1:])
            r = recs.get(n, {})
            said = [by_key[s] for s in r.get("speakers") or [] if s in by_key] if r.get("speaker_kind") == "card" else []
            card = said[0] if said else None
            kind = r.get("kind") or "unknown"
            rel = cb["startTime"] - cp["startTime"]
            line = {"panel": cp["id"], "id": cb["id"], "t": round(cb["startTime"], 3), "end": round(cb["endTime"], 3),
                    "order": (pi, bi), "kind": kind, "card": card.card if card else None, "w": sc.w,
                    "audio": (box.pid, n) in voiced, "text": r.get("text") or ""}
            if card is not None:
                x0, y0, x1, y1 = card.bbox
                frame = card.frame if isinstance(card.frame, int) else None
                line |= {"frame": frame, "share": (x1 - x0) * (y1 - y0) / (sc.w * sc.h), "height": y1 - y0,
                         "chars": sum(1 for l in sc.layers if l.kind == "character" and l.frame == frame)
                         if frame is not None else 0}
            else:  # a sound effect has no card: its frame is the one lit when it starts
                frame = next((f["index"] for f in reversed(frames) if f["startOffset"] <= rel + 1e-6), None)
                line |= {"frame": frame, "share": None, "height": None, "chars": 0}
                if kind == "sfx" and frame is not None:
                    line["pins"] = pins(sc.layers, frame)
            out.append(line)
    out.sort(key=lambda b: (b["t"], b["order"]))
    return out


def tuned_scale(b: dict) -> float:
    """The scale that raises the top of the line's card by RULES["rise"] px (at a REF_W-px panel), clamped."""
    R = RULES
    return min(R["scale_max"], max(R["scale_min"], 1 + R["rise"] * b["w"] / REF_W / b["height"]))


def scale_of(b: dict, trick: str | None, name: str) -> float | None:
    """A pop's peak or a cut's scale under a preset; None for an impact or no accent."""
    if trick not in ("pop", "cut"):
        return None
    return round(tuned_scale(b), 4) if name == "tuned" else FIXED_SCALE


def decide(lines: list[dict], name: str) -> list[tuple[str | None, str]]:
    """At most one accent per balloon, in episode clock order: [(trick or None, why not)] aligned with lines.

    A thought, a caption, a line without a speaking card in its own box, without a frame or without audio: nothing.
    Speech pops when its card differs from the card of the speech or shout before it (a card of another panel is
    another card) and its frame holds min_chars characters or more. Of a run of shouts (shouts back to back, armed
    again shout_rearm seconds after the one before began) only the first cuts. Sound effects starting together are
    one event, and an event is an impact when impact_every seconds have passed since the last one."""
    R = RULES
    sparse = name != "committee"
    size_gate = name != "tuned"
    panel_runs = name == "tuned"
    out = []
    prev_end = None
    prev_spoken = ("none",)          # the card of the speech or shout before, as (panel, card)
    prev_kind = None
    prev_panel = None
    prev_shout_t = None
    last_impact = None
    event = None                     # (start, index of the first sound effect at that start)
    for i, b in enumerate(lines):
        gap = b["t"] - prev_end if prev_end is not None else float("inf")
        kind = b["kind"]
        fire, why = None, []
        if kind == "thought":
            why.append("thought")
        elif kind == "sfx":
            if b["frame"] is None:
                why.append("no frame")
            elif event and abs(event[0] - b["t"]) < 1e-6:
                first = lines[event[1]]
                why.append(f"same moment as {first['panel']} {first['id']}")
            elif last_impact is not None and b["t"] - last_impact < R["impact_every"]:
                why.append(f"under {R['impact_every']:g} s since last impact ({b['t'] - last_impact:.1f} s)")
            else:
                fire, last_impact = "impact", b["t"]
            if not (event and abs(event[0] - b["t"]) < 1e-6):
                event = (b["t"], i)
        elif kind in SPOKEN:
            card = (b["panel"], b["card"]) if b["card"] is not None else None
            base = []
            if card is None:
                base.append("no speaker")
            elif b["frame"] is None:
                base.append("no frame")
            if not b["audio"]:
                base.append("no audio")
            share_ok = b["share"] is not None and b["share"] <= R["share_max"] + 1e-9
            cover = f"card covers {round(100 * b['share'])} %" if b["share"] is not None else None
            if kind == "speech":
                if card is not None and card == prev_spoken:
                    why.append("same speaker")
                if card is not None and b["chars"] < R["min_chars"]:
                    why.append({0: "no character in frame", 1: "one character in frame"}.get(
                        b["chars"], f"{b['chars']} characters in frame"))
                if card is not None and not share_ok and size_gate:
                    why.append(cover)
                if sparse and gap < R["sparse_gap"]:
                    why.append(f"gap {gap:.1f} s")
                fire = "pop"
            else:
                first = not (prev_kind == "shout" and b["t"] - prev_shout_t < R["shout_rearm"])
                if panel_runs and prev_panel != b["panel"]:
                    first = True
                if not first:
                    why.append("later shout of a run")
                if card is not None and not share_ok and size_gate:
                    why.append(cover)
                fire = "cut"
                prev_shout_t = b["t"]
            why = base + why
            if why:
                fire = None
            prev_spoken = card
        else:
            why.append(f"kind {kind}")
        out.append((fire, "; ".join(why)))
        prev_end = b["end"] if prev_end is None else max(prev_end, b["end"])
        prev_kind = kind
        prev_panel = b["panel"]
    return out


def accents(ep: Episode, clk: dict, voiced: set[tuple[str, int]], name: str | None = None) -> list[dict]:
    """The accents that fire in an episode under a preset (preset(name)), in clock order (fired)."""
    return fired(lines(ep, clk, voiced), preset(name))


def fired(ls: list[dict], name: str) -> list[dict]:
    """The accents decide fires on the lines ls under the preset `name`: {"panel", "bubble", "trick", "t" (seconds
    on the episode clock when it starts, the stagger included), "target" (the card, or "frame:<n>" for an impact),
    and "scale" (pop, cut) or "pins" (impact)}."""
    out = []
    for b, (trick, _) in zip(ls, decide(ls, name)):
        if trick is None:
            continue
        a = {"panel": b["panel"], "bubble": b["id"], "trick": trick, "t": round(b["t"] + STAGGER_S, 3)}
        if trick == "impact":
            a |= {"target": f"frame:{b['frame']}", "pins": b.get("pins") or {}}
        else:
            a |= {"target": b["card"], "scale": scale_of(b, trick, name)}
        out.append(a)
    return out


def tracks(accents: list[dict], clk: dict) -> dict[str, list[dict]]:
    """The accents as the format's animation tracks, {panel id: [track]}: each plays once (loop false) from
    startTime on the episode clock (delay: the same moment counted from its panel's start).
    pop: scale, keyframes 1 -> peak -> 1 with the "out" easing on each segment, pivot at the base's middle;
    cut: scale with the "step" easing (the first keyframe held until the last); impact: a decaying shake of a
    frame's content, its amplitude a share of the panel's width, with the cards pinned to a side."""
    start = {p["id"]: p["startTime"] for p in clk["panels"]}
    out: dict[str, list[dict]] = {}
    for a in accents:
        t = {"id": f"{a['bubble']}-{a['trick']}", "target": a["target"], "startTime": a["t"],
             "delay": round(a["t"] - start[a["panel"]], 3), "loop": False}
        if a["trick"] == "pop":
            t |= {"track": "scale", "duration": POP_S, "easing": "out", "pivot": BASE,
                  "keyframes": [{"t": 0, "v": 1}, {"t": round(POP_RISE_S / POP_S, 4), "v": a["scale"]}, {"t": 1, "v": 1}]}
        elif a["trick"] == "cut":
            t |= {"track": "scale", "duration": CUT_S, "easing": "step", "pivot": BASE,
                  "keyframes": [{"t": 0, "v": a["scale"]}, {"t": 1, "v": 1}]}
        else:
            t |= {"track": "shake", "duration": IMPACT_S, "easing": "linear",
                  "params": {"axis": "x", "amplitude": round(IMPACT_PX / REF_W, 6), "frequency": IMPACT_HZ,
                             "decay": IMPACT_DECAY, **({"pin": a["pins"]} if a["pins"] else {})}}
        out.setdefault(a["panel"], []).append(t)
    return out


def counts(found: list) -> dict[str, int]:
    """How many of each trick: from accents, or from decide's answers."""
    names = [a["trick"] if isinstance(a, dict) else a[0] for a in found]
    return {k: names.count(k) for k in ("pop", "cut", "impact")}


def motion_step(ep: Episode, n_boxes: int) -> dict | None:
    """The accents of the chosen preset on the saved clock and every preset's counts, as <episode>/motion/
    motion.json, for checking; the export decides them again on its own clock. None before the clock."""
    import clock
    import voices
    clk = clock.load(ep)
    if clk is None:
        print("  motion: no clock yet, skipped")
        return None
    voiced = set(voices.lines(ep, voices.backend()))
    ls = lines(ep, clk, voiced)
    name = preset()
    data = {"preset": name, "rules": RULES, "lines": len(ls),
            "counts": {p: counts(decide(ls, p)) for p in PRESETS}, "accents": accents(ep, clk, voiced, name)}
    out = ep.out / "motion"
    out.mkdir(parents=True, exist_ok=True)
    (out / "motion.json").write_text(json.dumps(data, indent=1), encoding="utf-8")
    print(f"  motion ({name}): " + "; ".join(f"{p}: " + ", ".join(f"{k} {v}" for k, v in c.items())
                                             for p, c in data["counts"].items()) + f"; {len(ls)} balloons")
    return data


if __name__ == "__main__":
    import clock
    import voices
    from chapter import Chapter
    ch = Chapter(Path(sys.argv[1]))
    e = Episode(Path(sys.argv[2]), ch.stem)
    motion_step(e, len(ch))
    if "--table" in sys.argv:
        ls = lines(e, clock.load(e), set(voices.lines(e, voices.backend())))
        plans = {p: decide(ls, p) for p in PRESETS}
        for i, b in enumerate(ls):
            print(f"{b['panel']} {b['id']:4} {b['t']:7.2f} {b['kind']:7} card={b['card']} f={b['frame']} "
                  f"chars={b['chars']} | " + " | ".join(f"{p}: {plans[p][i][0] or '-'} {plans[p][i][1]}" for p in PRESETS))
