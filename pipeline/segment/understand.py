"""Step 2c, Understand: a vision model reads, checks and attributes every segmented element of a panel.

    uv run python understand.py <episode.zumi> <masks dir> <out dir> --panels 1,17,31 [--models a,b]

Per panel, one call with two images: the panel with each mask outlined and numbered, and the elements cropped
at full resolution with the same numbers. The model returns, per element: keep (is the mask one whole bubble,
caption or sound effect and nothing else), the text, its kind, who or what it belongs to (a character from the
running cast, the narrator, or the environment) and an anchor point on that speaker. New characters join the
cast, which is carried from panel to panel so a character keeps one id all episode. Paid calls go through
openrouter.chat (2 USD/day cap).
"""

from __future__ import annotations

import argparse
import io
import json
import re
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, binary_erosion

from bubbles import load_masks
from openrouter import BudgetExceeded, chat, image_part, spent_today

MODELS = ["meta/muse-spark-1.3", "meta-llama/llama-4-maverick", "google/gemini-3.8-flash"]
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (240, 50, 230), (0, 128, 128), (170, 110, 40)]

SYSTEM = """You prepare webtoon panels for a reading app that erases the original lettering, redraws each \
bubble as live text and voices every line with the right character's voice. You are precise and never invent text."""

INSTRUCTIONS = """Image 1 is a comic panel. Each element found by an automatic segmenter is outlined in colour and \
numbered. Image 2 shows each element cropped at full resolution with the same number.

Characters already known in this episode (reuse these ids):
{cast}

For every numbered element decide:
- "keep": true only if its outline covers exactly one whole speech bubble, thought bubble, caption box or sound \
effect, including its tail, and nothing else. false if the outline cuts through the bubble or its letters, merges \
two separate bubbles, includes art that is not part of it, or the element is not lettering at all.
- "issue": when keep is false, a few words saying why; otherwise null.
- "kind": one of "speech", "thought", "shout", "caption", "sfx".
- "text": the exact words as written, line breaks as single spaces, keeping punctuation. Empty string if none.
- "speaker": who says it or makes the sound: a cast id from the list, a new id you add to new_cast, "narrator" \
for narration captions, "environment" for a sound not made by a character (a door, footsteps of someone unseen, \
wind), or "unknown". Follow the bubble's tail when there is one.
- "anchor": [x, y] in 0..1 panel coordinates (0,0 top-left) on the speaker's mouth or head, or on the sound's \
source; null for narrator or when the speaker is outside the panel.

Add every new character to "new_cast" with "id" (snake_case: the name if it is said or certain, otherwise a short \
description such as "girl_red_hoodie"), "name" (the name, or "" if unknown) and "look" (one line: hair, clothes, \
age, anything that identifies them in later panels).
Also give the panel "mood" in a few words (setting and feeling, for music and ambience).

Segmenter guesses for the elements, by number: {hints}

Answer with JSON only, no prose:
{{"elements": [{{"id": 1, "keep": true, "issue": null, "kind": "speech", "text": "...", "speaker": "...", "anchor": [0.5, 0.3]}}],
  "new_cast": [{{"id": "...", "name": "...", "look": "..."}}], "mood": "..."}}"""


def font(size: int) -> ImageFont.ImageFont:
    return ImageFont.load_default(size=size)


def numbered_overlay(img: Image.Image, masks: list[np.ndarray]) -> Image.Image:
    """The panel with each mask's outline drawn in a distinct colour and its number in a tag at the top-left."""
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
    """Each element's box cropped from the original panel, numbered, stacked top to bottom."""
    rows = []
    for k, m in enumerate(masks):
        ys, xs = np.nonzero(m)
        c = img.crop((max(0, xs.min() - 6), max(0, ys.min() - 6), min(img.width, xs.max() + 7), min(img.height, ys.max() + 7)))
        s = min((width - 80) / c.width, max(1.0, 90 / c.height), 3.0)
        c = c.resize((max(1, int(c.width * s)), max(1, int(c.height * s))), Image.LANCZOS)
        row = Image.new("RGB", (width, c.height + 12), (255, 255, 255))
        ImageDraw.Draw(row).text((8, 4), str(k + 1), fill=COLOURS[k % len(COLOURS)], font=font(40))
        row.paste(c, (72, 6))
        rows.append(row)
    sheet = Image.new("RGB", (width, sum(r.height for r in rows) or 1), (200, 200, 200))
    y = 0
    for r in rows:
        sheet.paste(r, (0, y))
        y += r.height
    return sheet


