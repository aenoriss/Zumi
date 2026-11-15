"""Voices: the cast's designed voices and every recorded line of an episode (CONTEXT.md: Voice), on one text-to-speech
backend behind one seam.

Two adapters sit at the seam, `gemini_tts` (Gemini 3.8 Flash TTS, the default: the owner's decision of 2026-11-15)
and `inworld` (Inworld TTS-2, with ZUMI_TTS=inworld); each owns
how its model is directed (a director's brief and a rate for Inworld, a short style and pace words for Gemini), the
key its voice ids live under in the cast record, its folder of lines and its engine name in the .zumi. A backend is
picked by name (ZUMI_TTS when none is given), so the two can be compared on one episode. Both adapters offer:

    NAME, ENGINE, VOICE_ID, AUDIO_DIR, SAMPLE_SUFFIX, SPEAKING_RATE
    DELIVERY_MODE                                            where the model has one (Inworld), else absent
    requests_left()                                          where the service counts requests a day (Gemini: 100)

A backend with a daily limit is planned by it: the voices are designed first, then the lines are recorded in
reading order, as many as the day leaves; the rest wait for a run on another day (design_voices and record_lines
return how many), and what was recorded is kept by its line record, so nothing is sent twice.
    design_voice(description, display_name, preview_text, language_code, gender, tag) -> {"id", "sample", "cost"}
    direct(style, pace, factor, char) -> {"brief", "rate"}   how one line is directed
    speech(text, voice, style, tag, context, rate, brief) -> (wav, cost, instruction)   text already spoken()

This module owns the rest: what a line says (spoken: lettering in caps to sentence case), its delivery note
(style_of), which balloons are voiced and which are current (record_lines), the line index (<episode>/<AUDIO_DIR>/
lines.json: one record per balloon), the voice a character speaks with (voice_of: a look that shares a voice points to
its owner), and the listening file (episode_audio).

    design_voices(cast, tts)                 every described voice of the cast not designed on this backend yet
    wanted_lines(ep, n, identity, cast, tts) the line records a recording run aims at, nothing sent
    record_lines(ep, n, identity, cast, tts) every voiced balloon recorded; only changed lines are paid for
    lines(ep, tts)                           the line index: {(pid, bubble): record} for lines whose file exists
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import ModuleType

import gemini_tts
import inworld
from boxstore import Episode
from openrouter import BudgetExceeded
from spend import paid_map

BACKENDS = {inworld.NAME: inworld, gemini_tts.NAME: gemini_tts}
STYLE = {"shout": "shouting", "thought": "thinking to themself, a quiet inner voice", "whisper": "whispering"}
PACE = {"slow": 0.9, "fast": 1.1}  # a line's tempo as Transcribe read it, times the voice's rate (user, 2026-11-06)
CONTEXT_LINES = 4  # balloons before a line, any speaker, sent as the scene so far
LINE_WORKERS = 4   # speech calls in flight (Inworld's free plan allows 5 concurrent)
LINE_RECIPE = ("voice_id", "text", "style", "brief", "rate", "model", "mode")  # a line record's fields that shape its
                                                                               # audio: one changed records it again


def backend(name: str | None = None) -> ModuleType:
    """The adapter named (gemini, inworld), else ZUMI_TTS's, else Gemini."""
    return BACKENDS[name or os.environ.get("ZUMI_TTS", gemini_tts.NAME)]


def left_today(tts: ModuleType) -> int | None:
    """The requests the backend's daily limit leaves today; None for a backend that counts none."""
    return tts.requests_left() if hasattr(tts, "requests_left") else None


def spoken(text: str) -> str:
    """The line as the model should read it: comic lettering is all caps, and to both models a capitalised word is a
    stressed one, so a line in caps throughout goes to sentence case; a line with mixed case keeps its caps, those are
    the lettering's stresses."""
    if text != text.upper() or not any(c.isalpha() for c in text):
        return text
    out, start = [], True
    for ch in text.lower():
        out.append(ch.upper() if start and ch.isalpha() else ch)
        if ch.isalpha():
            start = False
        elif ch in ".!?":
            start = True
    return re.sub(r"\bi\b", "I", "".join(out))


def style_of(r: dict) -> str | None:
    """A line's delivery note: what the balloon's kind says (STYLE) and what Transcribe read in the drawing (the
    record's delivery: emotion and manner), joined; None when neither says anything."""
    return ", ".join(s for s in (STYLE.get(r.get("kind")), (r.get("delivery") or "").strip()) if s) or None


def voice_of(chars: dict[str, dict], cid: str | None, key: str, hops: int = 0) -> tuple[str, str | None]:
    """(the character whose voice is used, its voice id under key, or None): a look sharing a voice points to its
    owner (same_voice_as). chars: {cast id: cast record}."""
    v = (chars.get(cid) or {}).get("voice") or {} if cid else {}
    if v.get("same_voice_as") and hops < 4:
        return voice_of(chars, v["same_voice_as"], key, hops + 1)
    return cid or "", v.get(key)


