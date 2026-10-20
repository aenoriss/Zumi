"""Understand step on superframes: Maverick sees 2-4 consecutive boxes in one image instead of one box.

    uv run python understand_superframe.py [--models meta-llama/llama-4-maverick]

Same masks, prompt rules, cast and transcript as understand.py. Boxes of each labelled run are grouped into
windows (up to 4 boxes, at most MAX_STACK px stacked at column width) and laid out in two columns, read left
column then right. Elements are numbered across the window in reading order; answers are mapped back to
(box, element) so score_understand.py scores them like the single-box runs.
"""

from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import understand as U
from bubbles import load_masks
from magi_superframe import COL_W, RUNS, layout
from openrouter import BudgetExceeded, chat, image_part, spent_today

ROOT = Path(__file__).resolve().parent.parent
MASKS = ROOT / ".data/out/understand/seg2/masks"
OUT = ROOT / ".data/out/understand/superframe"
MAX_BOXES, MAX_STACK = 4, 4000

LEAD = ("Image 1 shows {n} consecutive panels of a webtoon episode laid out in two columns: read the left column "
        "top to bottom, then the right column; white gaps separate the panels.")


def windows(run: list[int], heights: dict[int, int]) -> list[list[int]]:
    out, cur, acc = [], [], 0
    for b in run:
        if cur and (len(cur) == MAX_BOXES or acc + heights[b] > MAX_STACK):
            out.append(cur)
            cur, acc = [], 0
        cur.append(b)
        acc += heights[b]
    return out + ([cur] if cur else [])


def place_mask(m: np.ndarray, s: float, x: int, y: int, size: tuple[int, int]) -> np.ndarray:
    small = np.asarray(Image.fromarray(m).resize((COL_W, round(m.shape[0] * s)), Image.NEAREST))
    page = np.zeros((size[1], size[0]), bool)
    page[y : y + small.shape[0], x : x + small.shape[1]] = small
    return page


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default="meta-llama/llama-4-maverick")
    a = ap.parse_args()
    for model in a.models.split(","):
        slug = model.replace("/", "_")
        (OUT / slug).mkdir(parents=True, exist_ok=True)
        for ep, runs in RUNS.items():
            z = zipfile.ZipFile(ROOT / ".data/out/chapters" / f"{ep}.zumi")
            panels = json.loads(z.read("manifest.json"))["panels"]
            load = lambda i: Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB")
            cast, transcript, results = [], [], {}
            for run in runs:
                imgs = {b: load(b) for b in run}
                heights = {b: round(im.height * COL_W / im.width) for b, im in imgs.items()}
                for win in windows(run, heights):
                    page, place = layout([imgs[b] for b in win], "ltr")
                    elems = []  # (box, local id, page mask, box mask, kind) in reading order
                    for k, b in enumerate(win):
                        for e, f in enumerate(load_masks(MASKS / f"{ep}-p{b:03d}.npz"), 1):
                            elems.append((b, e, place_mask(f.mask, *place[k], page.size), f.mask, f.kind, imgs[b]))
                    if not elems:
                        continue
                    masks = [x[2] for x in elems]
                    kinds = [x[4] for x in elems]
                    tails = [U.tail(m) if kd != "sfx" else None for m, kd in zip(masks, kinds)]
                    prompt = U.INSTRUCTIONS.format(
                        panel=0, cast=U.cast_text(cast), transcript="\n".join(transcript[-U.CONTEXT_LINES:]) or "(start of the excerpt)",
                        hints=U.hints_text(masks, kinds, tails, page.width, page.height),
                        previous="Image 3 is the panel just before these, small, only to show who is present." if win[0] > 0 else "",
                    )
                    first = prompt.split(" Each element found")[0]
                    prompt = prompt.replace(first, LEAD.format(n=len(win)), 1)
                    crops = []
                    for b, e, _, m, kd, im in elems:
                        crops.append(U.crops_sheet(im, [m], width=1024))
                    sheet = Image.new("RGB", (1024, sum(c.height for c in crops)), (190, 190, 190))
                    y = 0
                    for n, c in enumerate(crops, 1):  # renumber each crop to its global id
                        ImageDraw.Draw(c).rectangle([(0, 0), (70, 50)], fill=(255, 255, 255))
                        ImageDraw.Draw(c).text((8, 4), str(n), fill=U.COLOURS[(n - 1) % len(U.COLOURS)], font=U.font(40))
                        sheet.paste(c, (0, y))
                        y += c.height
                    content = [{"type": "text", "text": prompt}, image_part(U.numbered_overlay(page, masks, tails)), image_part(sheet)]
                    if win[0] > 0:
                        content.append(image_part(load(win[0] - 1), max_side=640, quality=80))
                    try:
                        text, usage = chat(model, [{"role": "system", "content": U.SYSTEM}, {"role": "user", "content": content}],
                                           max_tokens=6000 if model in U.REASONING else 3500, tag=f"{ep} sf {win}",
                                           reasoning=U.REASONING.get(model))
                    except BudgetExceeded as e:
                        print("STOP:", e)
                        return
                    try:
                        res = U.normalise(U.parse(text), page.width, page.height)
                    except Exception:
                        res = {"elements": [], "new_cast": [], "names": [], "error": text[:300]}
                    known = {c["id"] for c in cast}
                    cast += [c for c in res.get("new_cast", []) if c.get("id") and c["id"] not in known]
                    for upd in res.get("names", []):
                        for c in cast:
                            if c["id"] == upd.get("id") and upd.get("name"):
                                c["name"] = upd["name"]
                    names = {c["id"]: c.get("name") or c["id"] for c in cast}
                    for el in res.get("elements", []):
                        g = el.get("id")
                        if not isinstance(g, int) or not 1 <= g <= len(elems):
                            continue
                        b, e = elems[g - 1][0], elems[g - 1][1]
                        results.setdefault(str(b), {"elements": []})["elements"].append({**el, "id": e})
                        if el.get("keep") and el.get("text") and el.get("kind") != "sfx":
                            transcript.append(f'p{b} {names.get(el.get("speaker"), el.get("speaker"))}: {el["text"]}')
                    U.numbered_overlay(page, masks, tails).save(OUT / slug / f"{ep}-{win[0]:03d}-{win[-1]:03d}.png")
                    print(f"{ep[:4]} {win}: {len(res.get('elements', []))}/{len(elems)} elements, "
                          f"{usage.get('cost', 0):.4f} USD, today {spent_today():.3f}" + ("  PARSE ERROR" if res.get("error") else ""))
            (OUT / slug / f"{ep}.json").write_text(json.dumps({"cast": cast, "panels": results}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
