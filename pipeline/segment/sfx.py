"""Step 9b, the sound effects: a sound for every balloon of kind sfx (CRAAAACK!, CLANC-CLANC-CLANC!), played at its
startTime on the episode clock. Lettered sound effects get no voice (voices.py); this step gives them a sound.

    plan_step(ep, ch, n)     what each sound effect sounds like: one Claude Sonnet 5.5 call over the episode's sound
                             effects, each with the crop of its frame, its place (settings.py), who is drawn there and
                             the lines around it; per balloon a short description of the sound and its length.
                             <episode>/sfx/plan.json (kept while its stamp holds)
    sfx_step(ep, ch, n)      the plan, then each sound bought once (ElevenLabs Sound Effects v3 on fal, fal.sound_effect)
                             and finished: trimmed, cut to its length, faded, normalised (finish). <episode>/sfx/
                             raw/<key>.mp3 as bought, sounds/<finish stamp>.wav and sfx.json. Returns the sound
                             effects still without a sound
    sound_of(ep)             {(box pid, bubble id): finished WAV}, for the export (panels/<id>/sfx/b<n>.wav)

    python sfx.py <chapter.zumi> <episode out dir> [--dry]     --dry: an offline preview that writes nothing

Why after the clock: a sound's length is capped by its balloon's slot on the clock (clock.py: a sound effect is shown
for a reading time, a run of them in one frame lands together), and nothing on the clock waits for the sounds; the
music, the places and the props do not read them, so the step sits before them and their larger spend cannot starve
it.

Why a vision call and not rules: the onomatopoeia gives the shape of a sound (one hit, three hits, a drawn-out hiss)
but not its source (CRAAAACK of what?), and no step before writes what happens in a frame (Transcribe reads only the
lettering, the objects step is skipped without the erase). The frame's crop with its place and lines answers it, for
about 0.03 USD an episode. The rules (shape, rule_seconds, rule_prompt) still give the length when the call gives
none, and the offline preview.

Length: the model's seconds for the sound (a tick is short, a whoosh long), else the rules', clamped to MIN_S..MAX_S
and to the balloon's slot plus RING_S: a sound may ring past its balloon into the gap after it (clock.GAP_S), never
far over the next line. Bought at least API_MIN_S long (the service's floor) and cut to its length after.

Level (finish): the trimmed sound's RMS brought to SFX_RMS_DB, 8 dB under the voices (-28 against about -20 dBFS;
score.py's loops sit at -22 dB RMS and play at gain 0.16-0.40, so the music is still below a sound effect), with
the peak held at PEAK_DB: an impact is mostly peak, and its RMS over a short clip would push it into clipping.
The music does not duck under a sound effect (score.envelope ducks under voiced lines only): a sound effect is a
short accent above the bed, not a line the music must make room for.

Format: WAV, mono, 16-bit PCM at OUT_RATE (44.1 kHz) behind a plain 44-byte header. Mono: the reader plays it from
one point. 44.1 kHz and not the voices' 24 kHz: the crack, the hiss and the tick live above 12 kHz, and a sound
effect is short (2 s is 176 kB).

Cache: a sound is keyed by what it is bought with (sound_key: the prompt, the requested seconds, the model and its
settings), so balloons with the same description and length share one purchase, and a changed prompt buys again.
The finished file is named by its stamp (the key, its cut length and finish's constants): a changed finish is redone
for free from the raw file kept in raw/. Every call goes through the shared daily cap (spend.reserve) and the fal ledger;
an offline run refuses it. Once the cap or the account refuses one sound none other is bought: the saved ones are
kept, the rest are left for the next run (the step returns how many), and those balloons stay silent until then.
"""
from __future__ import annotations

import io
import json
import math
import re
import struct
import sys
from pathlib import Path

import numpy as np

import fresh
from boxstore import Episode

