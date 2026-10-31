"""Step 5, Understand: a vision model reads, checks and attributes every segmented element of a panel.

    reader = Reader(); result, picture = reader.read(img, masks, kinds, panel, tag, previous)   # box by box, in order
    uv run python understand.py <episode.zumi> <episode out dir> <out dir> --panels 1,2,3 [--models a,b]

Panels are processed in reading order and carry context (the Reader): the running cast (ids, names, looks) and the
last lines of dialogue, so names said earlier and off-panel speakers resolve. Per panel, one call with two images:
the panel with each element outlined, numbered and, for bubbles, an arrow along the tail; and each element
cropped at full resolution with its outline drawn and everything outside it dimmed, so the model can judge the
mask itself. Tail tips are computed from the masks and also passed as numbers, so the model only has to say
who is at the tip. Per element the model returns keep (one whole bubble, caption or sound effect and nothing
else), the text inside that outline, the kind, the speaker (cast id, narrator, environment or unknown), a
confidence and an anchor on the speaker. Paid calls go through openrouter.ask_json (2 USD/day cap); a reply cut
off at its budget, or with no JSON in it, gives an empty result marked "error".
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt, label

from openrouter import BudgetExceeded, Truncated, ask_json, image_part, spent_today

MODELS = ["meta-llama/llama-4-maverick"]
REASONING = {"meta/muse-spark-1.3": "low", "google/gemini-3.8-flash": "low"}  # reasoning models only
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (240, 50, 230), (0, 128, 128), (170, 110, 40)]
CONTEXT_LINES = 12

SYSTEM = """You prepare webtoon panels for a reading app that erases the original lettering, redraws each \
bubble as live text and voices every line with the right character's voice. You are precise and never invent text."""

