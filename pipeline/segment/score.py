"""Step 10b, the score: the music of an episode (CONTEXT.md: Span, Mood, Role, Cue; decisions.md section 4 step 8,
amendment 2026-11-07).

reviewer_step   one text-only Claude Sonnet 5.5 call over the transcript in reading order, with each frame's setting:
                spans anchored to bubble and frame ids, each with a mood (light, tense, grave, epic, tender), a role
                (lead, under, source, out) and a few words of colour; and point events (button: the music gets out
                at once). <episode>/music/spans.json.
tracks_step     the music is made for the portal (CONTEXT.md: Place, 2026-11-08): the spans cut by the places timeline
                (places.plan on the clock), one Lyria song per (place, mood) with MIN_PAIR_S or more of music (a
                shorter pair plays the place's longest track), prompted as a family per place (the setting reader's
                tempo, key, instruments), capped at MAX_TRACKS, bought again only when its prompt or the Lyria
                model changes (song_stamp; fresh.py); the song's body cut
                to a bar-aligned loop and written as PCM WAV (an MP3 seam never closes; OGG once an encoder that does
                not crash is at hand). <episode>/music/<id>.wav,
                tracks.json.
envelope        a pure function of the spans, the tracks, the places timeline and the episode clock (clock.times: a
                frame runs until the next frame of its panel starts): per-track gain knots on the episode clock, each
                times its own portal's opening, so no portal means no music and a place swap is a track change (the
                portal's fades). The role sets the level; a voice ducks it (attack before the line, release after,
                the short gaps between lines stay ducked); a track enters on the tail of a line at bed level and
                settles to a floor; no track runs past MAX_RUN_S under continuous dialogue; a mood switch inside a
                place crossfades, a place change fades out, breathes, and enters; a button is the only cut.
placement       how the music sits in the room by role: source from a point inside the place, lead and under spread
                across the open walls (episode.score.placement).
strip           the envelope drawn against the lines, for a check without ears.
"""
from __future__ import annotations

import io
import json
import re
import sys
from pathlib import Path

import numpy as np

import clock
import fresh
import lyria
import places
from boxstore import Episode
from openrouter import BudgetExceeded, Truncated, ask_json

MODEL = "anthropic/claude-sonnet-5.5"
REASONING = "medium"
ANSWER_TOKENS = 6000
MOODS = ("light", "tense", "grave", "epic", "tender")
ROLES = ("lead", "under", "source", "out")

# ---- the envelope's constants (the artistic rule lives here and in the reviewer's prompt, not in code paths)
TRACK_RMS_DB = -22.0  # every loop normalised to this RMS: Lyria masters at about -15 dBFS, the voices sit near -20,
                      # so at gain 1 a track is 2 dB under a voice and the levels below are relative to that
LEVEL = {"lead": 0.40, "under": 0.16, "source": 0.20, "out": 0.0}  # a role's bed level, linear gain (lead about
                      # 10 dB under the voices, under about 18; the first cut was too loud, user 2026-11-07)
DUCK = 0.35           # times the level while a voice plays
ATTACK_S, RELEASE_S = 0.3, 1.2  # the duck starts this long before a line and lets go this long after it
SWELL_GAP_S = 2.0     # a gap between lines shorter than this stays ducked
SETTLE_S, FLOOR = 30.0, 0.5     # a track settles to FLOOR x level over SETTLE_S after its cue
ENTER_S = 3.0         # an entrance's rise
XFADE_S = 4.0         # a switch inside a setting: equal-power crossfade
EXIT_S, BREATH_S = 2.0, 1.5     # a setting change: fade out, silence, then an entrance
BUTTON_S = 0.3        # a button: out in this
MAX_RUN_S = 90.0      # no track past this under continuous dialogue: it leaves (RUN_OUT_S) until the next cue
RUN_OUT_S = 4.0
STEP = 0.1            # the envelope's sampling grid, seconds
MAX_TRACKS = 8
MIN_PAIR_S = places.MIN_STAY_S  # a (place, mood) pair earns its own track with this much music: as long as a stay
                                # that earns its place
LOOP_MAX_S = 60.0     # a loop body at most this long (PCM: about 10 MB a minute)

