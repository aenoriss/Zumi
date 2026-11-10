"""Step 10d, props: the objects of each place that stand in the reader's room while the place is open.

A prop is one solid object of the place a person could set on a floor, table or shelf of a living room; the reader
places it on the room's real surfaces at run time (the format carries no positions). This module's first stage is
the pick: one Claude Sonnet 5.5 call per built place sees the place's painted view (places.py's shown.png) and up to
FRAMES comic frames drawn in that setting (as drawn, characters included: the ones showing the most of the place),
with the script said in those boxes, and names 0 to max_props(seconds open) props, each with a box on the view, its
real height and the surface it rests on. Every prop's picture is cut from the view, never from a frame (user,
2026-11-10): the view paints its objects whole, large and with no character over them, and a prop cut from it
matches what shows through the wall; the frames and the script only say which of the view's objects the story cares
about. Saved per place as <episode>/props/<setting>/pick.json (boxes in the view's own pixels) beside the images it
saw (img<n>.jpg) and a sheet with the boxes drawn.

The second stage, the build, makes each picked prop a textured 3D model, in four steps, each kept as a file beside
the pick: SAM 3.1 on the local GPU cuts the object out of the view inside its box (<name>-cut.png); FLUX.2 [klein]
4B repaints the cutout alone, whole and evenly lit, on a flat ground (<name>-paint.png, about 0.015 USD); BiRefNet
mattes the repaint and TRELLIS lifts it to a GLB (<name>-raw.glb, 0.02 USD), lifted once more with another seed when
it stands on a plate the picture never showed; then, with no call, its loose pieces are dropped and its texture is
brought to the cutout's colours, non-metal (<name>.glb, prop_mesh.py). stamps.json holds, per prop and per file,
a stamp of what the file is made from: the file before it and its own recipe (the cut: the view, the box, the
prompts and the cut constants; the repaint: its prompt, model, seed and grounds; the lift: its seeds and TRELLIS
settings; the finish: prop_mesh.py). A file whose stamp still holds is kept; one missing or stale is made again,
and every file after it with it. A prop that cannot be made (no SAM instance, the cap, an offline run, a failed
call) is skipped with its reason and the others go on. The built props are listed in props.json with their height
and surface.

    python props.py <chapter.zumi> <episode out dir> [setting ...]
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import requests
from PIL import Image, ImageDraw
from scipy.ndimage import binary_fill_holes, label

import clock
import fal
import fresh
import places
import prop_mesh
import settings
from boxstore import Episode
from openrouter import Truncated, ask_json, image_part
from spend import BudgetExceeded

MODEL = "anthropic/claude-sonnet-5.5"
REASONING = "medium"
ANSWER_TOKENS = 3000
FRAMES = 8          # comic frames per place, besides its view (user, 2026-11-09: nine images is fine)
SIDE = 1024         # every image is sent at most this long, boxes are read in these pixels, and a cutout and its
                    # repaint are this long: what TRELLIS takes in
MAX_PROPS = 5

PAD = 0.15          # SAM's crop reaches this share of the box past each side, so the object's edges are inside it
PROB = 0.5          # SAM probability above which a pixel is the instance's
FILL = 0.5          # an instance fills the box when it covers at least this share of what the fullest one covers
PINHOLE = 0.002     # holes under this share of the mask are filled, larger ones are gaps the object has
LIGHT = 65          # mean CIE lightness above which an object counts as light: repainted on dark grey, not on white
REPAINT_MODEL = "flux-2-klein-4b"
REPAINT_SEED = 1    # the seed validated on the 2026-11-10 props
WHITE = ("pure white", (255, 255, 255))  # the repaint's grounds (name in the prompt, rgb): white, or dark grey
DARK = ("dark grey", (70, 70, 70))       # under a light object (ground_of)
LIFT_SEEDS = (11, 22)  # TRELLIS seeds: the first lift, then one retry when it has a plate (2026-11-10)
TEXTURE = 1024        # TRELLIS texture side, as validated 2026-11-10: the cutouts it copies are 1024 px long
SIMPLIFY = 0.95       # TRELLIS mesh_simplify (share of faces removed), as validated 2026-11-10: a prop is small in the room
RUNGS = (("cut", "-cut.png"), ("paint", "-paint.png"), ("raw", "-raw.glb"), ("glb", ".glb"))  # a prop's files, each
                                                                                             # made from the one before
# The repaint prompt rewritten in the plate test (2026-11-10) without its "complete what is hidden" sentence: the
# pick only takes objects the view paints whole, and on a whole axe that sentence drew a second head (2026-11-10).
PROMPT = ("The {what} from the reference image, redrawn alone and whole. It is the same object: its shape, proportions, "
          "colours and materials, with nothing added that the reference does not show. Keep its hand-painted look: the "
          "ink outlines and the painted texture of the reference, not a photograph. Soft, even light from the front "
          "shows its form; it casts no shadow. It stands free in empty {ground} space: flat {ground} all around it, "
          "under it and between its parts. The whole object is inside the picture, with a margin around it.")

TASK = """# Task: choose the props of a place

