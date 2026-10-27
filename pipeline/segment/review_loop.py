"""Reasoning layer over SAM 3.1: a vision LLM reviews a panel's masks and the segmenter carries out its fixes.

One loop for both tasks: "characters" (one mask per character, crowds merged) and "lettering" (speech bubbles,
captions, sound effects). Design from the literature review (docs/research, 2026-10-24) and our own failures:
- the model acts by mask number (set-of-mark), never by drawing: same, split, improve, drop, crowd, missing;
- every change to pixels is made by SAM 3.1 on a zoomed crop (missing, improve, split) and kept only if SAM
  confirms it; boxes from the model are prompts, never output;
- every destructive action (drop, merge) is checked again on that one mask, rendered alone with a zoomed crop
  (per-candidate verification beat choosing among all marks by 6-13 points in REF-VC); applied only on agreement;
- additions (missing) and enlargements (improve) are also checked alone, and only after SAM produced a candidate,
  so a proposal SAM cannot carry out costs no LLM call; an enlargement may not grow into a neighbour;
- any element may be dropped, bubbles and captions included, but only when the single-mask check agrees;
- at most 3 rounds, each only when the previous one changed pixels; any mask may be acted on again; the loop stops
  when a round changes nothing or brings back a mask set seen before (without an outside signal, more rounds
  degrade: SegAgent peaks at 5 steps then falls; self-correction without feedback degrades). Rounds after the first
  send only the marked image and a list of the changes made.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_fill_holes

from openrouter import chat, image_part

SMALL_FIGURE, DENSE = 0.02, 8  # 8+ character masks under 2% of the panel each: judged together as possible background
SAM_LOCK = threading.Lock()  # SAM runs on one GPU; LLM calls may run in parallel threads
COLOURS = [(230, 25, 75), (60, 180, 75), (0, 130, 200), (245, 130, 48), (145, 30, 180), (70, 200, 200), (240, 50, 230),
           (150, 190, 30), (0, 128, 128), (170, 110, 40), (128, 0, 0), (0, 0, 128)]
LABEL = {"bubble": "speech bubble", "caption": "caption box", "sfx": "sound effect", "character": "character", "crowd": "crowd"}

TASK = {
    "characters": {
        # a visible part counts: Haiku dropped the hand holding a book as "not a character" (True Beauty 7 p49)
        "what": "A character is any person, creature, monster, animal or robot, or a visible part of one (a hand, an "
                "arm, a head cut off by the panel edge). A character drawn alone on a plain background is still a "
                "character. Not characters: objects, clothing on its own, scenery, pictures of characters shown "
                "inside the scene (on a poster, a book page or a screen), and background figures that are part of the "
                "scenery rather than of the story (specimens in tanks, statues, distant passers-by and extras who are "
                "not the focus of the panel). Every character must have exactly one mask.",
        # "improve" narrowed like lettering's "extend": asked broadly, Haiku flagged nearly every mask (ToG 223 p2: 7
        # proposals on 6 masks, 2 applied, both grew into a neighbour)
        # one character in three masks went unflagged (user, 2026-10-24); a "crowd" of two people went unsplit (ToG 228 p52)
        "actions": '- "same": groups of numbers whose masks cover parts or copies of ONE character (overlapping masks '
                   'on the same body count too).\n'
                   '- "split": numbers whose single mask covers two or more separate characters, including a crowd mask '
                   'that is really two or three distinct characters.\n'
                   '- "improve": numbers whose character has a whole body part (head, arm, legs, tail) visible but left '
                   'uncoloured. Not for slightly loose edges.\n'
                   '- "drop": numbers whose mask is not a character or a part of one.\n'
                   '- "crowd": numbers that are figures of an amorphous mass meant as a crowd (spectators, a horde).\n'
                   '- "missing": characters with no mask, as boxes [x0, y0, x1, y1] in percent of the image (0-100).',
        "empty": '{"same": [], "split": [], "improve": [], "drop": [], "crowd": [], "missing": []}',
        # "a drawing on a page is not" read as the comic itself: "a drawn man in a suit ... comic illustration" -> no
        # (ToG 223 p48, 1 run in 4; same on p11 additions)
        "drop_q": 'Is the highlighted region a character (a person, creature, monster, animal or robot) in the scene, '
                  'or a visible part of one such as a hand or an arm? Everything in a comic is drawn; what is not a '
                  'character is a picture of one shown inside the scene, on a poster, a book page or a screen, or a '
                  'background figure that is part of the scenery (a specimen in a tank, a statue, a distant extra). '
                  'Reply with JSON only: {"yes": true}',
        # dense panels: 48 specimens in tanks as 48 numbered marks (ToG 228 p52) left the reviewer unable to act;
        # set-of-mark breaks down in dense scenes, so many small figures are judged together, in one question
        "background_q": 'The highlighted regions are many small figures of one panel. Are they background figures that '
                        'are part of the scenery (specimens in tanks, statues, a distant audience, extras), rather than '
                        'characters taking part in the story of this panel? Reply with JSON only: {"yes": true}',
        "same_q": 'Is the highlighted region exactly ONE character (not two or more different characters)? '
                  'Reply with JSON only: {"yes": true}',
        # improve's risk is taking in another character or background; a body part left out elsewhere does not matter
        "whole_q": 'Does the highlighted region belong to one single character, with no other character and no large '
                   'piece of background included? Parts of that character left outside it do not matter. '
                   'Reply with JSON only: {"yes": true}',
        "add_q": 'Is the highlighted region a character (a person, creature, monster, animal or robot) in the scene, '
                 'or a visible part of one? Everything in a comic is drawn; what is not a character is a picture of '
                 'one shown inside the scene, on a poster, a book page or a screen, or a background figure that is '
                 'part of the scenery (a specimen in a tank, a statue, a distant extra). Reply with JSON only: {"yes": true}',
        "prompts": ("character", "person", "creature"),
    },
    "lettering": {
        "what": "Elements are comic lettering: speech or thought bubbles, caption boxes, and sound effects (words drawn "
                "into the art, such as BANG or WHOOSH, or annotations like SHY with an arrow). Text that belongs to the "
                "drawn world (a sign, a screen, a book or comic page held in the scene, a note or letter, clothing) is "
                "not lettering, even when the reader must read it: never report it as missing.",
        # no general "improve" for lettering: Haiku flagged about half of all masks and none survived SAM and the
        # checks (2026-10-24, 12 panels x 2 runs). "extend" is the narrow case that does happen: whole letters of a
        # masked word left outside its mask (AK of AKREEE, ToG 223 p79; the first A of AAGHHH, p81)
        "actions": '- "same": groups of numbers that are pieces of ONE bubble, caption or sound-effect word.\n'
                   '- "split": numbers whose single mask covers two separate bubbles, captions or words.\n'
                   '- "extend": numbers of sound-effect words with whole letters of the SAME word visible outside their '
                   'coloured area (for example the first letters of the word left uncoloured).\n'
                   '- "drop": numbers whose mask is not lettering at all (art, a face, an object).\n'
                   '- "missing": bubbles, captions or sound effects with no mask, as boxes [x0, y0, x1, y1] in percent (0-100).',
        "empty": '{"same": [], "split": [], "extend": [], "drop": [], "missing": []}',
        "drop_q": 'Is the highlighted region comic lettering (a sound-effect word drawn into the art, a bubble or a '
                  'caption)? Reply with JSON only: {"yes": true}',
        "same_q": 'Is the highlighted region exactly ONE bubble, caption or sound-effect word (not two separate ones)? '
                  'Reply with JSON only: {"yes": true}',
        # extend's risk is adding art, not lettering nearby: "exactly one word" made Haiku refuse AKREEE (ToG 223 p79)
        "extend_q": 'Is everything inside the highlighted region lettering (letters of a sound-effect word drawn into '
                    'the art), with no art, face, clothing or background included? Lettering nearby that is not '
                    'highlighted does not matter.',
        "whole_q": 'Does the highlighted region cover exactly one complete bubble, caption or sound-effect word, with '
                   'no art or other lettering included? Reply with JSON only: {"yes": true}',
        "add_q": 'Is the highlighted region comic lettering (a speech or thought bubble, a caption box, or a '
                 'sound-effect word drawn into the art)? Art, faces, clothing, and text that belongs to the drawn '
                 'world (signs, screens, notes, book or comic pages held in the scene) are not. '
                 'Reply with JSON only: {"yes": true}',
        # "word" finds black-ink lettering over busy art that "letters" misses (RAAAHHH, ToG 223 p79: 0.45 vs 0.22)
        "prompts": ("speech bubble", "caption box", "letters", "word"),
    },
}
TASK["objects"] = {
    # the picker (scene_judge.choose_objects) lists them in one call and SAM masks each from its name and point; the
    # same loop as for characters and lettering then checks the masks (user, 2026-10-26): a mask that took the wrong
    # thing or half of it, two objects in one mask, an object the pick missed (P&C 39 p8: a mug "on" a counter that
    # had no mask)
    "what": "Objects are movable physical things in the scene: furniture (tables, chairs, stools, benches, counters, "
            "booth seats, beds, cabinets, barrels, crates), props (cups, mugs, glasses, bottles, jugs, plates, bowls, "
            "vases, potted plants, books, papers, baskets, sacks) and things characters hold (a newspaper, a cup, an "
            "instrument, a sword, a broom). Each mask is one object; an item resting on another (a cup on a table) is "
            "a separate object with its own mask. Not objects: characters or anything they wear, lettering, the "
            "floor, walls, ceiling, sky, windows, doors, stairs, fountains, and anything fixed to a wall or ceiling "
            "(pictures, signs, lamps, shelves and what is on them, hanging baskets).",
    "actions": '- "same": groups of numbers whose masks cover parts or copies of ONE object.\n'
               '- "split": numbers whose single mask covers two or more separate objects (two chairs, a table with the '
               'stool beside it).\n'
               '- "improve": numbers whose object has a whole part (a leg, a top, a back, a handle) visible but left '
               'uncoloured. Not for slightly loose edges.\n'
               '- "drop": numbers whose mask is not an object (a character, a wall, the floor, a wall-fixed thing, '
               'lettering) or only a scrap of one.\n'
               '- "missing": objects with no mask, as boxes [x0, y0, x1, y1] in percent of the image (0-100).',
    "empty": '{"same": [], "split": [], "improve": [], "drop": [], "missing": []}',
    "drop_q": 'Is the highlighted region one movable physical object in the scene (furniture, a prop, or an item a '
              'character holds), and not a character, the floor, a wall, a window or door, lettering, or something '
              'fixed to a wall or ceiling? Reply with JSON only: {"yes": true}',
    "same_q": 'Is the highlighted region exactly ONE object (not two separate objects, and not an object with another '
              'one resting on it)? Reply with JSON only: {"yes": true}',
    "whole_q": 'Does the highlighted region belong to one single object, with no character, no other object and no '
               'large piece of floor or wall included? Parts of that object left outside it do not matter. '
               'Reply with JSON only: {"yes": true}',
    "add_q": 'Is the highlighted region one movable physical object in the scene (furniture, a prop, or an item a '
             'character holds), and not a character, the floor, a wall, a window or door, lettering, or something '
             'fixed to a wall or ceiling? Reply with JSON only: {"yes": true}',
    "prompts": ("furniture", "object", "item"),
}
PROMPT_KIND = {"speech bubble": "bubble", "caption box": "caption", "letters": "sfx", "word": "sfx",
               "character": "character", "person": "character", "creature": "character",
               "furniture": "object", "object": "object", "item": "object"}


@dataclass
class El:
    mask: np.ndarray
    kind: str
    score: float
    touched: bool = False


@dataclass
class Log:
    calls: int = 0
    cost: float = 0.0
    proposed: dict = field(default_factory=dict)
    applied: list = field(default_factory=list)
    rejected: list = field(default_factory=list)


def _json(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    try:
        return json.loads(m.group(0)) if m else {}
    except json.JSONDecodeError:
        return {}


def _ask(model: str, effort: str | None, content: list, tag: str, log: Log, max_tokens: int = 500) -> dict:
    text, usage = chat(model, [{"role": "user", "content": content}], max_tokens=max_tokens + (4000 if effort else 0),
                       tag=tag, reasoning=effort)
    log.calls += 1
    log.cost += float(usage.get("cost", 0) or 0)
    return _json(text)


def marked(img: Image.Image, els: list[El]) -> Image.Image:
    base = np.asarray(img).astype(np.float32)
    for k, e in enumerate(els):
        base[e.mask] = base[e.mask] * 0.5 + np.array(COLOURS[k % len(COLOURS)]) * 0.5
    out = Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(out)
    from understand import font
    size = max(18, img.width // 24)
    for k, e in enumerate(els):
        ys, xs = np.nonzero(e.mask)
        y, x = int(np.median(ys)), int(np.median(xs))
        d.rectangle([(x, y), (x + size * 1.4, y + size * 1.2)], fill=COLOURS[k % len(COLOURS)])
        d.text((x + size * 0.2, y + size * 0.05), str(k + 1), fill=(255, 255, 255), font=font(size))
    return out


def single(img: Image.Image, m: np.ndarray) -> list:
    """One mask alone: the panel with only this mask highlighted, and a zoomed crop of it."""
    base = np.asarray(img).astype(np.float32).copy()
    edge = binary_dilation(m, iterations=3) & ~m
    base[m] = base[m] * 0.55 + np.array([255, 0, 200]) * 0.45
    base[edge] = [255, 0, 200]
    full = Image.fromarray(base.astype(np.uint8))
    ys, xs = np.nonzero(m)
    pad = int(0.25 * max(ys.ptp(), xs.ptp())) + 10
    box = (max(0, xs.min() - pad), max(0, ys.min() - pad), min(img.width, xs.max() + pad), min(img.height, ys.max() + pad))
    return [image_part(full, max_side=1024), image_part(full.crop(box), max_side=768)]


def zoom(proc, img: Image.Image, box, prompts) -> list[tuple[np.ndarray, float, str]]:
    """SAM 3.1 on a crop of `box` enlarged to fill its input: (panel-size mask, score, kind) per instance."""
    x0, y0, x1, y1 = box
    crop = img.crop(box)
    s = 1008 / max(crop.size)
    big = crop.resize((max(1, round(crop.width * s)), max(1, round(crop.height * s))), Image.LANCZOS)
    canvas = Image.new("RGB", (1008, 1008), (255, 255, 255))
    canvas.paste(big, (0, 0))
    out = []
    with SAM_LOCK:
        base = proc.set_image(canvas)
        for prompt in prompts:
            st = proc.set_text_prompt(prompt, base)
            for p, sc in zip(st["masks_logits"][:, 0].float().cpu().numpy(), st["scores"].float().cpu().numpy()):
                if sc < 0.3:
                    continue
                mm = np.asarray(Image.fromarray(p[: big.height, : big.width].astype(np.float32)).resize(crop.size, Image.BILINEAR)) > 0.5
                if not mm.any() or mm.mean() > 0.8:  # fills the crop: SAM marked the box, not an object
                    continue
                full = np.zeros((img.height, img.width), bool)
                full[y0:y1, x0:x1] = binary_fill_holes(mm)
                if PROMPT_KIND.get(prompt) == "character":
                    from characters import clean
                    full = clean(full)
                out.append((full, float(sc), PROMPT_KIND.get(prompt, "character")))
    return out


def _box(m: np.ndarray, grow: float, img: Image.Image):
    ys, xs = np.nonzero(m)
    gy, gx = int(grow * (ys.ptp() + 1)) + 8, int(grow * (xs.ptp() + 1)) + 8
    return (max(0, xs.min() - gx), max(0, ys.min() - gy), min(img.width, xs.max() + gx), min(img.height, ys.max() + gy))


def _ids(v, n):
    return [int(x) - 1 for x in (v if isinstance(v, list) else []) if isinstance(x, (int, float)) and 1 <= int(x) <= n]


def _passes_gates(img: Image.Image, cand) -> bool:
    """An added mask must pass the same rules as the segmentation pass: bubbles and captions hold letters
    (bubbles.py), sound effects have a lettering shape, a character does not fill its box (characters.confirm)."""
    from bubbles import dialogue_like, lettering
    m, score, kind = cand
    if kind == "object":  # no shape rule of its own; the single-mask check (add_q, whole_q) judges it
        return int(m.sum()) >= 150
    if kind == "character":
        ys, xs = np.nonzero(m)
        return len(ys) >= 200 and m.sum() <= 0.8 * (ys.ptp() + 1) * (xs.ptp() + 1)
    if kind == "sfx":
        return lettering(m)
    return dialogue_like(np.asarray(img), m, kind, score)


def needs_review(els: list[El], task: str) -> list[str]:
    """Reasons to review a panel; an empty list means skip it. Selective review: the model is only asked where the
    segmenter left doubt (every lettering fix on the 12 bench panels was on a sound effect or a touching pair)."""
    reasons = []
    if task == "lettering":
        if any(e.kind == "sfx" for e in els):
            reasons.append("sound effect")
        if any(e.kind in ("bubble", "caption") and e.score < 0.8 for e in els):
            reasons.append("low score")
    else:
        if els:
            reasons.append("characters present")
    for a in range(len(els)):
        grown = binary_dilation(els[a].mask, iterations=3)
        if any(np.logical_and(grown, els[b].mask).any() for b in range(a + 1, len(els))):
            reasons.append("touching masks")
            break
    return reasons


def _signature(els: list[El]) -> tuple:
    """Coarse fingerprint of a mask set, to stop when a round returns to an earlier state."""
    return tuple(sorted((e.kind, int(e.mask.sum()) // 200) for e in els))


def _check(model, effort, question, img, m, tag, log) -> bool:
    """Single-mask check. The model describes what it sees before deciding: asked for a bare yes/no, Haiku rejected
    a correct AKREEE mask three times out of three; asked to describe first, it accepted it."""
    q = question.split("Reply with JSON only")[0].strip()
    q += (' First say in one sentence what the highlighted region contains, then decide. Reply with JSON only: '
          '{"seen": "<one sentence>", "yes": true or false}')
    return bool(_ask(model, effort, [{"type": "text", "text": q}] + single(img, m), tag, log, max_tokens=300).get("yes"))


def review(proc, img: Image.Image, els: list[El], task: str, model: str, effort: str | None, tag: str,
           rounds: int = 3) -> tuple[list[El], Log]:
    """Up to `rounds` rounds; a round runs only when the previous one changed pixels, any mask may be acted on again,
    and the loop stops if a round brings back a mask set seen before."""
    t = TASK[task]
    log = Log()
    if task == "characters":
        small = [k for k, e in enumerate(els) if e.kind == "character" and e.mask.mean() < SMALL_FIGURE]
        if len(small) >= DENSE:
            union = np.logical_or.reduce([els[k].mask for k in small])
            if _check(model, effort, t["background_q"], img, union, f"{tag} background", log):
                els = [e for k, e in enumerate(els) if k not in set(small)]
                log.applied.append(("background", len(small)))
            else:
                log.rejected.append(("background", len(small)))
    seen = {_signature(els)}
    changes: list[str] = []
    for rnd in range(rounds):
        if not els:
            break
        n = len(els)
        listing = "\n".join(f"{k + 1}: {LABEL.get(e.kind, e.kind)}" for k, e in enumerate(els))
        head = ("Image 1: a comic panel with every candidate mask filled in a colour and numbered. Image 2: the same "
                "panel without marks.") if rnd == 0 else (
                "Image 1: the comic panel after your previous fixes, every mask filled in a colour and renumbered. "
                f"Changes made since your last look: {'; '.join(changes)}. Check the result.")
        prompt = (f"{head}\n{t['what']}\nMasks:\n{listing}\n\nFix the masks with these actions, using mask numbers. Only "
                  f"list clear cases; empty lists are fine.\n{t['actions']}\n\nReply with JSON only: {t['empty']}")
        content = [{"type": "text", "text": prompt}, image_part(marked(img, els))]
        if rnd == 0:  # later rounds: the marked image alone, to save tokens
            content.append(image_part(img, max_side=1024))
        v = _ask(model, effort, content, f"{tag} r{rnd}", log)
        log.proposed[f"r{rnd}"] = v
        changes = []
        free = lambda i: True
        changed = False
        new = list(els)
        gone: set[int] = set()
        # merges: verified on the merged mask alone
        for grp in v.get("same", []) if isinstance(v.get("same"), list) else []:
            g = [i for i in _ids(grp, n) if free(i) and i not in gone]
            if len(g) < 2:
                continue
            m = np.logical_or.reduce([els[i].mask for i in g])
            ok = _check(model, effort, t["same_q"], img, m, f"{tag} same", log)
            if ok:
                new.append(El(m, els[g[0]].kind, max(els[i].score for i in g), True))
                gone |= set(g)
                log.applied.append(("same", [i + 1 for i in g]))
                changes.append(f"merged {', '.join(str(i + 1) for i in g)}")
                changed = True
            else:
                log.rejected.append(("same", [i + 1 for i in g]))
        # drops: verified on the mask alone
        for i in _ids(v.get("drop", []), n):
            if i in gone or not free(i):
                continue
            keep = _check(model, effort, t["drop_q"], img, els[i].mask, f"{tag} drop", log)
            if keep:
                log.rejected.append(("drop", i + 1))
            else:
                gone.add(i)
                log.applied.append(("drop", i + 1))
                changes.append(f"dropped {i + 1}")
        # crowd (characters): label only, no pixels change
        crowd = [i for i in _ids(v.get("crowd", []), n) if i not in gone and free(i)]
        if crowd:
            m = np.logical_or.reduce([els[i].mask for i in crowd])
            new.append(El(m, "crowd", max(els[i].score for i in crowd), True))
            gone |= set(crowd)
            log.applied.append(("crowd", [i + 1 for i in crowd]))
        # improve: SAM on a zoomed box around the mask; kept if it grows the mask and still holds it
        for i in _ids(v.get("improve", []), n):
            if i in gone or not free(i):
                continue
            m = els[i].mask
            cands = [c for c in zoom(proc, img, _box(m, 0.35, img), t["prompts"]) if np.logical_and(c[0], m).sum() >= 0.7 * m.sum()]
            # a missing body part lies outside the outline; holes inside it are what covers the character (ToG 223 p48:
            # the "SHUT YOUR MOUTH" bubble on his chest, filled in by SAM's hole filling)
            holes = binary_fill_holes(m) & ~m
            cands = [(c[0] & ~holes, c[1], c[2]) for c in cands]
            # never grow into a neighbour (ToG 223 p2: an improved figure swallowed the bodies beside it): a candidate
            # that takes in a third of a neighbour is two characters; otherwise the neighbours' pixels are cut away,
            # as extend does for lettering
            others = [e.mask for k, e in enumerate(els) if k != i]
            taken = binary_dilation(np.logical_or.reduce(others), iterations=3) & ~m if others else np.zeros_like(m)
            cands = [(c[0] & ~taken, c[1], c[2]) for c in cands
                     if not any(np.logical_and(c[0] & ~m, o).sum() > 0.3 * o.sum() for o in others)]
            cands = [c for c in cands if 1.05 * m.sum() <= c[0].sum() <= 2.5 * m.sum() and _passes_gates(img, c)]
            # the model checks the grown mask alone; only now, so proposals SAM cannot carry out cost no LLM call
            if cands:
                best = max(cands, key=lambda c: c[1])
                grown = m | best[0]
                if _check(model, effort, t["whole_q"], img, grown, f"{tag} improve", log):
                    new[i] = El(grown, els[i].kind, els[i].score, True)
                    log.applied.append(("improve", i + 1))
                    changes.append(f"enlarged {i + 1}")
                    changed = True
                    continue
            log.rejected.append(("improve", i + 1))
        # split: SAM must return two or more instances inside the mask that cover most of it
        for i in _ids(v.get("split", []), n):
            if i in gone or not free(i):
                continue
            m = els[i].mask
            region = binary_dilation(m, iterations=4)
            parts = [c for c in zoom(proc, img, _box(m, 0.1, img), t["prompts"])
                     if np.logical_and(c[0], region).sum() >= 0.8 * c[0].sum() and c[0].sum() >= 0.15 * m.sum()]
            uniq = []
            for c in sorted(parts, key=lambda c: -c[1]):
                if all(np.logical_and(c[0], u[0]).sum() < 0.5 * min(c[0].sum(), u[0].sum()) for u in uniq):
                    uniq.append(c)
            if len(uniq) >= 2 and np.logical_or.reduce([u[0] for u in uniq]).__and__(m).sum() >= 0.7 * m.sum():
                gone.add(i)
                kind = {"sfx": None, "crowd": "character"}.get(els[i].kind, els[i].kind)  # a split crowd is characters
                new += [El(u[0] & region, kind or u[2], u[1], True) for u in uniq]
                log.applied.append(("split", i + 1, len(uniq)))
                changes.append(f"split {i + 1} into {len(uniq)}")
                changed = True
            else:
                log.rejected.append(("split", i + 1))
        # extend (lettering): letters of the same word next to its mask; SAM looks around it, only letter-shaped pieces
        # that touch no other element are added, and the grown word is checked alone
        for i in _ids(v.get("extend", []), n):
            if i in gone or els[i].kind != "sfx":
                continue
            m = els[i].mask
            ys, xs = np.nonzero(m)
            H = max(8, int(min(ys.ptp(), xs.ptp()) + 1))
            near = binary_dilation(m, iterations=min(120, int(1.5 * H)))
            others = [e.mask for k, e in enumerate(els) if k != i]
            taken = binary_dilation(np.logical_or.reduce(others), iterations=3) if others else np.zeros_like(m)
            pieces, whole = [], False
            for c in zoom(proc, img, _box(m, 0.6, img), ("letters", "word")):
                if (c[0] & ~m).sum() < 0.05 * m.sum():
                    continue
                if np.logical_and(c[0], m).sum() >= 0.5 * m.sum():
                    # SAM saw the whole word (AKREEE, ToG 223 p79): keep it, minus the neighbours' pixels
                    pieces.append(c[0] & ~taken)
                    whole = True
                elif np.logical_and(c[0], near).sum() >= 0.5 * c[0].sum() and \
                        not any(np.logical_and(c[0] & ~m, o).sum() > 0.1 * o.sum() for o in others):
                    pieces.append(c[0])
            grown = m | np.logical_or.reduce(pieces) if pieces else m
            from bubbles import lettering as letter_shape
            # SAM's whole-word mask, letter-shaped and clear of neighbours, needs no LLM check: the check was flaky on
            # exactly this case (refused AKREEE in the loop, accepted it when asked alone); loose pieces still need it
            if pieces and grown.sum() >= 1.05 * m.sum() and letter_shape(grown) and \
                    (whole or _check(model, effort, t["extend_q"], img, grown, f"{tag} extend", log)):
                new[i] = El(grown, "sfx", els[i].score, True)
                log.applied.append(("extend", i + 1))
                changes.append(f"extended {i + 1}")
                changed = True
            else:
                log.rejected.append(("extend", i + 1, "no letters found beside it" if not pieces else "failed shape or check"))
        # missing: SAM on the box must find an object that is not already masked
        miss = v.get("missing", [])
        if isinstance(miss, list) and len(miss) == 4 and all(isinstance(x, (int, float)) for x in miss):
            miss = [miss]
        w, h = img.size
        for b in miss if isinstance(miss, list) else []:
            if not (isinstance(b, list) and len(b) == 4 and all(isinstance(x, (int, float)) for x in b)):
                continue
            x0, y0, x1, y1 = [int(min(100, max(0, float(q))) / 100 * s) for q, s in zip(b, (w, h, w, h))]
            if x1 - x0 < 12 or y1 - y0 < 12:
                continue
            pad = int(0.1 * max(x1 - x0, y1 - y0))
            box = (max(0, x0 - pad), max(0, y0 - pad), min(w, x1 + pad), min(h, y1 + pad))
            inside = np.zeros((h, w), bool)
            inside[box[1]:box[3], box[0]:box[2]] = True
            found = zoom(proc, img, box, t["prompts"])
            cands = [c for c in found if np.logical_and(c[0], inside).sum() >= 0.6 * c[0].sum() and c[0].sum() >= 150]
            fresh = [c for c in cands if not any(np.logical_and(c[0], e.mask).sum() > 0.5 * c[0].sum() for e in new)]
            gated = [c for c in fresh if _passes_gates(img, c)]  # free: catches letterless "bubbles", boxy figures
            reason = ("sam found nothing" if not found else "outside box or tiny" if not cands else
                      "already masked" if not fresh else "failed segmentation rules" if not gated else "check said no")
            if gated:
                best = max(gated, key=lambda c: c[1])
                if best[2] == "sfx":  # one word often comes back in pieces (RAAA + HHH): add them as one mask
                    parts = [c for c in gated if c[2] == "sfx"]
                    best = (np.logical_or.reduce([c[0] for c in parts]), best[1], "sfx")
                # a "missing" character that overlaps a masked one is a part of it (ToG 223 p48: his clasped hands came
                # back as a second character); masks of two different characters hardly overlap
                host = next((k for k, e in enumerate(new) if k not in gone and e.kind == "character" and best[2] == "character"
                             and np.logical_and(best[0], e.mask).sum() >= 0.2 * best[0].sum()), None)
                if host is not None:
                    grown = new[host].mask | best[0]
                    if _check(model, effort, t["whole_q"], img, grown, f"{tag} join", log):
                        new[host] = El(grown, "character", new[host].score, True)
                        log.applied.append(("joined", b, host + 1))
                        changes.append(f"enlarged {host + 1}")
                        changed = True
                        continue
                    log.rejected.append(("missing", b, "part of a masked character, check said no"))
                    continue
                # additions are checked alone too (Haiku added two small "bubbles" on art: ToG 223 p11, TB 5 p57)
                if _check(model, effort, t["add_q"], img, best[0], f"{tag} add", log):
                    new.append(El(best[0], best[2], best[1], True))
                    log.applied.append(("missing", b))
                    changes.append("added a mask")
                    changed = True
                    continue
            log.rejected.append(("missing", b, reason))
        els = [e for k, e in enumerate(new) if k not in gone]
        sig = _signature(els)
        if not changed or sig in seen:  # nothing new, or back to an earlier state
            break
        seen.add(sig)
    return els, log
