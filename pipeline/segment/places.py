"""Step 10c, places: a setting's surroundings shown through the reader's walls (CONTEXT.md: Place; rule agreed
2026-11-08). Which settings earn a place and which place each moment shows, then each earned place built:

1. The wide view, in two calls (bfl.py), as the user's reference tavern was made (2026-11-08): a plain 16:9 view of
   the setting on FLUX.2 [klein] 4B at about 1 MP from its record (view_prompt) and up to REFS of the episode's boxes that
   show it (scene_refs), view16.png; then the 2:1 panorama on FLUX 3 continuing that view around the seat
   (pano_prompt), with the 16:9 view as its first reference, view.png. (Nano Banana 2.1 was tried for both: sharper,
   loose with its reference; the user kept FLUX 3 for the panorama.) With only comic boxes to go on, one call painted spans of 115-324 degrees;
   anchored on a normal view, 124-184.
2. Its geometry, on the local GPU (place_geometry.py in pipeline/.venv-moge), in three stages: depth (the view's span
   measured and MoGe-3's distance per pixel), show (the part of the view a place shows, shown.png, and the near
   objects' mask for the erase) and front (front.glb, cut at depth edges).
3. The erase: one FLUX Erase call (bfl.py) takes the near objects out of the view at about 1 MP. plate.png.
4. The back layer (place_geometry.py back): the surface behind the near objects, textured with the plate regraded to
   the view's colour; the reader shows it through the front mesh's gaps. back.glb.

Each stage is skipped when its output is current (fresh.py): the 16:9 view by a stamp of its prompt, references,
model and size, the panorama by its prompt, the 16:9 view's content, its reference, model, aspect and resolution
(place.json "stamp16", "stamp"); the plate by the image erased, its mask, ERASE_MP and the erase's dilation
(place.json "stamp_plate"). The geometry's four stamps (<place>/stamps.json) each cover the stage before and only
the constants of place_geometry.py that shape their own files (place_geometry.SHAPES): depth by the view, show by
the depth, the front mesh by show, the back mesh by show and the plate. So a change to the meshes alone (a thinning
tolerance, the material) builds meshes and nothing else: MoGe does not run, shown.png and erase-mask.png keep their
bytes and the paid erase stays current (one stamp covered depth, window and front mesh until 2026-11-15, and such a
change cost every place's erase again). Both paid calls go through the shared daily cap (spend.paid_map): a refused
call stops that place at that stage, and a later run picks it up.

The rule (plan) works on visits, the maximal runs of frames in one setting on the episode clock; a swap costs a fade
out and a fade in (about 2 s), so a place is earned by a stay, not by a setting's total screen time:

1. A visit earns its place if it lasts MIN_STAY_S or more (the swap is then at most ~29 % of the stay).
2. The final visit runs on through the credits: a last visit followed only by time with no setting counts that time.
3. A visit too short to earn its place keeps the open place when it is that place (a short return never swaps away);
   otherwise it shows the next earned place if that place begins within LEAD_S of the visit's end (an arrival opens
   the place it leads into), else the place already open; it never swaps on its own.
4. A setting is built only if at least one of its visits earns it.

Every threshold is a duration: nothing is read from what a scene shows.

    python places.py <chapter.zumi> <episode out dir> [--plan]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import clock
import place_geometry
import settings
import fresh
from boxstore import Episode
from spend import paid_map

ROOT = Path(__file__).resolve().parents[1]  # pipeline/
MOGE_PYTHON = Path(os.environ.get("ZUMI_MOGE_PYTHON") or ROOT / ".venv-moge/Scripts/python.exe")
GEOMETRY = Path(__file__).with_name("place_geometry.py")
MIN_STAY_S = 7.0  # 15 until 2026-11-09: the user wanted a 7.6 s arrival in the village to open its place
LEAD_S = 10.0
FADE_S = 1.0            # each half of a swap: the open place fades out, then the next fades in
REFS = 2                # boxes sent with the wide view's prompt
VIEW_MODEL, VIEW_SIZE = "flux-2-klein-4b", (1344, 768)  # the plain 16:9 view on FLUX.2 [klein] 4B, the cheapest, at
                                                       # ~1 MP: it is only the panorama's anchor (user, 2026-11-08)
ASPECT, RESOLUTION = "2:1", "1.5k"                  # the panorama on FLUX 3; 4k: 60.7 credits, not 7
PANO_MODEL = "flux-3-image"  # the endpoint bfl.flux3 calls (it takes no model argument), named here for the stamp
PLACE_WORKERS = 2       # places generated at once (each is two calls in a row); BFL caps a low-credit account at one
                        # task in flight and answers 429, which bfl.py backs off from
ERASE_MP = 1024 * 1024  # FLUX Erase's working size, in pixels


def visits(panels: list[dict], frame_setting: dict[str, str]) -> list[dict]:
    """The episode's visits in time order: [{"setting": id or None, "start", "end"}], consecutive frames in one
    setting joined; a frame is on screen as clock.times says (until the next frame of its panel starts)."""
    spans = sorted((t0, t1, frame_setting.get(fid)) for fid, (t0, t1) in clock.times(panels).items() if "/f" in fid)
    out: list[dict] = []
    for t0, t1, s in spans:
        if out and out[-1]["setting"] == s:
            out[-1]["end"] = max(out[-1]["end"], t1)
        else:
            out.append({"setting": s, "start": t0, "end": t1})
    return out


def plan(clk: dict, frame_setting: dict[str, str]) -> dict:
    """{"places": the settings to build, "visits": each visit with "shows" (the place open during it, or None)
    and "why"}, from the clock ({"duration", "panels"}) and {frame id: setting id} (settings.json's frame_setting)."""
    vs = visits(clk["panels"], frame_setting)
    end = clk.get("duration") or (vs[-1]["end"] if vs else 0.0)
    last = max((i for i, v in enumerate(vs) if v["setting"]), default=None)
    for i, v in enumerate(vs):
        stay = v["end"] - v["start"]
        if i == last and all(w["setting"] is None for w in vs[i + 1:]):
            stay = end - v["start"]                                     # rule 2: on through the credits
            v["stay"] = round(stay, 2)
        v["earns"] = bool(v["setting"]) and stay >= MIN_STAY_S          # rule 1
    current = None
    for i, v in enumerate(vs):
        if v["earns"]:
            v["shows"], v["why"] = v["setting"], "earned" + (" (with the credits)" if "stay" in v else "")
            current = v["setting"]
            continue
        nxt = next((w for w in vs[i + 1:] if w["earns"]), None)
        if v["setting"] and v["setting"] == current:                   # rule 3: a short return keeps its place
            v["shows"], v["why"] = current, "a short return to the open place"
        elif v["setting"] and nxt and nxt["start"] - v["end"] <= LEAD_S:  # an arrival opens the next place
            v["shows"], v["why"] = nxt["setting"], f"leads into {nxt['setting']} {nxt['start'] - v['end']:.1f} s later"
        else:
            v["shows"], v["why"] = current, "keeps the open place" if current else "nothing open"
    places = sorted({v["setting"] for v in vs if v["earns"]}, key=lambda s: next(v["start"] for v in vs if v["setting"] == s))
    return {"min_stay_s": MIN_STAY_S, "lead_s": LEAD_S, "duration": end, "places": places, "visits": vs}


def shows(pl: dict) -> list[dict]:
    """The plan as the reader plays it: [{"start", "end", "setting"}], consecutive visits showing one place joined, the
    last one on to the episode's end; time with no place open is left out."""
    out: list[dict] = []
    for v in pl["visits"]:
        if v["shows"] is None:
            continue
        if out and out[-1]["setting"] == v["shows"]:
            out[-1]["end"] = v["end"]
        else:
            out.append({"start": v["start"], "end": v["end"], "setting": v["shows"]})
    if out:
        out[-1]["end"] = pl["duration"]
    return [{**s, "start": round(s["start"], 2), "end": round(s["end"], 2)} for s in out]


# the portals open on the walls and ceiling, not the floor: anything standing close to the seat comes out large and low
# and is cut where the walls meet the floor (the terrace's table and chairs, 2026-11-09). Naming what to keep away
# ("furniture ... farther away") made FLUX paint furniture into the sky and the vision: say only the distance.
NEAR = "Nothing is close to the viewer: the nearest part of the place begins a few metres away."
TAIL = ("Empty of people, creatures and animals. No text, no letters, no speech balloons, no panel borders. The same "
        "hand-painted comic style, palette, line work and lighting as the reference images.")


def _what(s: dict) -> str:
    """A setting's record (settings.json: name, description, time of day, weather) as a sentence or two."""
    when = ", ".join(x for x in (s.get("time_of_day"), s.get("weather")) if x)
    return f"{s['name']}. {s.get('description', '')} {('Time and weather: ' + when + '.') if when else ''}".strip()


def view_prompt(s: dict) -> str:
    """The plain 16:9 view: the place filling the image from a seat in it (asked "as if seen through a large opening in
    a wall", FLUX painted the wall's frame)."""
    return (f"A wide view of this place from the comic shown in the reference images, seen from a seat in it at a "
            f"seated person's eye level, the place filling the whole image: no window, doorway, frame or border around "
            f"the view. {_what(s)} {NEAR} {TAIL}")


def pano_prompt(s: dict) -> str:
    """The 2:1 panorama continuing the 16:9 view (the first reference) around the seat, about 180 degrees (not a 360
    equirectangular, which FLUX does not paint)."""
    return (f"A wide panorama, 2:1, about 180 degrees across, of the place shown in the first reference image: the same "
            f"place in the same style, seen from the same seat, with that image's view in the middle, continuing to the "
            f"left, to the right and up to the sky or ceiling around the viewer, with no frame or border. {_what(s)} "
            f"Vertical lines stay vertical. {NEAR} {TAIL}")


def scene_refs(clk: dict, frame_setting: dict[str, str], setting: str, n: int = REFS) -> list[int]:
    """Up to n box indices that show the setting: the boxes all of whose frames are in it first, then boxes with any
    frame in it; fewest balloons first in each group."""
    whole, part = [], []
    for p in clk["panels"]:
        ss = [frame_setting.get(f"{p['id']}/f{f['index']}") for f in p["frames"]]
        if ss and all(s == setting for s in ss):
            whole.append((len(p["bubbles"]), p["index"]))
        elif setting in ss:
            part.append((len(p["bubbles"]), p["index"]))
    return ([i for _, i in sorted(whole)] + [i for _, i in sorted(part)])[:n]


def _lin(a: np.ndarray) -> np.ndarray:
    return np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4)