INSTRUCTIONS = """Image 1 is panel {panel} of a webtoon episode, read top to bottom. Each element found by an \
automatic segmenter is outlined in colour and numbered; bubbles with a tail have an arrow along the tail. Image 2 \
shows each element cropped at full resolution with its outline drawn; everything outside the outline is faded. \
{previous}

Characters known so far in this episode:
{cast}

Dialogue just before this panel (oldest first):
{transcript}

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
- "speaker": always fill it. Rules, in order:
  1. A bubble with a tail: the character at or just beyond the tail tip.
  2. A sound effect that is a person's action or feeling (whispering, waving, a heartbeat THUMP, SHY, a gasp, \
running DASH, a scream) belongs to that person: the one doing it or next to it. "environment" only for sounds of \
objects, nature or impacts with no one making them (a door, rain, an engine, rumbling ground, splashing water).
  3. A bubble or thought without a tail: the character it sits on or next to; if none is visible, whoever the \
conversation implies: lines usually alternate between the people talking, and a thought bubble in a panel with no \
one visible belongs to the character whose thoughts the recent panels follow.
  4. A word like "SUA!" or "WELL DONE, ENKIDU." names the person being spoken TO, never the speaker.
  5. "narrator" for narration captions (text boxes telling the story, often in first person, outside any bubble).
  6. "unknown" only if none of the above decides it.
  Use a known id when that character could be the one (same hair, same clothes, or the conversation continues); \
add a new character only for someone clearly not in the list.
- "confidence": "high", "medium" or "low" for the speaker.
- "anchor": [x, y] in 0..1 coordinates of image 1 (0,0 top-left) on the speaker's mouth or head, or on the sound's \
source; null if the speaker is not visible.

New characters go in "new_cast" with "id" (snake_case: the name if they are named, otherwise a short description \
such as "girl_red_hoodie"), "name" ("" if unknown) and "look" (one line: hair, clothes, anything that identifies \
them later). When a line names someone ("ENKIDU", "SUA"), that name belongs to the listener: if you can tell who \
the listener is, add {{"id": <their id>, "name": <name>}} to "names". Give the panel "mood" in a few words.

Answer with JSON only:
{{"elements": [{{"id": 1, "keep": true, "in_world": false, "issue": null, "kind": "speech", "text": "...", "speaker": "...", "confidence": "high", "anchor": [0.5, 0.3]}}],
  "new_cast": [{{"id": "...", "name": "...", "look": "..."}}], "names": [], "mood": "..."}}"""


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def tail(m: np.ndarray) -> tuple[tuple[float, float], tuple[float, float]] | None:
    """(base, tip) of a bubble's tail in pixel (x, y), or None if the shape has no single clear tail.

    Opening the mask with a disk about an eighth of the bubble's size removes thin protrusions; the tail is the
    largest removed piece, if it is clearly larger than the next (a burst's spikes are many similar pieces), and its
    tip is the point farthest from what remains.
    """
    ys, xs = np.nonzero(m)
    y0, x0 = ys.min(), xs.min()
    crop = m[y0 : ys.max() + 1, x0 : xs.max() + 1]
    s = min(1.0, 220 / max(crop.shape))
    small = np.asarray(Image.fromarray(crop).resize((max(1, int(crop.shape[1] * s)), max(1, int(crop.shape[0] * s))), Image.NEAREST))
    r = max(2.0, 0.12 * min(small.shape))
    padded = np.pad(small, 1)  # the crop edge counts as outside
    core = distance_transform_edt(padded) > r
    if not core.any():
        return None
    body = (distance_transform_edt(~core) <= r)[1:-1, 1:-1] & small  # opening with an exact disk
    rest = small & ~body
    pieces, n = label(rest)
    if n == 0:
        return None
    # A tail touches the body through a narrow neck and reaches far from it. Score = reach / neck width:
    # a rectangle's rounded-off corners and a burst's spikes meet the body along a wide arc or reach about the same,
    # specks in a noisy mask do not touch the body at all.
    dist = distance_transform_edt(~body)
    reach = np.zeros(n + 1)
    np.maximum.at(reach, pieces.ravel(), dist.ravel())
    rim = binary_dilation(body, iterations=2) & rest
    neck = np.bincount(pieces[rim], minlength=n + 1).astype(float)
    candidate = (neck > 0) & (reach >= 0.5 * r)  # outline nubs a pixel or two high do not compete
    score = np.where(candidate, reach / np.maximum(neck, 1.0), 0.0)[1:]
    reach = reach[1:]
    order = np.argsort(score)[::-1]
    if score[order[0]] == 0 or reach[order[0]] < 0.7 * r or (n > 1 and score[order[0]] < 1.6 * score[order[1]]):
        return None
    piece = pieces == order[0] + 1
    py, px = np.nonzero(piece)
    k = np.argmax(dist[py, px])
    tip = (x0 + px[k] / s, y0 + py[k] / s)
    by, bx = np.nonzero(piece & binary_dilation(body, iterations=2))
    base = (x0 + bx.mean() / s, y0 + by.mean() / s) if len(bx) else tip
    if np.hypot(tip[0] - base[0], tip[1] - base[1]) < 0.03 * max(crop.shape):
        return None
    return base, tip


def direction(base: tuple[float, float], tip: tuple[float, float]) -> str:
    dx, dy = tip[0] - base[0], tip[1] - base[1]
    v = "down" if dy > abs(dx) * 0.4 else "up" if -dy > abs(dx) * 0.4 else ""
    h = "right" if dx > abs(dy) * 0.4 else "left" if -dx > abs(dy) * 0.4 else ""
    return "-".join(p for p in (v, h) if p) or "?"


