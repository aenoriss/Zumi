"""The episode pipeline: box breakdown, segmentation (each task with its review), the erase, the flat layers,
Transcribe, the speakers, then character identity and voices. This script runs steps 2-8 on a chapter step 1 has cut; each step is a function of its
own inputs, steps hand data to each other through what they save (boxstore.Box), and a step skips the boxes whose
output is current (fresh.py: the saved stamp of its inputs and recipe equals today's): the lettering and the
characters (the box image, the segmentation's constants, the review's prompts and model), the frames (from the
current lettering), the objects, the layers (masks, frames, objects, plate, constants), the transcripts (masks,
prompts, models). A run where every box is current loads neither SAM nor the depth model. The GPU steps (SAM, DA3)
run in order; the network steps run beside them in background threads, each started once its inputs exist (the
frames' panel boxes at the start, Transcribe after the lettering); CPU work per box runs across processes
(workers.pmap), paid calls many at once (spend.paid_map).

    uv run python episode.py <episode.zumi> <out dir> [--panels 10-15 | --panels 3,7,9] [--no-review]
                             [--segment-only] [--no-erase] [--no-transcribe] [--from-masks]
                             [--no-identity] [--no-voices] [--no-music] [--no-places] [--series NAME]

<out dir> is <run>/dataset/<episode>. --panels limits steps 1-6 to those boxes and skips steps 7-10d, which read
the whole episode (identity and the voices pay for it): run them again without --panels.

1. Box breakdown. The chapter is cut into boxes by intake (pipeline/zumi/intake, `zumi intake`: the strip stitched,
   gutters scanned, one box per panel, packed as a .zumi). Within each box, its frames and the page around them
   (frames.ask: Claude Sonnet 5.5 panel boxes, about 0.0043 USD a box, cached; frames.update); depth is only ever
   estimated per frame. The panel boxes are asked for at the start; the split waits for 2a, since the page needs
   the lettering masks.
2. Segmentation, one SAM 3.1 model for the run (sam.Segmenter). Each task is found, then reviewed by the reasoning
   layer (review_loop.py, Claude Haiku 5.5, high reasoning: merge, split, improve, drop, missing, each change carried
   out by SAM on a zoomed crop and checked alone; boxes in parallel threads). On 221 held-out panels the review cut
   major errors by 56%, fixing 6-16 for each one it introduced (docs/research/reviewer-heldout-test-2026-10.md).
   Each box's masks carry two stamps (out/masks/stamps.json): segmented (image and recipe) and reviewed in full; a
   current box is neither segmented nor reviewed again (2026-11-10: every run did both, 8-10 minutes and both
   reviews paid again), and a review the daily cap stopped is done again next run on the saved masks (pending).
   a. lettering: bubbles.py (sound effects tightened to their letters inside); reviewed.
   b. characters: characters.py; reviewed.
   c. objects (objects.find): picked by a Haiku call (names, points and relations), masked by SAM, reviewed. Only
      with the erase: an object is cut out of the backdrop.
3. Erase (layers.py): what the art hides behind characters, objects and lettering. The card interiors are
   prefilled with the frame's plain background colour, a band as wide as a head move uncovers is masked, and ONE
   FLUX Erase call per box paints it (BFL API, 0.034 USD a call, 2 USD/day cap); a result that is the model's
   placeholder is retried frame by frame. Its masks need the cards and their depth: it reads them from the plan of
   step 4. Steps 3 and 4 are one call, layers.build.
4. Flat layers (layers.py: plan, then render on the plates): per frame the backdrop and one card per character
   and object, ordered by DA3MONO run on each frame alone, fixed steps between them; the lettering in front as cards
   of the original bubbles, placed just in front of what is behind each.
5. Transcribe (transcribe.update, Claude Haiku 5.5), optional: each bubble's text and kind, boxes in parallel, saved
   to transcripts.json stamped with the masks it read (Box.transcript_current; Box.bubbles joins it into the bubbles
   when they match; a box segmented again is read again). An element whose kind Haiku decided in a situation where
   typing goes wrong (balloon-less words by a person, a split word, a first-person box, an unclear sound maker) gets
   a doubt, and its box is read once more by Claude Sonnet 5.5, whose kind wins there (at most transcribe.SECOND_USD
   an episode). It moves nothing in the 3D and says nothing about speakers.
6. Speakers (speakers.assign_box): who speaks each bubble, by rules on the layers, the frames and Transcribe's kinds,
   run on every box each time; a bubble the identity reader corrected on the same layers keeps that correction.
7. Identity (character_identity.identity_step): which character cards are one character across the episode's boxes
   and the series' episodes: appearance groups (three frozen encoders, witness link), then one Claude Sonnet 5.5
   call that reads the story and edits them (pass 1, the series' first episode) or assigns them to the series cast
   (pass 2, later episodes). The same call reviews the speaker links: every link made without a clear tail (the
   only or the nearest figure, a shared or a tied tail, several cards) is marked `check` and decided by the tail
   and the turns of the conversation; a speaker may be any card of the episode or off-panel; the corrections go
   into the boxes' speaker records. identity/identity.json and the series cast (<run>/cast/<series>/); a rerun
   keeps the voices of the characters it founds again.
8. Voices (character_identity.voices_step): a voice description for every character with at least 3 lines and no
   voice yet (one Sonnet call), each designed once on Inworld TTS-2 and published (a voice id and sample in the
   cast, inworld.design_voice), then every balloon with a speaker recorded in its character's voice, the delivery
   note from the balloon's kind and Transcribe's reading of the drawing, with the scene's previous balloons as
   context (<episode>/audio/<pid>.b<bubble>.wav, audio/lines.json; only changed lines again; audio/episode.mp3
   joins them for listening). Inworld's free plan has no daily request limit (Gemini's 100 a day was why it went,
   2026-11-06; Inworld's CREATIVE delivery was also judged more expressive).
8b. The episode clock (clock.clock_step, no paid call): when every panel, frame and balloon is on screen, from the
   layers, the balloons, the reading order and the lines' lengths; <episode>/clock/clock.json. The steps after it
   and the export read their times from it (step 9, Motion, will change panel lengths and run before it).
10. Settings and score (score.score_step; step 9, Motion, is still to build): the places each frame is drawn in (one
   Sonnet call over contact sheets of the erased backdrops, settings.py), the music reviewer's spans with a mood and
   a role (one text-only Sonnet call), and one Lyria song per setting and mood used, cut to a loop (score.py). The
   export resolves them with the clock into per-track gain envelopes. About 0.55 USD an episode.
10c. Places (places.places_step): the settings a long enough stay earns, each a 2:1 wide view made in two FLUX 3 calls
   (a plain 16:9 view, then the panorama continuing it) and lifted to a mesh around the seat by MoGe-3 on the local
   GPU (place_geometry.py in pipeline/.venv-moge), at most 140 x 72 degrees of it shown, its near objects erased (one
   FLUX Erase call) for the back layer; <episode>/places/. About 0.17 USD a place. The export packs the meshes and
   plans which place shows when on its own clock.
10d. Props (props.props_step): per built place, one Sonnet call picks up to 5 objects of its view (more the longer
   it is open) as boxes, each with its height and surface; each is cut from the view by SAM 3.1, repainted alone on
   a flat ground (FLUX.2 [klein] 4B), matted (BiRefNet) and lifted to a GLB (fal TRELLIS, once more if it stands on
   a plate), then its loose pieces dropped and its colours brought back to the cutout's; <episode>/props/<setting>/
   (props.json). About 0.01 USD a pick and 0.035 a prop. A prop that cannot be made is skipped and the others go on.

Writes what boxstore.py lists (masks, frames and page, objects, layers, plates, transcripts.json, speakers), out/run.json (each
review's fixes and cost, each step's time), out/step1-strip.png and out/sheets/<episode>-pNNN.png (panel |
lettering | characters | Transcribe), identity/ and audio/ (steps 7-8).
"""

