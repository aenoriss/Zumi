"""The episode pipeline: box breakdown, segmentation (each task with its review), the erase, the flat layers, then
Understand. This script runs steps 2-5 on a chapter step 1 has cut; each step is a function of its own inputs, and
steps hand data to each other through what they save (boxstore.Box).

    uv run python episode.py <episode.zumi> <out dir> [--panels 10-15 | --panels 3,7,9] [--no-review]
                             [--no-depth] [--no-layers] [--no-understand] [--from-masks]

1. Box breakdown. The chapter is cut into boxes by intake (pipeline/zumi/intake, `zumi intake`: the strip stitched,
   gutters scanned, one box per panel, packed as a .zumi). Within each box, its frames and the page around them
   (frames_step: Claude Sonnet 5.5 panel boxes, about 0.0043 USD a box, cached; frames.split); depth is only ever
   estimated per frame. The frames are made right after 2a, since the page needs the lettering masks.
2. Segmentation, one SAM 3.1 model for the run (sam.Segmenter). Each task is found, then reviewed by the reasoning
   layer (review_loop.py, Claude Haiku 5.5, high reasoning: merge, split, improve, drop, missing, each change carried
   out by SAM on a zoomed crop and checked alone; boxes in parallel threads). On 221 held-out panels the review cut
   major errors by 56%, fixing 6-16 for each one it introduced (docs/research/reviewer-heldout-test-2026-10.md).
   a. lettering: bubbles.py, sound effects tightened by sfx_refine.py; reviewed.
   b. characters: characters.py; reviewed.
   c. objects (objects_step): picked by scene_judge.choose_objects (Haiku, names, points and relations), masked by
      SAM (objects.py); reviewed. Only with the erase: an object is cut out of the backdrop.
3. Erase (band_erase.py): what the art hides behind characters, objects and lettering. The card interiors are
   prefilled with the frame's plain background colour, a band as wide as a head move uncovers is masked, and ONE
   FLUX Erase call per box paints it (BFL API, 0.034 USD a call, 2 USD/day cap); a result that is the model's
   placeholder is retried frame by frame. Its masks need the cards and their depth, so it runs between two passes
   of step 4 (erase_step).
4. Flat layers (cards.layers): per frame the backdrop and one card per character and object, ordered by DA3MONO run
   on each frame alone, fixed steps between them; the lettering in front as cards of the original bubbles, placed
   by lettering_layer.py.
5. Understand (understand.Reader, Llama 4 Maverick), last and optional: bubble text, kind and speaker in reading
   order, saved to understand.json and joined into the layers' bubbles.json (the export's bubble text and speakers);
   it moves nothing in the 3D. A fresh segmentation drops the old results of its boxes (their ids changed).

Writes what boxstore.py lists (masks, frames and page, objects, layers, plates, understand.json), out/run.json (each
review's fixes and cost, each step's time), out/step1-strip.png and out/sheets/<episode>-pNNN.png (panel |
lettering | characters | Understand).
"""

from __future__ import annotations

import argparse
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import bubbles as B
import characters as CH
import understand as U
from boxstore import OBJECT_META_KEYS, Episode
from chapter import Chapter
from masks import Found, top_order, union
from openrouter import BudgetExceeded, Truncated, spent_today
from review_loop import review
from sam import Segmenter
from sfx_refine import refine_panel

Imgs = dict[int, Image.Image]  # box index -> box image
Masks = dict[int, list[Found]]  # box index -> masks


def parse_panels(spec: str, n: int) -> list[int]:
    if not spec:
        return list(range(n))
    out = []
    for part in spec.split(","):
        a, _, b = part.partition("-")
        out += list(range(int(a), int(b) + 1)) if b else [int(a)]
    return [i for i in out if 0 <= i < n]


def strip_view(ch: Chapter, picks) -> Image.Image:
    """The picked panels at their places in the episode strip, each boxed and numbered (step 1's cut)."""
    panels = ch.panels
    top = min(panels[i]["strip"]["y"] for i in picks) - 20
    bottom = max(panels[i]["strip"]["y"] + panels[i]["strip"]["h"] for i in picks) + 20
    w = max(panels[i]["size"]["w"] for i in picks)
    canvas = Image.new("RGB", (w + 120, bottom - top), (235, 235, 235))
    d = ImageDraw.Draw(canvas)
    for i in picks:
        p = panels[i]
        y = p["strip"]["y"] - top
        canvas.paste(ch.image(i), (0, y))
        d.rectangle([(0, y), (p["size"]["w"] - 1, y + p["size"]["h"] - 1)], outline=(220, 0, 0), width=4)
        d.text((w + 10, y + 10), f"panel {i}", fill=(220, 0, 0), font=U.font(22))
    return canvas