MODEL = "anthropic/claude-sonnet-5.5"
REASONING = "low"
ANSWER_TOKENS = 2500
CROP_SIDE = 768        # px on the long side of a frame's crop sent to the model
# the sounds
MIN_S, MAX_S = 0.3, 4.0  # a sound's length, clamped
RING_S = 1.0           # a sound may run this far past its balloon's slot
API_MIN_S = 0.5        # the service's shortest sound (fal.SFX_MIN_S): bought at least this long, then cut
HIT_S, SUSTAIN_S = 0.35, 0.15  # the rules' length: a hit, and each repeated letter drawing it out
STYLE = "single isolated sound effect, foley, close and dry, no music, no voices"
# finish
OUT_RATE = 44100       # Hz, mono, 16-bit PCM
SFX_RMS_DB = -28.0     # the trimmed sound's RMS, dBFS: 8 dB under the voices (-20); level with them they were too
                       # loud (owner, 2026-11-16); the music plays about 8-16 dB lower still (score.TRACK_RMS_DB -22 at
                       # gain 0.16-0.40)
PEAK_DB = -1.0         # and its peak never above this, dBFS
TRIM_DB = -45.0        # silence at either end: below this, relative to the peak
PRE_S = 0.01           # kept before the first sound above TRIM_DB
FADE_IN_S = 0.005      # against a click; the attack stays
FADE_OUT_S, FADE_OUT_SHARE = 0.08, 0.15  # the tail's fade: this long, at most this share of the sound
# the preview's estimate of the planning call: tokens a crop and a balloon's text, the reply, at the model's price
# (OpenRouter's list, 2026-11-15: 2 and 10 USD per million)
EST_IMAGE_TOKENS, EST_ITEM_TOKENS, EST_BASE_TOKENS, EST_REPLY_TOKENS = 800, 150, 900, 120
EST_PRICE_IN, EST_PRICE_OUT = 2.0 / 1e6, 10.0 / 1e6

TASK = """# Task: what each sound effect sounds like

A comic is played as a sound film: each balloon is voiced, and each lettered sound effect (an onomatopoeia drawn on
the art) is played as a real sound at the moment it appears. Below are the episode's sound effects, each with the
picture of the frame it is drawn in, the place, who is drawn there and the lines just before and after it.

For each one, decide what makes the sound in the story and describe that sound for a sound-effect generator:
- `prompt`: at most 25 words, concrete and physical: the source and its material, the action, its size and force,
  the space it is heard in (a small cafe, a street). Say how many hits or how it evolves when the lettering shows it
  (CLANC-CLANC-CLANC: three metallic clanks in quick succession; SHOOOOOSH: a long rushing whoosh). Describe the
  sound, never the letters: no onomatopoeia, no quotes, no music, no voices, no character names.
- `seconds`: how long the sound itself lasts, 0.3 to 4 (a tick 0.3, a crack 0.8, a whoosh 1.5-2.5).
- The same sound repeated in the episode (the same source doing the same thing) gets the same prompt word for word.

Reply with JSON only: {"sounds": [{"id": "<the id given>", "source": "<what makes it, a few words>", "prompt": "...",
"seconds": <number>}]}
"""


# ----------------------------------------------------------------------------------------------- the rules
def shape(text: str) -> dict:
    """The onomatopoeia's shape from its letters alone: {"word" (the first group, letters only), "hits" (groups that
    repeat it: CLANC-CLANC-CLANC is 3), "drawn" (letters past the first in its longest run of one letter: SHOOOOOSH
    is 4), "loud" (an exclamation mark)}."""
    groups = [g for g in re.split(r"[\s\-–—,.]+", text.upper()) if re.search(r"[A-Z]", g)]
    word = re.sub(r"[^A-Z]", "", groups[0]) if groups else ""
    hits = max(1, sum(1 for g in groups if re.sub(r"[^A-Z]", "", g) == word)) if word else 1
    runs = [len(m.group(0)) for m in re.finditer(r"([A-Z])\1*", word)]
    return {"word": word, "hits": hits, "drawn": max(runs, default=1) - 1, "loud": "!" in text}


def rule_seconds(text: str) -> float:
    """The sound's length by its shape: HIT_S a hit, drawn out by SUSTAIN_S a repeated letter, times its hits."""
    s = shape(text)
    return round(s["hits"] * (HIT_S + SUSTAIN_S * s["drawn"]), 2)


def rule_prompt(text: str, place: str | None) -> str:
    """A description from the shape alone, for the offline preview: the sound's word as the comic letters it, its
    shape, the place."""
    s = shape(text)
    how = (f"{s['hits']} quick hits" if s["hits"] > 1 else "a long drawn-out sound" if s["drawn"] >= 3
           else "one short sound")
    return (f"the sound a comic letters as {s['word'].lower()}: {how}" + (", loud" if s["loud"] else "")
            + (f", in {place}" if place else ""))