from __future__ import annotations

import argparse
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

# before any step imports huggingface_hub, which fixes its cache dir on import: the models live on D: (C: is full;
# the identity step's own default came too late under this script, 2026-11-06, and a download to C: died)
os.environ.setdefault("HF_HOME", "D:/hf-cache")

from PIL import Image, ImageDraw

import bubbles as B
import characters as CH
import frames as FR
import objects as OB
import transcribe as T
from boxstore import Episode, image_stamp
from chapter import Chapter
from fresh import digest
from masks import Found, stamp, top_order
from spend import paid_map, spent_today
from workers import pmap
from review_loop import recipe as review_recipe, review
from sam import Segmenter

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
        d.text((w + 10, y + 10), f"panel {i}", fill=(220, 0, 0), font=T.font(22))
    return canvas


def sheet(img, letters, chars, transcribed, title) -> Image.Image:
    cols = [("1. panel", img), ("2. lettering", B.overlay(img, letters)), ("2. characters", CH.overlay(img, chars))]
    if transcribed is not None:
        cols.append(("5. transcribe", transcribed))
    h = max(im.height for _, im in cols)
    out = Image.new("RGB", (sum(im.width + 20 for _, im in cols), h + 50), (255, 255, 255))
    d = ImageDraw.Draw(out)
    d.text((6, 4), title, fill=(0, 0, 0), font=T.font(16))
    x = 0
    for name, im in cols:
        out.paste(im, (x, 50))
        d.text((x + 6, 26), name, fill=(0, 0, 0), font=T.font(16))
        x += im.width + 20
    return out


