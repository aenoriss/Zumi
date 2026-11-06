"""Lettering masks with SAM 3.1 (step 2a): speech bubbles, caption boxes, confident sound effects, each sound effect
then tightened to its letters (the refinement, second half of this file).

    found = segment(seg, img, bank, episode, panel, statuses)   one box's lettering, refined; statuses gets the
                                                               refinement's per-effect outcomes for the run log
    uv run python bubbles.py <episode.zumi> <out dir> [--panels 3,7,12]   (masks saved as an episode run's, boxstore)

Dialogue is always masked: the reader redraws bubbles and captions as live text, so they are erased and the art
behind them inpainted. A sound effect is masked only when its segmentation is confident; otherwise it stays
part of the art (decided 2026-10-19). Confident = score >= 0.5, mask stability >= 0.75 (share of the pixels
SAM 3 is unsure about, probability 0.3-0.7 band edges, that are clearly in: above 0.7), and a lettering shape.
Measured on 368 sound-effect hits from 12 panels labelled by eye: clean letters had stability 0.76-0.95;
letters mixed with a crowd of small figures (Tower of God 223 p81) had 0.17-0.58 and scores under 0.4.

SAM 3 resizes every input to a 1008 x 1008 square, so a tall panel is cut into square tiles (side = panel
width, 25 % overlap). Each tile gets:
- text passes at full resolution: "speech bubble" (round and shaped bubbles), "caption box";
- exemplar passes (SAM 3 concept mode): the tile shrunk to 756 px with example crops from other panels in a
  margin, each marked as a positive box, so SAM 3 finds everything that looks like them. Examples come from a
  hand-picked bank (`.data/exemplars/bank.json`), never from the panel being segmented. The two dialogue groups
  share one canvas; each sound-effect group has its own (LAYOUT). A tile's images (the tile and its canvases) are
  encoded in one batch and each text prompt is encoded once: 7.34 -> 6.08 s per panel on 12 test panels, same
  masks (52 of 53 at IoU >= 0.8, 1 at 0.5-0.8). Tile by tile, not the whole panel at once: every encoded image
  holds 108 MB of GPU memory until its passes are done, and a 15-tile webtoon box (Omniscient Reader 0, 800 x
  8754) held 60 of them, filling the 12 GB and 18.8 GB of commit.

Masks of the same kind that overlap by more than half are one object seen twice (overlapping tiles); different
kinds merge only when near-identical, so a sound effect crossing a caption box stays a separate mask (Tower of
God 223 p4). A "bubble" inside a caption card is the card's text block; letters inside a bubble or caption are
its dialogue; both are dropped. A sound effect's letters are grouped into one mask per word.

Measured: "speech bubble" finds round bubbles at 0.95+ and black bursts at 0.35; "caption box" finds light
captions (0.78) but not black cards (0.14-0.24); card exemplars find a missed black card at 0.98.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, binary_fill_holes, label

from boxstore import Box
from chapter import Chapter
from masks import Found, top_order
from sam import SIDE as CANVAS, Segmenter, tiles
from shape import dialogue_like, letter_shaped, letter_stats, uniformity
from textcrops import clean_crop

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / ".data/exemplars/bank.json"
TILE = 756  # the tile's side inside an exemplar canvas (CANVAS, SAM's input side)
# Exemplar canvases: (groups sharing one canvas, margin cell side, examples per group). A 252 px cell gives 7
# margin cells, a 126 px cell 28. Dialogue examples keep their hits at 126 px; sound-effect examples lost hits
# on busy art when shrunk to 126 px (Tower of God 223 p79: GMHHH and AKREEE missed), so they keep full cells.
LAYOUT = [(("card", "burst"), 126, 7), (("sfx",), 252, 7), (("sfx_outline",), 252, 7)]
KIND_COLOUR = {"bubble": (255, 70, 70), "caption": (60, 140, 255), "sfx": (255, 0, 220)}
KIND_RANK = {"bubble": 2, "caption": 2, "sfx": 1}  # same shape found as two kinds: the container wins
DIALOGUE = ("bubble", "caption")
MAX_INSIDE = 0.6  # a bubble mostly inside a caption card is the card's text block
MAX_SFX_INSIDE = 0.9  # letters almost wholly inside a bubble are its dialogue; letters crossing its edge are their
#                       own element (True Beauty 5 p71 "DAMN IT!" over the burst)


@dataclass(frozen=True)
class Pass:
    prompt: str  # text prompt; with exemplars it names the concept the examples share
    min_score: float
    kind: str
    exemplars: str | None = None  # bank group, or None for a plain text pass
    min_stability: float = 0.0


PASSES = [
    Pass("speech bubble", 0.30, "bubble"),
    Pass("caption box", 0.5, "caption"),
    Pass("caption box", 0.5, "caption", exemplars="card"),
    Pass("speech bubble", 0.3, "bubble", exemplars="burst"),  # the black "!" splat in ToG 228 p89 scored 0.30
    Pass("letters", 0.5, "sfx", exemplars="sfx", min_stability=0.7),  # "DAMN IT!" 0.74; crowd blotches <= 0.58
    Pass("letters", 0.5, "sfx", exemplars="sfx_outline", min_stability=0.7),  # white letters, dark outline
]


def window(*fs: Found, pad: int = 0) -> tuple[slice, slice] | None:
    """The overlap of the masks' boxes (grown by pad), or None when the boxes do not touch."""
    y0 = max(f.bbox()[0] for f in fs) - pad
    y1 = min(f.bbox()[1] for f in fs) + pad
    x0 = max(f.bbox()[2] for f in fs) - pad
    x1 = min(f.bbox()[3] for f in fs) + pad
    if y0 >= y1 or x0 >= x1:
        return None
    return slice(max(0, y0), y1), slice(max(0, x0), x1)


