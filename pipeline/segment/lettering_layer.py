"""Lettering as data. The lettering erased from the art comes back as one floating panel per element, at the same
place: shape, colours and text size measured from the ORIGINAL pixels, and a depth just in front of whatever is behind
it (place); cards.lettering_layers draws each as a card of the original bubble. Understand's text, kind and
speaker are joined in by understood (at build, or afterwards with annotate).

build returns the box's bubbles.json (the caller saves it, boxstore.Box.save_bubbles):
  {pid, w, h, fov, font, cap_ratio, bubbles: [{id, text, kind, speaker, anchor, bbox, shape, polygon, fill, outline,
   outline_px, text_colour, text_px, font_px, line_height, lines, text_box, text_area, uppercase, depth, placement}]}
bbox, polygon, text_box in box px; text_area [cx, cy, max_w, max_h] is where the text is wrapped and centred (both
renderers: greedy word wrap at max_w, shrink 5% at a time until the block fits max_h); depth is camera-space (the
layers' nearest depth): the bubble's plane faces the panel camera and projects exactly onto bbox.
"""
from __future__ import annotations

import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_erosion, find_objects, label

from view import FOV, WINDOW_Z, focal

FONT_NAME = "Comic Neue"
CAP_RATIO = 0.681      # Comic Neue Bold: cap height / em (PIL getbbox("H") at 1000 px: 225..906)
RECT_FILL = 0.90       # mask share of its bbox above which the shape is a rectangle
MAX_POLY = 64
MARGIN = 6             # px around the bubble that must also lie behind it
GAP = 0.007            # the bubble sits this much in front of the nearest scene under it, and never behind the frames'
                       # windows (view.WINDOW_Z): the bubbles are not clipped, so they stand at the window, in front
                       # of the layers seen through it, not down among them
CLEAR_PX = 60          # px around the bubble checked for nearer surfaces a head move could slide over it
HEAD_SHIFT = 0.05      # head move as a share of scene depth (the parallax design value)


def _dominant(px: np.ndarray) -> np.ndarray | None:
    """Median of the pixels in the most common colour bin (32 levels per channel): robust to anti-aliasing and to a
    loose mask catching a little art."""
    if len(px) == 0:
        return None
    q = (px // 32).astype(np.int32)
    key = q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2]
    mode = np.bincount(key).argmax()
    return np.median(px[key == mode], axis=0)


def _dist(px: np.ndarray, c: np.ndarray) -> np.ndarray:
    return np.linalg.norm(px.astype(np.float32) - c[None].astype(np.float32), axis=1)


def _hex(c) -> str:
    return "#%02x%02x%02x" % tuple(int(round(v)) for v in c)


def _polygon(mask: np.ndarray) -> list[list[int]]:
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return []
    c = max(cs, key=cv2.contourArea)
    eps = 1.0
    p = cv2.approxPolyDP(c, eps, True)
    while len(p) > MAX_POLY:
        eps *= 1.5
        p = cv2.approxPolyDP(c, eps, True)
    return p.reshape(-1, 2).astype(int).tolist()


def _clean(mask: np.ndarray, valid: np.ndarray | None) -> np.ndarray:
    """Drops specks (< 2% of the element) and small parts lying wholly in the gutter (< 15%). A caption that crosses
    into the gutter is one connected part and stays whole."""
    lab, n = label(mask)
    if n <= 1:
        return mask
    sizes = np.bincount(lab.ravel())[1:]
    keep = np.zeros(n + 1, bool)
    for j, a in enumerate(sizes, 1):
        share = a / mask.sum()
        gutter_only = valid is not None and not (valid & (lab == j)).any()
        keep[j] = share >= 0.02 and not (gutter_only and share < 0.15)
    return keep[lab] if keep.any() else mask