def numbered_overlay(img: Image.Image, masks: list[np.ndarray], tails: list) -> Image.Image:
    out = np.asarray(img.convert("RGB")).copy()
    t = max(2, img.width // 250)
    for k, m in enumerate(masks):
        edge = binary_dilation(m & ~binary_erosion(m, iterations=1), iterations=t)
        out[edge] = COLOURS[k % len(COLOURS)]
    im = Image.fromarray(out)
    d = ImageDraw.Draw(im)
    size = max(18, img.width // 22)
    for k, (m, tl) in enumerate(zip(masks, tails)):
        c = COLOURS[k % len(COLOURS)]
        if tl:
            (bx, by), (tx, ty) = tl
            ex, ey = tx + (tx - bx) * 0.6, ty + (ty - by) * 0.6  # extend past the tip, toward the speaker
            d.line([(bx, by), (ex, ey)], fill=c, width=t * 2)
            a = np.arctan2(ey - by, ex - bx)
            for da in (2.6, -2.6):
                d.line([(ex, ey), (ex + size * 0.6 * np.cos(a + da), ey + size * 0.6 * np.sin(a + da))], fill=c, width=t * 2)
        ys, xs = np.nonzero(m)
        x, y = int(xs.min()), int(ys.min())
        d.rectangle([(x, y), (x + size * 1.4, y + size * 1.2)], fill=c)
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


def hints_text(masks: list[np.ndarray], kinds: list[str], tails: list, w: int, h: int) -> str:
    lines = []
    for k, (m, kind, tl) in enumerate(zip(masks, kinds, tails)):
        ys, xs = np.nonzero(m)
        box = f"box ({xs.min() / w:.2f},{ys.min() / h:.2f})-({xs.max() / w:.2f},{ys.max() / h:.2f})"
        tail_s = f", tail points {direction(*tl)} to ({tl[1][0] / w:.2f}, {tl[1][1] / h:.2f})" if tl else ", no tail"
        lines.append(f"{k + 1}: looks like {kind}, {box}{tail_s}")
    return "\n".join(lines)


def cast_text(cast: list[dict]) -> str:
    return "\n".join(f'- {c["id"]}: name {c.get("name") or "unknown"}; {c.get("look", "")}' for c in cast) or "(none yet)"


def normalise(result: dict, w: int, h: int) -> dict:
    for e in result.get("elements", []):
        a = e.get("anchor")
        if isinstance(a, list) and len(a) == 2 and all(isinstance(v, (int, float)) for v in a):
            if max(a) > 1.5:  # pixels instead of 0..1
                a = [a[0] / w, a[1] / h]
            e["anchor"] = [min(1.0, max(0.0, float(a[0]))), min(1.0, max(0.0, float(a[1])))]
        else:
            e["anchor"] = None
    return result


def understand(model: str, img: Image.Image, masks: list[np.ndarray], kinds: list[str], cast: list[dict],
               transcript: list[str], panel: int, tag: str, previous: Image.Image | None = None) -> tuple[dict, float, list]:
    """One panel read with the given context: (result, cost in USD, the tails drawn for it)."""
    tails = [tail(m) if kind != "sfx" else None for m, kind in zip(masks, kinds)]
    overlay = numbered_overlay(img, masks, tails)
    prompt = INSTRUCTIONS.format(
        panel=panel, cast=cast_text(cast), transcript="\n".join(transcript[-CONTEXT_LINES:]) or "(start of the excerpt)",
        hints=hints_text(masks, kinds, tails, img.width, img.height),
        previous="Image 3 is the panel just before, small, only to show who is present and who is talking." if previous else "",
    )
    content = [{"type": "text", "text": prompt}, image_part(overlay), image_part(crops_sheet(img, masks))]
    if previous is not None:
        content.append(image_part(previous, max_side=640, quality=80))
    empty = {"elements": [], "new_cast": [], "names": [], "mood": ""}
    try:
        result, cost = ask_json(model, content, tag, 2500, REASONING.get(model), system=SYSTEM, brief=False)
        if not result:  # no JSON in the reply: marked, not read as a panel with nothing to say
            result = {**empty, "error": "no JSON in the reply"}
    except Truncated as e:
        result, cost = {**empty, "error": "truncated: the reply spent its whole token budget"}, e.cost
    return enforce(normalise(result, img.width, img.height), kinds), cost, tails


class Reader:
    """Understand over the boxes of one episode, in reading order: the cast and the transcript one box leaves are
    the context the next is read with."""

    def __init__(self, model: str = MODELS[0]):
        self.model = model
        self.cast: list[dict] = []
        self.transcript: list[str] = []
        self.cost = 0.0

    def read(self, img: Image.Image, masks: list[np.ndarray], kinds: list[str], panel: int, tag: str,
             previous: Image.Image | None = None) -> tuple[dict, Image.Image]:
        """(the box's result, its report picture). Raises BudgetExceeded before a call the daily cap forbids."""
        result, cost, tails = understand(self.model, img, masks, kinds, self.cast, self.transcript, panel, tag, previous)
        self.cost += cost
        update_context(result, self.cast, self.transcript, panel)
        return result, report(img, masks, tails, result, tag)


def update_context(result: dict, cast: list[dict], transcript: list[str], panel: int) -> None:
    """The running cast (new characters, names learned) and transcript (kept dialogue lines) after one panel's
    result, in place: the context the next panel is read with."""
    known = {c["id"] for c in cast}
    cast += [c for c in result.get("new_cast", []) if c.get("id") and c["id"] not in known]
    for upd in result.get("names", []):
        for c in cast:
            if c["id"] == upd.get("id") and upd.get("name"):
                c["name"] = upd["name"]
    names = {c["id"]: c.get("name") or c["id"] for c in cast}
    for e in result.get("elements", []):
        if e.get("keep") and e.get("text") and e.get("kind") != "sfx":
            transcript.append(f'p{panel} {names.get(e.get("speaker"), e.get("speaker"))}: {e["text"]}')


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


def report(img: Image.Image, masks: list[np.ndarray], tails: list, result: dict, title: str) -> Image.Image:
    ov = numbered_overlay(img, masks, tails)
    scale = min(1.0, 900 / ov.height)
    ov = ov.resize((int(ov.width * scale), int(ov.height * scale)))
    d = ImageDraw.Draw(ov)
    for e in result.get("elements", []):
        if e.get("anchor"):
            x, y = e["anchor"][0] * ov.width, e["anchor"][1] * ov.height
            d.ellipse([(x - 7, y - 7), (x + 7, y + 7)], fill=(255, 255, 0), outline=(0, 0, 0), width=2)
            d.text((x + 9, y - 8), str(e.get("speaker", "")), fill=(255, 255, 0), font=font(14), stroke_width=2, stroke_fill=(0, 0, 0))
    lines = [title, f"mood: {result.get('mood', '')}", ""]
    for e in result.get("elements", []):
        mark = "KEEP" if e.get("keep") else "DROP"
        lines.append(f"#{e.get('id')} {mark} {e.get('kind', '')} [{e.get('speaker', '')}] ({e.get('confidence', '')})")
        lines.append(f"    {str(e.get('text', ''))[:70]}")
        if not e.get("keep") and e.get("issue"):
            lines.append(f"    issue: {str(e['issue'])[:70]}")
    for c in result.get("new_cast", []):
        lines.append(f"+ cast {c.get('id')}: {c.get('name') or '?'}; {str(c.get('look', ''))[:60]}")
    for c in result.get("names", []):
        lines.append(f"= name {c.get('id')}: {c.get('name')}")
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
    reader, results = Reader(model), {}
    for i in picks:
        found = Box(episode_out, ch.pid(i)).letters() or []
        if not found:
            continue
        cost0 = reader.cost
        result, picture = reader.read(ch.image(i), [f.mask for f in found], [f.kind for f in found], i,
                                      f"{ch.stem} p{i}", ch.image(i - 1) if i > 0 else None)
        results[i] = result
        (out / slug).mkdir(parents=True, exist_ok=True)
        picture.save(out / slug / f"{ch.pid(i)}.png")
        print(f"{model:32s} p{i:3d}: {len(result.get('elements', []))} elements, cost {reader.cost - cost0:.4f} USD, today {spent_today():.3f}")
    (out / slug / f"{ch.stem}.json").write_text(json.dumps({"cast": reader.cast, "panels": results}, indent=1,
                                                           ensure_ascii=False))
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("episode_out", type=Path, help="an episode run's out dir: its saved lettering is read")
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", required=True)
    ap.add_argument("--models", default=",".join(MODELS))
    a = ap.parse_args()
    picks = [int(x) for x in a.panels.split(",")]
    for model in a.models.split(","):
        try:
            run(model, a.zumi, a.episode_out, a.out, picks)
        except BudgetExceeded as e:
            print(f"STOP: {e}")
            return


if __name__ == "__main__":
    main()
