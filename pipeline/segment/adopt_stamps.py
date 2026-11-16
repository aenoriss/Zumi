"""Which outputs of an episode's working folder a run here would keep, and the adoption of those whose stamps are
in an older form: the one place where a stamp is rewritten without its output being made again.

audit() only reads: per step it computes today's stamp of each output (fresh.py's rule), the stamp the rule before
gives on this machine, and compares both with the saved one. It calls no step, no model and no provider, and writes
nothing. An output is then one of:

    current      the saved stamp is today's
    verified     the saved stamp is the one the rule before gives here: the output is current, its stamp's form is
                 old. A step adopts these by itself when it runs (fresh.holds); --write does it now.
    unverified   the saved stamp cannot be computed again here (the output was made on another machine under a rule
                 that was not portable: a sheet rendered with that machine's font, an image resized by its library),
                 but everything the stamp stood for can be checked another way, and is said: the files are there,
                 the outputs before it hold, the saved copy of what the model saw matches what is rendered now.
                 Never adopted silently: --write --unverified, after reading the list.
    stale        none of these: the step makes it again.

Places built before the geometry's stamps were split (geometry.json "stamp" over depth, shown window and front mesh
at once, until 2026-11-15) are brought to the split stamps the same way, verified by that old stamp: depth.json is
written from geometry.json's view_deg and the depth and show stages are stamped, so MoGe does not run again and the
paid erase stays current; the meshes are left to the next places step (free).

Every adoption written is appended to <episode>/stamps-adopted.json (when, what, the old and new stamp, why).

    python adopt_stamps.py <chapter.zumi> <episode out dir> [--write [--unverified]]
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import fresh
from boxstore import Episode

SHEET_DIFF = 4.0   # mean absolute difference (of 255) under which a saved sheet's cell and today's rendering show
                   # the same frames: another font and resampler measured 0.3-1.1 a cell (2026-11-15), another
                   # frame 20 and more
SENT_DIFF = 4.0    # the same for a pick's saved img<k>.jpg (JPEG at quality 92) against the image sent now
OLD_FRONT = ("MODEL", "STRIDE_PX", "FRONT_TOL", "HEAD_MOVE", "QUEST_PPD", "RTOL", "SNAP", "MERGE", "SKY_FAR",
             "CLOSE_WINDOW", "NEAR_SHARE", "OBJ_GROW", "ERASE_GROW", "SHOWN_DEG", "WORK_W")  # the one geometry stamp


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _set(path: Path, field: str, value: str) -> None:
    d = _json(path)
    d[field] = value
    path.write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")


def _diff(a: Image.Image, b: Image.Image) -> float:
    """Mean absolute difference of two images of one size, of 255; 255 when their sizes differ."""
    if a.size != b.size:
        return 255.0
    return float(np.abs(np.asarray(a.convert("RGB"), np.int16) - np.asarray(b.convert("RGB"), np.int16)).mean())


class Audit:
    """The rows of one audit: [{"step", "output", "state", "before", "why", "saved", "new", "write"}]."""

    def __init__(self):
        self.rows: list[dict] = []

    def add(self, step: str, output: str, saved, new: str, before: str | None = None, files=(), evidence=None,
            write=None) -> str:
        """One output. saved: its saved stamp; new: today's; before: the stamp the rule before gives here (None:
        the rule did not change); evidence: (holds, text) for a stamp that cannot be computed again here; write:
        saves `new` in place of `saved`. Returns its state."""
        before = new if before is None else before
        missing = [Path(f).name for f in files if not Path(f).exists()]
        if missing:
            state, why = "stale", f"missing {', '.join(missing)}"
        elif saved is None:
            state, why = "stale", "no stamp saved"
        elif saved == new:
            state, why = "current", ""
        elif saved == before:
            state, why = "verified", "the saved stamp is the one the rule before gives here"
        elif evidence and evidence[0]:
            state, why = "unverified", evidence[1]
        else:
            state, why = "stale", (evidence[1] if evidence else "the saved stamp is neither today's nor the rule "
                                                                "before's on this machine")
        self.rows.append({"step": step, "output": output, "state": state, "why": why, "saved": saved, "new": new,
                          "before": not missing and saved is not None and saved == before,
                          "write": write if state in ("verified", "unverified") else None})
        return state

    def ok(self, *steps: str) -> bool:
        """Every output of these steps is current or can be adopted."""
        return all(r["state"] != "stale" for r in self.rows if r["step"] in steps)


def audit(ch, ep: Episode) -> Audit:
    """Every stamped output of the episode against today's rule and the rule before. Reads only."""
    import bubbles as B
    import character_identity as CI
    import characters as CH
    import clock
    import layers as L
    import objects as OB
    import places
    import props as P
    import score
    import settings as S
    import transcribe as T
    import voices as V
    from review_loop import recipe as review_recipe

    a, n = Audit(), len(ch)
    imgs = {i: ch.image(i) for i in range(n)}
    px = {i: fresh.pixels(im) for i, im in imgs.items()}

    def box_row(step: str, box, what: str, new: str, before: str | None = None) -> None:
        st, key, files = box._stamped(what)
        a.add(step, f"{box.pid} {what}", st.get(key), new, before, files, write=lambda: st.made(key, new))

    # ---- steps 1-4: masks, frames, objects, plates and layers (per box)
    for task, rec in (("lettering", B.recipe()), ("characters", CH.recipe())):
        for i in range(n):
            s = fresh.digest(px[i], task, rec)
            box_row(task, ep.box(i), task, s)
            if ep.box(i).stamp_of(f"{task}-review") is not None:  # none: the review is still to do, not stale
                box_row(task, ep.box(i), f"{task}-review", fresh.digest(s, review_recipe(task)))
    for i in range(n):
        box = ep.box(i)
        f = box.frames()
        a.add("frames", f"{box.pid} frames", "made" if f and f.current else None, "made")
        s = OB.box_stamp(imgs[i], box.characters() or [])
        box_row("objects", box, "objects", s)
        if box.stamp_of("objects-review") is not None:
            box_row("objects", box, "objects-review", fresh.digest(s, review_recipe("objects")))
        s = L.inputs_stamp(box, imgs[i])
        nothing = fresh.digest(s, "nothing to erase")
        box_row("erase (band)", box, "plate", nothing if box.stamp_of("plate") == nothing else s)
        box_row("layers", box, "layers", fresh.digest(s, L.plate_state(box, s)),
                fresh.digest(s, L.plate_state(box, s, as_bytes=True)))

    # ---- transcripts, speakers, identity, voices
    rec = T.recipe()
    for i in range(n):
        box = ep.box(i)
        letters = box.letters() or []
        a.add("transcribe", f"{box.pid} transcript", "made" if box.transcript_current(letters, rec) else "other",
              "made")
        if box.scene() is not None:
            a.add("speakers", f"{box.pid} speakers", "made" if box.speakers() is not None else None, "made")
    got = CI.load(ep)
    if got:
        ident, cast = got
        cards = CI.read_cards(ep, n)
        a.add("identity", "identity.json", ident.get("stamp") if ep.stem in cast.d["episodes"] else None,
              CI.identity_stamp(cards, CI.pass_of(cast, ep.stem)))
        tts = V.backend()
        want, _ = V.wanted_lines(ep, n, ident, cast, tts)
        have = {(l["pid"], l["bubble"]): l for l in json.loads((ep.out / tts.AUDIO_DIR / "lines.json").read_text(
            encoding="utf-8"))} if (ep.out / tts.AUDIO_DIR / "lines.json").exists() else {}
        for line in want:
            old = have.get((line["pid"], line["bubble"]))
            same = bool(old) and all(old.get(k) == line[k] for k in V.LINE_RECIPE)
            a.add(f"voices ({tts.NAME})", line["file"], "made" if same else None if not old else "other", "made",
                  files=[ep.out / tts.AUDIO_DIR / old["file"]] if old else ())

    # ---- settings
    st = S.load(ep)
    items = S.episode_frames(ep, n)
    if st and items:
        ids, parts, d = [k for k, _ in items], S.sheets(items), ep.out / "settings"
        saved_parts = [(name, Image.open(d / name)) for name, _ in parts if (d / name).exists()]
        sent = len(saved_parts) == len(parts) and S.sheets_stamp(ids, saved_parts) == st.get("stamp")
        cw, chh = S.THUMB + 10, S.CELL_H
        worst = max((_diff(now.crop(c), was.crop(c)) for (_, now), (_, was) in zip(parts, saved_parts)
                     if now.size == was.size
                     for c in [(x, y, x + cw, y + chh) for y in range(0, now.height, chh)
                               for x in range(0, now.width, cw)]), default=255.0) if sent else 255.0
        up = a.ok("layers", "frames")
        a.add("settings", "settings.json", st.get("stamp"), S.stamp_of(items), S.sheets_stamp(ids, parts),
              evidence=(sent and worst < SHEET_DIFF and up,
                        f"the saved sheets are the ones stamped (the old stamp is theirs, with today's task, model, "
                        f"effort and frame ids: {'yes' if sent else 'NO'}); they show today's frames (the cell "
                        f"that differs most from today's rendering: {worst:.2f} of 255, under {SHEET_DIFF}); "
                        f"layers and frames hold: {'yes' if up else 'NO'}"),
              write=lambda d=d, new=S.stamp_of(items): _set(d / "settings.json", "stamp", new))

    # ---- places
    clk = clock.load(ep)
    fs = (st or {}).get("frame_setting") or {}
    record = {s["id"]: s for s in (st or {}).get("settings", [])}
    for sid in (places.plan(clk, fs)["places"] if clk and st else []):
        d = ep.out / "places" / sid
        meta, step = _json(d / "place.json"), f"place {sid}"
        if not meta:
            a.add(step, "view16.png", None, "")
            continue
        refs = places.kept_refs(clk, fs, sid, meta.get("refs") or []) or places.scene_refs(clk, fs, sid)
        a.add(step, "view16.png", meta.get("stamp16"), places.view16_stamp(record[sid], refs), files=[d / "view16.png"])
        if (d / "view16.png").exists():
            new = places.pano_stamp(record[sid], refs, d)
            a.add(step, "view.png", meta.get("stamp"), new, places.pano_stamp(record[sid], refs, d, as_bytes=True),
                  [d / "view.png"], write=lambda d=d, new=new: _set(d / "place.json", "stamp", new))
        if not (d / "view.png").exists():
            continue
        g, stamps = _json(d / "geometry.json"), fresh.Stamps(d / "stamps.json")
        if "stamp" in g:  # built before the split: one stamp over depth, shown window and front mesh
            holds = g["stamp"] == fresh.digest(d / "view.png", {k: getattr(places.place_geometry, k) for k in OLD_FRONT})
            a.add(step, "depth + show (one stamp, before the split)", g["stamp"] if holds else None, "split",
                  g["stamp"], [d / f for f in ("shown.png", "distance.npy", "erase-mask.png")],
                  write=lambda d=d: _split(d))
        for stage in places.GEOMETRY_FILES:
            if "stamp" in g and stage in ("depth", "show"):
                continue
            if stage == "back" and not (d / "plate.png").exists():
                a.add(step, "back.glb", None, "", files=[d / "plate.png"])
                continue
            new = places.geometry_stamp(stage, d)
            a.add(step, " ".join(places.GEOMETRY_FILES[stage]), stamps.get(stage), new,
                  places.geometry_stamp(stage, d, as_bytes=True), [d / f for f in places.GEOMETRY_FILES[stage]],
                  write=lambda d=d, stage=stage, new=new: fresh.Stamps(d / "stamps.json").made(stage, new))
        if (d / "shown.png").exists() and (d / "erase-mask.png").exists():
            new = places.plate_stamp(d)
            a.add(step, "plate.png (the paid erase)", meta.get("stamp_plate"), new, places.plate_stamp(d, as_bytes=True),
                  [d / "plate.png"], write=lambda d=d, new=new: _set(d / "place.json", "stamp_plate", new))

    # ---- props: the pick, then each prop's files
    secs = P.seconds_open(ep, fs) if clk and st else {}
    for sid in secs:
        d = ep.out / "props" / sid
        pk, step = _json(d / "pick.json"), f"props {sid}"
        if not (ep.out / "places" / sid / "shown.png").exists():
            continue
        if not pk:
            a.add(step, "pick.json", None, "")
            continue
        sent, sources, text, k = P.pick_material(ep, sid, secs[sid], fs)
        same = pk.get("max") == k and pk.get("images") == [src for src, _ in sent]
        jpgs = [d / f"img{j}.jpg" for j in range(1, len(sent) + 1)]
        worst = max((_diff(im, Image.open(f)) for (_, im), f in zip(sent, jpgs)), default=255.0) \
            if same and all(f.exists() for f in jpgs) else 255.0
        up = a.ok("settings", "transcribe", "layers", f"place {sid}")
        a.add(step, "pick.json", pk.get("stamp"), P.pick_stamp(sources, text), P.stamp_before(pk, sent, text, k) or "",
              evidence=(same and worst < SENT_DIFF and up,
                        f"the same number of props allowed ({pk.get('max')} then, {k} now) and the same images chosen: "
                        f"{'yes' if same else 'NO'}; the saved img<k>.jpg are the images sent now (the one that "
                        f"differs most: {worst:.2f} of 255, under {SENT_DIFF}); settings, transcripts, layers and "
                        f"the place hold: {'yes' if up else 'NO'}"),
              write=lambda d=d, new=P.pick_stamp(sources, text): _set(d / "pick.json", "stamp", new))
        saved, picked = _json(d / "stamps.json"), a.rows[-1]["state"] != "stale"
        for p in pk.get("props") or []:
            now = P.stamps_of(P.view_stamp(ep, sid), p)
            was = P.stamps_of(P.view_stamp(ep, sid, as_bytes=True), p)
            mine = saved.get(p["name"]) or {}
            # a cut stamp names the view by the bytes of the file the cutting machine had (an episode made on
            # Linux, 2026-11-15: neither these bytes nor these pixels gave it, though its pick saw these very
            # pixels): it cannot be computed again, but every rung after it can, from the saved cut stamp
            chain = mine.get("cut") is not None and all(P.stamps_after(mine["cut"], p)[r] == mine.get(r)
                                                         for r, _ in P.RUNGS[1:])
            files = all((d / f"{p['name']}{s}").exists() for _, s in P.RUNGS)
            for r, suffix in P.RUNGS:
                a.add(step, f"{p['name']}{suffix}", mine.get(r), now[r], was[r], [d / f"{p['name']}{suffix}"],
                      evidence=(picked and chain and files,
                                f"the pick holds (the view's pixels are those it was picked on): "
                                f"{'yes' if picked else 'NO'}; paint, raw and glb are today's recipe over the saved "
                                f"cut stamp: {'yes' if chain else 'NO'}; all four files there: {'yes' if files else 'NO'}"),
                      write=lambda d=d, name=p["name"], r=r, new=now[r]: _rung(d / "stamps.json", name, r, new))

    # ---- music: the reviewer's spans, then each track's song
    sp = _json(ep.out / "music" / "spans.json")
    if st and sp:
        a.add("music", "spans.json", sp.get("stamp"), score.reviewer_stamp(score.material(ep, n, st)[0]))
        have = {t["id"]: t for t in _json(ep.out / "music" / "tracks.json").get("tracks", [])}
        for w in score.track_plan(ep, st, sp):
            a.add("music", f"{w['id']}.mp3", (have.get(w["id"]) or {}).get("stamp"), score.song_stamp(w["prompt"]),
                  files=[ep.out / "music" / f"{w['id']}.mp3"])
    return a


