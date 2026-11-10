"""The episode clock: when every panel, frame and balloon of an episode is on screen (CONTEXT.md: Clock).

The reader needs no pacing logic: the clock is precomputed from what the steps before it saved and nothing after
them. Its inputs are each box's layers (whether it has any, its frames in reading order and which frame holds each
balloon: frame_plan), its balloons (text, kind) and their reading order (speakers.json), and each recorded line's
length (the voices step's line index). So it is built right after the voices (step 8) and read by everything that
hangs on time: the music envelope, the places, the export. Before 2026-11-08 it lived inside the export, and three
modules re-derived it, with a frame ending at its own content's end in one and at the next frame's start in another.

    build(ep, n_boxes)      the clock: {"duration", "panels": [{"id", "pid", "index", "scene", "startTime", "endTime",
                            "duration", "frames": [{"index", "startOffset", "duration"}], "bubbles": [{"id",
                            "startOffset", "durationHint", "startTime", "endTime"}] in clock order}]}
    times(panels)           {"p007/f1": (start, end), "p007/b3": (start, end)} on the episode clock, for the clock's
                            panels or an exported manifest's (same fields): a frame is on screen from its start until
                            the next frame of its panel starts, the last one until the panel ends; a balloon from its
                            startTime to its endTime. The one definition every step uses.
    clock_step(ep, n)       build, saved as <episode>/clock/clock.json

Within a box (timing): balloons frame by frame in reading order, each for its clip's length or a reading time, GAP_S
between them; a wordless frame holds by its share of the box; the box starts with BOX_LEAD_S and ends with TAIL_S; a
run of sound effects in one frame lands together. Across boxes: in index order, a box without layers holds
PANEL_MIN_S.
"""
from __future__ import annotations

import json
from pathlib import Path

from boxstore import Box, Episode, pid_of

GAP_S = 0.6        # between one balloon's end and the next's start (and in audio/episode.mp3)
READ_CPS = 15.0    # reading speed for a balloon without a clip (a caption, a sound effect): seconds = chars / READ_CPS
READ_MIN_S = 1.5   # and at least this long
TAIL_S = 1.0       # after the last balloon before the panel may move on
PANEL_MIN_S = 3.0  # a box with nothing to say (no layers) holds the clock this long
# a frame with no balloon holds the clock by its size: FRAME_HOLD_MIN_S for a sliver, FRAME_HOLD_MAX_S for one that
# fills the box (user, 2026-11-06: a fixed 2 s felt long on small frames)
FRAME_HOLD_MIN_S, FRAME_HOLD_MAX_S = 0.5, 2.0
BOX_LEAD_S = 0.8   # a small pause after a box appears before its first voice (user, 2026-11-06)


def panel_id(i: int) -> str:
    """The manifest's id of box i, as intake names it ("p007"); the suffix of the box's pid."""
    return f"p{i:03d}"


def hold_s(share: float) -> float:
    """Seconds a wordless frame holds, from its share of the box's area (0..1)."""
    return FRAME_HOLD_MIN_S + (FRAME_HOLD_MAX_S - FRAME_HOLD_MIN_S) * min(1.0, max(0.0, share))


def frame_plan(box: Box) -> tuple[list[int], dict[int, int], dict[int, float]]:
    """(the box's frames in reading order, {bubble id: its frame}, {frame: its share of the box's area}) from the saved
    layers: a balloon belongs to the frame whose backdrop holds its centre, else the nearest one. ([], {}, {}) without
    layers."""
    sc = box.scene()
    fr = box.frames()
    if sc is None or fr is None or not fr.masks:
        return [], {}, {}
    from speakers import reading_order
    order = reading_order(fr.masks)
    backs = {l.frame: l.bbox for l in sc.layers if l.kind == "backdrop" and l.frame is not None}
    share = {}
    for l in sc.layers:
        if l.kind == "backdrop" and l.frame is not None:
            x0, y0, x1, y1 = l.window_bbox or l.bbox  # the frame's own extent, not the backdrop's margin
            share[l.frame] = (x1 - x0) * (y1 - y0) / max(1, sc.w * sc.h)
    of = {}
    for l in sc.layers:
        if l.kind != "lettering" or l.bubble is None:
            continue
        cx, cy = (l.bbox[0] + l.bbox[2]) / 2, (l.bbox[1] + l.bbox[3]) / 2
        best, best_d = None, float("inf")
        for f, (x0, y0, x1, y1) in backs.items():
            d = max(x0 - cx, 0, cx - x1) + max(y0 - cy, 0, cy - y1)
            if d < best_d:
                best, best_d = f, d
        if best is not None:
            of[l.bubble] = best
    return [f for f in order if f in backs], of, share


def timing(bubbles: list[dict], seconds: dict[int, float], frames: list[int], frame_of: dict[int, int],
           share: dict[int, float] | None = None, sfx: set[int] = frozenset()) -> tuple[float, list[dict]]:
    """startOffset and durationHint on each bubble entry ({"id": "b<n>", "text"}), frame by frame in reading order (a
    bubble's order kept inside its frame), from the clips' lengths (seconds: bubble id -> clip seconds) and a reading
    time for bubbles without one; a frame with no balloon holds hold_s(its share of the box, 1 when unknown); the box
    starts with a BOX_LEAD_S pause (its first frame lit). A run of sound effects (sfx: their bubble ids) in one frame
    lands together: one start, the run as long as its longest (user, 2026-11-06). Returns (the panel's duration: the
    time its frames take plus TAIL_S, the frames' timing: [{index, startOffset, duration}])."""
    t = BOX_LEAD_S
    plan = []
    by_frame: dict[int | None, list[dict]] = {}
    for e in bubbles:
        by_frame.setdefault(frame_of.get(int(e["id"][1:])), []).append(e)
    for f in list(frames) + ([None] if None in by_frame else []):
        start = t if plan else 0.0
        run = None  # (start, end) of the sound effects landing together
        for e in by_frame.get(f, []):
            n = int(e["id"][1:])
            d = seconds.get(n) or max(READ_MIN_S, len(e["text"]) / READ_CPS)
            if n in sfx and run:
                e["startOffset"], e["durationHint"] = round(run[0], 2), round(d, 2)
                run = (run[0], max(run[1], run[0] + d))
            else:
                e["startOffset"], e["durationHint"] = round(t, 2), round(d, 2)
                run = (t, t + d) if n in sfx else None
            t = (run[1] if run else t + d) + GAP_S
        if not by_frame.get(f):
            t += hold_s((share or {}).get(f, 1.0)) + GAP_S
        if f is not None:
            plan.append({"index": f, "startOffset": round(start, 2), "duration": round(t - GAP_S - start, 2)})
    return (round(t - GAP_S + TAIL_S, 2) if t else 0.0), plan