A comic episode is read in mixed reality. While a place of the story is open, a painted view of it shows through
the reader's walls, and a few of its objects stand in the reader's real room, on the floor or on a table, so the
place carries on into the room. You choose those objects for one place.

## What you get
- Image 1: the painted view of the place made for the walls. Every prop is cut out of this image, so every prop
  you choose is an object painted in it.
- Images 2 and on: frames of the comic drawn in this place, as drawn, characters included. They are never a prop's
  picture; they show what the story does in this place.
- The script: what is said in the comic boxes these frames come from.

## What a prop is
One solid object of this place that a person could set down on the floor, a table or a shelf of a living room:
between about 5 cm and 1.2 m tall, still, whole on its own. Not a character, creature or animal; not part of a
building or a landscape (walls, doors, windows, beams, fences, trees, rocks, ground, sky); not light, smoke, weather
or magic effects; not lettering.

## How to choose
Choose up to {n} props among the objects painted in image 1: the ones that most say this is this place. An object
the frames also draw, or the story makes important (named, handled, fought over), comes before one only the view
shows. Several copies of one object count as one prop: choose the copy painted best.

The object is cut out of image 1 along its outline, with whatever lies over it. So choose only objects image 1
paints whole: all of it inside the image, nothing standing in front of it or resting on it, not merged with a
neighbour, and large enough to see how it is made. Between two copies, take the larger and less covered one. An
object the story cares about that image 1 does not paint, or paints only partly, is left out: say so in the notes.
Choose fewer, or none, when image 1 has no such objects (an open sky, a far landscape): an empty list is a right
answer.

For each prop, give a tight box around that one object in image 1's pixels (its size is listed below): around
the one copy you chose, not around a group. In `what`, say only what kind of thing it is and what it is made of,
with the story's name for it when the story names it: no colour, no place, no position. Its colours are taken from
the picture, and a colour word here would repaint it (a chair that looks pale under a lamp is not a white chair).
In `noun`, give the one plain word for the kind of thing: the cutting tool finds single objects best by it.

## Output
Reply with ONE JSON object:

```json
{{"props": [{{"name": "short-id-with-hyphens", "what": "the kind of thing and its material, a few words",
             "noun": "one word", "box": [x0, y0, x1, y1], "height_m": 0.9, "surface": "floor",
             "why": "one sentence"}}],
 "notes": "anything uncertain"}}
```