class LazySegmenter:
    """The run's one SAM 3.1 model (sam.Segmenter, its methods passed through), loaded the first time a step uses it:
    segmentation, a review carrying out a fix, the objects' masks. A run whose boxes are all current never loads it
    (before 2026-11-10 every run without --from-masks loaded it and segmented every box again)."""

    def __init__(self):
        self._seg = None
        self._lock = threading.Lock()

    def __getattr__(self, name):
        with self._lock:
            if self._seg is None:
                print("  (loading SAM 3.1)")
                self._seg = Segmenter()
        return getattr(self._seg, name)

    def release(self) -> None:
        if self._seg is not None:
            self._seg = None
            import torch
            torch.cuda.empty_cache()


SAVED = {"lettering": lambda box: box.letters(), "characters": lambda box: box.characters()}
SAVE = {"lettering": lambda box, m: box.save_letters(m), "characters": lambda box, m: box.save_characters(m)}


def mask_stamps(task: str, imgs: Imgs) -> dict[int, tuple[str, str]]:
    """Per box the stamps of its `task` masks: (segmented from this image by the task's recipe, bubbles.recipe or
    characters.recipe; that segmentation reviewed in full by review_loop.recipe)."""
    rec, rrec = {"lettering": B.recipe, "characters": CH.recipe}[task](), review_recipe(task)
    out = {}
    for i, img in imgs.items():
        s = digest(image_stamp(img), task, rec)
        out[i] = (s, digest(s, rrec))
    return out


def pending(task: str, ep: Episode, imgs: Imgs, review_on: bool, stamps=None) -> tuple[Masks, list[int], Masks]:
    """What a segmentation task has to do: (the boxes whose saved masks are current, {i: masks}; the boxes to
    segment; the boxes only to review, {i: their saved masks}). Saved masks are current when segmented by today's
    recipe and, with review_on, reviewed in full by today's review. A box with no review stamp (its review stopped by
    the daily cap, or segmented under --no-review) is reviewed on its saved masks: they are fine as segmented, and a
    review stopped part way keeps the fixes it made. A box reviewed by another review recipe is segmented again, so
    the new review starts from the segmentation and not from the old review's fixes. stamps: mask_stamps's, when
    already computed."""
    stamps = stamps or mask_stamps(task, imgs)
    current, segment, review_only = {}, [], {}
    for i in imgs:
        box = ep.box(i)
        s, r = stamps[i]
        saved = SAVED[task](box) if box.current(task, s) else None
        if saved is None:
            segment.append(i)
        elif not review_on or box.current(f"{task}-review", r):
            current[i] = saved
        elif box.stamp_of(f"{task}-review") is None:
            review_only[i] = saved
        else:
            segment.append(i)
    return current, segment, review_only


