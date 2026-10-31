"""Step 5, Transcribe: a vision model reads the text of every segmented lettering element of a box, its kind, and
whether the element is lettering at all. It does not say who speaks (user, 2026-10-31): speakers.py decides that from
the cards, and identity across boxes is a step of its own.

    result, picture = read(img, masks, kinds, tag)   # boxes are independent: episode.transcribe_step runs them in parallel
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
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, binary_erosion

from openrouter import BudgetExceeded, Truncated, ask_json, image_part, spent_today

MODEL = "meta-llama/llama-4-maverick"
REASONING = {"meta/muse-spark-1.3": "low", "google/gemini-3.8-flash": "low"}  # reasoning models only
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (240, 50, 230), (0, 128, 128), (170, 110, 40)]
WORKERS = 8

SYSTEM = """You transcribe the lettering of webtoon panels for a reading app that erases the original lettering and \
redraws each bubble as live text. You are precise and never invent text."""

INSTRUCTIONS = """Image 1 is a webtoon panel. Each element found by an automatic segmenter is outlined in colour and \
numbered. Image 2 shows each element cropped at full resolution with its outline drawn; everything outside the \
outline is faded.

Elements, with what the segmenter measured:
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
- "kind": one of "speech", "thought", "shout", "caption", "sfx".
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


def hints_text(masks: list[np.ndarray], kinds: list[str], w: int, h: int) -> str:
    lines = []
    for k, (m, kind) in enumerate(zip(masks, kinds)):
        ys, xs = np.nonzero(m)
        lines.append(f"{k + 1}: looks like {kind}, box ({xs.min() / w:.2f},{ys.min() / h:.2f})-({xs.max() / w:.2f},{ys.max() / h:.2f})")
    return "\n".join(lines)


def transcribe(img: Image.Image, masks: list[np.ndarray], kinds: list[str], tag: str,
               model: str = MODEL) -> tuple[dict, float]:
    """One box read: (result, cost in USD). Raises BudgetExceeded before a call the daily cap forbids."""
    prompt = INSTRUCTIONS.format(hints=hints_text(masks, kinds, img.width, img.height))
    content = [{"type": "text", "text": prompt}, image_part(numbered_overlay(img, masks)), image_part(crops_sheet(img, masks))]
    empty = {"elements": []}
    try:
        result, cost = ask_json(model, content, tag, 2500, REASONING.get(model), system=SYSTEM, brief=False)
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
    """read() on many boxes at once, {box index: (img, masks, kinds, tag)} -> (results, pictures). A box the daily cap
    refuses is left out and a line printed; the others still run."""
    def one(item):
        i, (img, masks, kinds, tag) = item
        try:
            return i, read(img, masks, kinds, tag, model)
        except BudgetExceeded as e:
            print(f"STOP {tag}: {e}")
            return i, None
    results, pictures = {}, {}
    with ThreadPoolExecutor(WORKERS) as ex:
        for i, got in ex.map(one, jobs.items()):
            if got is not None:
                results[i], pictures[i] = got
    return results, pictures


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