`surface`: floor, table or shelf.
"""


def max_props(seconds: float) -> int:
    """How many props a place may have by how long it is open: one, and one more every 15 s, up to MAX_PROPS."""
    return min(MAX_PROPS, 1 + int(seconds // 15))


def _fit(img: Image.Image) -> Image.Image:
    img = img.convert("RGB")
    s = SIDE / max(img.size)
    return img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS) if s < 1 else img


def setting_frames(ep: Episode, frame_setting: dict[str, str], sid: str, n: int = FRAMES) -> list[tuple[str, Image.Image]]:
    """Up to n frames drawn in the setting, as drawn ("p007/f0", image), the ones showing the most of the place
    first, then in reading order. Showing the place = the frame's area its characters and objects leave free, times
    how much is drawn there (the backdrop's mean edge strength): a close-up on a face over a plain wash has free area
    but no place in it."""
    scored = []
    for fid, s in frame_setting.items():
        if s != sid:
            continue
        pid, f = fid.split("/f")
        box = ep.box(int(pid[1:]))
        sc = box.scene()
        if sc is None:
            continue
        back = next((l for l in sc.layers if l.kind == "backdrop" and l.frame == int(f)), None)
        if back is None:
            continue
        x0, y0, x1, y1 = back.window_bbox or (max(0, back.bbox[0]), max(0, back.bbox[1]), min(sc.w, back.bbox[2]),
                                              min(sc.h, back.bbox[3]))
        if x1 - x0 < 64 or y1 - y0 < 64:
            continue
        cover = np.zeros((sc.h, sc.w), bool)
        for l in sc.layers:
            if l.frame == int(f) and l.kind in ("character", "object"):
                cover |= l.mask((sc.h, sc.w))
        free = ~cover[y0:y1, x0:x1]
        bk = back.image().convert("L")
        plate = np.asarray(bk.crop((x0 - back.bbox[0], y0 - back.bbox[1], x1 - back.bbox[0], y1 - back.bbox[1])), np.float32)
        edge = np.abs(np.diff(plate, axis=0))[:, :-1] + np.abs(np.diff(plate, axis=1))[:-1]
        drawn = float(edge[free[:-1, :-1]].sum()) if free.any() else 0.0   # the place's drawing left visible
        scored.append((drawn, fid, sc, (x0, y0, x1, y1)))
    best = sorted(scored, key=lambda t: -t[0])[:n]
    best.sort(key=lambda t: list(frame_setting).index(t[1]))
    return [(fid, Image.fromarray(sc.art()).crop(win)) for _, fid, sc, win in best]


def script(ep: Episode, frame_ids: list[str]) -> str:
    """The lines said in the boxes the frames come from, box by box (sound effects and dropped text left out)."""
    tr = ep.transcripts()
    out = []
    for pid in dict.fromkeys(f.split("/")[0] for f in frame_ids):
        lines = [e["text"] for e in (tr.get(int(pid[1:])) or {}).get("elements", [])
                 if e.get("keep", True) and e.get("kind") != "sfx" and e.get("text")]
        if lines:
            out.append(f"{pid}: " + " / ".join(lines))
    return "\n".join(out) or "(nothing is said)"


def pick_material(ep: Episode, sid: str, seconds: float, frame_setting: dict[str, str]) -> tuple[list, str, int]:
    """What the pick call sees: ([(source, image as sent)], the text before the images, the props allowed)."""
    view = ep.out / "places" / sid / "shown.png"
    imgs = [("view", _fit(Image.open(view)))] + [(fid, _fit(im)) for fid, im in setting_frames(ep, frame_setting, sid)]
    n = max_props(seconds)
    sizes = "\n".join(f"- Image {k}: {'the painted view' if src == 'view' else 'comic frame ' + src}, "
                      f"{im.width} x {im.height} px" for k, (src, im) in enumerate(imgs, 1))
    text = (TASK.format(n=n) + f"\n## The place\n{_place_text(ep, sid)}\nOpen for {seconds:.0f} s.\n\n"
            f"## The images\n{sizes}\n\n## The script\n{script(ep, [fid for fid, _ in imgs[1:]])}\n")
    return imgs, text, n


def pick_stamp(imgs: list, text: str) -> str:
    """pick.json's stamp: the whole text and every image's pixels as the call sees them, the model and its effort."""
    return fresh.digest(text, [hashlib.sha256(im.tobytes()).hexdigest() for _, im in imgs], MODEL, REASONING)


def pick(ep: Episode, sid: str, seconds: float, frame_setting: dict[str, str]) -> dict:
    """The props of one place (pick.json), read once per pick_stamp. A prop's name is made safe from the reply's
    (settings.slug) and numbered when it collides: it names the prop's files."""
    d = ep.out / "props" / sid
    d.mkdir(parents=True, exist_ok=True)
    view = ep.out / "places" / sid / "shown.png"
    imgs, text, n = pick_material(ep, sid, seconds, frame_setting)
    stamp = pick_stamp(imgs, text)
    f_json = d / "pick.json"
    if f_json.exists():
        old = json.loads(f_json.read_text(encoding="utf-8"))
        if old.get("stamp") == stamp:
            return old
    content = [{"type": "text", "text": text}]
    for k, (_, im) in enumerate(imgs, 1):
        content += [{"type": "text", "text": f"Image {k}:"}, image_part(im, max_side=SIDE)]
    reply, cost = ask_json(MODEL, content, f"{ep.stem} props {sid}", ANSWER_TOKENS, REASONING, brief=False)
    for k, (_, im) in enumerate(imgs, 1):
        im.save(d / f"img{k}.jpg", quality=92)
    w, h = imgs[0][1].size
    full = Image.open(view).width / w   # the box is read on the view as sent and kept in the view's own pixels
    props, seen, names = [], [], set()
    for p in reply.get("props") or []:
        if len(p.get("box") or []) != 4:
            continue
        x0, y0, x1, y1 = (int(round(float(v))) for v in p["box"])
        x0, x1 = sorted((max(0, min(w, x0)), max(0, min(w, x1))))
        y0, y1 = sorted((max(0, min(h, y0)), max(0, min(h, y1))))
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue
        name = base = settings.slug(p.get("name"), f"prop-{len(props) + 1}")
        k = 2
        while name in names:
            name, k = f"{base}-{k}", k + 1
        names.add(name)
        seen.append({"name": name, "image": 1, "box": [x0, y0, x1, y1]})
        props.append({"name": name, "what": p.get("what"), "noun": p.get("noun"),
                      "box": [round(v * full) for v in (x0, y0, x1, y1)],
                      "height_m": p.get("height_m"), "surface": p.get("surface"), "why": p.get("why")})
    data = {"stamp": stamp, "setting": sid, "seconds": round(seconds, 1), "max": n,
            "images": [src for src, _ in imgs], "props": props, "notes": reply.get("notes"), "cost": cost}
    f_json.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    _sheet(d, imgs, seen)
    return data


def _place_text(ep: Episode, sid: str) -> str:
    s = next((s for s in (settings.load(ep) or {}).get("settings", []) if s["id"] == sid), None)
    return places._what(s) if s else sid


def _sheet(d: Path, imgs: list, props: list[dict]) -> None:
    """Every image the call saw, with the chosen boxes drawn and named: the step's review sheet."""
    tiles = []
    for k, (src, im) in enumerate(imgs, 1):
        t = im.copy()
        dr = ImageDraw.Draw(t)
        for p in props:
            if p["image"] == k:
                dr.rectangle(p["box"], outline=(255, 40, 40), width=4)
                dr.text((p["box"][0] + 4, p["box"][1] + 4), p["name"] or "?", fill=(255, 255, 0))
        t.thumbnail((480, 480))
        cell = Image.new("RGB", (480, 500), (20, 20, 20))
        cell.paste(t, (0, 0))
        ImageDraw.Draw(cell).text((4, 484), f"{k}: {src}", fill=(230, 230, 230))
        tiles.append(cell)
    cols = 3
    sheet = Image.new("RGB", (cols * 480, ((len(tiles) + cols - 1) // cols) * 500), (10, 10, 10))
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 480, (i // cols) * 500))
    sheet.save(d / "pick-sheet.png")


def seconds_open(ep: Episode, frame_setting: dict[str, str]) -> dict[str, float]:
    """Seconds each place is open on the saved clock (places.plan's timeline)."""
    out: dict[str, float] = {}
    for s in places.shows(places.plan(clock.load(ep), frame_setting)):
        out[s["setting"]] = out.get(s["setting"], 0.0) + s["end"] - s["start"]
    return out


def ground_of(cut: Image.Image) -> tuple[str, tuple[int, int, int]]:
    """The repaint's ground for a cutout, (name in the prompt, rgb): white, or dark grey under a light object. A white
    chair on white gave the matte nothing to tell the gaps of its scrollwork from the chair (2026-11-10)."""
    a = np.asarray(cut.convert("RGBA"))
    light = prop_mesh.to_lab(a[..., :3][a[..., 3] > 127])[:, 0].mean() > LIGHT
    return DARK if light else WHITE


def cut_of(seg, img: Image.Image, box, prompts: list[str]) -> tuple[Image.Image | None, str | None]:
    """The object in its box on the view, alone on a transparent ground and enlarged to SIDE on its long side, and the
    prompt SAM found it by; (None, None) when no instance reaches into the box."""
    x0, y0, x1, y1 = box
    px, py = (x1 - x0) * PAD, (y1 - y0) * PAD
    crop = (int(max(0, x0 - px)), int(max(0, y0 - py)), int(min(img.width, x1 + px)), int(min(img.height, y1 + py)))
    found = seg.zoom(img, crop, prompts)
    bx = (slice(int(y0 - crop[1]), int(y1 - crop[1])), slice(int(x0 - crop[0]), int(x1 - crop[0])))
    # Among the instances that fill the box, SAM's most confident: a descriptive prompt merged two overlapping chairs
    # into one instance that covered more of the box, while the plain prompt gave the front chair alone with a higher
    # score (2026-11-10).
    inside = [int((t[0][bx] > PROB).sum()) for t in found]
    if not found or max(inside) == 0:
        return None, None
    best = max((t for t, n in zip(found, inside) if n >= FILL * max(inside)), key=lambda t: t[1])
    # Only pinholes are filled: filling every hole closed the gaps of a chair's scrollwork with the wall seen through
    # them, and the model's back came out solid (2026-11-10).
    m = best[0] > PROB
    holes, k = label(binary_fill_holes(m) & ~m)
    if k:
        size = np.bincount(holes.ravel())
        m = m | ((size[holes] < PINHOLE * m.sum()) & (holes > 0))
    lab, n = label(m)
    if n > 1:
        m = lab == 1 + int(np.argmax(np.bincount(lab.ravel())[1:]))
    cut = img.crop(crop).convert("RGBA")
    cut.putalpha(Image.fromarray((m * 255).astype(np.uint8)))
    ys, xs = np.nonzero(m)
    cut = cut.crop((max(0, xs.min() - 8), max(0, ys.min() - 8), min(cut.width, xs.max() + 9), min(cut.height, ys.max() + 9)))
    s = SIDE / max(cut.size)
    return cut.resize((round(cut.width * s), round(cut.height * s)), Image.LANCZOS), best[2]


def stamps_of(view: str, p: dict) -> dict[str, str]:
    """What each of a prop's files is made from, {rung: stamp}: each stamp covers the one before it and its own
    rung's recipe, so a change anywhere reaches every file after it. view: the view's digest (fresh.digest)."""
    cut = fresh.digest(view, p["box"], p.get("noun"), p["what"], [PAD, PROB, FILL, PINHOLE, SIDE])
    paint = fresh.digest(cut, PROMPT, p["what"], REPAINT_MODEL, REPAINT_SEED, LIGHT, [WHITE, DARK])
    raw = fresh.digest(paint, LIFT_SEEDS, TEXTURE, SIMPLIFY)
    # The finish costs nothing, so any edit of prop_mesh.py makes it again rather than guessing which edits change
    # its bytes.
    glb = fresh.digest(raw, fresh.source(prop_mesh))
    return {"cut": cut, "paint": paint, "raw": raw, "glb": glb}


def _todo(d: Path, name: str, saved: dict, now: dict) -> list[str]:
    """The rungs of a prop to make, in order: from the first whose file is missing or whose saved stamp is not the
    one computed now, to the last. Their files are deleted and their stamps dropped from `saved`."""
    k = next((i for i, (r, suffix) in enumerate(RUNGS)
              if saved.get(r) != now[r] or not (d / f"{name}{suffix}").exists()), len(RUNGS))
    for r, suffix in RUNGS[k:]:
        (d / f"{name}{suffix}").unlink(missing_ok=True)
        saved.pop(r, None)
    return [r for r, _ in RUNGS[k:]]


def _made(d: Path, stamps: dict, name: str, rung: str, now: dict) -> None:
    """A rung's stamp saved, once its file is written."""
    stamps.setdefault(name, {})[rung] = now[rung]
    (d / "stamps.json").write_text(json.dumps(stamps, indent=1), encoding="utf-8")


def _finish(d: Path, sid: str, p: dict, todo: list[str], made, last: dict) -> dict:
    """One prop from its cut to its model, the rungs in `todo` made in turn (made(rung) once each file is written):
    its props.json entry. last: its entry from the run that made the files kept."""
    name, tag = p["name"], f"prop {sid}/{p['name']}"
    cut = Image.open(d / f"{name}-cut.png").convert("RGBA")
    pp, raw, out = d / f"{name}-paint.png", d / f"{name}-raw.glb", d / f"{name}.glb"
    if "paint" in todo:
        from bfl import flux2
        ground, rgb = ground_of(cut)
        flat = Image.new("RGB", cut.size, rgb)
        flat.paste(cut, mask=cut.getchannel("A"))
        img, _ = flux2(PROMPT.format(what=p["what"], ground=ground), [flat], SIDE, SIDE, model=REPAINT_MODEL,
                       tag=f"{tag} repaint", seed=REPAINT_SEED)
        img.save(pp)
        made("paint")
    lifts = last.get("lifts", 0)
    if "raw" in todo:
        paint = Image.open(pp).convert("RGB")
        rgba = paint.convert("RGBA")
        rgba.putalpha(Image.fromarray((fal.birefnet(paint) * 255).astype(np.uint8)))
        glb, lifts = None, 0
        for seed in LIFT_SEEDS:
            try:
                glb = fal.trellis(rgba, seed, TEXTURE, SIMPLIFY, f"{tag} lift s{seed}")
            except BudgetExceeded:
                if glb is None:
                    raise
                break  # the retry refused: the first lift is kept, plate and all, rather than paid for and lost
            lifts += 1
            if not prop_mesh.on_plate(glb)[0]:
                break
        raw.write_bytes(glb)
        made("raw")
    b = raw.read_bytes()
    is_plate, ratio = prop_mesh.on_plate(b)
    dropped = last.get("loose_dropped")
    if "glb" in todo:
        fin, dropped = prop_mesh.finish(b, cut)
        out.write_bytes(fin)
        made("glb")
    return {"name": name, "what": p["what"], "height_m": p.get("height_m"), "surface": p.get("surface"),
            "model": out.name, "plate": bool(is_plate), "plate_ratio": ratio, "loose_dropped": dropped,
            "lifts": lifts}


def build(ep: Episode, picks: dict[str, dict]) -> dict[str, dict]:
    """Every picked prop of the given places made into a model (see the module docstring); per place the saved
    <episode>/props/<setting>/props.json: the built props and the skipped ones with why."""
    props, stamps, now = {}, {}, {}
    for sid, pk in picks.items():
        d = ep.out / "props" / sid
        d.mkdir(parents=True, exist_ok=True)
        view = fresh.digest(ep.out / "places" / sid / "shown.png")
        f = d / "stamps.json"
        old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        props[sid] = pk["props"]
        for name in set(old) - {p["name"] for p in props[sid]}:  # a prop no longer picked: its files go
            for _, suffix in RUNGS:
                (d / f"{name}{suffix}").unlink(missing_ok=True)
        stamps[sid] = {}
        for p in props[sid]:
            now[sid, p["name"]] = stamps_of(view, p)
            stamps[sid][p["name"]] = dict(old.get(p["name"]) or {})
            _todo(d, p["name"], stamps[sid][p["name"]], now[sid, p["name"]])
        f.write_text(json.dumps(stamps[sid], indent=1), encoding="utf-8")
    skipped: dict[str, list] = {sid: [] for sid in picks}
    need = [(sid, p) for sid, ps in props.items() for p in ps if "cut" not in stamps[sid][p["name"]]]
    if need:  # one SAM for the run, loaded only when a prop has no cut yet
        from sam import Segmenter
        seg = Segmenter()
        for sid, p in need:
            view = Image.open(ep.out / "places" / sid / "shown.png").convert("RGB")
            c, by = cut_of(seg, view, p["box"], [q for q in (p.get("noun"), p["what"], "object") if q])
            if c is None:
                skipped[sid].append({"name": p["name"], "why": "no SAM instance in its box"})
                print(f"  prop {sid}/{p['name']}: no SAM instance in its box, skipped")
                continue
            d = ep.out / "props" / sid
            c.save(d / f"{p['name']}-cut.png")
            _made(d, stamps[sid], p["name"], "cut", now[sid, p["name"]])
            print(f"  prop {sid}/{p['name']}: cut {c.size[0]} x {c.size[1]} by '{by}'")
        del seg
        import torch
        torch.cuda.empty_cache()
    out = {}
    for sid, ps in props.items():
        d = ep.out / "props" / sid
        f = d / "props.json"
        last = {e["name"]: e for e in json.loads(f.read_text(encoding="utf-8")).get("props", [])} if f.exists() else {}
        built = []
        for p in ps:
            name, nw = p["name"], now[sid, p["name"]]
            todo = _todo(d, name, stamps[sid][name], nw)
            if "cut" in todo:
                continue
            try:
                built.append(_finish(d, sid, p, todo, lambda r, name=name, nw=nw: _made(d, stamps[sid], name, r, nw),
                                     last.get(name, {})))
            except (BudgetExceeded, requests.RequestException, RuntimeError, TimeoutError) as e:
                # one prop failing stops none of the others: the cap, an offline run, a failed or refused call
                skipped[sid].append({"name": p["name"], "why": str(e)[:300]})
                print(f"  prop {sid}/{p['name']}: skipped, {str(e)[:300]}")
                continue
            print(f"  prop {sid}/{p['name']}: {built[-1]['model']}, plate {built[-1]['plate_ratio']}"
                  f"{' (PLATE)' if built[-1]['plate'] else ''}, {built[-1]['loose_dropped']} loose pieces dropped")
        out[sid] = {"setting": sid, "props": built, "skipped": skipped[sid]}
        (d / "props.json").write_text(json.dumps(out[sid], indent=1, ensure_ascii=False), encoding="utf-8")
    return out


def _say(sid: str, r: dict) -> None:
    print(f"  {sid}: {len(r['props'])}/{r['max']} props from {len(r['images'])} images, {r['cost']:.3f} USD: " +
          "; ".join(f"{p['name']} ({p['box'][2] - p['box'][0]} x {p['box'][3] - p['box'][1]} px, "
                    f"{p['height_m']} m, {p['surface']})" for p in r["props"]))
    if r.get("notes"):
        print(f"    notes: {r['notes']}")


def props_step(ep: Episode, only: list[str] | None = None) -> dict | None:
    """The pick for every built place (or only those given), then the build; per place its props.json."""
    st = settings.load(ep)
    if not clock.load(ep) or not st:
        print("  props: no clock or settings yet, skipped")
        return None
    fs = st.get("frame_setting") or {}
    secs = seconds_open(ep, fs)
    picks = {}
    for sid in only or [s for s in secs if places.built(ep.out / "places" / s)]:
        try:
            picks[sid] = pick(ep, sid, secs.get(sid, 0.0), fs)
        except (BudgetExceeded, Truncated) as e:  # the cap, an offline run, a reply cut off: the next run asks again
            print(f"  props {sid}: no pick, {e}")
            continue
        _say(sid, picks[sid])
    return build(ep, picks)


if __name__ == "__main__":
    from chapter import Chapter
    ch = Chapter(Path(sys.argv[1]))
    props_step(Episode(Path(sys.argv[2]), ch.stem), sys.argv[3:] or None)