def segmentation_step(task: str, ep: Episode, seg, imgs: Imgs, review_on: bool, log: dict, segment, final) -> Masks:
    """One segmentation task with its review (pending decides what each box needs): segment(seg, i, img) -> masks for
    the boxes to segment, each saved at once (final: as saved) and stamped; then the review (review_loop, every box
    in parallel threads, spend.paid_map) of those and of the boxes only to review, each box saved as its review ends
    and stamped as reviewed when no call was stopped (Log.complete; a review logs the calls the cap refuses and keeps
    the masks). Its fixes and cost go into log under "p<i> <task>". Returns every box's masks as saved."""
    stamps = mask_stamps(task, imgs)
    out, todo, to_review = pending(task, ep, imgs, review_on, stamps)
    print(f"  {len(out)} of {len(imgs)} boxes current, {len(todo)} to segment"
          + (f", {len(to_review)} only to review" if review_on else ""))
    for i in todo:
        found = segment(seg, i, imgs[i])
        box = ep.box(i)
        out[i] = final(found)
        SAVE[task](box, out[i])
        box.made(task, stamps[i][0])
        box.unmade(f"{task}-review")
        if review_on:
            to_review[i] = found
    if not to_review:
        return out

    def reviewed(i, res):
        masks, lg = res
        box = ep.box(i)
        log[f"p{i} {task}"] = lg.record()
        if lg.applied:
            out[i] = final(masks)
            SAVE[task](box, out[i])
        if lg.complete:
            box.made(f"{task}-review", stamps[i][1])
        else:
            print(f"  p{i} {task}: review stopped by the daily cap or an offline run; reviewed again next run")

    paid_map(lambda i: review(seg, imgs[i], to_review[i], task, f"{ep.stem} p{i} {task}"), sorted(to_review),
             on_done=reviewed)
    return out


def lettering_step(ep: Episode, seg, imgs: Imgs, chapters: Path, review_on: bool, log: dict) -> Masks:
    """2a: bubbles, captions and sound effects (bubbles.segment, the exemplar bank's crops from the .zumi files in
    `chapters`; the sound effects tightened inside), then reviewed; saved in top_order (one numbering in memory and on
    disk). Only the boxes whose masks are not current (segmentation_step)."""
    bank = []

    def segment(seg, i, img):
        if not bank:
            bank.append(B.Bank(B.BANK, chapters))
        statuses = []
        found = B.segment(seg, img, bank[0], ep.stem, i, statuses)
        if statuses:  # the run log: what the sound-effect refinement did ("dropped-partial", "word-captured", ...)
            log[f"p{i} sfx"] = {s: statuses.count(s) for s in sorted(set(statuses))}
        return found

    return segmentation_step("lettering", ep, seg, imgs, review_on, log, segment, top_order)


def characters_step(ep: Episode, seg, imgs: Imgs, review_on: bool, log: dict) -> Masks:
    """2b: one mask per character, a crowd as one (characters.py), reviewed, then made exclusive (characters.exclusive:
    a crowd without the characters masked on their own, no mask left as specks of others' outlines) and saved in
    top_order. Only the boxes whose masks are not current (segmentation_step)."""
    return segmentation_step("characters", ep, seg, imgs, review_on, log, lambda seg, i, img: CH.segment(seg, img),
                             lambda found: top_order(CH.exclusive(found)))