def _rung(path: Path, name: str, rung: str, stamp: str) -> None:
    d = _json(path)
    d.setdefault(name, {})[rung] = stamp
    path.write_text(json.dumps(d, indent=1), encoding="utf-8")


def _split(d: Path) -> None:
    """A place's one geometry stamp, which holds, replaced by the depth and show stages' stamps."""
    import places
    g = _json(d / "geometry.json")
    (d / "depth.json").write_text(json.dumps({"view_deg": g["view_deg"]}), encoding="utf-8")
    st = fresh.Stamps(d / "stamps.json")
    for stage in ("depth", "show"):
        st.made(stage, places.geometry_stamp(stage, d))
    g.pop("stamp", None)
    (g.get("back") or {}).pop("stamp", None)
    (d / "geometry.json").write_text(json.dumps(g, indent=1), encoding="utf-8")


def table(a: Audit) -> list[tuple]:
    """Per step: (step, outputs, current before the fix here, why not, state after adoption)."""
    out = []
    for step in dict.fromkeys(r["step"] for r in a.rows):
        rows = [r for r in a.rows if r["step"] == step]
        count = {s: sum(r["state"] == s for r in rows) for s in ("current", "verified", "unverified", "stale")}
        before = sum(r["before"] for r in rows)
        not_before = sorted({r["output"].split(" ", 1)[-1] if len(rows) > 12 else r["output"]
                             for r in rows if not r["before"]})
        out.append((step, len(rows), f"{before}/{len(rows)}", ", ".join(not_before[:6]) + (" ..." if len(not_before) > 6 else ""),
                    ", ".join(f"{v} {k}" for k, v in count.items() if v)))
    return out