REVIEW_TASK = """# Task: score a comic episode

You are the music reviewer of a comic read aloud: every balloon is voiced, panel by panel, and instrumental music
plays under it from a small set of tracks, one per place and mood. You decide, span by span, which mood the music
has and what it does. Below is the whole episode in reading order: each frame with its setting (the place, from the
setting reader), each balloon with its id, speaker and words. Wordless frames are marked.

## What you label
Divide the episode into **spans**: runs of balloons and frames in reading order. Each span has:
- `mood`: one of light, tense, grave, epic, tender. Not a scale: a tale told in a tavern is epic while the tavern
  stays light; a brawl is tense; a confession is grave; a reconciliation is tender.
- `role`: what the music does there.
  - `lead`: the music carries the moment: a wordless frame, an arrival, a performance, a journey, the credits.
  - `under`: an underscore beneath the lines.
  - `source`: music heard in the room itself (a tavern band, a radio), part of the place.
  - `out`: silence. A state of its own. The default for a private, earnest scene until its turn; the right choice
    for a confrontation that needs air, for the lines after a punchline, for a reveal that must land dry.
- `colour`: a few words that shape the piece (mock-heroic, tipsy, hushed, wistful). They never make a new track.

Also mark **buttons**: a punchline or an interruption after which the music must get out at once (the deflating
reply to a grand tale, the drunks crashing into a quiet scene). A button goes on the balloon it lands on.

## How to think
Music changes at seams (a scene change, a new movement of the story, a turn of mood), never on a beat: a swell on a
punchline is a sting, a reveal underscored before the line lands is telegraphed. The voices do the turning. Loud
scenes are their own score; under shouting the music only needs to be present or absent. Silence is a mark, not an
absence: when music returns after silence that return is an event, so spend it where the story turns. Private,
earnest scenes play dry until their turn; the turn is where the music comes back, as tender or grave. Read the whole
episode before labelling.

## Output
Reply with ONE JSON object, exactly this shape:

```json
{
  "spans": [
    {"from": "p000/f0", "to": "p001/b3", "mood": "tender", "role": "lead", "colour": "airy, dusk, a long day", "why": "the road, wordless then tired talk"},
    {"from": "p002/f0", "to": "p005/f1", "mood": "light", "role": "source", "colour": "tipsy folk dance", "why": "..."}
  ],
  "buttons": [{"at": "p015/b1", "why": "the shrug that deflates the tale"}],
  "notes": "anything uncertain"
}
```

`from` and `to` are ids from the material (`p<box>/b<n>` a balloon, `p<box>/f<n>` a frame), `to` inclusive. The
spans cover the episode in order without gaps; a span may cross boxes. Ten to twenty spans is usual.
"""


# ----------------------------------------------------------------------------------------------- the material
def _speaker_name(r: dict, identity: dict, cast) -> str:
    s = (r.get("speakers") or [None])[0]
    if not s:
        return "?"
    cid = identity["cards"].get(s if "/" in s else f"{r['pid']}/{s}")
    c = cast.char(cid) if cid else None
    return (c or {}).get("name") or cid or "?"


def material(ep: Episode, n_boxes: int, settings: dict) -> tuple[str, list[str]]:
    """(the transcript the reviewer reads, every id in reading order)."""
    import character_identity as CI
    from clock import frame_plan
    identity, cast = CI.load(ep) or ({"cards": {}, "series": ""}, None)
    place = settings.get("frame_setting") or {}
    names = {s["id"]: s["name"] for s in settings.get("settings") or []}
    lines, ids = [], []
    for i in range(n_boxes):
        box = ep.box(i)
        pid = box.pid.rsplit("-", 1)[-1]
        frames, frame_of, _ = frame_plan(box)
        recs = sorted(box.speakers() or [], key=lambda r: r["order"])
        by_frame: dict[int | None, list[dict]] = {}
        for r in recs:
            by_frame.setdefault(frame_of.get(r["bubble"]), []).append(r)
        lines.append(f"## box {pid}")
        for f in list(frames) + ([None] if None in by_frame else []):
            if f is not None:
                fid = f"{pid}/f{f}"
                ids.append(fid)
                where = names.get(place.get(fid), "no place") if place.get(fid) else "no place"
                lines.append(f"- {fid} [{where}]" + ("" if by_frame.get(f) else " (wordless)"))
            for r in by_frame.get(f, []):
                bid = f"{pid}/b{r['bubble']}"
                ids.append(bid)
                who = "sfx" if r.get("kind") == "sfx" else _speaker_name(r, identity, cast) if cast else "?"
                text = (r.get("text") or "").strip()
                lines.append(f"  - {bid} {r.get('kind', 'speech')} {who}: \"{text}\"")
    return "\n".join(lines), ids


GAP_JOIN = 3  # unlabelled ids fewer than this between two spans join the span before them (a frame's trailing balloon)


def tile(reply: dict, ids: list[str]) -> tuple[list[dict], list[dict]]:
    """The reviewer's spans checked against the ids and tiled over them in order: a short gap joins the span before
    it, a long one is silence, an overlap goes to the later span. (spans, buttons)."""
    pos = {k: n for n, k in enumerate(ids)}
    spans = []
    for s in reply.get("spans") or []:
        a, b = pos.get(str(s.get("from"))), pos.get(str(s.get("to")))
        mood, role = str(s.get("mood", "")).lower(), str(s.get("role", "")).lower()
        if a is None or b is None or mood not in MOODS or role not in ROLES:
            print(f"  span dropped: {s}")
            continue
        if b < a:
            a, b = b, a
        spans.append({"from": ids[a], "to": ids[b], "mood": mood, "role": role,
                      "colour": (s.get("colour") or "").strip() or None, "why": s.get("why")})
    spans.sort(key=lambda s: pos[s["from"]])
    tiled, cursor = [], 0
    for s in spans:
        a, b = pos[s["from"]], pos[s["to"]]
        if b < cursor:
            continue
        if a > cursor:
            if tiled and a - cursor < GAP_JOIN:
                tiled[-1]["to"] = ids[a - 1]
            else:
                tiled.append({"from": ids[cursor], "to": ids[a - 1], "mood": "light", "role": "out", "colour": None, "why": "unlabelled"})
        s["from"] = ids[max(a, cursor)]
        tiled.append(s)
        cursor = b + 1
    if cursor < len(ids):
        if tiled and len(ids) - cursor < GAP_JOIN:
            tiled[-1]["to"] = ids[-1]
        else:
            tiled.append({"from": ids[cursor], "to": ids[-1], "mood": "light", "role": "out", "colour": None, "why": "unlabelled"})
    buttons = [{"at": str(b.get("at")), "why": b.get("why")} for b in reply.get("buttons") or [] if str(b.get("at")) in pos]
    return tiled, buttons