def clip_seconds(ep: Episode, tts=None) -> dict[tuple[str, int], float]:
    """{(box pid, bubble id): seconds} for every recorded line on the voice backend tts (voices.backend() when None)."""
    import voices
    return {k: float(l.get("seconds") or 0) for k, l in voices.lines(ep, tts or voices.backend()).items()}


def box_clock(box: Box, seconds: dict[tuple[str, int], float]) -> dict:
    """One box's clock, before its place on the episode clock: {"scene", "duration", "frames", "bubbles"}. A box with
    no layers has no scene and holds PANEL_MIN_S."""
    sc = box.scene()
    if sc is None or not sc.layers:
        return {"scene": False, "duration": PANEL_MIN_S, "frames": [], "bubbles": []}
    bd = box.bubbles()
    frames, frame_of, share = frame_plan(box)
    if bd is None:  # a wordless box: its frames hold in turn, or the whole box holds once
        dur, plan = timing([], {}, frames or [0], frame_of, share)
        return {"scene": True, "duration": dur, "frames": plan, "bubbles": []}
    order = {r["bubble"]: r["order"] for r in box.speakers() or []}  # the box's reading order (speakers.reading_order)
    entries = [{"id": f"b{b['id']}", "text": b.get("text") or ""}
               for b in sorted(bd["bubbles"], key=lambda b: (order.get(b["id"], 10**6), b["bbox"][1]))]
    secs = {b["id"]: seconds[(box.pid, b["id"])] for b in bd["bubbles"] if (box.pid, b["id"]) in seconds}
    sfx = {b["id"] for b in bd["bubbles"] if b.get("kind") == "sfx"}
    dur, plan = timing(entries, secs, frames, frame_of, share, sfx)
    entries.sort(key=lambda e: e.get("startOffset", 0))  # the clock's order, frame by frame
    return {"scene": True, "duration": dur, "frames": plan,
            "bubbles": [{k: e[k] for k in ("id", "startOffset", "durationHint")} for e in entries]}


def build(ep: Episode, n_boxes: int, tts=None) -> dict:
    """The episode clock: every box's clock placed in index order from the episode's start, its lines' lengths from
    the voice backend tts (voices.backend() when None)."""
    seconds = clip_seconds(ep, tts)
    panels, t = [], 0.0
    for i in range(n_boxes):
        box = ep.box(i)
        c = box_clock(box, seconds)
        p = {"id": panel_id(i), "pid": box.pid, "index": i, "scene": c["scene"], "duration": c["duration"],
             "startTime": round(t, 2), "endTime": round(t + c["duration"], 2), "frames": c["frames"], "bubbles": []}
        for b in c["bubbles"]:
            start = round(t + b["startOffset"], 2)
            p["bubbles"].append({**b, "startTime": start, "endTime": round(start + b["durationHint"], 2)})
        panels.append(p)
        t += c["duration"]
    return {"duration": round(t, 2), "panels": panels}


def times(panels: list[dict]) -> dict[str, tuple[float, float]]:
    """Every frame and balloon id on the episode clock: a frame is on screen from its start until the next frame of
    its panel starts (the last one until the panel ends), a balloon from its startTime to its endTime. Works on the
    clock's panels and on an exported manifest's, which carry the same fields."""
    out = {}
    for p in panels:
        fs = sorted(p.get("frames") or [], key=lambda f: f["startOffset"])
        for k, f in enumerate(fs):
            end = p["startTime"] + fs[k + 1]["startOffset"] if k + 1 < len(fs) else p["endTime"]
            out[f"{p['id']}/f{f['index']}"] = (round(p["startTime"] + f["startOffset"], 2), round(end, 2))
        for b in p.get("bubbles") or []:
            if "startTime" in b:
                out[f"{p['id']}/{b['id']}"] = (b["startTime"], b.get("endTime") or b["startTime"])
    return out


def clock_step(ep: Episode, n_boxes: int) -> dict:
    """The clock, saved as <episode>/clock/clock.json for the steps after it (and anyone checking the pacing)."""
    c = build(ep, n_boxes)
    out = ep.out / "clock"
    out.mkdir(parents=True, exist_ok=True)
    (out / "clock.json").write_text(json.dumps(c, indent=1), encoding="utf-8")
    print(f"  clock: {len(c['panels'])} panels, {sum(len(p['bubbles']) for p in c['panels'])} balloons, {c['duration']:.1f} s")
    return c


def load(ep: Episode) -> dict | None:
    f = ep.out / "clock" / "clock.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


if __name__ == "__main__":
    import sys
    from chapter import Chapter
    ch = Chapter(Path(sys.argv[1]))
    clock_step(Episode(Path(sys.argv[2]), ch.stem), len(ch))