def area(f: Found) -> int:
    y0, y1, x0, x1 = f.bbox()
    return int(f.mask[y0:y1, x0:x1].sum())


class Bank:
    """Example crops by group, loaded from the .zumi files they were picked from."""

    def __init__(self, path: Path, episodes: Path):
        spec = json.loads(path.read_text())
        self.crops: dict[str, list[tuple[str, int, Image.Image]]] = {}
        for group, items in spec.items():
            if group.startswith("_"):
                continue
            for ep, panel, box in items:
                crop = Chapter(episodes / f"{ep}.zumi").image(panel).crop(box)
                self.crops.setdefault(group, []).append((ep, panel, crop))

    def pick(self, group: str, episode: str, panel: int, n: int = 7) -> list[Image.Image]:
        return [c for ep, p, c in self.crops.get(group, []) if (ep, p) != (episode, panel)][:n]


def margin_cells(cell: int) -> list[tuple[int, int]]:
    """Top-left corners of the cell x cell squares in the canvas margin (right strip, then bottom strip)."""
    right = [(x, y) for y in range(0, CANVAS - cell + 1, cell) for x in range(TILE, CANVAS - cell + 1, cell)]
    bottom = [(x, y) for y in range(TILE, CANVAS - cell + 1, cell) for x in range(0, TILE - cell + 1, cell)]
    return right + bottom


def composite(tile: Image.Image, groups: dict[str, list[Image.Image]], cell: int) -> tuple[Image.Image, dict[str, list[list[float]]]]:
    """Tile at TILE px top-left; the groups' examples share the margin in cell x cell squares.
    Returns the canvas and, per group, its example boxes as normalised cx, cy, w, h."""
    canvas = Image.new("RGB", (CANVAS, CANVAS), (255, 255, 255))
    canvas.paste(tile.resize((TILE, TILE)), (0, 0))
    cells = iter(margin_cells(cell))
    boxes: dict[str, list[list[float]]] = {}
    for group, examples in groups.items():
        for crop, (cx, cy) in zip(examples, cells):
            crop = crop.copy()
            crop.thumbnail((cell - 6, cell - 6))
            ox, oy = cx + (cell - crop.width) // 2, cy + (cell - crop.height) // 2
            canvas.paste(crop, (ox, oy))
            boxes.setdefault(group, []).append(
                [(ox + crop.width / 2) / CANVAS, (oy + crop.height / 2) / CANVAS, crop.width / CANVAS, crop.height / CANVAS])
    return canvas, boxes


