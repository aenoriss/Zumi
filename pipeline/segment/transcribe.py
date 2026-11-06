"""Step 5, Transcribe: a vision model reads the text of every segmented lettering element of a box, its kind, and
whether the element is lettering at all. It does not say who speaks (user, 2026-10-31): speakers.py decides that from
the cards, and identity across boxes is a step of its own.

    pictures = update(ep, imgs, letters)             # the step: the boxes whose transcript is stale, read and saved
    result, picture = read(img, masks, kinds, tag)   # one box
    results, pictures = read_boxes({i: (img, masks, kinds, tag)})   # many, in parallel (spend.paid_map)
    uv run python transcribe.py <episode.zumi> <episode out dir> <out dir> --panels 1,2,3 [--models a,b]

One call per box with two images: the box with each element outlined and numbered, and each element cropped at full
resolution with its outline drawn and everything outside it faded, so the model reads only that element's letters.
Per element the model returns the text, the kind (speech, thought, shout, caption, sfx), keep (one whole element),
in_world (text drawn in the scene: a screen, a sign, a printed page), delivery (how the line is said, from the face,
the balloon and the words: the voice step's style note for the line) and doubt (the kind was decided in a situation
where typing often goes wrong); enforce turns those into the one keep the layers use. A box with a doubted element
is read once more by SECOND_MODEL, whose kind wins for those elements (read). Paid calls go through
openrouter.ask_json (the shared daily cap); a reply cut off at its budget, or with no JSON in it, gives an empty
result marked "error".
"""

from __future__ import annotations

import argparse
import json
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, binary_erosion

from boxstore import Episode
from openrouter import Truncated, ask_json, image_part
from spend import paid_map, spent_today

# Claude Haiku 5.5 (2026-11-01): on the 670 labelled lines of P&C 36-39 its kinds matched the speaker labels 650 times,
# Llama 4 Maverick's 598 (old prompt) to 619; Maverick also left elements out. Both about 0.0007 USD a box.
MODEL = "anthropic/claude-haiku-5.5"
SECOND_MODEL = "anthropic/claude-sonnet-5.5"  # reads again the boxes where Haiku's kind came from an ambiguous situation
                                               # (its "doubt"), about 7x Haiku's price a box; its kind wins there
SECOND_USD = 0.25  # the most the second opinions of one update() may cost (user, 2026-11-06: at 0.4 nothing was capped
                   # and the score did not move); the boxes read after it is reached keep Haiku's kinds, doubts noted
_second = {"usd": 0.0, "cap": SECOND_USD}  # the running sum of the current update(), shared by its threads
_second_lock = threading.Lock()
REASONING = {"meta/muse-spark-1.3": "low", "google/gemini-3.8-flash": "low"}  # reasoning models only
MAX_TOKENS = 4000  # the answer's budget: Haiku 5.5 spent all of 2500 on boxes of 14+ elements (P&C 38 p18, 36 p12)
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (240, 50, 230), (0, 128, 128), (170, 110, 40)]

SYSTEM = """You transcribe the lettering of webtoon panels for a reading app that erases the original lettering and \
redraws each bubble as live text. You are precise and never invent text."""