def reviewer_stamp(text: str) -> str:
    """spans.json's stamp: the material the reviewer reads and its recipe."""
    return fresh.digest(text, REVIEW_TASK, MODEL, REASONING)


def reviewer_step(ep: Episode, n_boxes: int, settings: dict) -> dict | None:
    """spans.json: {"spans": [...], "buttons": [...], "ids": [...]} from one reviewer call; kept while its stamp (the
    material, REVIEW_TASK, the model and its effort) holds. When the call cannot be made (the cap, an offline run)
    the saved spans are kept, None when there are none."""
    out = ep.out / "music"
    f_json = out / "spans.json"
    text, ids = material(ep, n_boxes, settings)
    stamp = reviewer_stamp(text)
    old = json.loads(f_json.read_text(encoding="utf-8")) if f_json.exists() else None
    if old and old.get("stamp") == stamp:
        print(f"  spans current: {len(old['spans'])}")
        return old
    content = [{"type": "text", "text": REVIEW_TASK}, {"type": "text", "text": "episode.md:\n" + text}]
    try:
        reply, cost = ask_json(MODEL, content, f"{ep.stem} music reviewer", ANSWER_TOKENS, REASONING, brief=False)
    except (BudgetExceeded, Truncated) as e:
        print(f"  spans not reviewed ({e}): {'the saved spans are kept' if old else 'no spans yet'}, the next run "
              f"reviews them")
        return old
    out.mkdir(parents=True, exist_ok=True)
    (out / "material.md").write_text(text, encoding="utf-8")
    (out / "task.md").write_text(REVIEW_TASK, encoding="utf-8")
    (out / "reply.json").write_text(json.dumps({"cost": cost, **reply}, indent=1, ensure_ascii=False), encoding="utf-8")
    tiled, buttons = tile(reply, ids)
    data = {"stamp": stamp, "ids": ids, "spans": tiled, "buttons": buttons, "cost": cost, "notes": reply.get("notes")}
    f_json.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  spans: {len(tiled)}, buttons {len(buttons)}; " +
          " | ".join(f"{s['from']}-{s['to']} {s['mood']}/{s['role']}" for s in tiled) + f"; {cost:.3f} USD")
    return data


# ----------------------------------------------------------------------------------------------- the tracks
MOOD_PROMPT = {
    "light": "light and easy, good-humoured, a relaxed pulse, nothing dramatic",
    "tense": "tense and watchful, a held-back pulse, suspense without a climax",
    "grave": "grave and quiet, slow, spare, a few instruments, sorrow held in",
    "epic": "epic and grand, a stirring theme that builds, heroic but still intimate in scale",
    "tender": "tender and warm, slow, gentle, affectionate, wistful",
}


def track_prompt(setting: dict, mood: str, colour: str | None, role: str) -> str:
    m = setting.get("music") or {}
    fam = f"Steady 4/4 at {m.get('bpm') or 100} BPM in {m.get('key') or 'D minor'}, played on {m.get('instruments') or 'a small folk ensemble'}"
    sparse = " Sparse arrangement: it sits under spoken dialogue, so leave room, no lead melody competing for attention." \
        if role in ("under", "source") else ""
    return (f"Instrumental only, no vocals, about two minutes. {fam}; the feel of the place: {m.get('feel') or ''}. "
            f"A piece for {setting.get('name') or 'a place'} ({setting.get('description') or ''}), mood: {MOOD_PROMPT[mood]}"
            + (f", {colour}" if colour else "") + f".{sparse} No intro, no outro, no ritardando: a steady piece that "
            f"can loop, keeping the same character all the way through.")


def portal_pieces(panels: list[dict], spans: dict, shows: list[dict]) -> list[dict]:
    """The music is made for the portal (CONTEXT.md: Place, decided 2026-11-08): every span cut by the places timeline
    ([{"start", "end", "setting"}], places.shows) into pieces [{"start", "end", "place", "mood", "role", "colour"}],
    in span order (a later span wins where two overlap). Time no portal covers is in no piece: it has no music."""
    times = clock.times(panels)
    out = []
    for j, s in enumerate(spans["spans"]):
        if s["from"] not in times or s["to"] not in times:
            continue
        t0, t1 = times[s["from"]][0], times[s["to"]][1]
        for sh in shows:
            a, b = max(t0, sh["start"]), min(t1, sh["end"])
            if b > a:
                out.append({"start": a, "end": b, "place": sh["setting"], "mood": s["mood"], "role": s["role"],
                            "colour": s.get("colour"), "span": j})
    return out


def pair_seconds(pieces: list[dict]) -> dict[tuple[str, str], float]:
    """Seconds of music (roles other than out) per (place, mood)."""
    secs: dict[tuple[str, str], float] = {}
    for p in pieces:
        if p["role"] != "out":
            secs[(p["place"], p["mood"])] = secs.get((p["place"], p["mood"]), 0.0) + p["end"] - p["start"]
    return secs