def stability(prob: np.ndarray) -> float:
    """Share of the pixels above 0.3 that are also above 0.7: 1 for a crisp mask, low for a hesitant one."""
    return float((prob > 0.7).sum() / max(1, (prob > 0.3).sum()))


def run_pass(seg: Segmenter, state: dict, tile: Image.Image, ps: Pass, boxes: list[list[float]] | None) -> list[tuple[np.ndarray, float]]:
    """(tile-size mask, score) for one pass on one tile. `state` holds the encoded tile (text passes) or the
    encoded canvas (exemplar passes, with this group's example boxes)."""
    if ps.exemplars is not None and not boxes:
        return []
    crop = None if ps.exemplars is None else TILE
    probs, scores = seg.ground(state, ps.prompt, boxes if ps.exemplars is not None else None)  # sigmoid probabilities
    out = []
    for p, s in zip(probs, scores):
        if s < ps.min_score:
            continue
        m = p > 0.5
        if crop:
            if m[:crop, :crop].sum() <= 0.9 * m.sum():  # an example in the margin, not the tile
                continue
            p = p[:crop, :crop]
            m = np.asarray(Image.fromarray(m[:crop, :crop]).resize(tile.size, Image.NEAREST))
        if ps.min_stability and stability(p) < ps.min_stability:
            continue
        m = binary_fill_holes(m)
        if ps.kind == "sfx" and not letter_shaped(m):
            continue
        if ps.kind in DIALOGUE and not dialogue_like(np.asarray(tile), m, ps.kind, float(s)):
            continue
        out.append((m, float(s)))
    return out


def add(found: list[Found], new: Found) -> None:
    """`new` merged into every mask it is one object with, transitively: a balloon found whole after its two lobes
    takes both (merging into the first lobe only left the second as a nested duplicate, transcribed and spoken
    twice: 30 balloons of P&C 36-39, 2026-11-06)."""
    while True:
        b = area(new)
        for i, f in enumerate(found):
            win = window(f, new)
            if win is None:
                continue
            inter = np.logical_and(f.mask[win], new.mask[win]).sum()
            if not inter:
                continue
            a = area(f)
            same_object = f.kind == new.kind and inter / min(a, b) > 0.5
            same_shape = inter / (a + b - inter) > 0.7
            if same_object or same_shape:
                kind = max((f, new), key=lambda x: (KIND_RANK[x.kind], x.score)).kind
                new = Found(np.logical_or(f.mask, new.mask), max(f.score, new.score), kind)
                del found[i]
                break
        else:
            found.append(new)
            return


def drop_inner_text(found: list[Found]) -> list[Found]:
    """Drop masks lying mostly inside a container: a bubble inside a caption card is the card's text block,
    letters inside a bubble or caption are its dialogue."""
    def inside(f: Found, kinds: tuple[str, ...], share: float) -> bool:
        cs = [g for g in found if g.kind in kinds and g is not f and window(f, g) is not None]
        if not cs:
            return False
        y0, y1, x0, x1 = f.bbox()
        cover = np.logical_or.reduce([g.mask[y0:y1, x0:x1] for g in cs])
        return np.logical_and(f.mask[y0:y1, x0:x1], cover).sum() > share * area(f)

    return [
        f for f in found
        if not (f.kind == "bubble" and inside(f, ("caption",), MAX_INSIDE) or f.kind == "sfx" and inside(f, DIALOGUE, MAX_SFX_INSIDE))
    ]