def sheet(img, letters, chars, understood, title) -> Image.Image:
    cols = [("1. panel", img), ("2. lettering", B.overlay(img, letters)), ("2. characters", CH.overlay(img, chars))]
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


def reviewed(ep: Episode, seg: Segmenter, imgs: Imgs, els: Masks, task: str, log: dict) -> Masks:
    """A segmentation task's review (review_loop), every box in parallel threads; its fixes and cost go into log
    under "p<i> <task>"."""
    def job(i):
        return i, *review(seg, imgs[i], els[i], task, f"{ep.stem} p{i} {task}")

    out = {}
    with ThreadPoolExecutor(8) as ex:
        for i, new, lg in ex.map(job, list(els)):
            out[i] = new
            log[f"p{i} {task}"] = _review_record(lg)
    return out


def _review_record(lg) -> dict:
    """A review's log (review_loop.Log) as the run log keeps it."""
    return {"applied": lg.applied, "rejected": lg.rejected, "cost": lg.cost, "truncated": lg.truncated,
            "stopped": lg.stopped}


def lettering_step(ep: Episode, seg: Segmenter, imgs: Imgs, chapters: Path, review_on: bool, log: dict) -> Masks:
    """2a: bubbles, captions and sound effects (bubbles.py, the exemplar bank's crops from the .zumi files in
    `chapters`), sound effects tightened (sfx_refine.py), then reviewed."""
    bank = B.Bank(B.BANK, chapters)
    letters = {i: refine_panel(seg, img, B.segment(seg, img, bank, ep.stem, i)) for i, img in imgs.items()}
    return reviewed(ep, seg, imgs, letters, "lettering", log) if review_on else letters


def characters_step(ep: Episode, seg: Segmenter, imgs: Imgs, review_on: bool, log: dict) -> Masks:
    """2b: one mask per character, a crowd as one (characters.py), then reviewed."""
    chars = {i: CH.segment(seg, img) for i, img in imgs.items()}
    return reviewed(ep, seg, imgs, chars, "characters", log) if review_on else chars


def frames_step(ep: Episode, imgs: Imgs, letters: Masks) -> None:
    """Step 1's frames within each box (frames.py: Claude Sonnet 5.5 panel boxes, 8 boxes asked at once, answers
    cached; frames.split), saved with the page they leave out (Box.save_frames), which every later step uses as the
    page. The lettering feeds the gutter (a bubble touching the box edge is not page). A box with no answer (the daily
    cap, two unreadable replies) is one scene, saved as unanswered so the next run asks again."""
    import frames as FR
    import page as PG

    def ask(i):
        try:
            return i, FR.layout(imgs[i], f"panels:{ep.box(i).pid}")
        except (BudgetExceeded, FR.PanelError) as e:
            print(f"p{i}: no panel boxes ({e}); one scene for now")
            return i, None

    with ThreadPoolExecutor(8) as ex:
        asked = dict(ex.map(ask, list(imgs)))
    counts = []
    for i, img in imgs.items():
        L = union(letters[i], (img.height, img.width))
        s = FR.split(img, PG.gutter(img, L if L.any() else None), asked[i], L)
        ep.box(i).save_frames(s.frames, s.flat, s.page, asked[i] is not None)
        counts.append(len(s.frames))
    print(f"frames per box: {counts}")