def resolve(place: str | None, mood: str, secs: dict[tuple[str, str], float], have: set[str]) -> str | None:
    """The track a moment in place with mood plays: the pair's own track when it has one, else the place's
    longest-scored track that exists, else none."""
    if not place:
        return None
    if f"{place}-{mood}" in have:
        return f"{place}-{mood}"
    own = sorted(((v, m) for (pl, m), v in secs.items() if pl == place and f"{pl}-{m}" in have), reverse=True)
    return f"{place}-{own[0][1]}" if own else None


def wanted_tracks(pieces: list[dict]) -> list[dict]:
    """The (place, mood) tracks to generate, in first-use order, each with the role that uses it most and its
    colours: a pair earns its own track with at least MIN_PAIR_S of music; a place none of whose pairs reaches it
    keeps its longest pair (an open portal is never silent for lack of time)."""
    secs = pair_seconds(pieces)
    own = {k for k, v in secs.items() if v >= MIN_PAIR_S}
    for place in {pl for pl, _ in secs}:
        if not any(pl == place for pl, _ in own):
            own.add(max((k for k in secs if k[0] == place), key=secs.get))
    want: dict[str, dict] = {}
    for p in pieces:
        k = (p["place"], p["mood"])
        if p["role"] == "out" or k not in own:
            continue
        w = want.setdefault(f"{k[0]}-{k[1]}", {"id": f"{k[0]}-{k[1]}", "setting": k[0], "mood": k[1], "spans": {},
                                               "colours": [], "seconds": round(secs[k], 1)})
        w["spans"][p["span"]] = p["role"]
        if p.get("colour") and p["colour"] not in w["colours"]:
            w["colours"].append(p["colour"])
    for w in want.values():  # the role most of its spans give it (the prompt's arrangement follows it)
        roles = list(w.pop("spans").values())
        w["role"] = max(roles, key=roles.count)
    return list(want.values())


def plan_shows(ep: Episode, settings: dict) -> list[dict]:
    """The places timeline the tracks are made for: places.plan on the saved clock (the export plans again on its
    own clock and resolves any pair it lacks to the place's longest track)."""
    clk = clock.load(ep)
    return places.shows(places.plan(clk, settings.get("frame_setting") or {})) if clk else []