def target_seconds(proposed: float | None, slot: float, text: str = "") -> float:
    """The sound's length: the proposed one (else the rules'), within MIN_S..MAX_S and at most the slot plus RING_S."""
    s = proposed if isinstance(proposed, (int, float)) and proposed > 0 else rule_seconds(text)
    return round(max(MIN_S, min(s, MAX_S, max(MIN_S, slot) + RING_S)), 2)


def request_seconds(seconds: float) -> float:
    """What is bought: at least API_MIN_S, rounded up to a tenth (the price is per second)."""
    return max(API_MIN_S, math.ceil(seconds * 10 - 1e-9) / 10)


def sound_prompt(description: str) -> str:
    """The generator's prompt: the sound's description, then STYLE."""
    return f"{description.strip().rstrip('.')}. {STYLE}"


def sound_key(prompt: str, seconds: float) -> str:
    """A sound's identity: what it is bought with. Same key, same file."""
    import fal
    return fresh.digest(prompt, request_seconds(seconds), fal.SFX, fal.SFX_INFLUENCE, fal.SFX_FORMAT)


def finish_stamp(key: str, seconds: float) -> str:
    return fresh.digest(key, round(seconds, 2), [OUT_RATE, SFX_RMS_DB, PEAK_DB, TRIM_DB, PRE_S, FADE_IN_S,
                                                 FADE_OUT_S, FADE_OUT_SHARE])


# ----------------------------------------------------------------------------------------------- finish
def finish(audio: np.ndarray, rate: int, seconds: float) -> np.ndarray:
    """A bought sound as it ships: mono at OUT_RATE, silence trimmed at both ends (TRIM_DB under its peak, PRE_S kept
    before the attack), cut to `seconds`, faded in FADE_IN_S and out over its tail, its RMS brought to SFX_RMS_DB with
    the peak at most PEAK_DB. float32 in -1..1."""
    x = np.asarray(audio, dtype=np.float64)
    if x.ndim == 2:
        x = x.mean(1)
    if rate != OUT_RATE and len(x):
        from scipy.signal import resample_poly
        g = math.gcd(int(rate), OUT_RATE)
        x = resample_poly(x, OUT_RATE // g, int(rate) // g)
    peak = float(np.max(np.abs(x))) if len(x) else 0.0
    if peak <= 1e-6:
        return np.zeros(0, dtype=np.float32)
    loud = np.flatnonzero(np.abs(x) >= peak * 10 ** (TRIM_DB / 20))
    a = max(0, loud[0] - int(PRE_S * OUT_RATE))
    x = x[a:loud[-1] + 1][:int(round(seconds * OUT_RATE))]
    n = len(x)
    fi = min(n, int(FADE_IN_S * OUT_RATE))
    fo = min(n, int(min(FADE_OUT_S, FADE_OUT_SHARE * n / OUT_RATE) * OUT_RATE))
    if fi:
        x[:fi] *= np.linspace(0.0, 1.0, fi, endpoint=False)
    if fo:
        x[n - fo:] *= np.linspace(1.0, 0.0, fo) ** 2
    rms = float(np.sqrt(np.mean(x ** 2)))
    gain = min(10 ** (SFX_RMS_DB / 20) / max(rms, 1e-9), 10 ** (PEAK_DB / 20) / max(float(np.max(np.abs(x))), 1e-9))
    return np.clip(x * gain, -1.0, 1.0).astype(np.float32)


def wav_bytes(samples: np.ndarray) -> bytes:
    """Mono 16-bit PCM at OUT_RATE behind a plain 44-byte RIFF header, nothing after the samples."""
    pcm = np.round(np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, OUT_RATE, OUT_RATE * 2, 2, 16) + b"data" + struct.pack("<I", len(pcm)) + pcm)


# ----------------------------------------------------------------------------------------------- the material
def _name(s: str, pid: str, identity: dict, cast) -> str:
    cid = identity.get("cards", {}).get(s if "/" in s else f"{pid}/{s}")
    c = cast.char(cid) if (cast is not None and cid) else None
    return (c or {}).get("name") or "someone"


