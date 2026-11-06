"""The episode pipeline: box breakdown, segmentation (each task with its review), the erase, the flat layers,
Transcribe, the speakers, then character identity and voices. This script runs steps 2-8 on a chapter step 1 has cut; each step is a function of its
own inputs, steps hand data to each other through what they save (boxstore.Box), and a step skips the boxes whose
output is current (frames from the current lettering, saved objects, a transcript of the same masks). The GPU steps
(SAM, DA3) run in order; the network steps run beside them in background threads, each started once its inputs exist
(the frames' panel boxes at the start, Transcribe after the lettering); CPU work per box runs across processes
(workers.pmap), paid calls many at once (spend.paid_map).

    uv run python episode.py <episode.zumi> <out dir> [--panels 10-15 | --panels 3,7,9] [--no-review]
                             [--segment-only] [--no-erase] [--no-transcribe] [--from-masks]
                             [--no-identity] [--no-voices] [--series NAME]

1. Box breakdown. The chapter is cut into boxes by intake (pipeline/zumi/intake, `zumi intake`: the strip stitched,
   gutters scanned, one box per panel, packed as a .zumi). Within each box, its frames and the page around them
   (frames.ask: Claude Sonnet 5.5 panel boxes, about 0.0043 USD a box, cached; frames.update); depth is only ever
   estimated per frame. The panel boxes are asked for at the start; the split waits for 2a, since the page needs
   the lettering masks.
2. Segmentation, one SAM 3.1 model for the run (sam.Segmenter). Each task is found, then reviewed by the reasoning
   layer (review_loop.py, Claude Haiku 5.5, high reasoning: merge, split, improve, drop, missing, each change carried
   out by SAM on a zoomed crop and checked alone; boxes in parallel threads). On 221 held-out panels the review cut
   major errors by 56%, fixing 6-16 for each one it introduced (docs/research/reviewer-heldout-test-2026-10.md).
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

Writes what boxstore.py lists (masks, frames and page, objects, layers, plates, transcripts.json, speakers), out/run.json (each
review's fixes and cost, each step's time), out/step1-strip.png and out/sheets/<episode>-pNNN.png (panel |
lettering | characters | Transcribe), identity/ and audio/ (steps 7-8).
"""

from __future__ import annotations

import argparse
import os
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
from boxstore import Episode
from chapter import Chapter
from masks import Found, top_order
from spend import paid_map, spent_today
from workers import pmap
from review_loop import review
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


def reviewed(ep: Episode, seg: Segmenter, imgs: Imgs, els: Masks, task: str, log: dict) -> Masks:
    """A segmentation task's review (review_loop), every box in parallel threads (spend.paid_map; a review logs the
    calls the cap refuses and keeps the masks); its fixes and cost go into log under "p<i> <task>"."""
    done, _ = paid_map(lambda i: review(seg, imgs[i], els[i], task, f"{ep.stem} p{i} {task}"), list(els))
    for i, (_, lg) in done.items():
        log[f"p{i} {task}"] = lg.record()
    return {i: done[i][0] if i in done else els[i] for i in els}


def lettering_step(ep: Episode, seg: Segmenter, imgs: Imgs, chapters: Path, review_on: bool, log: dict) -> Masks:
    """2a: bubbles, captions and sound effects (bubbles.segment, the exemplar bank's crops from the .zumi files in
    `chapters`; the sound effects tightened inside), then reviewed."""
    bank = B.Bank(B.BANK, chapters)
    letters = {}
    for i, img in imgs.items():
        statuses = []
        letters[i] = B.segment(seg, img, bank, ep.stem, i, statuses)
        if statuses:  # the run log: what the sound-effect refinement did ("dropped-partial", "word-captured", ...)
            log[f"p{i} sfx"] = {s: statuses.count(s) for s in sorted(set(statuses))}
    return reviewed(ep, seg, imgs, letters, "lettering", log) if review_on else letters