def layers_step(ep: Episode, imgs: Imgs, letters: Masks, chars: Masks, erase: bool = True) -> None:
    """Steps 3-4 (layers.build): every box planned, the erase on all of them (paid, boxes in parallel; the daily cap
    stops it cleanly), the layers drawn on the plates. erase: False pays for no erase: the layers are drawn on the
    art (or on plates an earlier run paid for), the objects stay painted on it."""
    import layers as LY
    LY.build([(ep.box(i), img, letters[i], chars[i]) for i, img in imgs.items()], erase,
             log=lambda s: print("  " + s.replace("\n", "\n  ")))


def speakers_step(ep: Episode, picks: list[int]) -> None:
    """Step 6: who speaks each bubble (speakers.assign_box: rules on the layers, the frames and the transcript's
    kinds), saved per box (speakers.json); boxes without layers are skipped."""
    import speakers as SP
    for i, recs in zip(picks, pmap(SP.assign_box, [ep.box(i) for i in picks])):  # boxes across processes
        if recs:
            print(f"  p{i}: " + ", ".join(f"#{r['bubble']} {r['speaker_kind']}" + (f" {len(r['speakers'])}"
                                          if r["speakers"] else "") for r in recs))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", default="", help="only these boxes (steps 1-6); steps 7-10d are skipped")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument("--segment-only", action="store_true",
                    help="segmentation, frames and Transcribe only: no objects, no erase, no layers, no speakers")
    ap.add_argument("--no-erase", action="store_true",
                    help="skip step 3's paid erase (and the objects): the layers are still built, on the original art")
    ap.add_argument("--no-transcribe", action="store_true",
                    help="skip Transcribe (bubble text and kind): without it the exported bubbles have no text, "
                         "so test runs of the 3D do without it")
    ap.add_argument("--from-masks", action="store_true",
                    help="reuse the saved lettering and character masks whatever their stamps (no SAM, no review for "
                         "them); every later step still runs, each skipping what is current (frames, objects, layers, "
                         "transcripts)")
    ap.add_argument("--no-identity", action="store_true", help="skip steps 7-8 (identity and voices)")
    ap.add_argument("--no-voices", action="store_true", help="skip step 8 (voice design and the recorded lines)")
    ap.add_argument("--no-music", action="store_true", help="skip step 10 (settings, the music reviewer, the tracks)")
    ap.add_argument("--no-places", action="store_true", help="skip step 10c (the places shown through the walls)")
    ap.add_argument("--series", default="",
                    help="the series whose cast identity uses (default: the episode name without its number)")
    a = ap.parse_args()
    ch = Chapter(a.zumi)
    ep = Episode(a.out, ch.stem)
    picks = parse_panels(a.panels, len(ch))
    for d in ("masks", "sheets"):
        (a.out / d).mkdir(parents=True, exist_ok=True)
    erase = not a.no_erase and not a.segment_only
    times, log = {}, {}

    def timed(name, fn, *args, **kw):
        print(f"== {name}")
        t = time.perf_counter()
        r = fn(*args, **kw)
        times[name] = time.perf_counter() - t
        ep.save_run_log(log, times)
        return r

    def background(name, fn, *args):
        """fn started in a thread now; the returned join() waits for its result where it is needed and times it. The
        network steps run so while SAM and DA3 hold the GPU."""
        def run():
            t = time.perf_counter()
            return fn(*args), time.perf_counter() - t

        def join():
            r, times[name] = fut.result()  # recorded here, in the main thread: timed() saves `times` meanwhile
            return r
        print(f"== {name} (in the background)")
        fut = net.submit(run)
        return join

    net = ThreadPoolExecutor(2)  # the background network steps; each fans its calls out itself (spend.paid_map)
    # 1. box breakdown: the boxes come cut by intake
    print(f"== 1 box breakdown: {len(picks)} boxes from intake ({a.zumi.name})")
    strip_view(ch, picks).save(a.out / "step1-strip.png")
    seg = LazySegmenter()
    review_on = not a.no_review
    if a.from_masks:
        letters, chars = {}, {}
        for i in picks:
            ls, cs = ep.box(i).letters(), ep.box(i).characters()
            if ls is None or cs is None:
                print(f"p{i}: no saved masks, skipped")
                continue
            letters[i], chars[i] = ls, cs
        imgs = {i: ch.image(i) for i in letters}
    else:
        imgs = {i: ch.image(i) for i in picks}
    frames_ok = {i for i in imgs if (f := ep.box(i).frames()) and f.current}
    # the frames are made again when they are not current or the lettering changes; their panel boxes need only the
    # images, so they are asked for now (cached answers cost nothing), while SAM segments, for every box whose
    # lettering may change
    if a.from_masks:
        maybe = set(imgs) - frames_ok
    else:
        done, _, _ = pending("lettering", ep, imgs, review_on)
        maybe = set(imgs) - (frames_ok & set(done))
    before = {i: stamp(ls) for i in maybe if (ls := ep.box(i).letters()) is not None}
    layouts = background("1 frame layouts", FR.ask, ep, {i: imgs[i] for i in sorted(maybe)}) if maybe else None
    changed = set()  # boxes whose masks were segmented or reviewed again: their debug sheets are drawn again
    if not a.from_masks:
        letters = timed("2a lettering", lettering_step, ep, seg, imgs, a.zumi.parent, review_on, log)
        changed |= {i for i in imgs if before.get(i) != stamp(letters[i])}
    stale = {i: imgs[i] for i in sorted(maybe) if i not in frames_ok or before.get(i) != stamp(letters[i])}
    # Transcribe needs only the lettering: it reads while characters, objects, the erase and the layers run
    transcript = None if a.no_transcribe else background("5 transcribe", T.update, ep, imgs, letters)
    if not a.from_masks:
        was = {i: ep.box(i).content("characters") for i in imgs}
        chars = timed("2b characters", characters_step, ep, seg, imgs, review_on, log)
        changed |= {i for i in imgs if ep.box(i).content("characters") != was[i]}
    if stale:
        timed("1 frames", FR.update, ep, stale, letters, layouts())
    elif layouts is not None:
        layouts()
    if erase:
        timed("2c objects", OB.find, ep, seg, imgs, chars, review_on, log)
    seg.release()
    if not a.segment_only:
        timed("3 erase + 4 layers", layers_step, ep, imgs, letters, chars, erase)
    pictures = {} if transcript is None else transcript()  # the speakers read Transcribe's kinds
    net.shutdown()
    if not a.segment_only:
        timed("6 speakers", speakers_step, ep, list(imgs))
    late = not a.segment_only and not a.panels
    if not a.segment_only and a.panels:
        # identity, voices, the clock, the music, the places and the props read the whole episode (and identity and
        # the voices pay for it): a run on some boxes leaves them as they are
        print(f"== 7-10d skipped under --panels: they read the whole episode; run them with "
              f"`episode.py {a.zumi} {a.out}` (no --panels; the boxes already current are not done again)")
    if late and not a.no_identity:
        import character_identity as CI
        ident = timed("7 identity", CI.identity_step, ep, ch, a.series or CI.series_of(ch.stem))
        if ident and not a.no_voices:
            timed("8 voices", CI.voices_step, ep, ch, ident)
    if late:  # the episode clock: when every panel, frame and balloon is on screen, for the steps after
        import clock
        timed("8b clock", clock.clock_step, ep, len(ch))
    if late and not a.no_music:
        import score
        timed("10 settings + score", score.score_step, ep, len(ch))
    if late and not a.no_places:
        import places
        timed("10c places", places.places_step, ep, ch)
        import props
        timed("10d props", props.props_step, ep)
    for i in sorted(changed | set(pictures) | {i for i in imgs if not (a.out / "sheets" / f"{ch.pid(i)}.png").exists()}):
        sheet(imgs[i], letters[i], chars[i], pictures.get(i), f"{ch.stem} panel {i}").save(a.out / "sheets" / f"{ch.pid(i)}.png")
    print({k: round(v, 1) for k, v in times.items()}, f"spent today {spent_today():.3f} USD")


if __name__ == "__main__":
    main()