def measure(img: np.ndarray, mask: np.ndarray) -> dict:
    """Colours, outline thickness and text geometry of one element from the original pixels inside its mask."""
    ys, xs = np.nonzero(mask)
    x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
    bw, bh = x1 - x0, y1 - y0
    m = mask[y0:y1, x0:x1]
    px = img[y0:y1, x0:x1]
    edge = max(3, int(round(0.012 * min(bw, bh))))  # the outline band, ~1% of the bubble
    inner = binary_erosion(m, iterations=edge)
    if inner.sum() < 50:
        inner = m
    band = m & ~binary_erosion(m, iterations=edge)
    fill = _dominant(px[inner])
    d_in = _dist(px[inner], fill)
    # text: interior pixels far from the fill (half way to the most contrasting tenth)
    far = np.percentile(d_in, 99) if len(d_in) else 0
    out = {"bbox": [x0, y0, x1, y1], "fill": _hex(fill)}
    text_col, glyph_h, lines, line_px, tbox = None, None, 0, None, None
    if far > 60:
        tmask = np.zeros_like(m)
        tmask[inner] = d_in > far / 2
        cand = px[inner][d_in > 0.75 * far]  # the solid core of the letters, not their anti-aliased rim
        text_col = _dominant(cand)
        # glyphs: connected components of the text pixels, away from the outline
        core = binary_erosion(m, iterations=edge + 3)
        lab, n = label(tmask & core)
        boxes = []
        for sl in find_objects(lab):
            if sl is None:
                continue
            h, w = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            if h * w >= 6 and h < 0.4 * bh and w < 0.5 * bw:
                boxes.append((sl[1].start, sl[0].start, sl[1].stop, sl[0].stop))
        if boxes:
            hs = np.array([b[3] - b[1] for b in boxes], float)
            m0 = np.median(hs)
            letters = [b for b, h in zip(boxes, hs) if 0.6 * m0 <= h <= 1.6 * m0]
            if not letters:  # two marks of very different heights: none near the median (P&C 36 p3)
                letters = boxes
            glyph_h = float(np.median([b[3] - b[1] for b in letters]))
            tb = np.array([b for b, h in zip(boxes, hs) if h >= 0.25 * m0])  # punctuation in, specks out
            tbox = [int(tb[:, 0].min()) + x0, int(tb[:, 1].min()) + y0, int(tb[:, 2].max()) + x0, int(tb[:, 3].max()) + y0]
            cy = np.sort([(b[1] + b[3]) / 2 for b in letters])
            # line centres: mean of each run
            runs, cur = [], [cy[0]]
            for a, b in zip(cy[:-1], cy[1:]):
                if b - a > 0.6 * glyph_h:
                    runs.append(np.mean(cur)); cur = []
                cur.append(b)
            runs.append(np.mean(cur))
            lines = len(runs)
            line_px = float(np.median(np.diff(runs))) if lines > 1 else None
    # outline: band pixels unlike the fill, their most common colour; none when they are a small share of the band
    bpx = px[band]
    unlike = bpx[_dist(bpx, fill) > 60]
    if len(unlike) > 0.10 * len(bpx):
        outline = _dominant(unlike)
        perim = max(1.0, cv2.arcLength(max(cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)[0],
                                           key=cv2.contourArea), True))
        near = (_dist(bpx, outline) < 60).sum()
        outline_px = float(np.clip(near / perim, 1, 8))
    else:
        outline, outline_px = fill, 0.0
    out.update({"outline": _hex(outline), "outline_px": round(outline_px, 1),
                "text_colour": _hex(text_col) if text_col is not None else None,
                "text_px": round(glyph_h, 1) if glyph_h else None, "lines": lines,
                "line_px": round(line_px, 1) if line_px else None, "text_box": tbox, "fill_share": float(m.mean())})
    return out


def place(mask: np.ndarray, depth: np.ndarray, ok: np.ndarray, taken: np.ndarray, f: float) -> tuple[float, dict]:
    """A bubble's depth where the artist drew it, and why: (depth, {"pop", "violations"}). It never moves sideways:
    collisions are solved in depth only (user, 2026-10-25). Its depth is GAP in front of the NEAREST scene under it and
    a MARGIN around it (minimum, not a percentile: nothing pokes through), never behind the frames' windows. Logged:
    how far it pops out in front of the scene behind it, and the clearance violations within CLEAR_PX around it (a
    surface nearer than the bubble closer to its edge than a HEAD_SHIFT head move carries it,
    f * T * (1/d_near - 1/d_bubble) px). A bubble over one placed before it, or with almost no scene under it,
    stays in front of everything under it."""
    from scipy.ndimage import distance_transform_edt
    h, w = mask.shape
    ys, xs = np.nonzero(mask)
    under = binary_dilation(mask, iterations=MARGIN) & ok
    if (mask & taken).any() or under.sum() < 20:
        d = min(float(depth[under].min()), WINDOW_Z) * (1 - GAP) if under.any() else WINDOW_Z * (1 - GAP)
        return d, {"pop": None, "violations": None}
    d_near = float(depth[under].min())
    d_b = min(d_near, WINDOW_Z) * (1 - GAP)
    d_back = float(np.median(depth[mask & ok])) if (mask & ok).any() else d_near
    pop = d_back / d_b - 1  # how far in front of the scene behind it
    x0, x1 = max(0, xs.min() - CLEAR_PX), min(w, xs.max() + CLEAR_PX + 1)
    y0, y1 = max(0, ys.min() - CLEAR_PX), min(h, ys.max() + CLEAR_PX + 1)
    sub_m = mask[y0:y1, x0:x1]
    dist = distance_transform_edt(~sub_m)
    sd, so = depth[y0:y1, x0:x1], ok[y0:y1, x0:x1]
    nearer = so & ~sub_m & (sd < d_b)
    need = f * HEAD_SHIFT * (1 / np.maximum(sd, 1e-6) - 1 / d_b)
    return d_b, {"pop": round(pop, 3), "violations": int((nearer & (dist < need)).sum())}