def items(ep: Episode, n_boxes: int) -> list[dict]:
    """Every sound effect on the episode clock, in clock order: {"id" ("p019/b1"), "pid", "bubble", "index", "text",
    "frame", "slot" (its seconds on the clock), "startTime", "place" (its frame's setting: name and description),
    "drawn" (the names of the characters drawn in its frame), "before" and "after" (up to two spoken lines each:
    "name: words"), "window" (its frame's extent in the box, px)}."""
    import clock
    import settings as SE
    clk = clock.load(ep) or clock.build(ep, n_boxes)
    st = SE.load(ep) or {}
    place_of = st.get("frame_setting") or {}
    about = {s["id"]: s for s in st.get("settings") or []}
    try:
        import character_identity as CI
        identity, cast = CI.load(ep) or ({"cards": {}}, None)
    except Exception:  # a run without identity: nobody has a name
        identity, cast = {"cards": {}}, None
    spoken, out = [], []
    for cp in clk["panels"]:
        box = ep.box(cp["index"])
        recs = {r["bubble"]: r for r in box.speakers() or []}
        bd = box.bubbles() or {"bubbles": []}
        kinds = {b["id"]: b.get("kind") for b in bd["bubbles"]}
        texts = {b["id"]: (b.get("text") or "").strip() for b in bd["bubbles"]}
        sc = box.scene()
        windows = {l.frame: l.window_bbox or l.bbox for l in (sc.layers if sc else []) if l.kind == "backdrop"}
        chars = {}
        for l in sc.layers if sc else []:
            if l.kind == "character" and l.frame is not None:
                chars.setdefault(l.frame, []).append(_name(l.key, box.pid, identity, cast))
        for cb in cp["bubbles"]:
            n = int(cb["id"][1:])
            r = recs.get(n, {})
            text = texts.get(n) or (r.get("text") or "").strip()
            if not text:
                continue
            if kinds.get(n) != "sfx":
                who = _name(r["speakers"][0], box.pid, identity, cast) if r.get("speakers") else "narrator"
                spoken.append((len(out), f"{who}: {text}"))
                continue
            f = cb.get("frame")
            setting = about.get(place_of.get(f"{cp['id']}/f{f}")) if f is not None else None
            out.append({"id": f"{cp['id']}/{cb['id']}", "pid": box.pid, "bubble": n, "index": cp["index"],
                        "text": text, "frame": f, "slot": cb["durationHint"], "startTime": cb["startTime"],
                        "place": f"{setting['name']}: {setting.get('description', '')}" if setting else None,
                        "drawn": sorted(set(chars.get(f, []))), "window": windows.get(f)})
    for k, it in enumerate(out):  # the lines around each: spoken[j] = (sound effects before it, the line)
        it["before"] = [s for j, s in spoken if j <= k][-2:]
        it["after"] = [s for j, s in spoken if j > k][:2]
    return out


def crop(img, window, side: int = CROP_SIDE):
    """The frame's extent of the box image (the whole box without one), its long side at most `side` px."""
    from PIL import Image
    im = img.crop(tuple(int(v) for v in window)) if window else img
    k = side / max(im.size)
    return im.resize((max(1, round(im.width * k)), max(1, round(im.height * k))), Image.LANCZOS) if k < 1 else im


def material(its: list[dict]) -> str:
    """The text the planning call reads about each sound effect (its picture comes beside it)."""
    out = []
    for it in its:
        out += [f"## {it['id']}: \"{it['text']}\"", f"- place: {it['place'] or 'unknown'}",
                f"- drawn in the frame: {', '.join(it['drawn']) or 'nobody'}"]
        out += [f"- before: {s}" for s in it["before"]] + [f"- after: {s}" for s in it["after"]]
    return "\n".join(out)


def plan_stamp(text: str, crops: list[str]) -> str:
    """plan.json's stamp: the material, the crops by the box pixels and windows they are cut from, the task and model."""
    return fresh.digest(text, crops, TASK, MODEL, REASONING, CROP_SIDE)


def estimate_plan_usd(n: int) -> float:
    """The planning call's cost for n sound effects, estimated (EST_*)."""
    tin = EST_BASE_TOKENS + n * (EST_IMAGE_TOKENS + EST_ITEM_TOKENS)
    return round(tin * EST_PRICE_IN + n * EST_REPLY_TOKENS * EST_PRICE_OUT, 4)