def lines(ep: Episode, tts: ModuleType) -> dict[tuple[str, int], dict]:
    """The line index of this backend: {(box pid, bubble id): record} for every recorded line whose file exists;
    a record's "path" is the file's full path."""
    d = ep.out / tts.AUDIO_DIR
    index = d / "lines.json"
    if not index.exists():
        return {}
    return {(l["pid"], l["bubble"]): l | {"path": str(d / l["file"])}
            for l in json.loads(index.read_text(encoding="utf-8")) if (d / l["file"]).exists()}


def design_voices(cast, tts: ModuleType) -> int:
    """Every described voice of the cast without a designed one on this backend, designed (the character's own lines
    as the preview script): the voice id in the cast record under tts.VOICE_ID, its sample in
    <cast>/voices/K<n><SAMPLE_SUFFIX>.wav. A description the service refuses is printed and tried again on the next
    run; the cap stops the rest for the next run. Returns the voices the backend's daily limit left undesigned."""
    todo = [c for c in cast.chars if c["voice"] and c["voice"].get("description") and not c["voice"].get(tts.VOICE_ID)]
    if not todo:
        return 0
    (cast.dir / "voices").mkdir(parents=True, exist_ok=True)
    made, cost = 0, 0.0
    for c in todo:  # the cast saved after each voice: a crash keeps the voices already published and paid for
        v = c["voice"]
        preview = " ".join(c.get("lines") or [])[:400] or v["description"]
        if left_today(tts) == 0:
            break
        try:
            got = tts.design_voice(v["description"], v.get("display_name") or c["name"], preview,
                                   v.get("language_code") or "en-US", v.get("gender"), tag=f"{cast.d['series']} voice {c['id']}")
        except BudgetExceeded as e:
            print(f"  voices not designed ({e}); the next run designs them")
            break
        except RuntimeError as e:
            print(f"  {c['id']} {c['name']}: {e}")
            continue
        v[tts.VOICE_ID], v["design_cost"] = got["id"], got["cost"]
        (cast.dir / "voices" / f"{c['id']}{tts.SAMPLE_SUFFIX}.wav").write_bytes(got["sample"])
        cast.save()
        made, cost = made + 1, cost + got["cost"]
    print(f"  {made} of {len(todo)} voices designed on {tts.NAME} ({cost:.4f} USD at list price): " +
          ", ".join(f"{c['id']} {c['name']}" for c in todo if c['voice'].get(tts.VOICE_ID)))
    return len(todo) - made if left_today(tts) == 0 else 0


def within_limit(todo: list, left: int | None) -> tuple[list, int]:
    """(the lines a run sends, how many wait for another day): the first `left` in reading order, all of them when
    the backend has no daily limit (None)."""
    return (todo, 0) if left is None else (todo[:left], max(0, len(todo) - left))


def wanted_lines(ep: Episode, n_boxes: int, identity: dict, cast, tts: ModuleType) -> tuple[list[dict], dict]:
    """(every line to be voiced on this backend as its line record, without what recording adds; {character: lines
    skipped for want of a designed voice}): each spoken balloon with a speaker card (speakers.json: kind not sfx; the
    card in the box, or in another box by the reader's correction) in its character's voice, directed as the adapter
    directs it; a balloon of marks alone ("...") is not voiced."""
    chars = {c["id"]: c for c in cast.chars}
    out, unvoiced, said = [], {}, []
    for i in range(n_boxes):
        box = ep.box(i)
        for r in sorted(box.speakers() or [], key=lambda r: r["order"]):
            text = (r.get("text") or "").strip()
            if r.get("kind") == "sfx" or not text:
                continue
            context = said[-CONTEXT_LINES:] or None  # the scene so far, whoever spoke
            said.append(text)
            if not r.get("speakers"):
                continue
            if not re.search(r"[^\W_]", text):  # a balloon of marks alone ("...", "?!!"): a reaction, no words to say
                continue
            s = r["speakers"][0]  # a card of the box, or "<pid>/<key>" of another box (the reader's correction)
            cid = identity["cards"].get(s if "/" in s else f"{r['pid']}/{s}")
            who, vid = voice_of(chars, cid, tts.VOICE_ID)
            if not vid:
                unvoiced[who or "?"] = unvoiced.get(who or "?", 0) + 1
                continue
            style = style_of(r)
            how = tts.direct(style, r.get("pace"), PACE.get(r.get("pace") or "", 1.0), chars.get(who))
            out.append({"pid": r["pid"], "bubble": r["bubble"], "box": i, "order": r["order"], "character": cid,
                        "voice": who, "voice_id": vid, "text": text, "style": style, "brief": how["brief"],
                        "context": context, "rate": how["rate"], "model": tts.ENGINE,
                        "mode": getattr(tts, "DELIVERY_MODE", None), "file": f"{r['pid']}.b{r['bubble']}.wav"})
    return out, unvoiced