def characters_step(ep: Episode, seg: Segmenter, imgs: Imgs, review_on: bool, log: dict) -> Masks:
    """2b: one mask per character, a crowd as one (characters.py), reviewed, then made exclusive (characters.exclusive:
    a crowd without the characters masked on their own, no mask left as specks of others' outlines)."""
    chars = {i: CH.segment(seg, img) for i, img in imgs.items()}
    if review_on:
        chars = reviewed(ep, seg, imgs, chars, "characters", log)
    return dict(zip(chars, pmap(CH.exclusive, list(chars.values()))))  # boxes across processes


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
    ap.add_argument("--panels", default="")
    ap.add_argument("--no-review", action="store_true")
    ap.add_argument("--segment-only", action="store_true",
                    help="segmentation, frames and Transcribe only: no objects, no erase, no layers, no speakers")
    ap.add_argument("--no-erase", action="store_true",
                    help="skip step 3's paid erase (and the objects): the layers are still built, on the original art")
    ap.add_argument("--no-transcribe", action="store_true",
                    help="skip Transcribe (bubble text and kind): without it the exported bubbles have no text, "
                         "so test runs of the 3D do without it")
    ap.add_argument("--from-masks", action="store_true",
                    help="reuse the saved lettering and character masks (no SAM for them); every later step still "
                         "runs, each skipping what is current (frames, objects, transcripts of the same masks)")
    ap.add_argument("--no-identity", action="store_true", help="skip steps 7-8 (identity and voices)")
    ap.add_argument("--no-voices", action="store_true", help="skip step 8 (voice design and the recorded lines)")
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
    seg = None
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
    # the frames are made again when the lettering is new or they are not current; their panel boxes need only the
    # images, so they are asked for now, while SAM segments
    stale = {i: imgs[i] for i in imgs if not a.from_masks or not ((f := ep.box(i).frames()) and f.current)}
    layouts = background("1 frame layouts", FR.ask, ep, stale) if stale else None
    if not a.from_masks:
        seg = Segmenter()
        letters = timed("2a lettering", lettering_step, ep, seg, imgs, a.zumi.parent, not a.no_review, log)
        for i in imgs:  # saved before the slow steps (a crash there must not lose them), in one numbering
            letters[i] = top_order(letters[i])
            ep.box(i).save_letters(letters[i])
    # Transcribe needs only the lettering: it reads while characters, objects, the erase and the layers run
    transcript = None if a.no_transcribe else background("5 transcribe", T.update, ep, imgs, letters)
    if not a.from_masks:
        chars = timed("2b characters", characters_step, ep, seg, imgs, not a.no_review, log)
        for i in imgs:
            chars[i] = top_order(chars[i])
            ep.box(i).save_characters(chars[i])
    if stale:
        timed("1 frames", FR.update, ep, stale, letters, layouts())
    if erase:
        timed("2c objects", OB.find, ep, seg, imgs, chars, not a.no_review, log)
    if seg is not None:
        del seg
        import torch
        torch.cuda.empty_cache()
    if not a.segment_only:
        timed("3 erase + 4 layers", layers_step, ep, imgs, letters, chars, erase)
    pictures = {} if transcript is None else transcript()  # the speakers read Transcribe's kinds
    net.shutdown()
    if not a.segment_only:
        timed("6 speakers", speakers_step, ep, list(imgs))
    if not a.segment_only and not a.no_identity:
        import character_identity as CI
        ident = timed("7 identity", CI.identity_step, ep, ch, a.series or CI.series_of(ch.stem))
        if ident and not a.no_voices:
            timed("8 voices", CI.voices_step, ep, ch, ident)
    for i in imgs:
        sheet(imgs[i], letters[i], chars[i], pictures.get(i), f"{ch.stem} panel {i}").save(a.out / "sheets" / f"{ch.pid(i)}.png")
    print({k: round(v, 1) for k, v in times.items()}, f"spent today {spent_today():.3f} USD")


if __name__ == "__main__":
    main()
