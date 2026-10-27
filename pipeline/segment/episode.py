"""The episode pipeline: box breakdown, segmentation (each task with its review), the erase, the flat layers, then
Understand. This script runs steps 2-5 on a chapter step 1 has cut.

    uv run python episode.py <episode.zumi> <out dir> [--panels 10-15 | --panels 3,7,9] [--no-review]
                             [--no-depth] [--no-layers] [--no-understand] [--from-masks]

1. Box breakdown. The chapter is cut into boxes by intake (pipeline/zumi/intake, `zumi intake`: the strip stitched,
   gutters scanned, one box per panel, packed as a .zumi). Within each box, its frames (frames.py: the art's connected
   pieces between gutters, split further by straight gutter cuts); depth is only ever estimated per frame. The
   frames are made right after 2a, since the gutter needs the lettering masks (box_frames).
2. Segmentation, one SAM 3.1 model for the run. Each task is found, then reviewed by the reasoning layer
   (review_loop.py, Claude Haiku 5.5, high reasoning: merge, split, improve, drop, missing, each change carried out
   by SAM on a zoomed crop and checked alone; boxes in parallel threads). On 221 held-out panels the review cut major
   errors by 56%, fixing 6-16 for each one it introduced (docs/research/reviewer-heldout-test-2026-10.md).
   a. lettering: bubbles.py, sound effects tightened by sfx_refine.py; reviewed.
   b. characters: characters.py; reviewed.
   c. objects: picked by scene_judge.choose_objects (Haiku, names, points and relations), masked by SAM
      (objects.py); reviewed (choose_box_objects).
3. Erase (band_erase.py): what the art hides behind characters, objects and lettering. The card interiors are
   prefilled with the frame's plain background colour, a band as wide as a head move uncovers is masked, and ONE
   FLUX Erase call per box paints it (BFL API, 0.034 USD a call, 2 USD/day cap); a result that is the model's
   placeholder is retried frame by frame. Its masks need the cards and their depth, so it runs between two passes
   of step 4 (erase_step).
4. Flat layers (cards.py): per frame the backdrop and one card per character and object, ordered by
   DA3MONO run on each frame alone, fixed steps between them; the lettering in front as cards of the original
   bubbles, placed by lettering_layer.py. The depth-based surface this replaced is legacy_mesh.py (--legacy-mesh).
5. Understand (understand.py, Llama 4 Maverick), last and optional: bubble text, kind and speaker in reading order,
   saved to understand.json; it feeds nothing in the 3D.

Writes out/masks/<episode>-pNNN-{lettering,characters,objects3}.*, out/understand.json, out/step1-strip.png,
out/sheets/<episode>-pNNN.png (panel | lettering | characters | Understand), out/parallax/plates/<episode>-pNNN/ and
out/parallax/mesh/<episode>-pNNN.* (cards, bubbles: the viewer's layout).
"""

from __future__ import annotations

import argparse
import io
import json
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import torch
from PIL import Image, ImageDraw

import bubbles as B
import characters as CH
import understand as U
from openrouter import BudgetExceeded, spent_today
from review_loop import El, review
from sfx_refine import refine_panel

REVIEW_MODEL, REVIEW_EFFORT = "anthropic/claude-haiku-5.5", "high"


