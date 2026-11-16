"""Step 10a, settings: the places an episode is drawn in, one per frame (CONTEXT.md: Setting).

One Claude Sonnet 5.5 call over numbered contact sheets of every frame, in reading order, each shown as drawn beside
its backdrop (the erased card: the place without its people); the drawn frame says where the characters are. The reader names each setting (a place as drawn; time of day and weather are
attributes), lists its frames, and writes a music family for it (tempo, key, instruments, feel) so the tracks of one
setting can be generated as siblings. A frame with no place (a title, credits) gets none. Settings belong to the
episode: a later episode reads its own. Saved as <episode>/settings/settings.json with the sheets and the reply.

settings.json's stamp (fresh.py) covers what the sheets are rendered from: every frame's pair by its pixels (so a
backdrop erased again is read again), the sheets' layout, the task, the model and its reasoning effort. The sheets'
own pixels are not in it: their captions and thumbnails render differently on another machine (font, image library),
and an episode made on Linux would have been read again here for the same frames (2026-11-15). The cap, an offline run or a reply with no setting keeps the
saved file and leaves the read for the next run.

    python settings.py <chapter.zumi> <episode out dir>
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path

from PIL import Image, ImageDraw

import fresh
from boxstore import Box, Episode
from openrouter import BudgetExceeded, Truncated, ask_json, image_part
from speakers import reading_order

MODEL = "anthropic/claude-sonnet-5.5"
REASONING = "medium"
ANSWER_TOKENS = 6000
COLS, THUMB, CELL_H = 4, 460, 260  # a sheet: COLS thumbnails of THUMB px wide a row (each a drawn + backdrop pair)
PER_SHEET = 32
PAIR_GAP = 8
SAME_PLACE = 0.5  # frames shared over frames in either: a re-read setting at least this close keeps the earlier id

TASK = """# Task: name the places a comic episode is drawn in

You get every frame of one comic episode as a thumbnail, in reading order, numbered. Each thumbnail shows the frame
twice: on the left as drawn, with its characters; on the right with the characters and movable objects painted out,
the place alone. Decide which frames show the same place.

## What a setting is
A **setting** is a place as the comic draws it: the main room of a tavern, the road over a valley, a kitchen, a
rooftop. It is where the characters are: the ground they stand on, what they lean on or handle, what stands around
them. Read that from the left image. Whatever is seen beyond them (sky, clouds, hills, distant houses) is the view
from that place, so characters standing outdoors under an open sky are in an outdoor place on the ground, not in the
sky; they are in the sky only when nothing holds them up. The right image helps match one frame's place to another's,
but painting out what surrounded the characters can leave it emptier than the place was. A scene the story tells or
imagines (a tale, a memory, a dream, a vision) is drawn in its own place, the one shown, not the room where it is
told. A frame can show both, the teller in the room and the told scene around them: when the told scene fills most of
the frame it belongs to that scene's place; when the room fills it and the told scene is only a tint, a glow or a
corner, it is the room. A frame showing only a landscape or a sky, with nobody in it, shows that place. Time of day and weather are attributes of a setting, not new settings: the same square at dusk and at dawn
is one setting. A new camera angle on the same room is the same setting. A different room of the same building is a
different setting. A frame with no place at all (a title card, a credits page, a pattern, a close-up on a face with
no background to speak of) belongs to no setting: list it under `no_place`.

## How to work
Go through the frames in order. A frame joins a setting already named when its place is the one seen before (the same
walls, furniture, landscape, light); when its place is new, name a new setting. Comics return to places: the tavern
seen in frame 8 is the tavern again in frame 40 if the room is the same. When a frame is too tight to tell, follow
the story: a frame between two frames of one place, in the same scene, is in that place.

For each setting also write its **music family**: a tempo in BPM, a key, three to five instruments and a feel, so
that every piece of music written for this place, in any mood, sounds like the same band in the same room. Choose
from what the drawing suggests (period, culture, indoors or out, warmth) and keep it instrumental.