def understood(e: dict, kind: str | None) -> dict:
    """A bubble's fields from Understand's element for it (e, {} when none), `kind` its kind so far: the text it read
    (none when it dropped the element), its finer kind (speech, caption, shout) when it gave one, the speaker and
    the anchor on the speaker. The one place these fields are joined into bubbles."""
    text = (e.get("text") or "") if e.get("keep", True) and e else ""
    return {"text": text, "kind": e.get("kind") or kind, "speaker": e.get("speaker"), "anchor": e.get("anchor")}


def annotate(bubbles: dict, result: dict) -> dict:
    """bubbles (lettering_layer.build's) with Understand's result for its box joined in (understood)."""
    els = {int(e["id"]): e for e in (result or {}).get("elements", []) if "id" in e}
    for b in bubbles.get("bubbles", []):
        if b["id"] in els:
            b.update(understood(els[b["id"]], b.get("kind")))
            b["uppercase"] = (not b["text"]) or b["text"] == b["text"].upper()
    return bubbles


def build(pid: str, img, letter_masks: list[np.ndarray], understand_result: dict | None, depth: np.ndarray,
          kinds: list[str] | None = None, valid: np.ndarray | None = None) -> dict:
    """The box's bubbles.json (the caller saves it). img: the original box (RGB, lettering still in it).
    letter_masks: per element, element k is understand's id k+1. depth: camera-space depth of the box (H x W).
    valid: pixels with a real surface (not gutter); all when None. kinds: the segmenter's kind per mask, used when
    understand has none."""
    img = np.asarray(img.convert("RGB")) if isinstance(img, Image.Image) else np.asarray(img)
    h, w = img.shape[:2]
    els = {int(e["id"]): e for e in (understand_result or {}).get("elements", []) if "id" in e}
    ok = np.isfinite(depth) & (depth > 0) & (valid if valid is not None else True)
    bubbles = []
    f = focal(w, h)
    taken = np.zeros((h, w), bool)
    # biggest first: they have the least room to move
    order = sorted(range(len(letter_masks)), key=lambda k: -int(letter_masks[k].sum()))
    for k in order:
        raw = letter_masks[k]
        mask = _clean(raw.astype(bool), valid)
        if not mask.any():
            continue
        d, why = place(mask, depth, ok, taken, f)
        taken |= binary_dilation(mask, iterations=4)
        mm = measure(img, mask)
        x0, y0, x1, y1 = mm["bbox"]
        bw, bh = x1 - x0, y1 - y0
        rect = mm.pop("fill_share") > RECT_FILL
        und = understood(els.get(k + 1, {}), kinds[k] if kinds and k < len(kinds) else None)
        text = und["text"]
        # layout shared by both renderers: font from the measured cap height, text centred where the original was
        font_px = (mm["text_px"] / CAP_RATIO) if mm["text_px"] else max(10.0, 0.08 * min(bw, bh))
        lh = float(np.clip(mm["line_px"] / font_px, 1.0, 1.6)) if mm["line_px"] else 1.2
        inset = 0.86 if rect else 0.70
        tb = mm["text_box"]
        cx, cy = ((tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2) if tb else ((x0 + x1) / 2, (y0 + y1) / 2)
        max_w = min(bw * inset, ((tb[2] - tb[0]) * 1.05) if tb else bw * inset)  # the original's line breaks
        bubbles.append({
            "id": k + 1, **und,
            "bbox": mm["bbox"], "shape": "rect" if rect else "ellipse", "polygon": _polygon(mask),
            "fill": mm["fill"], "outline": mm["outline"], "outline_px": mm["outline_px"], "text_colour": mm["text_colour"],
            "text_px": mm["text_px"], "font_px": round(font_px, 1), "line_height": round(lh, 3), "lines": mm["lines"],
            "text_box": tb, "text_area": [round(cx, 1), round(cy, 1), round(max_w, 1), round(bh * inset, 1)],
            "uppercase": (not text) or text == text.upper(), "depth": round(d, 5), "placement": why,
        })
    bubbles.sort(key=lambda b: b["id"])
    return {"pid": pid, "w": w, "h": h, "fov": FOV, "font": FONT_NAME, "cap_ratio": CAP_RATIO, "bubbles": bubbles}