INSTRUCTIONS = """Image 1 is a webtoon panel. Each element found by an automatic segmenter is outlined in colour and \
numbered. Image 2 shows each element cropped at full resolution with its outline drawn; everything outside the \
outline is faded.

Elements, with where each lies in the panel:
{hints}

For every numbered element decide:
- "keep": true only if, in image 2, the outline encloses exactly one whole speech bubble, thought bubble, caption box \
or sound effect, including its tail. Two bubble shapes joined into one (a figure-eight, one bubble flowing into the \
next) or a caption box made of joined parts count as ONE element: keep. A sound effect repeated at different places \
gives separate elements with the same text: keep each. false only if the outline cuts through the bubble or its \
letters, encloses two bubbles that do not touch, or the element is not lettering (a whole picture). Comic \
annotations are lettering: a word or short phrase written over the art that labels a feeling, an action or a thing, \
often with an arrow or lines pointing at it: keep. When unsure, keep it.
- "in_world": true only if the text belongs to the drawn world rather than the comic's lettering: a phone or \
computer screen, a chat or social-media interface, a sign or poster, a letter, book or printed page, text on \
clothing or objects. false for every speech bubble, thought bubble, caption and sound effect.
- "issue": when keep is false or in_world is true, a few words saying why; otherwise null.
- "kind": who or what produces the words. Decide it from the scene in image 1, not from the lettering style: \
balloon-less lettering drawn straight on the art is as often a character's voice as a noise. First look at what is \
drawn around the lettering and what each figure is: a person, or an animal. Comics often draw animals with \
expressive, almost human faces: fur, a snout or muzzle, floppy or pointed ears, paws and a tail make it an animal.
  - "speech": words or vocal sounds a character makes aloud: talking, calling out, laughing, sighing, groaning, \
crying, whispering, singing. Not an animal's cries: those are sfx. In a balloon of any shape (round, rectangular, dark; a box holding a character's own \
words is speech, not a caption), or with no balloon at all when the character in the scene voices it.
  - "shout": the same, yelled: a spiky or jagged balloon, or large bold letters a character cries out.
  - "thought": a character's unspoken words: a cloud-shaped balloon, a balloon joined by small circles, letters \
inside or attached to such a balloon, or words near a character that read as their inner voice. A word or short \
phrase written over the art beside a character that voices that character's feeling or state, or their opinion of \
what they see or of themselves (a teasing aside, a verdict), is that character's inner voice: thought, or speech \
when it is clearly said to someone. A rectangular box whose words are in the first person, about the character's \
own situation or feelings, is that character's thought wherever the box sits, not a caption.
  - "caption": the narrator's words, not a character's: time, place, a fact about who or what is shown, or story \
told from outside, usually in a rectangular box at the edge of the panel with no tail.
  - "sfx": a sound no character voices: made by objects, actions, machines, screens or the surroundings, a body \
without intent (breathing, panting, gasping, coughing, a heartbeat), or an animal's cries (barking, meowing, \
growling), even when the animal is a character of the story, or the background noise of a crowd. Also a label \
written from outside the story that identifies what is drawn (who a person is, what a thing is, where or when we \
are), often with an arrow, which no character says; and an element with no letters in it. Nothing inside a \
balloon is sfx, and neither is a sentence a character says, nor punctuation marks alone (exclamation or \
question marks) drawn next to a character: that is the character's reaction, speech or thought. Words with no \
balloon are a character's when a person in the scene produces them: words a person cries out in big letters by \
their shouting face are a shout, and a vocal sound written as the sound itself beside the person making it (a \
laugh, a sigh, a groan, a hum) is that person's speech, while a noise made by a thing, an action or an animal is \
sfx. A stage direction that describes how nearby words are delivered (whispering, muttering, often in asterisks or \
small letters by a balloon) is not spoken by anyone: sfx.
  A word cut into pieces by the segmenter (one piece in one element, the rest in another) has in every piece the \
kind of the whole word.
- "text": exactly the words inside this element's own coloured outline in image 2, line breaks as single spaces, \
keeping punctuation. Faded words in image 2 lie outside the outline and belong to another element: never include them.
- "delivery": for speech, shout and thought, a few words on how the character says or thinks this line, for the \
voice actor: the emotion and the manner, read from the character's face and posture in image 1, the balloon's \
shape and the lettering's weight, and the words themselves (for example "cold, mocking", "shouting through tears", \
"tired, half-joking", "flat, bored"). Only what this moment shows, nothing about the voice itself. null for sfx, \
captions and in-world text.
- "pace": for speech, shout and thought, the tempo this line is said at as the drawing and the words show it: "slow" \
(a halting line, pauses or dashes, a weary or solemn moment, a drawn-out word), "fast" (a burst, a rush, an \
interruption, excited chatter, a short exclamation), else "normal". null for sfx, captions and in-world text.
- "doubt": null, or a few words naming the situation when the element is in one of the few where typing often goes \
wrong: words with no balloon written over the art next to a person, where a word could be that person's shout, \
reaction, thought or a label; a piece of a word split across elements; a rectangular box whose words are in the \
first person; or a sound whose maker (a person, an animal, a thing) is not clear in the scene. Name the situation, \
not how sure you feel. No doubt for a balloon of any shape, a caption that tells time, place or who someone is, or \
a noise word with no person near it: those are typed reliably.

Answer with JSON only:
{{"elements": [{{"id": 1, "keep": true, "in_world": false, "issue": null, "kind": "speech", "text": "...", "delivery": "...", "pace": "normal", "doubt": null}}]}}"""


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def numbered_overlay(img: Image.Image, masks: list[np.ndarray]) -> Image.Image:
    out = np.asarray(img.convert("RGB")).copy()
    t = max(2, img.width // 250)
    for k, m in enumerate(masks):
        edge = binary_dilation(m & ~binary_erosion(m, iterations=1), iterations=t)
        out[edge] = COLOURS[k % len(COLOURS)]
    im = Image.fromarray(out)
    d = ImageDraw.Draw(im)
    size = max(18, img.width // 22)
    for k, m in enumerate(masks):
        ys, xs = np.nonzero(m)
        x, y = int(xs.min()), int(ys.min())
        d.rectangle([(x, y), (x + size * 1.4, y + size * 1.2)], fill=COLOURS[k % len(COLOURS)])
        d.text((x + size * 0.2, y + size * 0.05), str(k + 1), fill=(255, 255, 255), font=font(size))
    return im


def crops_sheet(img: Image.Image, masks: list[np.ndarray], width: int = 1024) -> Image.Image:
    """Each element cropped with its outline drawn and everything outside it faded, numbered, stacked."""
    arr = np.asarray(img.convert("RGB"))
    rows = []
    for k, m in enumerate(masks):
        ys, xs = np.nonzero(m)
        y0, y1, x0, x1 = max(0, ys.min() - 12), min(arr.shape[0], ys.max() + 13), max(0, xs.min() - 12), min(arr.shape[1], xs.max() + 13)
        c, mm = arr[y0:y1, x0:x1].astype(np.float32), m[y0:y1, x0:x1]
        c[~mm] = c[~mm] * 0.35 + 255 * 0.65
        edge = binary_dilation(mm & ~binary_erosion(mm, iterations=1), iterations=2)
        c[edge] = COLOURS[k % len(COLOURS)]
        ci = Image.fromarray(c.astype(np.uint8))
        s = min((width - 80) / ci.width, max(1.0, 110 / ci.height), 3.0)
        ci = ci.resize((max(1, int(ci.width * s)), max(1, int(ci.height * s))), Image.LANCZOS)
        row = Image.new("RGB", (width, ci.height + 12), (255, 255, 255))
        ImageDraw.Draw(row).text((8, 4), str(k + 1), fill=COLOURS[k % len(COLOURS)], font=font(40))
        row.paste(ci, (72, 6))
        rows.append(row)
    sheet = Image.new("RGB", (width, sum(r.height for r in rows) or 1), (190, 190, 190))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    return sheet


def hints_text(masks: list[np.ndarray], w: int, h: int) -> str:
    """Each element's box in the panel (shares of its size). The segmenter's kind is not passed: on P&C 37-39 it
    called free sound-effect words "bubble", and the model followed it some of the time (2026-11-01)."""
    lines = []
    for k, m in enumerate(masks):
        ys, xs = np.nonzero(m)
        lines.append(f"{k + 1}: box ({xs.min() / w:.2f},{ys.min() / h:.2f})-({xs.max() / w:.2f},{ys.max() / h:.2f})")
    return "\n".join(lines)


def transcribe(img: Image.Image, masks: list[np.ndarray], kinds: list[str], tag: str,
               model: str = MODEL) -> tuple[dict, float]:
    """One box read by one model: (result, cost in USD). Raises BudgetExceeded before a call the daily cap forbids."""
    prompt = INSTRUCTIONS.format(hints=hints_text(masks, img.width, img.height))
    content = [{"type": "text", "text": prompt}, image_part(numbered_overlay(img, masks)), image_part(crops_sheet(img, masks))]
    empty = {"elements": []}
    try:
        result, cost = ask_json(model, content, tag, MAX_TOKENS, REASONING.get(model), system=SYSTEM, brief=False)
        if not result:  # no JSON in the reply: marked, not read as a box with nothing to say
            result = {**empty, "error": "no JSON in the reply"}
    except Truncated as e:
        result, cost = {**empty, "error": "truncated: the reply spent its whole token budget"}, e.cost
    return enforce(result, kinds), cost


def read(img: Image.Image, masks: list[np.ndarray], kinds: list[str], tag: str,
         model: str = MODEL) -> tuple[dict, Image.Image]:
    """(the box's result, its report picture). A box with a kept element whose kind Haiku doubted (its "doubt":
    balloon-less lettering, a box without a tail, a split word, a label beside a figure, an unclear sound maker) is
    read again by SECOND_MODEL, and for those elements its kind replaces Haiku's ("kind_by": "sonnet", Haiku's under
    "kind_haiku"); its text too when Haiku read none. Raises BudgetExceeded before a call the daily cap forbids."""
    result, _ = transcribe(img, masks, kinds, tag, model)
    doubted = [e for e in result.get("elements", []) if e.get("keep") and e.get("doubt")]
    with _second_lock:
        room = _second["usd"] < _second["cap"]
    if doubted and model == MODEL and room:
        second, cost = transcribe(img, masks, kinds, f"{tag} second opinion", SECOND_MODEL)
        with _second_lock:
            _second["usd"] += cost
        by_id = {e.get("id"): e for e in second.get("elements", [])}
        for e in doubted:
            s = by_id.get(e.get("id"))
            if s and s.get("kind"):
                e["kind_haiku"], e["kind"], e["kind_by"] = e.get("kind"), s["kind"], "sonnet"
                if not (e.get("text") or "").strip() and s.get("text"):
                    e["text"] = s["text"]
    return result, report(img, masks, result, tag)


def read_boxes(jobs: dict[int, tuple[Image.Image, list[np.ndarray], list[str], str]],
               model: str = MODEL) -> tuple[dict[int, dict], dict[int, Image.Image]]:
    """read() on many boxes at once (spend.paid_map), {box index: (img, masks, kinds, tag)} -> (results, pictures).
    The boxes the daily cap stops are left out, for the next run to read."""
    done, _ = paid_map(lambda i: read(*jobs[i], model), list(jobs))
    return {i: r for i, (r, _) in done.items()}, {i: p for i, (_, p) in done.items()}


def update(ep: Episode, imgs: dict[int, Image.Image], letters: dict[int, list]) -> dict[int, Image.Image]:
    """Step 5 for an episode: every box whose transcript was not made from its current lettering
    (Box.transcript_current) is read (read_boxes, in parallel) and saved stamped with that lettering
    (Episode.save_transcripts); a box the daily cap refuses is skipped, the others are kept. Returns the report
    picture per box read."""
    jobs = {i: (img, [f.mask for f in letters[i]], [f.kind for f in letters[i]], f"{ep.stem} p{i}")
            for i, img in imgs.items() if not ep.box(i).transcript_current(letters[i])}
    print(f"  {len(jobs)} of {len(imgs)} boxes to read ({len(imgs) - len(jobs)} current or without lettering)")
    with _second_lock:
        _second["usd"] = 0.0
    results, pictures = read_boxes(jobs)
    ep.save_transcripts(results, letters)
    n = sum(1 for r in results.values() for e in r.get("elements", []) if e.get("doubt"))
    m = sum(1 for r in results.values() for e in r.get("elements", []) if e.get("kind_by") == "sonnet")
    print(f"  {n} elements doubted, {m} retyped by {SECOND_MODEL.split('/')[-1]} for {_second['usd']:.3f} USD"
          + (f" (cap {_second['cap']} reached)" if _second["usd"] >= _second["cap"] else ""))
    return pictures


def enforce(result: dict, kinds: list[str]) -> dict:
    """Dialogue is never dropped on the model's say-so: a segmented bubble or caption stays unless the model marks
    it in-world text (a screen, a sign, a printed page). The model dropped real bubbles and captions as "part of
    another element" or "outline cuts through" (Tower of God 223 p48, True Beauty 7 p49 and p50)."""
    for e in result.get("elements", []):
        i = e.get("id")
        if not isinstance(i, int) or not 1 <= i <= len(kinds):
            continue
        in_world = bool(e.get("in_world"))
        if kinds[i - 1] in ("bubble", "caption"):
            if not e.get("keep") and not in_world:
                e["overruled"] = e.get("issue")
            e["keep"] = not in_world
        elif in_world:
            e["keep"] = False
    return result


def report(img: Image.Image, masks: list[np.ndarray], result: dict, title: str) -> Image.Image:
    ov = numbered_overlay(img, masks)
    scale = min(1.0, 900 / ov.height)
    ov = ov.resize((int(ov.width * scale), int(ov.height * scale)))
    lines = [title, ""]
    for e in result.get("elements", []):
        mark = "KEEP" if e.get("keep") else "DROP"
        lines.append(f"#{e.get('id')} {mark} {e.get('kind', '')}")
        lines.append(f"    {str(e.get('text', ''))[:70]}")
        if not e.get("keep") and e.get("issue"):
            lines.append(f"    issue: {str(e['issue'])[:70]}")
    if result.get("error"):
        lines.append("PARSE ERROR: " + result["error"][:200])
    out = Image.new("RGB", (ov.width + 640, max(ov.height, 20 * len(lines) + 20)), (255, 255, 255))
    out.paste(ov, (0, 0))
    d = ImageDraw.Draw(out)
    for k, line in enumerate(lines):
        d.text((ov.width + 10, 10 + 20 * k), line, fill=(180, 0, 0) if " DROP " in line else (0, 0, 0), font=font(15))
    return out


def run(model: str, zumi: Path, episode_out: Path, out: Path, picks: list[int]) -> dict:
    """The CLI's comparison run: `model` on the boxes of a chapter, from the lettering an episode run saved
    (episode_out, boxstore), a report image per box and one json per model under out/."""
    from boxstore import Box
    from chapter import Chapter
    ch = Chapter(zumi)
    slug = model.replace("/", "_")
    jobs = {}
    for i in picks:
        found = Box(episode_out, ch.pid(i)).letters() or []
        if found:
            jobs[i] = (ch.image(i), [f.mask for f in found], [f.kind for f in found], f"{ch.stem} p{i}")
    s0 = spent_today()
    results, pictures = read_boxes(jobs, model)
    (out / slug).mkdir(parents=True, exist_ok=True)
    for i, picture in pictures.items():
        picture.save(out / slug / f"{ch.pid(i)}.png")
    (out / slug / f"{ch.stem}.json").write_text(json.dumps({"panels": results}, indent=1, ensure_ascii=False))
    print(f"{model}: {len(results)} boxes, {spent_today() - s0:.4f} USD, today {spent_today():.3f}")
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("episode_out", type=Path, help="an episode run's out dir: its saved lettering is read")
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", required=True)
    ap.add_argument("--models", default=MODEL)
    a = ap.parse_args()
    picks = [int(x) for x in a.panels.split(",")]
    for model in a.models.split(","):
        run(model, a.zumi, a.episode_out, a.out, picks)


if __name__ == "__main__":
    main()