def objects_step(ep: Episode, seg: Segmenter | None, imgs: Imgs, chars: Masks, review_on: bool, log: dict) -> None:
    """2c, every object in front of the backdrop per box (scene_judge, Haiku 5.5) masked by SAM 3.1 (objects.py),
    then reviewed like characters and lettering (review_loop, task "objects"), saved (Box.save_objects) and reused on
    reruns. A box whose pick fails (the daily cap, a reply cut off) is not saved, so the next run asks again. The
    first version listed big furniture only (it chose what to erase): the vase on ToG 228 p6's side table stayed
    painted on the backdrop."""
    import objects as OB
    from scene_judge import choose_objects
    todo = {}
    for i, img in imgs.items():
        if ep.box(i).has_objects():
            continue
        try:
            objs = choose_objects(img, union(chars[i], (img.height, img.width)), tag=f"{ep.stem} p{i} objects")
        except BudgetExceeded as e:
            print(f"STOP objects: {e}")
            break
        except Truncated as e:  # no answer is not "no objects": nothing saved, so the next run asks again
            print(f"p{i}: objects not chosen ({e}); not saved")
            continue
        per = []
        if objs:
            seg = seg or Segmenter()
            _, per = OB.masks_for_objects(seg, img, objs)
        todo[i] = per

    def job(i):
        per = todo[i]
        if not per or not review_on:
            return i, per, None
        els = [Found(o["mask"], o["score"], "object", o["name"]) for o in per]
        new, lg = review(seg, imgs[i], els, "objects", f"{ep.stem} p{i} objects")
        # each mask keeps its pick's name and relations; a mask the review added is a plain object; repeated names
        # (a split mask's parts) get a number, as the picker numbers repeats
        meta = {o["name"]: o for o in per}
        seen, kept = {}, []
        for e in new:
            base = e.name if e.name in meta else "object"
            seen[base] = seen.get(base, 0) + 1
            name = base if seen[base] == 1 else f"{base} {seen[base]}"
            kept.append({"name": name, "mask": e.mask, "score": e.score,
                         **{k: meta.get(base, {}).get(k) for k in OBJECT_META_KEYS}})
        return i, kept, lg

    with ThreadPoolExecutor(8) as ex:
        for i, per, lg in ex.map(job, list(todo)):
            ep.box(i).save_objects(per)
            if lg is not None:
                log[f"p{i} objects"] = _review_record(lg)
            fixes = f", review: {lg.applied}" if lg is not None and lg.applied else ""
            print(f"p{i}: objects {[o['name'] + (' @ ' + o['on'] if o.get('on') else '') + (' [held]' if o.get('held') else '') + (' [front]' if o.get('front') else '') for o in per] or 'none'}{fixes}")


def layers_step(ep: Episode, imgs: Imgs, letters: Masks, chars: Masks, und: dict, depth_fn,
                objects: bool = True) -> None:
    """Step 4, the flat layers of every box (cards.layers) on the frames the frame step saved. objects: the saved
    objects as cards even without an erase plate (off when no erase is paid for: they stay painted on the art)."""
    import cards as CD
    for i, img in imgs.items():
        box = ep.box(i)
        print(f"  {box.pid} layers: {CD.layers(box, img, letters[i], chars[i], und.get(i), depth_fn, objects)}")


def erase_step(ep: Episode, imgs: Imgs, letters: Masks, chars: Masks, und: dict, erase: bool = True) -> None:
    """Steps 3-4: the band erase (band_erase.py) between two passes of the flat layers. Its masks come from the
    cards (their outlines, and how far each slides at a head move, which needs their depth), so a first layers pass
    lays the cards out on the art; band_erase then paints what is behind them, ONE FLUX Erase call per box (a box
    whose result is the model's placeholder is retried frame by frame; paid results cached by mask, the BFL daily cap
    stops it cleanly); the second pass rebuilds the layers on its plates. The first pass costs ~5 s per box. erase:
    False pays for no erase: the layers stay on the art (or on band plates an earlier run paid for). DA3MONO on
    each frame alone orders the cards and gives each frame's backdrop distance (user, 2026-10-26: DA3METRIC per frame
    tied characters DA3MONO told apart and lost the figure on close-ups, P&C 39 p24)."""
    import band_erase as BE
    import depth as DP
    import torch
    mono = DP.load()
    depth_fn = lambda rgb: DP.frame_infer(mono, rgb)  # noqa: E731
    print("  (first pass: the cards on the art)")
    layers_step(ep, imgs, letters, chars, und, depth_fn, objects=erase)
    if not erase:
        return
    boxes = [(ep.box(i), np.asarray(imgs[i])) for i in imgs]
    BE.erase_boxes([(b, img) for b, img in boxes if b.cards() is not None],  # boxes in parallel, budget-safe
                   log=lambda s: print("  " + s.replace("\n", "\n  ")))
    torch.cuda.empty_cache()
    print("  (second pass: the cards on the erased plates)")
    layers_step(ep, imgs, letters, chars, und, depth_fn, objects=erase)