def record_lines(ep: Episode, n_boxes: int, identity: dict, cast, tts: ModuleType) -> int:
    """Every line of wanted_lines as audio, to <episode>/<AUDIO_DIR>/<pid>.b<bubble>.wav and its lines.json. A
    balloon already recorded with the same words, voice, note, brief and rate on the same model and delivery mode
    (LINE_RECIPE) is kept; one whose character has no designed voice is skipped, counted. On a backend with a daily
    limit only the lines the day leaves are sent, the first in reading order (within_limit). Returns the lines that
    limit left for another day."""
    out = ep.out / tts.AUDIO_DIR
    index = out / "lines.json"
    have = {(l["pid"], l["bubble"]): l for l in json.loads(index.read_text(encoding="utf-8"))} if index.exists() else {}
    want, unvoiced = wanted_lines(ep, n_boxes, identity, cast, tts)
    todo, kept, wanted = [], 0, set()
    for line in want:
        wanted.add((line["pid"], line["bubble"]))
        old = have.get((line["pid"], line["bubble"]))
        # current when the same words go to the same designed voice at the same rate under the same brief, on the
        # same model and delivery mode (a rerun renumbers the characters, K12 to K11, while the voice they inherited
        # is the same one)
        if old and all(old.get(k) == line[k] for k in LINE_RECIPE) and (out / old["file"]).exists():
            kept += 1
            continue
        todo.append(line)
    stale = [k for k in have if k not in wanted]  # recorded earlier, no longer a voiced balloon (its speaker changed)
    for k in stale:
        (out / have.pop(k)["file"]).unlink(missing_ok=True)
    print(f"  {tts.NAME}: {len(todo)} lines to record, {kept} current" + (f", {len(stale)} dropped" if stale else "") +
          (f"; no voice for {sum(unvoiced.values())}: " + ", ".join(f"{k} {n}" for k, n in unvoiced.items())
           if unvoiced else ""))
    if stale:
        index.write_text(json.dumps(sorted(have.values(), key=lambda l: (l["box"], l["order"])), indent=1,
                                    ensure_ascii=False), encoding="utf-8")
    if not todo:
        return 0
    out.mkdir(parents=True, exist_ok=True)
    asked = len(todo)
    todo, _ = within_limit(todo, left_today(tts))

    def one(n: int) -> dict:
        l = todo[n]
        wav, cost, instruction = tts.speech(spoken(l["text"]), l["voice_id"], l["style"],
                                            tag=f"{ep.stem} line {l['pid']} b{l['bubble']}",
                                            context=[spoken(c) for c in l["context"]] if l.get("context") else None,
                                            rate=l["rate"], brief=l.get("brief"))
        (out / l["file"]).write_bytes(wav)
        import soundfile as sf
        info = sf.info(out / l["file"])
        return l | {"seconds": round(info.duration, 2), "cost": round(cost, 5), "instruction": instruction}

    def save(n: int, l: dict) -> None:  # after each line: a run stopped half-way keeps what it recorded
        have[(l["pid"], l["bubble"])] = l
        index.write_text(json.dumps(sorted(have.values(), key=lambda l: (l["box"], l["order"])), indent=1,
                                    ensure_ascii=False), encoding="utf-8")

    done, stopped = paid_map(one, range(len(todo)), workers=LINE_WORKERS, on_done=save)
    cost = sum(done[n]["cost"] for n in done)
    secs = sum(done[n]["seconds"] for n in done)
    waiting = asked - len(done) if left_today(tts) == 0 else 0  # the limit, by the count or by the service's word
    print(f"  {len(done)} lines recorded, {secs:.0f} s of audio, {cost:.4f} USD at list price" +
          (f"; {len(stopped)} stopped by the cap: the next run records them" if stopped and not waiting else ""))
    if waiting:
        print(f"  voices: {len(done)} of {asked} lines recorded, the daily limit of {tts.TTS_DAILY_REQUESTS} "
              f"{tts.NAME} TTS requests is reached; the rest are recorded by the next run on another day")
    if done or stale:
        episode_audio(ep, tts)
    return waiting


def episode_audio(ep: Episode, tts: ModuleType) -> Path | None:
    """The episode's recorded lines joined in reading order with the clock's gap between them, as
    <episode>/<AUDIO_DIR>/episode.mp3 for listening and sharing, with episode.txt beside it (the time, speaker and
    text of each line). Written after each recording run; None when there are no lines."""
    import numpy as np
    import soundfile as sf
    from clock import GAP_S
    recs = sorted(lines(ep, tts).values(), key=lambda l: (l["box"], l["order"]))
    parts, cues, t, sr = [], [], 0.0, 24000
    for l in recs:
        data, rate = sf.read(l["path"])
        if rate != sr:
            continue
        cues.append(f"{int(t // 60)}:{t % 60:04.1f} {l['voice']:>4} {l['text'][:80]}")
        parts += [data, np.zeros(int(GAP_S * sr))]
        t += len(data) / sr + GAP_S
    if not parts:
        return None
    out = ep.out / tts.AUDIO_DIR / "episode.mp3"
    sf.write(out, np.concatenate(parts), sr, format="MP3")
    out.with_suffix(".txt").write_text("\n".join(cues), encoding="utf-8")
    print(f"  episode audio: {len(cues)} lines, {t / 60:.1f} min, {out.name}")
    return out