def _hex(c: np.ndarray) -> str:
    """A linear colour as an sRGB light colour: its brightest channel at full."""
    c = np.clip(c / max(float(c.max()), 1e-6), 0, 1)
    s = np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)
    return "#" + "".join(f"{round(255 * v):02x}" for v in s)


def light(d: Path, indoor: bool | None) -> dict:
    """How the place lights the reader's room (the format's placeLight), from its shown view (shown.png, the span in
    geometry.json): ambient = the mean colours of the top, middle and bottom thirds; key = the connected region of
    the brightest 1 % of pixels holding the most light (its centroid's direction, its colour, how far the brightest
    pixels stand out from the median); room = the grade of the
    real room (brightness from the view's mean luminance against mid-grey, tint and its strength from its mean
    colour); occlusion by indoor or not. No model, a few milliseconds."""
    g = _read(d / "geometry.json")
    img = Image.open(d / "shown.png").convert("RGB")
    img = img.resize((480, max(1, round(480 * img.height / img.width))))
    a = _lin(np.asarray(img, np.float64) / 255)
    h = a.shape[0]
    lum = a @ np.array([0.2126, 0.7152, 0.0722])
    thirds = [a[: h // 3], a[h // 3: 2 * h // 3], a[2 * h // 3:]]
    p99, med = np.percentile(lum, 99), np.median(lum)
    from scipy.ndimage import binary_dilation, label
    blobs, n = label(binary_dilation(lum >= p99, iterations=2))  # the bright pixels, as regions
    best = max(range(1, n + 1), key=lambda k: lum[(blobs == k) & (lum >= p99)].sum())  # the region with most light
    ys, xs = np.nonzero((blobs == best) & (lum >= p99))   # its centroid, not all bright pixels' (that lands mid-view)
    w = lum[ys, xs]
    cx, cy = float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum())
    mean = a.reshape(-1, 3).mean(0)
    mean_lum = float(lum.mean())
    return {
        "ambient": {"sky": _hex(thirds[0].reshape(-1, 3).mean(0)), "horizon": _hex(thirds[1].reshape(-1, 3).mean(0)),
                    "ground": _hex(thirds[2].reshape(-1, 3).mean(0))},
        "key": {"yaw": round((cx / a.shape[1] - 0.5) * g["h_deg"], 1), "pitch": round((0.5 - cy / h) * g["v_deg"], 1),
                "color": _hex(a[ys, xs].mean(0)), "strength": round(float(np.clip((p99 - med) / (p99 + 1e-6), 0, 1)), 3)},
        "room": {"brightness": round(float(np.clip(np.log2(mean_lum / 0.18) / 3, -0.6, 0.15)), 3), "tint": _hex(mean),
                 "tintStrength": round(float(np.clip(1 - mean.min() / max(mean.max(), 1e-6), 0, 1)) * 0.6, 3)},
        "occlusion": 0.5 if indoor else 0.3,
    }


def kept_refs(clk: dict, frame_setting: dict[str, str], setting: str, panel_ids: list[str]) -> list[int]:
    """The box indices of a place's earlier references (place.json "refs", panel ids) while any one still has a frame
    in the setting, else []: a re-read of the settings that keeps the place (settings.keep_ids) keeps what it was
    painted from, and it is painted again only when none of them shows it any more."""
    index = {p["id"]: p["index"] for p in clk["panels"]}
    shows = {p["id"] for p in clk["panels"]
             if any(frame_setting.get(f"{p['id']}/f{f['index']}") == setting for f in p["frames"])}
    return [index[i] for i in panel_ids if i in index] if any(i in shows for i in panel_ids) else []


def view16_stamp(s: dict, refs: list[int]) -> str:
    """The 16:9 view's stamp (place.json "stamp16"): its prompt, the boxes it is painted from, model and size."""
    return fresh.digest(view_prompt(s), refs, VIEW_MODEL, VIEW_SIZE)


def pano_stamp(s: dict, refs: list[int], d: Path) -> str:
    """The panorama's stamp (place.json "stamp"): its prompt, the 16:9 view by content, its reference box, the model,
    aspect and resolution."""
    return fresh.digest(pano_prompt(s), fresh.digest(d / "view16.png"), refs[:1], PANO_MODEL, ASPECT, RESOLUTION)


GEOMETRY_FILES = {  # each geometry stage's files (place_geometry.py), in the order the stages run
    "depth": ("depth.json", "distance-full.npy"),
    "show": ("shown.png", "distance.npy", "erase-mask.png", "geometry.json"),
    "front": ("front.glb",),
    "back": ("back.glb",),
}


def geometry_stamp(stage: str, d: Path) -> str:
    """A geometry stage's stamp (<place>/stamps.json): what it is made from and the constants that shape its own
    files. depth: the view; show: the depth; front: show; back: show and the plate."""
    own = place_geometry.recipe(stage)
    if stage == "depth":
        return fresh.digest(d / "view.png", own)
    if stage == "show":
        return fresh.digest(geometry_stamp("depth", d), own)
    if stage == "front":
        return fresh.digest(geometry_stamp("show", d), own)
    return fresh.digest(geometry_stamp("show", d), d / "plate.png", own)


def geometry_current(stage: str, d: Path) -> bool:
    """The stage's files are there and its saved stamp is today's."""
    return fresh.Stamps(d / "stamps.json").current(stage, geometry_stamp(stage, d),
                                                   *(d / f for f in GEOMETRY_FILES[stage]))


def plate_stamp(d: Path) -> str:
    """The plate's stamp (place.json "stamp_plate"): the image erased, its mask and the erase's recipe."""
    from bfl import DILATE
    return fresh.digest(d / "shown.png", d / "erase-mask.png", ERASE_MP, DILATE)


def _read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _write(path: Path, d: dict) -> None:
    path.write_text(json.dumps(d, indent=1), encoding="utf-8")


def geometry(stage: str, d: Path) -> dict:
    """place_geometry.py <stage> on a place folder, in MoGe's environment, and its stamp saved; its summary."""
    r = subprocess.run([str(MOGE_PYTHON), str(GEOMETRY), stage, str(d)], capture_output=True, text=True,
                       encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    if r.returncode:
        raise RuntimeError(f"place_geometry {stage} {d.name}: {r.stderr.strip()[-800:]}")
    fresh.Stamps(d / "stamps.json").made(stage, geometry_stamp(stage, d))
    return json.loads(r.stdout.strip().splitlines()[-1])


def erase(d: Path) -> Image.Image:
    """The part of the view a place shows (shown.png) with its near objects taken out (FLUX Erase at about ERASE_MP),
    back at its size."""
    from bfl import flux_erase
    img = Image.open(d / "shown.png").convert("RGB")
    w, h = img.size
    s = (ERASE_MP / (w * h)) ** 0.5
    W, H = round(w * s / 16) * 16, round(h * s / 16) * 16
    mask = Image.open(d / "erase-mask.png").convert("L").resize((W, H), Image.NEAREST)
    out, _, _ = flux_erase(img.resize((W, H), Image.LANCZOS), mask, tag=f"place {d.name} back")
    return out.resize((w, h), Image.LANCZOS)


def built(d: Path) -> bool:
    """A place is built when its geometry's stamps hold, each stage made from the one before: the depth from its
    current view, the back from its current plate."""
    if not all((d / f).exists() for f in ("view.png", "plate.png")):
        return False
    return all(geometry_current(stage, d) for stage in GEOMETRY_FILES)


def places_step(ep: Episode, ch) -> dict | None:
    """The plan, saved as <episode>/places/plan.json, and every earned place built in <episode>/places/<setting>/
    (view.png, front.glb, erase-mask.png, plate.png, back.glb, geometry.json, place.json). Returns the plan with each
    place's state (built, stopped by the cap, incomplete)."""
    clk, st = clock.load(ep), settings.load(ep)
    if not clk or not st:
        print("  places: no clock or settings yet, skipped")
        return None
    fs = st.get("frame_setting") or {}
    pl = plan(clk, fs)
    root = ep.out / "places"
    root.mkdir(parents=True, exist_ok=True)
    record = {s["id"]: s for s in st["settings"]}

    def view(sid: str) -> bool:
        from bfl import flux2, flux3
        d = root / sid
        d.mkdir(exist_ok=True)
        meta = _read(d / "place.json")
        refs = kept_refs(clk, fs, sid, meta.get("refs") or []) or scene_refs(clk, fs, sid)
        paid = False
        p16 = view_prompt(record[sid])
        s16 = view16_stamp(record[sid], refs)
        if meta.get("stamp16") != s16 or not (d / "view16.png").exists():
            boxes = [ch.image(i) for i in refs]
            img, credits = flux2(p16, boxes, *VIEW_SIZE, model=VIEW_MODEL, tag=f"place {sid} view16")
            img.save(d / "view16.png")
            meta = {"setting": sid, "stamp16": s16, "view_prompt": p16, "refs": [clock.panel_id(i) for i in refs],
                    "credits16": credits}
            _write(d / "place.json", meta)
            paid = True
        pp = pano_prompt(record[sid])
        stamp = pano_stamp(record[sid], refs, d)
        if meta.get("stamp") != stamp or not (d / "view.png").exists():
            img, credits = flux3(pp, [Image.open(d / "view16.png").convert("RGB")] + [ch.image(i) for i in refs[:1]],
                                 ASPECT, RESOLUTION, tag=f"place {sid} view")
            img.save(d / "view.png")
            _write(d / "place.json", {**meta, "stamp": stamp, "pano_prompt": pp, "credits": credits, "size": img.size})
            paid = True
        return paid

    made, stopped = paid_map(view, pl["places"], PLACE_WORKERS)
    ready = [s for s in pl["places"] if s not in stopped and (root / s / "view.png").exists()]
    if ready and not MOGE_PYTHON.exists():
        print(f"  places: no MoGe environment at {MOGE_PYTHON} (ZUMI_MOGE_PYTHON), geometry skipped")
        ready = []
    for sid in ready:  # one at a time: the depth stage loads MoGe-3 on the GPU
        d = root / sid
        for stage in ("depth", "show", "front"):  # in order: a stage made again makes the next ones stale
            if not geometry_current(stage, d):
                g = geometry(stage, d)
                print(f"  place {sid}: " + ("depth by MoGe, the view {} x {} deg".format(*g["view_deg"])
                                           if stage == "depth" else
                                           f"shown {g['h_deg']} x {g['v_deg']} deg and the erase's mask"
                                           if stage == "show" else f"front {g['front']['faces']} faces"))

    def plate(sid: str) -> bool:
        d = root / sid
        if _read(d / "place.json").get("stamp_plate") == plate_stamp(d) and (d / "plate.png").exists():
            return False
        erase(d).save(d / "plate.png")
        _write(d / "place.json", {**_read(d / "place.json"), "stamp_plate": plate_stamp(d)})
        return True

    erased, stopped_erase = paid_map(plate, ready)
    for sid in ready:
        d = root / sid
        if sid in stopped_erase or not (d / "plate.png").exists() or geometry_current("back", d):
            continue
        g = geometry("back", d)
        print(f"  place {sid}: back {g['back']['faces']} faces")
    for sid in ready:  # the place's light on the reader's room, measured from its shown view (free)
        d = root / sid
        if (d / "shown.png").exists():
            _write(d / "light.json", light(d, record[sid].get("indoor")))
    pl["state"] = {s: "built" if built(root / s) else "stopped" if s in stopped or s in stopped_erase else "incomplete"
                   for s in pl["places"]}
    _write(root / "plan.json", pl)
    print(f"  places: {', '.join(f'{s} {v}' for s, v in pl['state'].items()) or 'none earned'}; "
          f"{sum(made.values())} places' views and {sum(erased.values())} erases paid this run")
    return pl


def into(man: dict, ep: Episode, clk: dict, frame_setting: dict[str, str], added: dict[str, bytes]) -> None:
    """The built places into an export: each place's two meshes at episode/places/<setting>/{front,back}.glb, and
    episode.places: the meshes with their span and how far the place is in the meshes' own units (what a reader
    scales it to its room by), the timeline of which place shows when (planned on the export's own clock, which
    follows the voice backend), and the fade."""
    pl = plan(clk, frame_setting)
    meshes = []
    for sid in pl["places"]:
        d = ep.out / "places" / sid
        if not built(d):
            continue
        g = _read(d / "geometry.json")
        entry = {"setting": sid, "hDeg": g["h_deg"], "vDeg": g["v_deg"],
                 "nearM": g["near_m"], "medianM": g["median_m"], "farM": g["far_m"]}
        if (d / "light.json").exists():
            entry["light"] = _read(d / "light.json")
        for part in ("front", "back"):
            entry[part] = f"episode/places/{sid}/{part}.glb"
            added[entry[part]] = (d / f"{part}.glb").read_bytes()
        meshes.append(entry)
    if meshes:
        have = {m["setting"] for m in meshes}
        man["episode"]["places"] = {"fade": FADE_S, "meshes": meshes,
                                    "timeline": [s for s in shows(pl) if s["setting"] in have]}


if __name__ == "__main__":
    from chapter import Chapter
    ch = Chapter(Path(sys.argv[1]))
    ep = Episode(Path(sys.argv[2]), ch.stem)
    if "--plan" in sys.argv:
        pl = plan(clock.load(ep), settings.load(ep).get("frame_setting") or {})
        print("places to build:", ", ".join(pl["places"]))
        for v in pl["visits"]:
            print(f"  {v['start']:6.1f}-{v['end']:6.1f}  {str(v['setting']):16s} -> {str(v['shows']):14s} {v['why']}")
    else:
        places_step(ep, ch)
