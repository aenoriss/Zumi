"""Step 5, Transcribe: a vision model reads the text of every segmented lettering element of a box, its kind, and
whether the element is lettering at all. It does not say who speaks (user, 2026-10-31): speakers.py decides that from
the cards, and identity across boxes is a step of its own.

    result, picture = read(img, masks, kinds, tag)   # one box
    results, pictures = read_boxes({i: (img, masks, kinds, tag)})   # many, in parallel (spend.paid_map)
    uv run python transcribe.py <episode.zumi> <episode out dir> <out dir> --panels 1,2,3 [--models a,b]

One call per box with two images: the box with each element outlined and numbered, and each element cropped at full
resolution with its outline drawn and everything outside it faded, so the model reads only that element's letters.
Per element the model returns the text, the kind (speech, thought, shout, caption, sfx), keep (one whole element)
and in_world (text drawn in the scene: a screen, a sign, a printed page); enforce turns those into the one keep the
layers use. Paid calls go through openrouter.ask_json (the shared daily cap); a reply cut off at its budget, or with
no JSON in it, gives an empty result marked "error".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, binary_erosion

from openrouter import Truncated, ask_json, image_part
from spend import paid_map, spent_today

# Claude Haiku 5.5 (2026-11-01): on the 670 labelled lines of P&C 36-39 its kinds matched the speaker labels 650 times,
# Llama 4 Maverick's 598 (old prompt) to 619; Maverick also left elements out. Both about 0.0007 USD a box.
MODEL = "anthropic/claude-haiku-5.5"
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
annotations are lettering: a word or short phrase written over the art to label a feeling or an action, often with \
an arrow or lines pointing at a character (IGNORED, SHY, BLUSH, STARE): keep, kind "sfx". When unsure, keep it.
- "in_world": true only if the text belongs to the drawn world rather than the comic's lettering: a phone or \
computer screen, a chat or social-media interface, a sign or poster, a letter, book or printed page, text on \
clothing or objects. false for every speech bubble, thought bubble, caption and sound effect.
- "issue": when keep is false or in_world is true, a few words saying why; otherwise null.
- "kind": who the words belong to, read from the words and from what surrounds them in image 2:
  - "speech": words a character says, in a balloon (a drawn shape with an outline around the letters, often with \
a tail toward the speaker). Its shape can be round, rectangular or dark: a rectangular or dark box holding a \
character's own words ("Oh, my...") is speech, not a caption. Song lyrics in a balloon (often with music notes) are \
speech. A single word that sounds like a noise is speech when it sits in a balloon: "Oh?!", "Tsk!", "GRRR...!".
  - "shout": a character's words in a spiky or jagged balloon, or in large bold letters.
  - "thought": a character's unspoken words: a cloud-shaped balloon, a balloon joined by small circles, or words \
floating near a character with no balloon at all.
  - "caption": the narrator's words, not a character's: time, place, or story told from outside ("Meanwhile...", \
"North of the city..."), usually in a rectangular box at the edge of the panel with no tail.
  - "sfx": the sound of something happening, drawn straight on the art with no balloon: usually one or a few \
stylised, coloured or slanted words ("CREEEE", "Dzing", "TING-A-LING!", "BOOM"), or a comic annotation. A sentence \
("Agh... It didn't work on them.") is never sfx, and nothing inside a balloon is.
- "text": exactly the words inside this element's own coloured outline in image 2, line breaks as single spaces, \
keeping punctuation. Faded words in image 2 lie outside the outline and belong to another element: never include them.

Answer with JSON only:
{{"elements": [{{"id": 1, "keep": true, "in_world": false, "issue": null, "kind": "speech", "text": "..."}}]}}"""


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
    """One box read: (result, cost in USD). Raises BudgetExceeded before a call the daily cap forbids."""
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
    """(the box's result, its report picture). Raises BudgetExceeded before a call the daily cap forbids."""
    result, _ = transcribe(img, masks, kinds, tag, model)
    return result, report(img, masks, result, tag)


def read_boxes(jobs: dict[int, tuple[Image.Image, list[np.ndarray], list[str], str]],
               model: str = MODEL) -> tuple[dict[int, dict], dict[int, Image.Image]]:
    """read() on many boxes at once (spend.paid_map), {box index: (img, masks, kinds, tag)} -> (results, pictures).
    The boxes the daily cap stops are left out, for the next run to read."""
    done, _ = paid_map(lambda i: read(*jobs[i], model), list(jobs))
    return {i: r for i, (r, _) in done.items()}, {i: p for i, (_, p) in done.items()}


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
