"""Step 6: lettering as data. The lettering erased from the art (hidden_layers.prepare) comes back as one floating panel
per element, drawn by the reader at the same place: shape, colours and text size measured from the ORIGINAL pixels.

    uv run python lettering_layer.py room     # ToG 228 p6: bubbles.json for the viewer + an offline check image

Writes <out>/<pid>.bubbles.json:
  {pid, w, h, fov, font, cap_ratio, bubbles: [{id, text, kind, speaker, anchor, bbox, shape, polygon, fill, outline,
   outline_px, text_colour, text_px, font_px, line_height, lines, text_box, text_area, uppercase, depth}]}
bbox, polygon, text_box in box px; text_area [cx, cy, max_w, max_h] is where the text is wrapped and centred (both
renderers: greedy word wrap at max_w, shrink 5% at a time until the block fits max_h); depth is camera-space (the
cloud2 depth, -z): the bubble's plane faces the panel camera and projects exactly onto bbox.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import binary_dilation, binary_erosion, find_objects, label

DATA = Path(__file__).resolve().parents[1] / ".data"
FONT_FILE = DATA / "fonts" / "ComicNeue-Bold.ttf"
FONT_NAME = "Comic Neue"
CAP_RATIO = 0.681      # Comic Neue Bold: cap height / em (PIL getbbox("H") at 1000 px: 225..906)
FOV = 55.0             # parallax.FOV, long side
RECT_FILL = 0.90       # mask share of its bbox above which the shape is a rectangle
MAX_POLY = 64
RING_PX = 20           # scene depth is sampled this far around the mask
DEPTH_PCT = 5
DEPTH_FRONT = 0.97     # floats just in front of the nearest scene around it (fallback only; see place)
NUDGE_MAX = 0          # px a bubble may move sideways from where the artist put it: 0, collisions are solved in depth
                       # only (z), the bubble stays exactly where it was drawn (user, 2026-10-25)
NUDGE_STEP = 4
MARGIN = 6             # px around the bubble that must also lie behind it
GAP = 0.007            # the bubble sits this much in front of the nearest scene under it, and never behind the frames'
WINDOW_Z = 1.0         # windows (cards.WINDOW_Z): the bubbles are not clipped, so they stand at the window, in front
                       # of the layers seen through it, not down among them
CLEAR_PX = 60          # px around the bubble checked for nearer surfaces a head move could slide over it
HEAD_SHIFT = 0.05      # head move as a share of scene depth (the parallax design value)
POP_WEIGHT = 4.0       # cost of floating far in front of the scene behind (1.0 = a full NUDGE_MAX shift per 25%)
VIOL_WEIGHT = 20.0     # cost per clearance violation, as a share of the bubble's area


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


def place(mask: np.ndarray, depth: np.ndarray, ok: np.ndarray, taken: np.ndarray, f: float) -> tuple[int, int, float, dict]:
    """Where a bubble goes without colliding with the 3D scene: (dx, dy, depth, why).

    Collisions are of two kinds: scene geometry poking through the bubble (something under it nearer than it), and
    geometry nearer than the bubble sliding over it when the head moves. Small shifts around the original position
    (up to NUDGE_MAX px, every NUDGE_STEP) are tried; for each, the bubble's depth is GAP in front of the NEAREST scene
    under it and a MARGIN around it (minimum, not a percentile: nothing pokes through), and the scene is checked
    out to CLEAR_PX around it: a surface nearer than the bubble must be farther from its edge than a HEAD_SHIFT head
    move can carry it, f * T * (1/d_near - 1/d_bubble) px. Cost: the shift (stay where the artist put it), how far the
    bubble pops out in front of the scene behind it (pulled very close it looks detached), and clearance violations.
    Shifts overlapping another placed bubble or leaving the art are ruled out."""
    from scipy.ndimage import distance_transform_edt, shift as nd_shift
    h, w = mask.shape
    best = None
    ys, xs = np.nonzero(mask)
    for dy in range(-NUDGE_MAX, NUDGE_MAX + 1, NUDGE_STEP):
        for dx in range(-NUDGE_MAX, NUDGE_MAX + 1, NUDGE_STEP):
            if dx * dx + dy * dy > NUDGE_MAX * NUDGE_MAX:
                continue
            yy, xx = ys + dy, xs + dx
            if yy.min() < 0 or xx.min() < 0 or yy.max() >= h or xx.max() >= w:
                continue
            m = np.zeros_like(mask)
            m[yy, xx] = True
            if (m & taken).any():
                continue
            if (m & ok).sum() < 0.5 * (mask & ok).sum():  # mostly off the art (the gutter)
                continue
            under = binary_dilation(m, iterations=MARGIN) & ok
            if under.sum() < 20:
                continue
            d_near = float(depth[under].min())
            d_b = min(d_near, WINDOW_Z) * (1 - GAP)
            d_back = float(np.median(depth[m & ok])) if (m & ok).any() else d_near
            pop = d_back / d_b - 1  # how far in front of the scene behind it
            # clearance: nearer-than-bubble surfaces around it, closer to its edge than a head move carries them
            x0, x1 = max(0, xx.min() - CLEAR_PX), min(w, xx.max() + CLEAR_PX + 1)
            y0, y1 = max(0, yy.min() - CLEAR_PX), min(h, yy.max() + CLEAR_PX + 1)
            sub_m = m[y0:y1, x0:x1]
            dist = distance_transform_edt(~sub_m)
            sd, so = depth[y0:y1, x0:x1], ok[y0:y1, x0:x1]
            nearer = so & ~sub_m & (sd < d_b)
            need = f * HEAD_SHIFT * (1 / np.maximum(sd, 1e-6) - 1 / d_b)
            viol = int((nearer & (dist < need)).sum())
            cost = (dx * dx + dy * dy) ** 0.5 / max(1, NUDGE_MAX) + POP_WEIGHT * pop + VIOL_WEIGHT * viol / max(1, int(m.sum()))
            if best is None or cost < best[0]:
                best = (cost, dx, dy, d_b, {"pop": round(pop, 3), "violations": viol})
    if best is None:  # nowhere free: stay, in front of everything under it
        under = binary_dilation(mask, iterations=MARGIN) & ok
        d = min(float(depth[under].min()), WINDOW_Z) * (1 - GAP) if under.any() else WINDOW_Z * (1 - GAP)
        return 0, 0, d, {"pop": None, "violations": None}
    return best[1], best[2], best[3], best[4]


def build(pid: str, img, letter_masks: list[np.ndarray], understand_result: dict | None, depth: np.ndarray,
          out_path: Path, kinds: list[str] | None = None, valid: np.ndarray | None = None) -> dict:
    """img: the original box (RGB, lettering still in it). letter_masks: per element, element k is understand's id k+1.
    depth: camera-space depth of the box (H x W). valid: pixels with a real surface (not gutter); all when None.
    kinds: the segmenter's kind per mask, used when understand has none."""
    img = np.asarray(img.convert("RGB")) if isinstance(img, Image.Image) else np.asarray(img)
    h, w = img.shape[:2]
    els = {int(e["id"]): e for e in (understand_result or {}).get("elements", []) if "id" in e}
    ok = np.isfinite(depth) & (depth > 0) & (valid if valid is not None else True)
    fallback = float(np.percentile(depth[ok], DEPTH_PCT)) if ok.any() else float(np.median(depth))
    bubbles = []
    f = max(w, h) / (2 * np.tan(np.radians(FOV) / 2))
    taken = np.zeros((h, w), bool)
    # biggest first: they have the least room to move
    order = sorted(range(len(letter_masks)), key=lambda k: -int(letter_masks[k].sum()))
    for k in order:
        raw = letter_masks[k]
        mask = _clean(raw.astype(bool), valid)
        if not mask.any():
            continue
        e = els.get(k + 1, {})
        dx, dy, d, why = place(mask, depth, ok, taken, f)
        mask = np.roll(np.roll(mask, dy, 0), dx, 1)  # the bubble at its placed position (place keeps it in bounds)
        taken |= binary_dilation(mask, iterations=4)
        mm = measure(np.roll(np.roll(img, dy, 0), dx, 1), mask)  # colours read where the original pixels moved to
        d = d / DEPTH_FRONT  # (written as d * DEPTH_FRONT below)
        x0, y0, x1, y1 = mm["bbox"]
        bw, bh = x1 - x0, y1 - y0
        rect = mm.pop("fill_share") > RECT_FILL
        text = (e.get("text") or "") if e.get("keep", True) and e else ""
        kind = e.get("kind") or (kinds[k] if kinds and k < len(kinds) else None)
        # layout shared by both renderers: font from the measured cap height, text centred where the original was
        font_px = (mm["text_px"] / CAP_RATIO) if mm["text_px"] else max(10.0, 0.08 * min(bw, bh))
        lh = float(np.clip(mm["line_px"] / font_px, 1.0, 1.6)) if mm["line_px"] else 1.2
        inset = 0.86 if rect else 0.70
        tb = mm["text_box"]
        cx, cy = ((tb[0] + tb[2]) / 2, (tb[1] + tb[3]) / 2) if tb else ((x0 + x1) / 2, (y0 + y1) / 2)
        max_w = min(bw * inset, ((tb[2] - tb[0]) * 1.05) if tb else bw * inset)  # the original's line breaks
        bubbles.append({
            "id": k + 1, "text": text, "kind": kind, "speaker": e.get("speaker"), "anchor": e.get("anchor"),
            "bbox": mm["bbox"], "shape": "rect" if rect else "ellipse", "polygon": _polygon(mask),
            "fill": mm["fill"], "outline": mm["outline"], "outline_px": mm["outline_px"], "text_colour": mm["text_colour"],
            "text_px": mm["text_px"], "font_px": round(font_px, 1), "line_height": round(lh, 3), "lines": mm["lines"],
            "text_box": tb, "text_area": [round(cx, 1), round(cy, 1), round(max_w, 1), round(bh * inset, 1)],
            "uppercase": (not text) or text == text.upper(), "depth": round(d * DEPTH_FRONT, 5),
            "nudge": [dx, dy], "placement": why,
        })
    bubbles.sort(key=lambda b: b["id"])
    res = {"pid": pid, "w": w, "h": h, "fov": FOV, "font": FONT_NAME, "cap_ratio": CAP_RATIO, "bubbles": bubbles}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(res, indent=1))
    return res