def parse_panels(spec: str, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return [i for i in out if 0 <= i < n]


def strip_view(z, panels, picks) -> Image.Image:
    """The picked panels at their places in the episode strip, each boxed and numbered (step 1's cut)."""
    top = min(panels[i]["strip"]["y"] for i in picks) - 20
    bottom = max(panels[i]["strip"]["y"] + panels[i]["strip"]["h"] for i in picks) + 20
    w = max(panels[i]["size"]["w"] for i in picks)
    canvas = Image.new("RGB", (w + 120, bottom - top), (235, 235, 235))
    d = ImageDraw.Draw(canvas)
    for i in picks:
        p = panels[i]
        y = p["strip"]["y"] - top
        canvas.paste(Image.open(io.BytesIO(z.read(p["layers"][0]["image"]))).convert("RGB"), (0, y))
        d.rectangle([(0, y), (p["size"]["w"] - 1, y + p["size"]["h"] - 1)], outline=(220, 0, 0), width=4)
        d.text((w + 10, y + 10), f"panel {i}", fill=(220, 0, 0), font=U.font(22))
    return canvas


def sheet(img, letters, chars, understood, title) -> Image.Image:
    cols = [("1. panel", img), ("2. lettering", B.overlay(img, letters)),
            ("2. characters", CH.overlay(img, [CH.Char(c.mask, c.score, c.kind) for c in chars]))]
    if understood is not None:
        cols.append(("3. understand", understood))
    h = max(im.height for _, im in cols)
    out = Image.new("RGB", (sum(im.width + 20 for _, im in cols), h + 50), (255, 255, 255))
    d = ImageDraw.Draw(out)
    d.text((6, 4), title, fill=(0, 0, 0), font=U.font(16))
    x = 0
    for name, im in cols:
        out.paste(im, (x, 50))
        d.text((x + 6, 26), name, fill=(0, 0, 0), font=U.font(16))
        x += im.width + 20
    return out


OBJECTS_NPZ = "{pid}-objects3.npz"  # v3: the committee's rules (2026-10-26); kind = the object's name
OBJECTS_META = "{pid}-objects3.json"  # per mask, same order: name, on, held, front, except, animal


def load_box_objects(out_dir: Path, pid: str) -> list[dict]:
    """The saved objects of a box: [{"name", "mask", "on", "held", "front", "except", "animal"}]."""
    f = out_dir / "masks" / OBJECTS_NPZ.format(pid=pid)
    if not f.exists():
        return []
    ms = B.load_masks(f)
    mf = out_dir / "masks" / OBJECTS_META.format(pid=pid)
    # matched by name, not position: save_masks sorts the masks top to bottom, the metadata keeps the picker's order,
    # and paired by position P&C 39 p10's bottle took the table's "front" and the table the cup's "on"
    meta = {md["name"]: md for md in json.loads(mf.read_text(encoding="utf-8"))} if mf.exists() else {}
    return [{"name": m.kind, "mask": m.mask, **{k: v for k, v in meta.get(m.kind, {}).items() if k != "name"}} for m in ms]


def choose_box_objects(a, stem, picks, imgs, chars_u, proc=None, review_on=True) -> dict:
    """Every object in front of the backdrop per box (scene_judge, Haiku 5.5) masked by SAM 3.1 (objects.py), then
    reviewed like characters and lettering (review_loop, task "objects": merge, split, improve, drop, missing, each
    change carried out by SAM and checked alone), saved as out/masks/<box>-objects3.npz (+ .json) and reused on
    reruns. {box: union mask or None}. The first version listed big furniture only (it chose what to erase): the vase
    on ToG 228 p6's side table stayed painted on the backdrop."""
    import objects as OB
    from scene_judge import choose_objects
    out, todo = {}, {}
    for i in picks:
        f = a.out / "masks" / OBJECTS_NPZ.format(pid=f"{stem}-p{i:03d}")
        if f.exists():
            ms = B.load_masks(f)
            out[i] = np.logical_or.reduce([m.mask for m in ms]) if ms else None
            continue
        try:
            objs = choose_objects(imgs[i], chars_u[i], tag=f"{stem} p{i} objects")
        except BudgetExceeded as e:
            print(f"STOP objects: {e}")
            break
        per = []
        if objs:
            proc = proc or OB.load_processor()
            _, per = OB.masks_for_objects(proc, imgs[i], objs)
            per = [o for o in per if o.get("mask") is not None]
        todo[i] = per
    meta_keys = ("on", "held", "front", "except", "animal")

    def job(i):
        per = todo[i]
        if not per or not review_on or a.no_review:
            return i, per, None
        els = [El(o["mask"], o["name"], float(o.get("score", 1.0))) for o in per]
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            new, lg = review(proc, imgs[i], els, "objects", REVIEW_MODEL, REVIEW_EFFORT, f"{stem} p{i} objects")
        # each mask keeps its pick's name and relations; a mask the review added is a plain object; repeated names
        # (a split mask's parts) get a number, as the picker numbers repeats
        meta = {o["name"]: o for o in per}
        seen, kept = {}, []
        for e in new:
            base = e.kind if e.kind in meta else "object"
            seen[base] = seen.get(base, 0) + 1
            name = base if seen[base] == 1 else f"{base} {seen[base]}"
            kept.append({"name": name, "mask": e.mask, "score": e.score,
                         **{k: meta.get(base, {}).get(k) for k in meta_keys}})
        return i, kept, lg

    with ThreadPoolExecutor(8) as ex:
        for i, per, lg in ex.map(job, list(todo)):
            found = [B.Found(o["mask"], float(o.get("score", 1.0)), o["name"]) for o in per]
            B.save_masks(a.out / "masks" / OBJECTS_NPZ.format(pid=f"{stem}-p{i:03d}"), found)
            (a.out / "masks" / OBJECTS_META.format(pid=f"{stem}-p{i:03d}")).write_text(
                json.dumps([{"name": o["name"], **{k: o.get(k) for k in meta_keys}} for o in per], indent=1,
                           ensure_ascii=False), encoding="utf-8")
            out[i] = np.logical_or.reduce([m.mask for m in found]) if found else None
            fixes = f", review: {lg.applied}" if lg is not None and lg.applied else ""
            print(f"p{i}: objects {[o['name'] + (' @ ' + o['on'] if o.get('on') else '') + (' [held]' if o.get('held') else '') + (' [front]' if o.get('front') else '') for o in per] or 'none'}{fixes}")
    return out


FRAMES_NPZ = "{pid}-frames.npz"
_union = lambda els, shape: np.logical_or.reduce([e.mask for e in els]) if els else np.zeros(shape, bool)


def box_frames(a, stem, picks, imgs, letters) -> dict:
    """Step 1, frames within each box (frames.py), saved as out/masks/<box>-frames.npz. Made as soon as the lettering
    masks exist: the gutter needs them (a bubble touching the box edge is not page), and without them 8 of P&C 39's
    31 boxes got other frames (p8: a bubble in the gutter became a frame of its own)."""
    import frames as FR
    import parallax as PX
    out = {}
    for i in picks:
        L = _union(letters[i], (imgs[i].height, imgs[i].width))
        fr = [m for m in FR.frames(imgs[i], PX.gutter(imgs[i], L if L.any() else None)) if m.any()]
        B.save_masks(a.out / "masks" / FRAMES_NPZ.format(pid=f"{stem}-p{i:03d}"), [B.Found(m, 1.0, "frame") for m in fr])
        out[i] = fr
    print(f"frames per box: {[len(out[i]) for i in picks]}")
    return out


def load_frames(out_dir: Path, pid: str) -> list[np.ndarray] | None:
    f = out_dir / "masks" / FRAMES_NPZ.format(pid=pid)
    return [m.mask for m in B.load_masks(f)] if f.exists() else None


def erase_step(a, stem, picks, imgs, letters, chars, und=None) -> None:
    """Steps 3-4: the band erase (band_erase.py) between two passes of the flat layers. Its masks come from the
    cards (their outlines, and how far each slides at a head move, which needs their depth), so a first layers pass
    lays the cards out on the art; band_erase then paints what is behind them, ONE FLUX Erase call per box (a box
    whose result is the model's placeholder is retried frame by frame; paid results cached by mask, the BFL daily cap
    stops it cleanly); the second pass rebuilds the layers on its plates. The first pass costs ~5 s per box. It
    replaced hidden_layers.erase_boxes (every mask whole, two copies packed per call), kept for legacy_mesh.py."""
    import band_erase as BE
    print("  (first pass: the cards on the art)")
    layers_step(a, stem, picks, imgs, letters, chars, und)
    if a.no_layers:  # no paid erase: the layers stay on the art (or on band plates an earlier run paid for)
        return
    mesh = a.out / "parallax" / "mesh"
    jobs = [(f"{stem}-p{i:03d}", np.asarray(imgs[i]), json.loads((mesh / f"{stem}-p{i:03d}.cards.json").read_text()),
             mesh, a.out / "parallax" / "plates" / f"{stem}-p{i:03d}")
            for i in picks if (mesh / f"{stem}-p{i:03d}.cards.json").exists()]
    BE.erase_boxes(jobs, log=lambda s: print("  " + s.replace("\n", "\n  ")))  # boxes in parallel, budget-safe
    torch.cuda.empty_cache()
    print("  (second pass: the cards on the erased plates)")
    layers_step(a, stem, picks, imgs, letters, chars, und)


def layers_step(a, stem, picks, imgs, letters, chars, und=None) -> None:
    """Step 4, the flat layers of every box (cards.py): per frame of step 1 the backdrop and one card per character
    and object, ordered by DA3MONO on each frame alone, then the original bubbles as cards in front, placed by
    lettering_layer. The backdrop is the box's band-erase plate (step 3) when it has one, else the art itself;
    the depth model sees the box with its lettering filled in (band_erase.lettering_free)."""
    import band_erase as BE
    import cards as CD
    import depth as DP
    import lettering_layer as LL
    import parallax as PX
    from hidden_layers import GROW
    from scipy.ndimage import binary_dilation
    root = a.out / "parallax"
    und = und or {}
    # DA3MONO on each frame alone, for everything (user, 2026-10-26): it orders the cards and gives each frame's
    # backdrop distance. DA3METRIC per frame tied characters DA3MONO told apart and lost the figure on close-ups
    # (P&C 39 p24); on a wide street (p2) the two were close
    mono = DP.load()
    for i in picks:
        pid = f"{stem}-p{i:03d}"
        img = np.asarray(imgs[i])
        shape = img.shape[:2]
        let = _union(letters[i], shape)
        g = PX.gutter(imgs[i], let)
        fringe = PX.claim_fringe(imgs[i], _union(chars[i], shape), g)
        frames = load_frames(a.out, pid)
        lettering = binary_dilation(let, iterations=GROW) & ~g if let.any() else None
        base = BE.lettering_free(img, lettering, frames if frames else [~g]) if lettering is not None else None
        # the band erase paints behind every object too (each one a card); without its plate the objects stay
        # painted on the art
        bp = root / "plates" / pid / "band-plate.png"
        if bp.exists():
            backdrop = np.asarray(Image.open(bp).convert("RGB"))
            objects = load_box_objects(a.out, pid)
        else:
            backdrop = img
            objects = [] if a.no_layers else load_box_objects(a.out, pid)
        # depth is never estimated on a whole box, only on each frame alone, in one pass (user, 2026-10-26)
        info, D = CD.build(pid, img, [e.mask for e in chars[i]], objects, backdrop, g, None, root / "mesh", fringe,
                           lettering, depth_img=base, depth_fn=lambda r: DP.frame_infer(mono, r), frames=frames)
        print(f"  {pid} layers: {info}")
        # the viewer's "segmentation" view (its "depth" view is written by cards.build)
        CD.seg_view(img, [e.mask for e in chars[i]], [(o["name"], o["mask"]) for o in load_box_objects(a.out, pid)],
                    [e.mask for e in letters[i]], load_frames(a.out, pid) or [], root / "mesh" / f"{pid}.seg.png")
        if letters[i]:
            # placement (depth clear of the layers) from lettering_layer; what is drawn is the original bubble, cut
            # from the art (cards.add_lettering)
            bub = LL.build(pid, imgs[i], [e.mask for e in letters[i]], und.get(i), D,
                           root / "mesh" / f"{pid}.bubbles.json", kinds=[e.kind for e in letters[i]], valid=~g)
            print(f"  {pid} lettering cards: {CD.add_lettering(pid, img, [e.mask for e in letters[i]], bub, root / 'mesh')}")


def depth_and_layers(a, stem, picks, img_of, letters, chars, und=None, proc=None) -> dict:
    """Steps 2c-4 from saved masks (--from-masks): objects (saved, or picked and reviewed now), frames (saved, or made
    now), the erase, the flat layers. The depth-based surface they replaced: legacy_mesh.py (--legacy-mesh)."""
    if getattr(a, "legacy_mesh", False):
        import legacy_mesh
        return legacy_mesh.depth_and_layers(a, stem, picks, img_of, letters, chars, und, proc)
    times, imgs = {}, {i: img_of(i) for i in picks}
    t = time.perf_counter()
    choose_box_objects(a, stem, picks, imgs, {i: _union(chars[i], (imgs[i].height, imgs[i].width)) for i in picks}, proc)
    missing = [i for i in picks if load_frames(a.out, f"{stem}-p{i:03d}") is None]
    if missing:
        box_frames(a, stem, missing, imgs, letters)
    times["2c objects + 1 frames"] = time.perf_counter() - t
    t = time.perf_counter()
    erase_step(a, stem, picks, imgs, letters, chars, und)
    times["3 erase + 4 layers"] = time.perf_counter() - t
    return times


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", default="")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument("--no-depth", action="store_true", help="stop after step 2 (segmentation): no erase, no layers")
    ap.add_argument("--no-layers", action="store_true", help="skip step 3's paid erase (and the objects): layers on the "
                                                             "original art")
    ap.add_argument("--no-understand", action="store_true",
                    help="skip Understand (bubble text, kind, speaker, saved to understand.json): it feeds nothing in "
                         "the 3D, so test runs of the 3D do without it")
    ap.add_argument("--legacy-mesh", action="store_true",
                    help="steps 4-6 as the old depth-based surface (legacy_mesh.py) instead of flat layers")
    ap.add_argument("--from-masks", action="store_true",
                    help="reuse out/masks and out/understand.json from an earlier run: steps 4-6 only (no SAM, review "
                         "or Understand)")
    a = ap.parse_args()
    z = zipfile.ZipFile(a.zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    picks = parse_panels(a.panels, len(panels))
    stem = a.zumi.stem
    img_of = lambda i: Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
    for d in ("masks", "sheets"):
        (a.out / d).mkdir(parents=True, exist_ok=True)
    times = {}
    if a.from_masks:
        letters, chars = {}, {}
        for i in picks:
            pre = a.out / "masks" / f"{stem}-p{i:03d}"
            if not (pre.parent / f"{pre.name}-lettering.npz").exists():
                print(f"p{i}: no saved masks, skipped")
                continue
            letters[i] = [El(f.mask, f.kind, f.score) for f in B.load_masks(pre.parent / f"{pre.name}-lettering.npz")]
            chars[i] = [El(f.mask, f.kind, f.score) for f in B.load_masks(pre.parent / f"{pre.name}-characters.npz")]
        picks = [i for i in picks if i in letters]
        prev = json.loads((a.out / "understand.json").read_text(encoding="utf-8")) if (a.out / "understand.json").exists() else {}
        und = {int(k): v for k, v in prev.get("panels", {}).items()}
        times.update(depth_and_layers(a, stem, picks, img_of, letters, chars, und))
        prev.setdefault("times_s", {}).update({k: round(v, 1) for k, v in times.items()})
        (a.out / "understand.json").write_text(json.dumps(prev, indent=1, ensure_ascii=False, default=str))
        print({k: round(v, 1) for k, v in times.items()})
        return
    imgs = {i: img_of(i) for i in picks}
    shape = lambda i: (imgs[i].height, imgs[i].width)
    log, cast, transcript, results, pictures = {}, [], [], {}, {}

    def save_understand():
        (a.out / "understand.json").write_text(json.dumps({"cast": cast, "panels": results, "review": log,
                                                           "times_s": {k: round(v, 1) for k, v in times.items()}},
                                                          indent=1, ensure_ascii=False, default=str))

    def reviewed(task, els_by_box):  # a segmentation task's review: every box in parallel threads
        if a.no_review:
            return els_by_box

        def job(i):
            with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
                new, lg = review(proc, imgs[i], els_by_box[i], task, REVIEW_MODEL, REVIEW_EFFORT, f"{stem} p{i} {task}")
            return i, new, lg

        out = {}
        with ThreadPoolExecutor(8) as ex:
            for i, new, lg in ex.map(job, picks):
                out[i] = new
                log[f"p{i} {task}"] = {"applied": lg.applied, "cost": lg.cost}
        return out

    # 1. box breakdown: the boxes come cut by intake; their frames follow as soon as the lettering exists (2a)
    print(f"== 1 box breakdown: {len(picks)} boxes from intake ({a.zumi.name})")
    strip_view(z, panels, picks).save(a.out / "step1-strip.png")

    # 2. segmentation, each task with its review
    proc = CH.Sam3Processor(CH.build_sam3_image_model(checkpoint_path=str(B.CKPT), load_from_HF=False), confidence_threshold=0.3)
    print("== 2a lettering")
    t = time.perf_counter()
    bank = B.Bank(B.BANK, a.zumi.parent)
    letters = {}
    for i in picks:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            letters[i] = [El(f.mask, f.kind, f.score) for f in refine_panel(proc, imgs[i], B.segment(proc, imgs[i], bank, stem, i))]
    letters = reviewed("lettering", letters)
    times["2a lettering"] = time.perf_counter() - t
    print("== 1 frames (they need the lettering)")
    t = time.perf_counter()
    box_frames(a, stem, picks, imgs, letters)
    times["1 frames"] = time.perf_counter() - t
    print("== 2b characters")
    t = time.perf_counter()
    chars = {}
    for i in picks:
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            chars[i] = [El(c.mask, c.kind, c.score) for c in CH.segment(proc, imgs[i])]
    chars = reviewed("characters", chars)
    times["2b characters"] = time.perf_counter() - t
    for i in picks:  # saved before the paid and slow steps: a crash there must not lose them
        B.save_masks(a.out / "masks" / f"{stem}-p{i:03d}-lettering.npz", [B.Found(e.mask, e.score, e.kind) for e in letters[i]])
        B.save_masks(a.out / "masks" / f"{stem}-p{i:03d}-characters.npz", [B.Found(e.mask, e.score, e.kind) for e in chars[i]])
    if not a.no_depth and not a.no_layers:
        print("== 2c objects")
        t = time.perf_counter()
        choose_box_objects(a, stem, picks, imgs, {i: _union(chars[i], shape(i)) for i in picks}, proc)
        times["2c objects"] = time.perf_counter() - t
    del proc
    torch.cuda.empty_cache()
    save_understand()

    if not a.no_depth:
        # 3-4. the band erase between two passes of the flat layers (erase_step); the legacy path erases its own way
        print("== 3 erase + 4 flat layers")
        t = time.perf_counter()
        if getattr(a, "legacy_mesh", False):
            import legacy_mesh
            times.update(legacy_mesh.depth_and_layers(a, stem, picks, img_of, letters, chars, {}, None))
        else:
            erase_step(a, stem, picks, imgs, letters, chars)
        times["3 erase + 4 layers"] = time.perf_counter() - t
        save_understand()

    # 5. Understand, last and optional: data only (understand.json), it feeds nothing in the 3D
    print("== 5 understand" + (" (skipped)" if a.no_understand else ""))
    t = time.perf_counter()
    try:
        for i in picks:
            found = [B.Found(e.mask, e.score, e.kind) for e in letters[i]]
            if not found or a.no_understand:
                continue
            img = imgs[i]
            prev = img_of(i - 1) if i > 0 else None
            result, usage, tails = U.understand(U.MODELS[0], img, [f.mask for f in found], [f.kind for f in found], cast,
                                                transcript, i, f"{stem} p{i}", previous=prev)
            known = {c["id"] for c in cast}
            cast += [c for c in result.get("new_cast", []) if c.get("id") and c["id"] not in known]
            for upd in result.get("names", []):
                for c in cast:
                    if c["id"] == upd.get("id") and upd.get("name"):
                        c["name"] = upd["name"]
            names = {c["id"]: c.get("name") or c["id"] for c in cast}
            for e in result.get("elements", []):
                if e.get("keep") and e.get("text") and e.get("kind") != "sfx":
                    transcript.append(f'p{i} {names.get(e.get("speaker"), e.get("speaker"))}: {e["text"]}')
            results[i] = result
            pictures[i] = U.report(img, [f.mask for f in found], tails, result, f"{stem} p{i}")
    except BudgetExceeded as e:
        print(f"STOP: {e}")
    times["5 understand"] = time.perf_counter() - t

    for i in picks:
        sheet(imgs[i], [B.Found(e.mask, e.score, e.kind) for e in letters[i]], chars[i], pictures.get(i),
              f"{stem} panel {i}").save(a.out / "sheets" / f"{stem}-p{i:03d}.png")
    save_understand()
    print({k: round(v, 1) for k, v in times.items()}, f"spent today {spent_today():.3f} USD")


if __name__ == "__main__":
    main()