def group_letters(found: list[Found], reach: int) -> list[Found]:
    """Letters of one sound effect become one mask: sfx masks within `reach` px of each other join."""
    sfx = [f for f in found if f.kind == "sfx"]
    if len(sfx) < 2:
        return found
    h, w = sfx[0].mask.shape
    # dilate within the letters' joint box (plus the reach), not over the whole panel
    y0 = max(0, min(f.bbox()[0] for f in sfx) - reach)
    y1 = min(h, max(f.bbox()[1] for f in sfx) + reach)
    x0 = max(0, min(f.bbox()[2] for f in sfx) - reach)
    x1 = min(w, max(f.bbox()[3] for f in sfx) + reach)
    crops = [f.mask[y0:y1, x0:x1] for f in sfx]
    words, n = label(binary_dilation(np.logical_or.reduce(crops), iterations=reach))
    # a mask whose letters lie far apart touches two words; words sharing a mask are one word, so each mask ends up
    # in exactly one group (ToG 223 p79: 6 masks came out as 9, six of them duplicates)
    parent = list(range(n + 1))

    def find(k):
        while parent[k] != k:
            parent[k] = parent[parent[k]]
            k = parent[k]
        return k

    labels = [set(np.unique(words[c])) - {0} for c in crops]
    for ls in labels:
        ls = sorted(ls)
        for a in ls[1:]:
            parent[find(a)] = find(ls[0])
    groups: dict[int, list[Found]] = {}
    for f, ls in zip(sfx, labels):
        if ls:
            groups.setdefault(find(min(ls)), []).append(f)
    grouped = [Found(np.logical_or.reduce([f.mask for f in g]), max(f.score for f in g), "sfx") for g in groups.values()]
    return [f for f in found if f.kind != "sfx"] + grouped