# ---------- offline renderer: the viewer's layout rules in PIL, to check a bubbles.json on the base image ----------
def wrap(text: str, width_of, max_w: float) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if cur and width_of(t) > max_w:
            lines.append(cur); cur = word
        else:
            cur = t
    return lines + ([cur] if cur else [])


def fit_text(text: str, b: dict, font_for) -> tuple[float, list[str]]:
    """Greedy wrap at text_area's width; the font shrinks 5% at a time until the block fits its height."""
    _, _, max_w, max_h = b["text_area"]
    px = b["font_px"]
    while True:
        f = font_for(px)
        lines = wrap(text, f.getlength, max_w)
        block = (len(lines) - 1) * b["line_height"] * px + CAP_RATIO * px
        wide = max((f.getlength(l) for l in lines), default=0)
        if (block <= max_h and wide <= max_w * 1.02) or px <= 8:
            return px, lines
        px *= 0.95


def render(base: Image.Image, data: dict, scale: int = 2) -> Image.Image:
    """Draws every bubble on the base image (supersampled by `scale`), the way the viewer draws its canvas."""
    W, H = base.size
    big = base.convert("RGB").resize((W * scale, H * scale), Image.LANCZOS)
    d = ImageDraw.Draw(big)
    fonts = {}
    font_for = lambda px: fonts.setdefault(round(px * scale, 1), ImageFont.truetype(str(FONT_FILE), max(1, round(px * scale))))
    S = lambda v: v * scale
    for b in data["bubbles"]:
        x0, y0, x1, y1 = b["bbox"]
        ow = b["outline_px"]
        if b["shape"] == "rect":
            r = 0.012 * min(x1 - x0, y1 - y0)  # CORNER in the viewer
            d.rounded_rectangle([S(x0), S(y0), S(x1) - 1, S(y1) - 1], radius=S(r), fill=b["fill"],
                                outline=b["outline"] if ow else None, width=max(1, round(S(ow))))
        elif len(b["polygon"]) >= 3:
            pts = [(S(x), S(y)) for x, y in b["polygon"]]
            d.polygon(pts, fill=b["fill"])
            if ow:
                d.line(pts + pts[:1], fill=b["outline"], width=max(1, round(S(ow))), joint="curve")
        else:
            d.ellipse([S(x0), S(y0), S(x1), S(y1)], fill=b["fill"], outline=b["outline"] if ow else None,
                      width=max(1, round(S(ow))))
        text = b["text"].upper() if b["uppercase"] else b["text"]
        if not text or not b["text_colour"]:
            continue
        unscaled = lambda px: _Scaled(font_for(px), scale)
        px, lines = fit_text(text, b, unscaled)
        cx, cy = b["text_area"][:2]
        lh = b["line_height"] * px
        block = (len(lines) - 1) * lh + CAP_RATIO * px
        base_y = cy - block / 2 + CAP_RATIO * px
        f = font_for(px)
        for i, line in enumerate(lines):
            d.text((S(cx), S(base_y + i * lh)), line, font=f, fill=b["text_colour"], anchor="ms")
    return big.resize((W, H), Image.LANCZOS)