def rules_plan(its: list[dict]) -> dict[str, dict]:
    """The plan the rules alone give: {id: {"prompt", "seconds", "source": None}}."""
    return {it["id"]: {"prompt": rule_prompt(it["text"], (it["place"] or "").split(":")[0] or None),
                       "seconds": target_seconds(None, it["slot"], it["text"]), "source": None} for it in its}


def merge(reply: dict, its: list[dict]) -> dict[str, dict]:
    """The model's reply joined to the items: its prompt and seconds (clamped, target_seconds) where it gave them,
    the rules' for a sound effect it left out."""
    got = {s.get("id"): s for s in reply.get("sounds") or [] if isinstance(s, dict)}
    plan = rules_plan(its)
    for it in its:
        s = got.get(it["id"])
        if s and str(s.get("prompt") or "").strip():
            plan[it["id"]] = {"prompt": str(s["prompt"]).strip(), "source": s.get("source"),
                              "seconds": target_seconds(s.get("seconds"), it["slot"], it["text"])}
    return plan


def plan_step(ep: Episode, ch, n_boxes: int, dry: bool = False) -> tuple[list[dict], dict[str, dict], bool]:
    """(the sound effects, their plan {id: {"prompt", "seconds", "source"}}, whether the plan is the model's). Kept
    while its stamp holds; a call the cap or an offline run refuses leaves the saved plan, else the rules' (not
    saved: the next run asks). dry: nothing is called or written."""
    from openrouter import BudgetExceeded, Truncated, ask_json, image_part
    its = items(ep, n_boxes)
    if not its:
        return [], {}, True
    imgs = {}
    for it in its:
        if it["index"] not in imgs:
            imgs[it["index"]] = ch.image(it["index"])
    text = material(its)
    stamp = plan_stamp(text, [[fresh.pixels(imgs[it["index"]]), it["window"]] for it in its])
    f = ep.out / "sfx" / "plan.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else None
    if old and old.get("stamp") == stamp:
        return its, merge({"sounds": [{"id": k, **v} for k, v in old["plan"].items()]}, its), True
    if dry:
        return its, rules_plan(its), False
    content = [{"type": "text", "text": TASK}]
    for it in its:
        content += [{"type": "text", "text": f"Picture of {it['id']}:"}, image_part(crop(imgs[it["index"]], it["window"]))]
    content.append({"type": "text", "text": "sound effects:\n" + text})
    try:
        reply, cost = ask_json(MODEL, content, f"{ep.stem} sfx plan", ANSWER_TOKENS, REASONING)
    except (BudgetExceeded, Truncated) as e:
        print(f"  sfx plan not made ({e}): " + ("the saved plan is kept" if old else "nothing is bought this run"))
        if old:
            return its, merge({"sounds": [{"id": k, **v} for k, v in old["plan"].items()]}, its), True
        raise BudgetExceeded(f"sfx plan: {e}") from None
    plan = merge(reply, its)
    f.parent.mkdir(parents=True, exist_ok=True)
    (f.parent / "material.md").write_text(text, encoding="utf-8")
    f.write_text(json.dumps({"stamp": stamp, "cost": cost, "plan": plan}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  sfx plan: {len(plan)} sounds, {cost:.3f} USD")
    return its, plan, True


# ----------------------------------------------------------------------------------------------- the step
def sfx_step(ep: Episode, ch, n_boxes: int, dry: bool = False) -> int:
    """The plan, then every sound bought (fal.sound_effect, once per sound_key) and finished; sfx.json maps each
    balloon to its sound. Returns how many sound effects are still without one (the cap, the account, an offline
    run): the next run buys them. dry: prints what would be bought, at what cost, and writes nothing."""
    import fal
    from spend import BudgetExceeded
    try:
        its, plan, final = plan_step(ep, ch, n_boxes, dry)
    except BudgetExceeded:
        return len(items(ep, n_boxes))
    if not its:
        print("  sfx: no sound effects in the episode")
        return 0
    out = ep.out / "sfx"
    stamps = fresh.Stamps(out / "stamps.json")
    keys = {it["id"]: sound_key(sound_prompt(plan[it["id"]]["prompt"]), plan[it["id"]]["seconds"]) for it in its}
    if dry:
        seen, total = set(), 0.0
        print(f"  {'balloon':10s} {'text':20s} {'slot':>5s} {'sec':>5s} {'buy':>5s} {'USD':>7s}  prompt"
              + ("" if final else "  (rules preview: the Sonnet call writes the final prompts)"))
        for it in its:
            p, k = plan[it["id"]], keys[it["id"]]
            usd = 0.0 if k in seen or stamps.current(k, k, out / "raw" / f"{k}.mp3") else \
                request_seconds(p["seconds"]) * fal.SFX_USD_PER_S
            seen.add(k)
            total += usd
            print(f"  {it['id']:10s} {it['text'][:20]:20s} {it['slot']:5.2f} {p['seconds']:5.2f} "
                  f"{request_seconds(p['seconds']):5.1f} {usd:7.4f}  {sound_prompt(p['prompt'])}")
        llm = 0.0 if final else estimate_plan_usd(len(its))
        print(f"  sfx: {len(its)} sound effects, {len(seen)} sounds; about {total:.4f} USD of sounds (fal) + "
              f"{llm:.4f} USD for the plan (OpenRouter, estimated) = {total + llm:.4f} USD")
        return len(its)
    index, why, cost = {}, None, 0.0
    for it in its:
        p, k = plan[it["id"]], keys[it["id"]]
        fs = finish_stamp(k, p["seconds"])  # one bought sound may be cut to two lengths: a file per cut
        raw, wav = out / "raw" / f"{k}.mp3", out / "sounds" / f"{fs}.wav"
        if not stamps.current(k, k, raw):
            if why is None:
                try:
                    data, usd = fal.sound_effect(sound_prompt(p["prompt"]), request_seconds(p["seconds"]),
                                                 tag=f"{ep.stem} sfx {it['id']}")
                    raw.parent.mkdir(parents=True, exist_ok=True)
                    raw.write_bytes(data)
                    stamps.made(k, k)
                    cost += usd
                except BudgetExceeded as e:
                    why = e
                except Exception as e:  # a refused prompt, a failed download: that balloon stays silent, the rest go on
                    print(f"  sfx {it['id']}: no sound ({type(e).__name__}: {str(e)[:160]}); tried again next run")
                    continue
            if why is not None:
                continue
        if not wav.exists():  # named by its stamp: there, it is current
            import soundfile as sf
            audio, rate = sf.read(io.BytesIO(raw.read_bytes()), dtype="float32", always_2d=True)
            wav.parent.mkdir(parents=True, exist_ok=True)
            wav.write_bytes(wav_bytes(finish(audio, rate, p["seconds"])))
        index[f"{it['pid']}.b{it['bubble']}"] = {"id": it["id"], "text": it["text"], "key": k,
                                                 "file": f"sounds/{fs}.wav", "prompt": sound_prompt(p["prompt"]),
                                                 "seconds": p["seconds"], "source": p.get("source")}
    out.mkdir(parents=True, exist_ok=True)
    (out / "sfx.json").write_text(json.dumps(index, indent=1, ensure_ascii=False), encoding="utf-8")
    missing = len(its) - len(index)
    print(f"  sfx: {len(index)} of {len(its)} with a sound, {len({v['key'] for v in index.values()})} sounds, "
          f"{cost:.4f} USD new" + (f"; {missing} left for the next run ({why})" if missing else ""))
    return missing


def sound_of(ep: Episode) -> dict[tuple[str, int], Path]:
    """{(box pid, bubble id): its finished WAV} from sfx.json, the files that exist."""
    f = ep.out / "sfx" / "sfx.json"
    if not f.exists():
        return {}
    out = {}
    for k, v in json.loads(f.read_text(encoding="utf-8")).items():
        pid, _, b = k.rpartition(".b")
        if (ep.out / "sfx" / v["file"]).exists():
            out[(pid, int(b))] = ep.out / "sfx" / v["file"]
    return out


if __name__ == "__main__":
    from chapter import Chapter
    import spend
    dry = "--dry" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--dry"]
    ch = Chapter(Path(args[0]))
    ep = Episode(Path(args[1]), ch.stem)
    if dry:
        with spend.offline():
            sfx_step(ep, ch, len(ch), dry=True)
    else:
        sfx_step(ep, ch, len(ch))