def segment(seg: Segmenter, img: Image.Image, bank: Bank, episode: str, panel: int,
            statuses: list[str] | None = None) -> list[Found]:
    """The box's lettering: the passes on each tile, duplicates across tiles merged, inner text dropped, sound
    effects grouped into words and refined (refine_panel; statuses, when given, collects its outcomes)."""
    w, h = img.size
    tops = tiles(h, w)
    layout = [(names, cell, {g: bank.pick(g, episode, panel, n) for g in names}) for names, cell, n in LAYOUT]
    found: list[Found] = []
    for top in tops:
        tile = img.crop((0, top, w, min(h, top + w)))
        # the tile, then one canvas per layout entry: one encoder batch, freed before the next tile
        images, where = [tile], {}  # where[group] = (image index, example boxes)
        for names, cell, groups in layout:
            canvas, boxes = composite(tile, groups, cell)
            for g in names:
                where[g] = (len(images), boxes.get(g))
            images.append(canvas)
        states = seg.encode(images)
        for ps in PASSES:
            if ps.exemplars is None:
                hits = run_pass(seg, states[0], tile, ps, None)
            else:
                i, boxes = where[ps.exemplars]
                hits = run_pass(seg, states[i], tile, ps, boxes)
            for m, s in hits:
                full = np.zeros((h, w), bool)
                full[top : top + m.shape[0]] = m
                add(found, Found(full, s, ps.kind))
        del states
    return refine_panel(seg, img, group_letters(drop_inner_text(found), reach=max(8, w // 40)), statuses)


def overlay(img: Image.Image, found: list[Found]) -> Image.Image:
    base = np.asarray(img.convert("RGB")).astype(np.float32)
    for f in found:
        base[f.mask] = base[f.mask] * 0.45 + np.array(KIND_COLOUR[f.kind]) * 0.55
    out = Image.fromarray(base.astype(np.uint8))
    d = ImageDraw.Draw(out)
    for f in found:
        ys, xs = np.nonzero(f.mask)
        d.rectangle([(xs.min(), ys.min()), (xs.max(), ys.max())], outline=KIND_COLOUR[f.kind], width=3)
        d.text((xs.min() + 4, ys.min() + 2), f"{f.kind} {f.score:.2f}", fill=(0, 0, 0))
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("zumi", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--panels", default="")
    a = ap.parse_args()

    t0 = time.perf_counter()
    seg = Segmenter(min(p.min_score for p in PASSES))
    bank = Bank(BANK, a.zumi.parent)
    print(f"model and bank loaded in {time.perf_counter() - t0:.1f}s")

    ch = Chapter(a.zumi)
    pick = [int(i) for i in a.panels.split(",") if i] or list(range(len(ch)))
    a.out.mkdir(parents=True, exist_ok=True)
    for i in pick:
        img = ch.image(i)
        t = time.perf_counter()
        found = segment(seg, img, bank, ch.stem, i)
        overlay(img, found).save(a.out / f"{ch.pid(i)}.png")
        Box(a.out, ch.pid(i)).save_letters(found)
        pixels = np.asarray(img)
        dialogue = top_order([f for f in found if f.kind in DIALOGUE])  # text crops are for reading dialogue
        for k, f in enumerate(dialogue):
            if (crop := clean_crop(pixels, f.mask)) is not None:
                (a.out / "text").mkdir(exist_ok=True)
                crop.save(a.out / "text" / f"{ch.pid(i)}-{k:02d}-{f.kind}.png")
        kinds = {k: sum(f.kind == k for f in found) for k in ("bubble", "caption", "sfx")}
        print(f"panel {i:3d} {img.width}x{img.height}: {kinds}, {time.perf_counter() - t:.2f}s")


# =====================================================================================================
# Sound-effect refinement (was sfx_refine.py): each sound-effect mask tightened to its letters with a zoomed SAM 3.1
# pass. The first pass finds sound effects on a whole tile, so their masks are loose (art between letters, a
# whisper's "per" beside "whis"). Per mask: SAM re-runs "letters" on a crop of the mask enlarged to 1008 px and keeps
# only what lies in the old mask; pieces it missed get a second zoomed pass ("letters", "text"); an empty result drops
# the effect unless the old mask is stroke-shaped (an isolated letter SAM will not re-find). Letters of the same word
# the old mask lacked are looked for around it and kept only if SAM confirms them. Then pieces of one word are grouped
# (only a fragment of 1-2 letters joins a neighbour) and the whole word is re-segmented; a word with a gap still wider
# than 2.2 letter spacings loses its fragments. Tuned on Tower of God 223 / 228, True Beauty 5, Pepper&Carrot 39
# (variant v9 of a scratch script, 2026-10-23).
# =====================================================================================================

C = dict(prompts=["letters"], prompts2=["letters", "text"], rescue=["text"], pad=16, fallback=0.35, margin=1, thr=0.45,
         missing_frac=0.3)


def zoom_masks(seg, img, box, region, prompts, thr):
    """Every instance SAM finds on the zoomed box (sam.Segmenter.zoom) that lies mostly inside `region`, united."""
    keep = np.zeros(region.shape, bool)
    for prob, _, _ in seg.zoom(img, box, prompts):
        # downsampled probabilities, then thresholded: smooth edges, thin strokes survive
        mm = prob > thr
        if mm.sum() and (mm & region).sum() >= 0.7 * mm.sum():
            keep |= mm
    return keep & region


def bbox(m, pad, h, w):
    ys, xs = np.nonzero(m)
    return (max(0, xs.min() - pad), max(0, ys.min() - pad), min(w, xs.max() + pad + 1), min(h, ys.max() + pad + 1))


def colour_codes(pixels):
    q = (pixels // 16).astype(np.int32)
    return q[..., 0] * 256 + q[..., 1] * 16 + q[..., 2]


def refine(seg, img, m):
    """One sound-effect mask -> (tightened mask, status); an empty mask means the effect is dropped."""
    c = C
    h, w = m.shape
    region = binary_dilation(m, iterations=3)
    out = np.zeros_like(m)
    x0, y0, x1, y1 = bbox(m, c["pad"], h, w)
    out[y0:y1, x0:x1] = zoom_masks(seg, img, (x0, y0, x1, y1), region[y0:y1, x0:x1], c["prompts"], c["thr"])
    if out.sum() < c["fallback"] * m.sum():  # e.g. white outlined letters on white
        out[y0:y1, x0:x1] |= zoom_masks(seg, img, (x0, y0, x1, y1), region[y0:y1, x0:x1], c["rescue"], c["thr"])
    rest = m & ~binary_dilation(out, iterations=6)
    lab, n = label(rest)
    for k in range(1, n + 1):
        part = lab == k
        if part.sum() < 0.03 * m.sum() or part.sum() < 150:
            continue
        bx = bbox(part, c["pad"], h, w)
        out[bx[1]:bx[3], bx[0]:bx[2]] |= zoom_masks(seg, img, bx, binary_dilation(part, iterations=3)[bx[1]:bx[3], bx[0]:bx[2]],
                                                    c["prompts2"], c["thr"])
    if out.sum() < c["fallback"] * m.sum():
        # SAM would not re-find it zoomed, but the original mask looks like strokes, not a flat region: an isolated
        # letter (ToG 223: K, R, H, E, PAT were wrongly dropped; hair, cape, skin were flat or solid)
        ys, xs = np.nonzero(m)
        fill = m.sum() / ((ys.ptp() + 1) * (xs.ptp() + 1))
        if fill <= 0.55 and uniformity(np.asarray(img), m) <= 0.45:
            return m, "kept-original"
        return np.zeros_like(m), "dropped"
    out, status = complete(np.asarray(img), m, out)
    if status == "partial":
        return np.zeros_like(m), "dropped-partial"
    out, st2 = extend(seg, img, out)
    if st2 != "ok":
        status = st2 if status == "ok" else status + "+" + st2
    region = region | binary_dilation(out, iterations=3)
    out = binary_dilation(out, iterations=c["margin"]) & region
    return out, status


def complete(pixels, orig, out):
    """Letters SAM's zoomed pass missed: blobs of the original mask, away from the new mask, whose colours match the
    captured letters rather than the gaps between them. Recapture them; a letter-like leftover still unresolved is
    reported, so the whole effect is dropped instead of half-erased."""
    if not out.any():
        return out, "ok"
    code = colour_codes(pixels)
    gaps = orig & ~binary_dilation(out, iterations=2)
    letters_h = np.bincount(code[out], minlength=4096) / max(1, out.sum())
    gaps_h = np.bincount(code[gaps], minlength=4096) / max(1, gaps.sum())
    letter_colour = letters_h > 2.0 * gaps_h + 1e-4  # far commoner in the letters than in the gaps
    rest = orig & ~binary_dilation(out, iterations=4)
    cand = rest & letter_colour[code]
    lab, n = label(cand)
    if not n:
        return out, "ok"
    letter_lab, _ = label(out)
    areas = np.bincount(letter_lab.ravel())[1:]
    typical = float(np.median(areas)) if len(areas) else 0
    sizes = np.bincount(lab.ravel())
    missing = [k for k in range(1, n + 1) if sizes[k] >= C["missing_frac"] * typical]
    if not missing:
        return out, "ok"
    add = binary_dilation(np.isin(lab, missing), iterations=2) & orig  # the blob plus its outline ring
    new = out | add
    left = orig & ~binary_dilation(new, iterations=4) & letter_colour[code]
    ll, nn = label(left)
    if nn and np.bincount(ll.ravel())[1:].max() >= C["missing_frac"] * typical:
        return out, "partial"
    return new, "recaptured"


def extend(seg, img, out):
    """A letter the original mask never had: a blob near the captured letters with their colours and size, in line
    with the word. Added only if SAM confirms it on a zoomed crop; an unconfirmed candidate is ignored (Tower of God
    223: all 4 effects dropped on an unconfirmed candidate were complete words)."""
    if not out.any():
        return out, "ok"
    pixels = np.asarray(img)
    h, w = out.shape
    lab, nl = label(out)
    hs, areas = [], []
    for j in range(1, nl + 1):
        ys = np.nonzero(lab == j)[0]
        hs.append(ys.max() - ys.min() + 1)
        areas.append((lab == j).sum())
    H, A = float(np.median(hs)), float(np.median(areas))
    if H < 8:
        return out, "ok"
    code = colour_codes(pixels)
    band = binary_dilation(out, iterations=int(1.2 * H)) & ~binary_dilation(out, iterations=3)
    letters_h = np.bincount(code[out], minlength=4096) / max(1, out.sum())
    band_h = np.bincount(code[band], minlength=4096) / max(1, band.sum())
    letter_colour = letters_h > 3.0 * band_h + 1e-4
    cand = band & letter_colour[code]
    top2 = np.argsort(letters_h)[::-1][:2]  # fill and outline: a missing letter must hold both
    cy = np.array([np.mean(np.nonzero(lab == j)[0]) for j in range(1, nl + 1)])
    cx = np.array([np.mean(np.nonzero(lab == j)[1]) for j in range(1, nl + 1)])
    pts = np.stack([cx, cy], 1)
    centre = pts.mean(0)
    axis = np.linalg.svd(pts - centre)[2][0] if nl >= 2 else np.array([1.0, 0.0])
    cl, cn = label(binary_dilation(cand, iterations=1))
    status = "ok"
    for k in range(1, cn + 1):
        blob = (cl == k) & cand
        ys, xs = np.nonzero(blob)
        bh, bw = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        if not (0.3 * A <= blob.sum() <= 3 * A and 0.5 * H <= bh <= 2 * H):
            continue
        if blob.sum() / (bh * bw) > 0.66:  # solid: art, not a stroke
            continue
        if min((code[blob] == t).mean() for t in top2) < 0.1:
            continue
        d = np.array([xs.mean(), ys.mean()]) - centre
        if abs(d[0] * axis[1] - d[1] * axis[0]) > H:  # not in line with the word
            continue
        bx = bbox(blob, C["pad"], h, w)
        got = zoom_masks(seg, img, bx, binary_dilation(blob, iterations=4)[bx[1]:bx[3], bx[0]:bx[2]], C["prompts"], C["thr"])
        if got.sum() >= 0.5 * blob.sum():
            out[bx[1]:bx[3], bx[0]:bx[2]] |= got
            status = "extended"
    return out, status


def same_word(code, a, b):
    """Two sound-effect masks are pieces of one word: same letter colours, similar letter height, close."""
    ha = np.bincount(code[a], minlength=4096) / max(1, a.sum())
    hb = np.bincount(code[b], minlength=4096) / max(1, b.sum())
    if np.minimum(ha, hb).sum() < 0.4:
        return False
    _, Ha = letter_stats(a)
    _, Hb = letter_stats(b)
    if not Ha or not Hb or max(Ha, Hb) / min(Ha, Hb) > 1.7:
        return False
    ya, xa = np.nonzero(a)
    yb, xb = np.nonzero(b)
    gy = max(0, max(ya.min(), yb.min()) - min(ya.max(), yb.max()))
    gx = max(0, max(xa.min(), xb.min()) - min(xa.max(), xb.max()))
    return (gy ** 2 + gx ** 2) ** 0.5 <= 3 * max(Ha, Hb)


def gap_letters(code, union, H, A, region):
    """Letter-like blobs (the word's colours, letter size, stroke-shaped) inside `region` not covered by `union`."""
    # background colours from the whole panel outside the word, not a ring around it: a ring would hold the missing
    # letters themselves (RUMBLE, ToG 223 p2)
    band = ~binary_dilation(union, iterations=3)
    lh = np.bincount(code[union], minlength=4096) / max(1, union.sum())
    bh = np.bincount(code[band], minlength=4096) / max(1, band.sum())
    colour = lh > 3.0 * bh + 1e-4
    top2 = np.argsort(lh)[::-1][:2]
    cand = region & ~binary_dilation(union, iterations=3) & colour[code]
    cl, cn = label(binary_dilation(cand, iterations=1))
    out = np.zeros_like(union)
    for k in range(1, cn + 1):
        blob = (cl == k) & cand
        ys, xs = np.nonzero(blob)
        bh_, bw_ = ys.max() - ys.min() + 1, xs.max() - xs.min() + 1
        if not (0.3 * A <= blob.sum() <= 3 * A and 0.5 * H <= bh_ <= 2.2 * H):
            continue
        if blob.sum() / (bh_ * bw_) > 0.66:
            continue
        if min((code[blob] == t).mean() for t in top2) < 0.08:
            continue
        out |= blob
    return out


def widest_gap(m, H):
    """Largest gap between consecutive letters along the word's axis, in normal letter spacings (or letter heights
    when there are too few letters to measure spacing)."""
    lab, n = label(m)
    cents = []
    for j in range(1, n + 1):
        ys, xs = np.nonzero(lab == j)
        if ys.ptp() + 1 >= 0.4 * H:
            cents.append((xs.mean(), ys.mean()))
    if len(cents) < 2:
        return 0.0
    pts = np.array(cents)
    axis = np.linalg.svd(pts - pts.mean(0))[2][0]
    gaps = np.diff(np.sort((pts - pts.mean(0)) @ axis))
    unit = float(np.median(gaps)) if len(gaps) >= 3 else H
    return float(gaps.max() / max(unit, 1.0))


def word_check(seg, img, pieces):
    """Pieces judged to be one word (or one short fragment alone) -> (mask, or per-piece list, or None; status)."""
    union = np.logical_or.reduce(pieces)
    _, H = letter_stats(union)
    h, w = union.shape
    if len(pieces) > 1:
        # zoom SAM on the whole word to capture letters between the pieces, then require even spacing
        if not H or H < 8:
            return union, "word-joined"
        bx = bbox(union, int(0.5 * H), h, w)
        got = zoom_masks(seg, img, bx, np.ones((bx[3] - bx[1], bx[2] - bx[0]), bool), C["prompts"], C["thr"])
        grown = union.copy()
        grown[bx[1]:bx[3], bx[0]:bx[2]] |= got
        before, after = widest_gap(union, H), widest_gap(grown, H)
        if after > 2.2:
            # letters still missing: drop the fragments (1-2 letters, the half-erasure risk), keep complete words
            # (GAAAAH beside a stray "AA" of another word, ToG 223 p4)
            return [p if letter_stats(p)[0] > 2 else None for p in pieces], "dropped-word-gap"
        return grown, ("word-captured" if before > 2.2 else "word-joined")
    if not H or H < 8:
        return union, "ok"
    code = colour_codes(np.asarray(img))
    lab, _ = label(union)
    A = float(np.median(np.bincount(lab.ravel())[1:]))
    missing = gap_letters(code, union, H, A, binary_dilation(union, iterations=int(1.5 * H)))
    if not missing.any():
        return union, "ok"
    bx = bbox(union | missing, C["pad"], h, w)
    got = zoom_masks(seg, img, bx, binary_dilation(union | missing, iterations=6)[bx[1]:bx[3], bx[0]:bx[2]], C["prompts"], C["thr"])
    grown = union.copy()
    grown[bx[1]:bx[3], bx[0]:bx[2]] |= got
    left = missing & ~binary_dilation(grown, iterations=2)
    if left.sum() < 0.3 * missing.sum():
        return grown, "fragment-captured"
    return None, "dropped-fragment"


def refine_panel(seg, img: Image.Image, found: list[Found], log: list[str] | None = None) -> list[Found]:
    """All sound effects of a panel refined and grouped into words; bubbles and captions pass through unchanged.
    log: gets each effect's refine status and each word check's ("dropped-partial", "word-captured", ...)."""
    log = [] if log is None else log
    items, seen = [], set()
    for f in found:
        if f.kind != "sfx":
            continue
        k = f.mask.tobytes().__hash__()
        if k in seen:
            continue
        seen.add(k)
        r, status = refine(seg, img, f.mask)
        log.append(status)
        items.append([f, r])
    code = colour_codes(np.asarray(img))
    live = [k for k, it in enumerate(items) if it[1].any()]
    parent = {k: k for k in live}

    def find(k):
        while parent[k] != k:
            k = parent[k]
        return k

    letters = {k: letter_stats(items[k][1])[0] for k in live}
    for i1 in live:
        for i2 in live:
            # two pieces of 3+ letters each are separate words (SCRITCH beside SCRIBBLE, MUMBLE MUMBLE); only a
            # fragment of 1-2 letters is joined to a neighbour (RUMBLE split as R + LE)
            if i1 < i2 and min(letters[i1], letters[i2]) <= 2 and same_word(code, items[i1][1], items[i2][1]):
                parent[find(i1)] = find(i2)
    groups: dict[int, list[int]] = {}
    for k in live:
        groups.setdefault(find(k), []).append(k)
    for ks in groups.values():
        if len(ks) == 1 and letters[ks[0]] > 2:
            continue  # a word of 3+ letters on its own: nothing to check
        res, status = word_check(seg, img, [items[k][1] for k in ks])
        log.append(status)
        for n_, k in enumerate(ks):
            if isinstance(res, list):
                items[k][1] = res[n_] if res[n_] is not None else np.zeros_like(items[k][1])
            else:
                items[k][1] = res if res is not None else np.zeros_like(items[k][1])
    out = [f for f in found if f.kind != "sfx"]
    return out + [Found(r, f.score, "sfx") for f, r in items if r.any()]


if __name__ == "__main__":
    main()