class _Scaled:
    """A font measured in unscaled box px."""
    def __init__(self, f, s):
        self.f, self.s = f, s

    def getlength(self, t):
        return self.f.getlength(t) / self.s


# ---------- the room box (ToG 228 p6): no understand JSON yet, the captions' text given by hand ----------
def room() -> None:
    import io
    import zipfile
    from masks import load_masks
    pid = "tower-of-god-s3-228-p006"
    out = DATA / "out"
    z = zipfile.ZipFile(out / "chapters" / "tower-of-god-s3-228.zumi")
    panel = json.loads(z.read("manifest.json"))["panels"][6]
    img = Image.open(io.BytesIO(z.read(panel["layers"][0]["image"]))).convert("RGB")
    found = load_masks(out / "heldout" / "tog228" / "lettering_rev" / f"{pid}.npz")
    w, h = img.size
    buf = np.fromfile(out / "parallax_viewer" / "cloud2" / f"{pid}.bin", np.uint8)
    n = w * h
    xyz = buf[: n * 12].view(np.float32).reshape(h, w, 3)
    lab = buf[n * 15: n * 16].reshape(h, w)
    depth = -xyz[..., 2]
    texts = ["...WAS TO HAVE A SPOT AS CLOSE TO THAT BEAUTIFUL CREATURE AS POSSIBLE.",
             "I JUST WANTED TO HAVE THE PRIVILEGE OF GAZING AT HIM AND TALKING TO HIM."]
    order = sorted(range(len(found)), key=lambda k: found[k].bbox()[0])  # top to bottom
    und = {"elements": [{"id": k + 1, "keep": True, "kind": "caption", "text": texts[r], "speaker": "narrator"}
                        for r, k in enumerate(order[: len(texts)])]}
    res = build(pid, img, [f.mask for f in found], und, depth, out / "parallax_viewer" / "mesh" / f"{pid}.bubbles.json",
                kinds=[f.kind for f in found], valid=lab != 2)
    base = Image.open(out / "room_plate" / pid / "r8-tone" / "base.png").convert("RGB")
    drawn = render(base, res)
    sheet = Image.new("RGB", (w * 3 + 32, h + 40), "white")
    for i, (im, t) in enumerate([(img, "original box"), (base, "base (lettering erased)"), (drawn, "base + redrawn lettering")]):
        sheet.paste(im, (8 + i * (w + 8), 32))
        ImageDraw.Draw(sheet).text((8 + i * (w + 8), 8), t, fill=(0, 0, 0), font=ImageFont.truetype(str(FONT_FILE), 20))
    (out / "lettering").mkdir(parents=True, exist_ok=True)
    sheet.save(out / "lettering" / "room_check.png")
    for b in res["bubbles"]:
        print({k: b[k] for k in ("id", "bbox", "shape", "fill", "outline", "outline_px", "text_colour", "text_px",
                                 "font_px", "line_height", "lines", "text_box", "depth")})


if __name__ == "__main__":
    {"room": room}[sys.argv[1]]()