def main() -> None:
    from chapter import Chapter
    ch, out = Chapter(Path(sys.argv[1])), Path(sys.argv[2])
    write, unverified = "--write" in sys.argv, "--unverified" in sys.argv
    a = audit(ch, Episode(out, ch.stem))
    print(f"{'step':28s} {'outputs':>7s} {'current before':>14s}  after adoption")
    for step, k, before, not_before, after in table(a):
        print(f"{step:28s} {k:7d} {before:>14s}  {after}" + (f"   [not current before: {not_before}]" if not_before else ""))
    for state in ("verified", "unverified", "stale"):
        rows = [r for r in a.rows if r["state"] == state]
        if rows:
            print(f"\n{state} ({len(rows)}):")
            for r in rows:
                print(f"  {r['step']}: {r['output']}  {r['saved']} -> {r['new'] if state != 'stale' else '-'}  ({r['why']})")
    todo = [r for r in a.rows if r["write"] and (r["state"] == "verified" or unverified)]
    held = sum(1 for r in a.rows if r["state"] == "unverified") if not unverified else 0
    if not write:
        print(f"\nnothing written. --write would adopt {sum(r['state'] == 'verified' for r in a.rows)} verified stamps"
              + (f"; --write --unverified also the {held} unverified ones above" if held else ""))
        return
    log = out / "stamps-adopted.json"
    done = json.loads(log.read_text(encoding="utf-8")) if log.exists() else []
    for r in todo:
        r["write"]()
        done.append({"at": dt.datetime.now().isoformat(timespec="seconds"), "step": r["step"], "output": r["output"],
                     "from": r["saved"], "to": r["new"], "state": r["state"], "why": r["why"]})
    log.write_text(json.dumps(done, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"\n{len(todo)} stamps adopted, logged in {log}" + (f"; {held} unverified left (--unverified)" if held else ""))


if __name__ == "__main__":
    main()