def loop_body(audio: np.ndarray, sr: int) -> tuple[np.ndarray, dict]:
    """The song's body as a seamless loop: the beat period from the onset envelope's autocorrelation, a bar of four
    beats, the loop from the first strong onset after LEAD_IN to the latest point a whole number of bars later that
    best matches it (waveform correlation at the seam), spliced with a 20 ms equal-power crossfade. Returns (the
    loop, {"bpm", "start", "end", "seam"}); the whole song, trimmed of its tail, when no beat is found."""
    LEAD_IN, TAIL = 6.0, 6.0
    mono = audio.mean(axis=1) if audio.ndim == 2 else audio
    hop = int(sr * 0.01)
    n = len(mono) // hop
    rms = np.sqrt(np.mean(mono[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    onset = np.maximum(np.diff(rms, prepend=rms[0]), 0)
    onset -= onset.mean()
    ac = np.correlate(onset, onset, mode="full")[len(onset) - 1:]
    lo, hi = int(0.3 / 0.01), int(1.0 / 0.01)  # 60-200 BPM
    if len(ac) <= hi:
        return audio[: int((len(audio) / sr - TAIL) * sr)], {"bpm": None, "start": 0.0, "end": len(audio) / sr - TAIL, "seam": None}
    period = (lo + int(np.argmax(ac[lo:hi]))) * 0.01
    bpm = 60.0 / period
    bar = 4 * period
    first = int(LEAD_IN / 0.01) + int(np.argmax(onset[int(LEAD_IN / 0.01):int((LEAD_IN + bar) / 0.01)]))
    start = first * 0.01
    dur = len(audio) / sr
    best, best_c = None, -2.0
    k = 8
    win = int(0.05 * sr)
    while start + k * bar <= min(dur - TAIL, start + LOOP_MAX_S):
        end = start + k * bar
        a0, b0 = int(start * sr), int(end * sr)
        if b0 + win > len(mono):
            break
        x, y = mono[a0:a0 + win], mono[b0:b0 + win]
        c = float(np.dot(x, y) / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9))
        if c > best_c:
            best, best_c = end, c
        k += 4
    if best is None:
        return audio[: int((dur - TAIL) * sr)], {"bpm": round(bpm, 1), "start": 0.0, "end": dur - TAIL, "seam": None}
    a0, b0 = int(start * sr), int(best * sr)
    body = audio[a0:b0].copy()
    xf = int(0.02 * sr)
    ramp = np.linspace(0, 1, xf)[:, None] if audio.ndim == 2 else np.linspace(0, 1, xf)
    body[:xf] = body[:xf] * np.sqrt(ramp) + audio[b0:b0 + xf] * np.sqrt(1 - ramp)  # the seam: the end flows into the start
    return body, {"bpm": round(bpm, 1), "start": round(start, 2), "end": round(best, 2), "seam": round(best_c, 3)}


def song_stamp(prompt: str) -> str:
    """A track's song stamp: what a Lyria song is bought from, its prompt and the model. The loop cut from it costs
    nothing and is cut again whenever its WAV is missing."""
    return fresh.digest(prompt, lyria.SONG)


def track_plan(ep: Episode, settings: dict, spans: dict) -> list[dict]:
    """The tracks wanted (wanted_tracks on the saved clock's places timeline, capped at MAX_TRACKS, the least used
    dropped), each with its Lyria prompt ("prompt")."""
    by_id = {s["id"]: s for s in settings["settings"]}
    clk = clock.load(ep)
    want = wanted_tracks(portal_pieces(clk["panels"], spans, plan_shows(ep, settings))) if clk else []
    if len(want) > MAX_TRACKS:
        print(f"  {len(want)} tracks wanted, capped at {MAX_TRACKS}: the least used are dropped")
        want.sort(key=lambda w: -w["seconds"])
        want = want[:MAX_TRACKS]
    return [{**w, "prompt": track_prompt(by_id[w["setting"]], w["mood"], ", ".join(w["colours"][:2]) or None,
                                         w["role"])} for w in want]


def tracks_step(ep: Episode, settings: dict, spans: dict) -> dict:
    """tracks.json: every wanted track's song bought once per song stamp (a changed prompt or Lyria model buys it
    again, nothing else does), its loop written as WAV. tracks.json is written after each track, so a run stopped by
    the cap or a crash keeps what it bought; a track the cap refuses keeps its saved song and record (stale) and the
    next run buys it."""
    import soundfile as sf
    out = ep.out / "music"
    out.mkdir(parents=True, exist_ok=True)
    f_json = out / "tracks.json"
    have = {t["id"]: t for t in json.loads(f_json.read_text(encoding="utf-8"))["tracks"]} if f_json.exists() else {}
    want = track_plan(ep, settings, spans)
    tracks, cost, refused, why = [], 0.0, [], None

    def save(rest: list[dict]) -> None:  # the tracks done, then the saved records of those not reached yet
        keep = tracks + [have[w["id"]] for w in rest if w["id"] in have]
        f_json.write_text(json.dumps({"tracks": keep}, indent=1, ensure_ascii=False), encoding="utf-8")

    for k, w in enumerate(want):
        prompt = w["prompt"]
        stamp = song_stamp(prompt)
        old = have.get(w["id"])
        song = out / f"{w['id']}.mp3"
        if old and old.get("stamp") == stamp and song.exists():
            if (out / old["file"]).exists() and old.get("loop", {}).get("rms_db") is not None:
                tracks.append(old)
                continue
            mp3, usd, about = song.read_bytes(), old.get("cost", 0.0), old.get("about", "")  # only the loop is cut again
        else:
            if why is None:  # once the cap refuses one song no other is bought; free re-cuts still go on
                try:
                    mp3, usd, about = lyria.generate(prompt, lyria.SONG, tag=f"{ep.stem} music {w['id']}")
                except BudgetExceeded as e:
                    why = e
            if why is not None:
                refused.append(w["id"])
                if old:
                    tracks.append(old)  # its saved song keeps playing until the next run buys the new one
                continue
            cost += usd
            song.write_bytes(mp3)
        audio, sr = sf.read(io.BytesIO(mp3), dtype="float32", always_2d=True)
        body, loop = loop_body(audio, sr)
        rms = float(np.sqrt(np.mean(body.mean(axis=1) ** 2)) + 1e-9)
        body = np.clip(body * (10 ** (TRACK_RMS_DB / 20) / rms), -1.0, 1.0)
        loop["rms_db"] = round(20 * np.log10(rms), 1)
        # WAV, not OGG: libsndfile 1.2.2's Vorbis writer crashes the process on this machine (2026-11-07) and an MP3
        # seam never closes (encoder priming). PCM 16-bit stereo; a loop is kept under LOOP_MAX_S to bound the size
        sf.write(out / f"{w['id']}.wav", body, sr, format="WAV", subtype="PCM_16")
        rec = {"id": w["id"], "setting": w["setting"], "mood": w["mood"], "role": w["role"], "file": f"{w['id']}.wav",
               "song": f"{w['id']}.mp3", "prompt": prompt, "model": lyria.SONG, "stamp": stamp, "about": about,
               "duration": round(len(body) / sr, 2), "song_duration": round(len(audio) / sr, 2), "loop": loop,
               "cost": usd}
        tracks.append(rec)
        save(want[k + 1:])
        print(f"  {w['id']}: {rec['song_duration']} s song, loop {rec['duration']} s at {loop.get('bpm')} BPM, seam {loop.get('seam')}")
    save([])
    if refused:
        print(f"  tracks: {', '.join(refused)} not bought ({why}); the saved ones are kept, the next run buys them")
    print(f"  tracks: {len(tracks)}, {cost:.2f} USD new")
    return {"tracks": tracks}


# ----------------------------------------------------------------------------------------------- the envelope
def opening(shows: list[dict], grid: np.ndarray, fade: float) -> tuple[list, np.ndarray]:
    """(the place shown, how open its portal is 0..1) at every grid time, as a reader plays the places timeline: a
    swap fades the open place out over `fade` seconds, then the next in over `fade`; the first place fades in, the
    last one out at its end."""
    place, gate = [None] * len(grid), np.zeros(len(grid))
    for k, sh in enumerate(shows):
        swap = k > 0 and shows[k - 1]["end"] >= sh["start"] - 1e-6
        for i in np.nonzero((grid >= sh["start"]) & (grid < sh["end"]))[0]:
            t = grid[i] - sh["start"]
            if swap and t < fade:                       # the previous place still fading out
                place[i], gate[i] = shows[k - 1]["setting"], 1.0 - t / fade
            else:
                place[i] = sh["setting"]
                rise = t - (fade if swap else 0.0)
                gate[i] = min(1.0, rise / fade, (sh["end"] - grid[i]) / fade if k == len(shows) - 1 else 1.0)
    return place, np.clip(gate, 0.0, 1.0)


def placement(pieces: list[dict]) -> list[dict]:
    """How the music sits in the room over time, by role: source music from a point inside the place, lead and
    under spread across the open walls ([{"start", "end", "mode": "point" | "wide"}], consecutive ones joined)."""
    out: list[dict] = []
    for p in sorted((p for p in pieces if p["role"] != "out"), key=lambda p: p["start"]):
        mode = "point" if p["role"] == "source" else "wide"
        if out and out[-1]["mode"] == mode and p["start"] <= out[-1]["end"] + STEP:
            out[-1]["end"] = max(out[-1]["end"], round(p["end"], 2))
        else:
            out.append({"start": round(p["start"], 2), "end": round(p["end"], 2), "mode": mode})
    return out


def envelope(man: dict, spans: dict, tracks: dict, settings: dict) -> dict[str, list[list[float]]]:
    """Per-track gain knots from the spans, the places timeline (episode.places, from the export) and the clock (see
    the module's docstring for the rules), every gain times its portal's opening: no portal, no music. Pure."""
    times = clock.times(man["panels"])
    end_t = man["episode"].get("durationHint") or max((e for _, e in times.values()), default=0.0)
    n = int(end_t / STEP) + 2
    grid = np.arange(n) * STEP
    have = {t["id"] for t in tracks["tracks"]}
    place_of = {t["id"]: t["setting"] for t in tracks["tracks"]}
    pl = man["episode"].get("places") or {}
    shows = pl.get("timeline") or []
    pieces = portal_pieces(man["panels"], spans, shows)
    secs = pair_seconds(pieces)
    shown, gate = opening(shows, grid, pl.get("fade", 1.0))
    want_track = [None] * n   # the track at every moment, or None
    want_level = np.zeros(n)
    want_setting = [None] * n  # the place: a change of place is a change of track (out, a breath, in)
    buttons = sorted(times[b["at"]][0] for b in spans.get("buttons") or [] if b["at"] in times)
    for p in pieces:
        i0, i1 = int(p["start"] / STEP), min(n, int(p["end"] / STEP) + 1)
        tid = resolve(p["place"], p["mood"], secs, have) if p["role"] != "out" else None
        for i in range(i0, i1):
            want_setting[i] = p["place"]
            want_track[i] = tid
            want_level[i] = LEVEL[p["role"]] if tid else 0.0
    # a button: out from the button's start until the next span starts
    for bt in buttons:
        i = int(bt / STEP)
        cur = want_track[i] if i < n else None
        j = i
        while j < n and want_track[j] == cur:
            want_track[j] = None
            want_level[j] = 0.0
            j += 1
    # voice: a duck window around every voiced bubble; short gaps stay ducked
    voice = np.zeros(n, dtype=bool)
    for p in man["panels"]:
        for b in p.get("bubbles") or []:
            if b.get("audio"):
                a, e = b["startTime"] - ATTACK_S, (b.get("endTime") or b["startTime"]) + RELEASE_S
                voice[max(0, int(a / STEP)):min(n, int(e / STEP) + 1)] = True
    gap = int(SWELL_GAP_S / STEP)
    i = 0
    while i < n:
        if not voice[i]:
            j = i
            while j < n and not voice[j]:
                j += 1
            if 0 < i and j < n and j - i < gap:
                voice[i:j] = True
            i = j
        else:
            i += 1
    # cues: a change of wanted track, the first wordless frame of a span, and the run limit
    cue_at = np.full(n, -1.0)
    last_cue, last_track, run_from = -1e9, None, 0.0
    target = {tid: np.zeros(n) for tid in have}
    prev_setting = None
    breath_until = -1.0
    for i in range(n):
        t = grid[i]
        tid = want_track[i]
        if tid != last_track:
            if tid is not None:
                if last_track is not None and want_setting[i] != prev_setting:
                    breath_until = t + EXIT_S + BREATH_S  # a setting change: out, a breath, then in
                last_cue = max(t, breath_until)
                run_from = last_cue
            last_track = tid
            prev_setting = want_setting[i] if tid is not None else prev_setting
        if tid is None:
            continue
        if t < last_cue:  # inside the breath
            continue
        since = t - last_cue
        settle = 1.0 - (1.0 - FLOOR) * min(1.0, since / SETTLE_S)
        if t - run_from > MAX_RUN_S and voice[i]:
            continue  # ran long under dialogue: leaves until the next cue
        level = want_level[i] * settle * (DUCK if voice[i] else 1.0)
        target[tid][i] = level
    # the follower: each track's gain slews toward its target at the rates of the moment
    env = {}
    for tid in have:
        g = np.zeros(n)
        cur = 0.0
        for i in range(n):
            tg = target[tid][i]
            if tg > cur:
                rate = LEVEL["lead"] / ENTER_S if cur < 1e-6 else LEVEL["lead"] / RELEASE_S
            else:
                near_button = any(abs(grid[i] - bt) < BUTTON_S + STEP for bt in buttons)
                rate = LEVEL["lead"] / BUTTON_S if near_button else LEVEL["lead"] / ATTACK_S if tg > 0 else LEVEL["lead"] / XFADE_S
            cur += max(-rate * STEP, min(rate * STEP, tg - cur))
            g[i] = cur
        own = np.array([s == place_of.get(tid) for s in shown])  # heard only through its own place's portal
        env[tid] = _knots(grid, g * gate * own)
    return env


def _knots(t: np.ndarray, g: np.ndarray, tol: float = 0.004) -> list[list[float]]:
    """A polyline through (t, g) simplified (Ramer-Douglas-Peucker), ending at 0: what the reader interpolates."""
    pts = np.stack([t, g], axis=1)

    def rdp(a: int, b: int, keep: list[int]) -> None:
        if b <= a + 1:
            return
        p, q = pts[a], pts[b]
        seg = q - p
        L = np.hypot(*seg) or 1.0
        d = np.abs(seg[0] * (pts[a + 1:b, 1] - p[1]) - seg[1] * (pts[a + 1:b, 0] - p[0])) / L
        k = int(np.argmax(d))
        if d[k] > tol:
            rdp(a, a + 1 + k, keep)
            keep.append(a + 1 + k)
            rdp(a + 1 + k, b, keep)

    keep = [0, len(pts) - 1]
    rdp(0, len(pts) - 1, keep)
    keep = sorted(set(keep))
    knots = [[round(float(pts[i, 0]), 2), round(float(max(0.0, pts[i, 1])), 3)] for i in keep]
    if not any(k[1] > 0 for k in knots):
        return []
    # trim the zero runs at both ends to one knot each
    while len(knots) > 2 and knots[0][1] == 0 and knots[1][1] == 0:
        knots.pop(0)
    while len(knots) > 2 and knots[-1][1] == 0 and knots[-2][1] == 0:
        knots.pop()
    return knots


def gain_at(knots: list[list[float]], t: float) -> float:
    if not knots or t < knots[0][0] or t > knots[-1][0]:
        return 0.0
    for (t0, g0), (t1, g1) in zip(knots, knots[1:]):
        if t <= t1:
            return g0 + (g1 - g0) * ((t - t0) / (t1 - t0) if t1 > t0 else 1.0)
    return knots[-1][1]


def check(man: dict, env: dict[str, list[list[float]]]) -> list[str]:
    """The invariants a score must hold; the broken ones as messages."""
    bad = []
    for p in man["panels"]:
        for b in p.get("bubbles") or []:
            if not b.get("audio"):
                continue
            mid = (b["startTime"] + (b.get("endTime") or b["startTime"])) / 2
            total = sum(gain_at(k, mid) for k in env.values())
            if total > LEVEL["lead"] * DUCK + 0.03:
                bad.append(f"{p['id']}/{b['id']}: {total:.2f} under a voice")
    steepest = LEVEL["lead"] / min(ATTACK_S, BUTTON_S) * 1.5  # a duck's attack or a button: the fastest legitimate slope
    for tid, k in env.items():
        for (t0, g0), (t1, g1) in zip(k, k[1:]):
            if abs(g1 - g0) > 0.1 and abs(g1 - g0) / max(t1 - t0, 1e-6) > steepest:
                bad.append(f"{tid}: a cut at {t0}")
    return bad


def strip(man: dict, env: dict, spans: dict, tracks: dict, path: Path) -> None:
    """The score as a picture: time left to right, a lane per track filled by its gain, the lines as bars above,
    the spans as a band below with mood/role."""
    from PIL import Image, ImageDraw
    end_t = man["episode"].get("durationHint") or 1.0
    W, LANE, PX = 2400, 60, 2400 / end_t
    tids = [t["id"] for t in tracks["tracks"]]
    H = 70 + LANE * max(1, len(tids)) + 60
    im = Image.new("RGB", (W, H), (18, 18, 18))
    d = ImageDraw.Draw(im)
    from settings import _font
    f = _font(13)
    for m in range(0, int(end_t) + 1, 30):
        x = int(m * PX)
        d.line((x, 0, x, H), fill=(50, 50, 50))
        d.text((x + 2, 2), f"{m // 60}:{m % 60:02d}", fill=(150, 150, 150), font=f)
    for p in man["panels"]:
        d.line((int(p["startTime"] * PX), 20, int(p["startTime"] * PX), 70), fill=(70, 70, 70))
        d.text((int(p["startTime"] * PX) + 2, 20), p["id"], fill=(120, 120, 120), font=f)
        for b in p.get("bubbles") or []:
            x0, x1 = int(b["startTime"] * PX), int((b.get("endTime") or b["startTime"]) * PX)
            d.rectangle((x0, 40 if b.get("audio") else 56, max(x0 + 1, x1), 54 if b.get("audio") else 66),
                        fill=(90, 160, 230) if b.get("audio") else (90, 90, 90))
    PAL = {"light": (240, 200, 80), "tense": (230, 100, 80), "grave": (120, 100, 200), "epic": (220, 120, 40), "tender": (120, 200, 160)}
    for j, tid in enumerate(tids):
        y0 = 70 + j * LANE
        d.line((0, y0 + LANE - 1, W, y0 + LANE - 1), fill=(40, 40, 40))
        d.text((4, y0 + 2), tid, fill=(200, 200, 200), font=f)
        k = env.get(tid) or []
        col = PAL.get(tid.rsplit("-", 1)[-1], (200, 200, 200))
        pts = [(int(t * PX), int(y0 + LANE - 2 - g / LEVEL["lead"] * (LANE - 8))) for t, g in k]
        if len(pts) > 1:
            d.polygon([(pts[0][0], y0 + LANE - 2)] + pts + [(pts[-1][0], y0 + LANE - 2)], fill=tuple(c // 3 for c in col))
            d.line(pts, fill=col, width=2)
    times = clock.times(man["panels"])
    y = 70 + LANE * max(1, len(tids)) + 6
    for s in spans["spans"]:
        if s["from"] not in times or s["to"] not in times:
            continue
        x0, x1 = int(times[s["from"]][0] * PX), int(times[s["to"]][1] * PX)
        col = PAL.get(s["mood"], (200, 200, 200)) if s["role"] != "out" else (60, 60, 60)
        d.rectangle((x0, y, x1, y + 22), fill=col, outline=(18, 18, 18))
        d.text((x0 + 3, y + 4), f"{s['mood']}/{s['role']}", fill=(10, 10, 10) if s["role"] != "out" else (160, 160, 160), font=f)
    for b in spans.get("buttons") or []:
        if b["at"] in times:
            x = int(times[b["at"]][0] * PX)
            d.line((x, 36, x, H), fill=(255, 60, 60), width=2)
    im.save(path)


def score_step(ep: Episode, n_boxes: int) -> dict | None:
    """Settings (settings_step), the reviewer, the tracks: everything the export needs; None without frames."""
    from settings import settings_step
    st = settings_step(ep, n_boxes)
    if not st:
        return None
    sp = reviewer_step(ep, n_boxes, st)
    if sp is None:
        print("  tracks: no spans yet, no music this run")
        return None
    tr = tracks_step(ep, st, sp)
    return {"settings": st, "spans": sp, "tracks": tr}


def music_into(man: dict, sc: dict, ep_out: Path, added: dict[str, bytes]) -> None:
    """The score into an export's manifest (after its clock; the settings are the export's, settings.into): the tracks
    as episode/music/<id>.wav, the envelope and the spans under episode.score; the strip saved beside the step's files
    and the invariants checked (broken ones printed, the export still written)."""
    st, sp, tr = sc["settings"], sc["spans"], sc["tracks"]
    man["episode"]["music"] = []
    for t in tr["tracks"]:
        src = ep_out / "music" / t["file"]
        if not src.exists():
            continue
        path = f"episode/music/{t['id']}.wav"
        added[path] = src.read_bytes()
        man["episode"]["music"].append({"id": t["id"], "file": path, "loop": True, "gain": 1.0, "mood": t["mood"],
                                        "setting": t["setting"], "duration": t["duration"]})
    env = envelope(man, sp, tr, st)
    shows = (man["episode"].get("places") or {}).get("timeline") or []
    man["episode"]["score"] = {"envelope": env, "placement": placement(portal_pieces(man["panels"], sp, shows)),
                               "spans": [{k: v for k, v in {"from": s["from"], "to": s["to"], "mood": s["mood"], "role": s["role"],
                                                            "colour": s.get("colour")}.items() if v is not None}
                                         for s in sp["spans"]]}
    for p in man["panels"]:
        p.pop("musicCue", None)
    strip(man, env, sp, tr, ep_out / "music" / "strip.png")
    bad = check(man, env)
    on = {tid: round(sum(max(0.0, t1 - t0) for (t0, g0), (t1, g1) in zip(k, k[1:]) if g0 > 0.01 or g1 > 0.01), 1)
          for tid, k in env.items()}
    print(f"  score: {len(man['episode']['music'])} tracks, {len(sp['spans'])} spans; seconds on: " +
          ", ".join(f"{k} {v}" for k, v in on.items()) + (f"; {len(bad)} invariants broken: " + "; ".join(bad[:5]) if bad else "; invariants hold"))


def load(ep: Episode) -> dict | None:
    """What the step saved, for the export; None when any part is missing."""
    from settings import load as load_settings
    st = load_settings(ep)
    fs = [ep.out / "music" / "spans.json", ep.out / "music" / "tracks.json"]
    if st is None or not all(f.exists() for f in fs):
        return None
    sp, tr = (json.loads(f.read_text(encoding="utf-8")) for f in fs)
    return {"settings": st, "spans": sp, "tracks": tr}


if __name__ == "__main__":
    from chapter import Chapter
    zumi, out = Path(sys.argv[1]), Path(sys.argv[2])
    ch = Chapter(zumi)
    score_step(Episode(out, ch.stem), len(ch))