def understand_step(ep: Episode, imgs: Imgs, img_of, letters: Masks, layers: bool) -> dict:
    """Step 5, Understand (understand.Reader) per box in reading order, saved (understand.json) and, when this run
    built the layers, joined into them (cards.annotate: bubbles.json's text, kinds, speakers and the lettering cards'
    names). Stops at the daily cap, keeping what it has. Returns the report picture per box."""
    import cards as CD
    reader, results, pictures = U.Reader(), {}, {}
    try:
        for i, img in imgs.items():
            if letters[i]:
                results[i], pictures[i] = reader.read(img, [f.mask for f in letters[i]], [f.kind for f in letters[i]], i,
                                                      f"{ep.stem} p{i}", img_of(i - 1) if i > 0 else None)
    except BudgetExceeded as e:
        print(f"STOP: {e}")
    ep.save_understanding(results, reader.cast)
    if layers:
        for i, r in results.items():
            CD.annotate(ep.box(i), r)
    return pictures


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", default="")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument("--no-depth", action="store_true",
                    help="no erase and no layers: segmentation, then Understand (saved, not joined into older layers)")
    ap.add_argument("--no-layers", action="store_true",
                    help="skip step 3's paid erase (and the objects): the layers are still built, on the original art")
    ap.add_argument("--no-understand", action="store_true",
                    help="skip Understand (bubble text, kind, speaker): without it the exported bubbles have no text, "
                         "so test runs of the 3D do without it")
    ap.add_argument("--from-masks", action="store_true",
                    help="reuse the masks and Understand's results of an earlier run: objects, frames when not current, "
                         "the erase and the layers (no SAM for lettering and characters, no Understand)")
    a = ap.parse_args()
    ch = Chapter(a.zumi)
    ep = Episode(a.out, ch.stem)
    picks = parse_panels(a.panels, len(ch))
    for d in ("masks", "sheets"):
        (a.out / d).mkdir(parents=True, exist_ok=True)
    erase = not a.no_layers
    times, log = {}, {}

    def timed(name, fn, *args, **kw):
        t = time.perf_counter()
        r = fn(*args, **kw)
        times[name] = time.perf_counter() - t
        return r

    if a.from_masks:
        if a.no_depth:
            print("--from-masks only rebuilds what --no-depth leaves out: nothing to do")
            return
        letters, chars = {}, {}
        for i in picks:
            ls, cs = ep.box(i).letters(), ep.box(i).characters()
            if ls is None or cs is None:
                print(f"p{i}: no saved masks, skipped")
                continue
            letters[i], chars[i] = ls, cs
        imgs = {i: ch.image(i) for i in letters}
        if erase:
            timed("2c objects", objects_step, ep, None, imgs, chars, not a.no_review, log)
        stale = {i: imgs[i] for i in imgs if not ((f := ep.box(i).frames()) and f.current)}
        if stale:
            timed("1 frames", frames_step, ep, stale, letters)
        timed("3 erase + 4 layers", erase_step, ep, imgs, letters, chars, ep.understanding()["panels"], erase)
        ep.save_run_log(log, times)
        print({k: round(v, 1) for k, v in times.items()})
        return

    imgs = {i: ch.image(i) for i in picks}
    pictures = {}

    # 1. box breakdown: the boxes come cut by intake; their frames follow as soon as the lettering exists (2a)
    print(f"== 1 box breakdown: {len(picks)} boxes from intake ({a.zumi.name})")
    strip_view(ch, picks).save(a.out / "step1-strip.png")
    seg = Segmenter()
    print("== 2a lettering")
    letters = timed("2a lettering", lettering_step, ep, seg, imgs, a.zumi.parent, not a.no_review, log)
    print("== 1 frames (they need the lettering)")
    timed("1 frames", frames_step, ep, imgs, letters)
    print("== 2b characters")
    chars = timed("2b characters", characters_step, ep, seg, imgs, not a.no_review, log)
    for i in picks:  # saved before the paid and slow steps: a crash there must not lose them
        letters[i], chars[i] = top_order(letters[i]), top_order(chars[i])  # one numbering in memory and on disk
        ep.box(i).save_letters(letters[i])
        ep.box(i).save_characters(chars[i])
    ep.save_understanding({}, drop=picks)  # new masks: the old results' element ids point at other bubbles
    if not a.no_depth and erase:
        print("== 2c objects")
        timed("2c objects", objects_step, ep, seg, imgs, chars, not a.no_review, log)
    del seg
    import torch
    torch.cuda.empty_cache()
    ep.save_run_log(log, times)

    if not a.no_depth:
        print("== 3 erase + 4 flat layers")
        timed("3 erase + 4 layers", erase_step, ep, imgs, letters, chars, {}, erase)
        ep.save_run_log(log, times)

    # 5. Understand, last and optional: joined into the layers this run built
    print("== 5 understand" + (" (skipped)" if a.no_understand else ""))
    if not a.no_understand:
        pictures = timed("5 understand", understand_step, ep, imgs, ch.image, letters, not a.no_depth)
    for i in picks:
        sheet(imgs[i], letters[i], chars[i], pictures.get(i), f"{ch.stem} panel {i}").save(a.out / "sheets" / f"{ch.pid(i)}.png")
    ep.save_run_log(log, times)
    print({k: round(v, 1) for k, v in times.items()}, f"spent today {spent_today():.3f} USD")


if __name__ == "__main__":
    main()