## Output
Reply with ONE JSON object, exactly this shape:

```json
{
  "settings": [
    {"id": "tavern", "name": "The tavern's main room", "description": "one or two sentences: what the place is and looks like",
     "indoor": true, "time_of_day": "night", "weather": null,
     "frames": [8, 9, 10, 14],
     "music": {"bpm": 104, "key": "D minor", "instruments": "fiddle, lute, bodhran, hurdy-gurdy", "feel": "warm, rowdy, tipsy folk dance"}}
  ],
  "no_place": [1, 70],
  "notes": "anything uncertain"
}
```

`id`: short, lowercase, letters digits and hyphens. `frames`: the thumbnails' numbers. Every frame number appears
exactly once, in a setting's `frames` or in `no_place`.
"""


def frame_images(box: Box) -> list[tuple[int, Image.Image]]:
    """[(frame index, the frame as drawn beside its backdrop, both cropped to the frame's extent)] in the box's reading
    order, [] without layers or frames. The backdrop alone can mislead: painting out the people and the movable things
    around them can leave little but the sky behind them."""
    sc, fr = box.scene(), box.frames()
    if sc is None or fr is None or not fr.masks:
        return []
    order = reading_order(fr.masks)
    backs = {l.frame: l for l in sc.layers if l.kind == "backdrop" and l.frame is not None}
    art = Image.fromarray(sc.art())
    out = []
    for f in order:
        l = backs.get(f)
        if l is None:
            continue
        im = l.image()
        wx0, wy0, wx1, wy1 = l.window_bbox or (max(0, l.bbox[0]), max(0, l.bbox[1]), min(sc.w, l.bbox[2]), min(sc.h, l.bbox[3]))
        crop = im.crop((wx0 - l.bbox[0], wy0 - l.bbox[1], wx1 - l.bbox[0], wy1 - l.bbox[1]))
        bg = Image.new("RGBA", crop.size, (255, 255, 255, 255))
        bg.alpha_composite(crop)
        drawn = art.crop((wx0, wy0, wx1, wy1))
        pair = Image.new("RGB", (drawn.width * 2 + PAIR_GAP, drawn.height), (20, 20, 20))
        pair.paste(drawn, (0, 0))
        pair.paste(bg.convert("RGB"), (drawn.width + PAIR_GAP, 0))
        out.append((f, pair))
    return out


def _font(size: int):
    from PIL import ImageFont
    try:
        return ImageFont.truetype("arial.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)  # no Arial (Linux): Pillow's own font, still at the asked size


def sheet(items: list[tuple[str, Image.Image]]) -> Image.Image:
    """Numbered thumbnails, COLS a row, each captioned: the material of one call."""
    rows = (len(items) + COLS - 1) // COLS
    out = Image.new("RGB", (COLS * (THUMB + 10), max(1, rows) * CELL_H), (20, 20, 20))
    d = ImageDraw.Draw(out)
    for j, (cap, im) in enumerate(items):
        t = im.copy()
        t.thumbnail((THUMB, CELL_H - 30))
        x, y = (j % COLS) * (THUMB + 10) + 5, (j // COLS) * CELL_H + 4
        out.paste(t, (x, y))
        d.rectangle((x, y + t.height, x + t.width, y + t.height + 22), fill=(40, 40, 40))
        d.text((x + 4, y + t.height + 3), cap, fill=(240, 240, 240), font=_font(16))
    return out


def episode_frames(ep: Episode, n_boxes: int) -> list[tuple[str, Image.Image]]:
    """Every frame of the episode in reading order as ("p007/f0", image)."""
    items = []
    for i in range(n_boxes):
        box = ep.box(i)
        for f, im in frame_images(box):
            items.append((f"{box.pid.rsplit('-', 1)[-1]}/f{f}", im))
    return items


def sheets(items: list[tuple[str, Image.Image]]) -> list[tuple[str, Image.Image]]:
    """The call's contact sheets, PER_SHEET frames each, numbered across the episode: [("sheet-1.png", image)]."""
    return [(f"sheet-{s // PER_SHEET + 1}.png",
             sheet([(f"#{s + j + 1} {k}", im) for j, (k, im) in enumerate(items[s:s + PER_SHEET])]))
            for s in range(0, len(items), PER_SHEET)]


def stamp_of(items: list[tuple[str, Image.Image]]) -> str:
    """settings.json's stamp: the frames (episode_frames) in order, each by its id and its pair's pixels, the layout
    the sheets are rendered by, and the recipe."""
    return fresh.digest([k for k, _ in items], [fresh.pixels(im) for _, im in items],
                        [COLS, THUMB, CELL_H, PER_SHEET, PAIR_GAP], TASK, MODEL, REASONING)


def sheets_stamp(ids: list[str], parts: list[tuple[str, Image.Image]]) -> str:
    """The stamp until 2026-11-15, over the rendered sheets' pixels: only to adopt a settings.json stamped then."""
    return fresh.digest(ids, [hashlib.sha256(img.tobytes()).hexdigest() for _, img in parts], TASK, MODEL, REASONING)


def settings_step(ep: Episode, n_boxes: int) -> dict | None:
    """The episode's settings (settings.json: {"frames": [ids in order], "settings": [...], "no_place": [...]}),
    read once: a saved file with the stamp computed now is kept. None when the episode has no frames yet, or when
    nothing is saved and the call could not be made."""
    out = ep.out / "settings"
    f_json = out / "settings.json"
    items = episode_frames(ep, n_boxes)
    if not items:
        return None
    ids = [k for k, _ in items]
    parts = sheets(items)
    stamp = stamp_of(items)
    old = json.loads(f_json.read_text(encoding="utf-8")) if f_json.exists() else None
    if old and fresh.holds(old.get("stamp"), stamp, lambda: sheets_stamp(ids, parts), "settings"):
        if old["stamp"] != stamp:
            old["stamp"] = stamp
            f_json.write_text(json.dumps(old, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"  settings current: {len(old['settings'])} settings over {len(ids)} frames")
        return old
    content = [{"type": "text", "text": TASK}]
    for k, (name, img) in enumerate(parts):
        content += [{"type": "text", "text": f"{name} (frames #{k * PER_SHEET + 1} on):"}, image_part(img)]
    kept = "the saved settings are kept" if old else "no settings yet"
    try:
        reply, cost = ask_json(MODEL, content, f"{ep.stem} settings", ANSWER_TOKENS, REASONING, brief=False)
    except (BudgetExceeded, Truncated) as e:
        print(f"  settings not read ({e}): {kept}, the next run reads them")
        return old
    out.mkdir(parents=True, exist_ok=True)
    for name, img in parts:
        img.save(out / name)
    (out / "task.md").write_text(TASK, encoding="utf-8")
    (out / "reply.json").write_text(json.dumps({"cost": cost, **reply}, indent=1, ensure_ascii=False), encoding="utf-8")
    if not reply.get("settings"):
        print(f"  settings: the reply names no setting ({cost:.3f} USD): {kept}, the next run reads them")
        return old
    data = {"stamp": stamp, **from_reply(reply, ids, (old or {}).get("settings") or []), "cost": cost}
    f_json.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  settings: {len(data['settings'])} over {len(ids)} frames ({len(data['no_place'])} with no place): " +
          "; ".join(f"{s['id']} x{len(s['frames'])}" + (" (kept)" if s.get("kept") else "") for s in data["settings"]) +
          f"; {cost:.3f} USD")
    return data


def slug(text, fallback: str) -> str:
    """A name from a model's reply made safe as an id and a file name: lower-case ASCII letters, digits and single
    hyphens (an accented letter loses its accent, anything else becomes a hyphen), the format's id pattern
    [a-z0-9_-]+; `fallback` when nothing is left."""
    ascii_ = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", ascii_).strip("-") or fallback


def from_reply(reply: dict, ids: list[str], old: list[dict]) -> dict:
    """The reader's reply as settings over the frame ids, each new setting matched to the earlier read's (`old`) by
    keep_ids (which also numbers an id that collides). {"frames", "settings", "no_place", "frame_setting", "notes"}."""
    settings = []
    for s in reply.get("settings") or []:
        sid = slug(s.get("id") or s.get("name"), "place")
        frames = [ids[int(n) - 1] for n in s.get("frames") or [] if 1 <= int(n) <= len(ids)]
        settings.append({"id": sid, "name": s.get("name") or sid, "description": s.get("description"),
                         "indoor": s.get("indoor"), "time_of_day": s.get("time_of_day"), "weather": s.get("weather"),
                         "music": s.get("music") or {}, "frames": frames})
    settings = keep_ids(settings, old)
    seen = {k: s["id"] for s in settings for k in s["frames"]}
    no_place = [ids[int(n) - 1] for n in reply.get("no_place") or [] if 1 <= int(n) <= len(ids)]
    for k in [k for k in ids if k not in seen and k not in no_place]:
        prev = seen.get(ids[ids.index(k) - 1]) if ids.index(k) else None  # an unlisted frame follows the one before it
        if prev:
            seen[k] = prev
            next(s for s in settings if s["id"] == prev)["frames"].append(k)
        else:
            no_place.append(k)
    return {"frames": ids, "settings": settings, "no_place": no_place, "frame_setting": seen, "notes": reply.get("notes")}


def keep_ids(new: list[dict], old: list[dict]) -> list[dict]:
    """A new read's settings, each that is the same place as an earlier read's setting taking that setting's id and
    record (name, description, attributes, music family) with its own frames, so the places and music made for it are
    reused, not made again under a new name. The same place = frames in common over frames in either (Jaccard) at
    least SAME_PLACE, matched one to one, largest share first; a new id that collides with an unmatched old one gets
    a suffix."""
    pairs = []
    for i, n in enumerate(new):
        for j, o in enumerate(old):
            a, b = set(n["frames"]), set(o["frames"])
            share = len(a & b) / len(a | b) if a | b else 0.0
            if share >= SAME_PLACE:
                pairs.append((share, i, j))
    taken_new, taken_old, out = set(), set(), [dict(s) for s in new]
    for _, i, j in sorted(pairs, reverse=True):
        if i not in taken_new and j not in taken_old:
            taken_new.add(i)
            taken_old.add(j)
            out[i] = {**{k: v for k, v in old[j].items() if k != "frames"}, "frames": new[i]["frames"], "kept": True}
    used = {out[i]["id"] for i in taken_new} | {o["id"] for o in old}
    for i, s in enumerate(out):
        if i not in taken_new and s["id"] in used:
            n = 2
            while f"{s['id']}-{n}" in used:
                n += 1
            s["id"] = f"{s['id']}-{n}"
        used.add(s["id"])
    return out


def load(ep: Episode) -> dict | None:
    """What the step saved (settings.json), None before it ran."""
    f = ep.out / "settings" / "settings.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def into(man: dict, st: dict) -> None:
    """The settings into an export's manifest: episode.settings (the format's camelCase fields) and each frame's
    setting."""
    man["episode"]["settings"] = [{k: v for k, v in {"id": s["id"], "name": s["name"], "description": s.get("description"),
                                                      "indoor": s.get("indoor"), "timeOfDay": s.get("time_of_day"),
                                                      "weather": s.get("weather")}.items() if v is not None}
                                  for s in st["settings"]]
    place = st.get("frame_setting") or {}
    for p in man["panels"]:
        for f in p.get("frames") or []:
            sid = place.get(f"{p['id']}/f{f['index']}")
            if sid:
                f["setting"] = sid


if __name__ == "__main__":
    from chapter import Chapter
    zumi, out = Path(sys.argv[1]), Path(sys.argv[2])
    ch = Chapter(zumi)
    settings_step(Episode(out, ch.stem), len(ch))