def parse(text: str) -> dict:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M)
    a, b = text.find("{"), text.rfind("}")
    return json.loads(text[a : b + 1])


def understand(model: str, img: Image.Image, masks: list[np.ndarray], kinds: list[str], cast: list[dict], tag: str) -> tuple[dict, dict]:
    cast_text = "\n".join(f'- {c["id"]}: {c.get("name") or "(name unknown)"}; {c.get("look", "")}' for c in cast) or "(none yet)"
    hints = ", ".join(f"{k + 1}: {kind}" for k, kind in enumerate(kinds))
    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": [
            {"type": "text", "text": INSTRUCTIONS.format(cast=cast_text, hints=hints)},
            image_part(numbered_overlay(img, masks)),
            image_part(crops_sheet(img, masks)),
        ]},
    ]
    text, usage = chat(model, messages, max_tokens=6000, tag=tag)
    try:
        result = parse(text)
    except (ValueError, json.JSONDecodeError):
        result = {"elements": [], "new_cast": [], "mood": "", "error": text[:500]}
    return result, usage


def report(img: Image.Image, masks: list[np.ndarray], result: dict, title: str) -> Image.Image:
    """Numbered overlay with anchors, beside the model's verdict for each element."""
    ov = numbered_overlay(img, masks)
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
        lines.append(f"#{e.get('id')} {mark} {e.get('kind', '')} [{e.get('speaker', '')}]")
        lines.append(f"    {e.get('text', '')[:70]}")
        if not e.get("keep") and e.get("issue"):
            lines.append(f"    issue: {e['issue'][:70]}")
    for c in result.get("new_cast", []):
        lines.append(f"+ cast {c.get('id')}: {c.get('name') or '?'}; {c.get('look', '')[:60]}")
    if result.get("error"):
        lines.append("PARSE ERROR: " + result["error"][:200])
    panel_w = 620
    out = Image.new("RGB", (ov.width + panel_w, max(ov.height, 20 * len(lines) + 20)), (255, 255, 255))
    out.paste(ov, (0, 0))
    d = ImageDraw.Draw(out)
    for k, line in enumerate(lines):
        colour = (180, 0, 0) if " DROP " in line else (0, 0, 0)
        d.text((ov.width + 10, 10 + 20 * k), line, fill=colour, font=font(15))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("masks", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", required=True)
    ap.add_argument("--models", default=",".join(MODELS))
    a = ap.parse_args()

    z = zipfile.ZipFile(a.zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    for model in a.models.split(","):
        slug = model.replace("/", "_")
        cast: list[dict] = []
        results = {}
        for i in [int(x) for x in a.panels.split(",")]:
            found = load_masks(a.masks / f"{a.zumi.stem}-p{i:03d}.npz")
            if not found:
                continue
            img = Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
            try:
                result, usage = understand(model, img, [f.mask for f in found], [f.kind for f in found], cast, f"{a.zumi.stem} p{i}")
            except BudgetExceeded as e:
                print(f"STOP: {e}")
                return
            cast += [c for c in result.get("new_cast", []) if c.get("id") not in {k["id"] for k in cast}]
            results[i] = result
            (a.out / slug).mkdir(parents=True, exist_ok=True)
            report(img, [f.mask for f in found], result, f"{model}  {a.zumi.stem} p{i}").save(a.out / slug / f"{a.zumi.stem}-p{i:03d}.png")
            print(f"{model:32s} p{i:3d}: {len(result.get('elements', []))} elements, cost {usage.get('cost', 0):.4f} USD, today {spent_today():.3f}")
        (a.out / slug / f"{a.zumi.stem}.json").write_text(json.dumps({"cast": cast, "panels": results}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
