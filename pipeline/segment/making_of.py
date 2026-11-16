"""The XR demo's "making-of" bundle: the real intermediate results of one finished run, laid out per pencil page for the
reader's pipeline screen (StreamingAssets/MakingOf/). Free and rerunnable: reads files only, no model, no API.

    pencil/NN.jpg   the scanned pencil page, cropped to the paper, at most 1600 px tall
    colour/NN.jpg   the artist's coloured page(s) for it, letterboxed on white to the pencil page's size
    masks/NN.png    RGBA over colour/NN.jpg: balloons coral, characters teal, panel frames as 4 px lines
    making-of.json  per page: frames, balloons (text, speaker, kind) and characters (cast id, box, centre) in page px;
                    the cast shown (name, colour); the picks for depth, voice, sfx

The coloured pages are matched to the pencil pages by content (SIFT matches): each coloured page goes to the pencil
page it matches best, so a pencil page drawn as two webtoon pages gets both, side by side. A box's masks reach its
coloured page through the intake strip (chapters/<stem>.zumi: each box's y in the stitched strip of the coloured pages,
which are stacked in order without gaps).

    python making_of.py [--out apps/xr/Assets/StreamingAssets/MakingOf]
"""
from __future__ import annotations

import argparse
import json
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from boxstore import Episode

ROOT = Path(__file__).resolve().parents[2]
SRC = Path(r"C:\Users\Usuario\Downloads\Paginas finales Comic")
PENCIL = [SRC / "Lapices" / f"Pagina lapiz {i}.jpg" for i in range(1, 11)]
COLOUR = [SRC / "Paginas color" / f"Webtoon Final - Pag {i}.png" for i in range(1, 12)]
CHAPTER = ROOT / "pipeline/.data/out/chapters/dan-buck.zumi"
DATASET = ROOT / "pipeline/.data/out/dan-buck-1115/dataset/dan-buck"
EXPORT = ROOT / "pipeline/.data/out/dan-buck-1115/export/dan-buck-v8.zumi"
OUT = ROOT / "apps/xr/Assets/StreamingAssets/MakingOf"

MAX_H = 1600
GAP = 24  # px between two coloured pages that share one pencil page (output px)
CORAL, TEAL, FRAME = (0xFF, 0x6A, 0x6A), (0x1F, 0xA8, 0x9A), (0xF0, 0xB0, 0x3A)  # coral and amber are theme tokens
ALPHA = int(0.45 * 255)
MIN_FRAME = 0.005  # a frame's smallest area, as a share of the page
SHORT = {"K1": "Buck", "K2": "Dan", "K3": "Barist.AI", "K7": "Barist.AI", "K4": "Customer", "K5": "Customer",
         "K6": "Customer", "K8": "Buck & Dan", "K9": "Officer"}
PICKS = {"depth": "p001", "voice": ("p011", "b1"), "sfx": ("p019", "b1")}
# the identification view: one display name and colour per character. K7 is Barist.AI's second look (the cast says
# so), shown as K3; K8 names a group (Buck, Dan and the officers in one card) and gets no line. Buck and Dan take the
# theme's red and a deep sky blue, the rest are the theme's accents deepened to read on the coloured pages.
SAME = {"K7": "K3"}
MIN_CHAR = 24  # page px: a character card narrower or shorter through its window is a sliver (p019 card-3, 3 x 11)
GROUP = {"K8"}
CAST = {"K1": ("Buck", "#E5332A"), "K2": ("Dan", "#1E88E5"), "K3": ("Barist.AI", "#A64DFF"),
        "K4": ("Shearling coat", "#F0B03A"), "K5": ("Pink top", "#FF4FB0"), "K6": ("Grey hoodie", "#34C759"),
        "K9": ("Officer", "#00B3A4")}


def gray(path: Path, width: int) -> np.ndarray:
    im = Image.open(path).convert("L")
    return np.asarray(im.resize((width, round(im.height * width / im.width)), Image.LANCZOS))


def match_pages() -> dict[int, list[int]]:
    """{pencil index: [coloured indices]} (0-based): every coloured page to the pencil page with most SIFT matches."""
    sift, bf = cv2.SIFT_create(4000), cv2.BFMatcher()
    pen = [sift.detectAndCompute(gray(p, 1000), None)[1] for p in PENCIL]
    col = [sift.detectAndCompute(gray(p, 500), None)[1] for p in COLOUR]
    score = np.array([[sum(1 for m, n in bf.knnMatch(c, p, k=2) if m.distance < 0.75 * n.distance) for c in col]
                      for p in pen])
    print("SIFT matches (rows pencil 1..10, cols colour 1..11):\n", score)
    out: dict[int, list[int]] = {i: [] for i in range(len(PENCIL))}
    for j in range(len(COLOUR)):
        out[int(score[:, j].argmax())].append(j)
    return out


def cast_cards(z: zipfile.ZipFile, pid: str) -> dict[str, str]:
    """{card: cast id} for a panel's character cards: the extras on its scene.glb's nodes."""
    name = f"panels/{pid}/scene.glb"
    if name not in z.namelist():
        return {}
    b = z.read(name)
    n = int.from_bytes(b[12:16], "little")
    nodes = json.loads(b[20:20 + n]).get("nodes", [])
    return {e["card"]: e["cast"] for e in (nd.get("extras") or {} for nd in nodes) if e.get("cast") and e.get("card")}


def preview(out: Path, path: Path) -> None:
    """The coloured pages in a 5 x 2 grid, each character's boxes outlined in its colour and its consecutive
    appearances joined by straight lines in page order, its name at the first one."""
    from PIL import ImageDraw, ImageFont
    doc = json.loads((out / "making-of.json").read_text(encoding="utf-8"))
    S, PAD = 0.4, 16
    W, H = (round(v * S) for v in doc["pages"][0]["size"])
    grid = Image.new("RGB", (5 * W + 6 * PAD, 2 * H + 3 * PAD), "#F7F4EF")
    origin = {}
    for k, p in enumerate(doc["pages"]):
        ox, oy = PAD + (k % 5) * (W + PAD), PAD + (k // 5) * (H + PAD)
        grid.paste(Image.open(out / p["colour"]).convert("RGB").resize((W, H), Image.LANCZOS), (ox, oy))
        origin[p["index"]] = (ox, oy)
    d = ImageDraw.Draw(grid)
    try:
        font = ImageFont.truetype("arialbd.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    at = lambda n, x, y: (origin[n][0] + x * S, origin[n][1] + y * S)
    for c in doc["cast"]:
        seen = [(p["index"], ch) for p in doc["pages"] for ch in p["characters"] if ch["cast"] == c["id"]]
        pts = [at(n, *ch["centre"]) for n, ch in seen]
        for a, b in zip(pts, pts[1:]):
            d.line([a, b], fill="#222222", width=6)
            d.line([a, b], fill=c["colour"], width=3)
        for n, ch in seen:
            x0, y0 = at(n, *ch["box"][:2])
            x1, y1 = at(n, *ch["box"][2:])
            d.rectangle([x0, y0, x1, y1], outline="#222222", width=6)
            d.rectangle([x0 + 1, y0 + 1, x1 - 1, y1 - 1], outline=c["colour"], width=3)
        if seen:
            n, ch = seen[0]
            x, y = at(n, *ch["box"][:2])
            d.text((x + 4, y + 4), c["name"], fill=c["colour"], font=font, stroke_width=3, stroke_fill="#222222")
    path.parent.mkdir(parents=True, exist_ok=True)
    grid.save(path, quality=88)


def paper(path: Path) -> Image.Image:
    """The pencil scan cropped to the paper (rows and columns at the edge darker than paper dropped), upright."""
    im = Image.open(path)
    g =np.asarray(im.convert("L"), np.float32)
    rows, cols = g.mean(1) > 120, g.mean(0) > 120
    y0, y1 = rows.argmax(), len(rows) - rows[::-1].argmax()
    x0, x1 = cols.argmax(), len(cols) - cols[::-1].argmax()
    im = im.convert("RGB").crop((x0, y0, x1, y1))
    if im.width > im.height:
        im = im.rotate(90, expand=True)
    s = min(1.0, MAX_H / im.height)
    return im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--preview", type=Path, help="also write the identification preview (a JPEG) here")
    args = ap.parse_args()
    out = args.out
    for d in ("pencil", "colour", "masks"):
        (out / d).mkdir(parents=True, exist_ok=True)

    chapter = json.loads(zipfile.ZipFile(CHAPTER).read("manifest.json"))["panels"]
    zumi = zipfile.ZipFile(EXPORT)
    final = json.loads(zumi.read("manifest.json"))
    panels = {p["id"]: p for p in final["panels"]}
    heights = [Image.open(p).height for p in COLOUR]
    tops = np.cumsum([0] + heights[:-1])
    assert tops[-1] + heights[-1] == final["episode"]["layout"]["height"], "coloured pages do not stack to the strip"
    page_of = {}  # box index -> coloured page index
    for i, p in enumerate(chapter):
        y0, y1 = p["strip"]["y"], p["strip"]["y"] + p["strip"]["h"]
        j = int(np.searchsorted(tops, y0, side="right") - 1)
        assert y1 <= tops[j] + heights[j], f"box {i} crosses a page edge"
        page_of[i] = j

    mapping = match_pages()
    ep = Episode(DATASET, "dan-buck")
    pages, where = [], {}
    for k, pen_path in enumerate(PENCIL):
        n = k + 1
        pen = paper(pen_path)
        pen.save(out / "pencil" / f"{n:02d}.jpg", quality=85)
        W, H = pen.size
        cols = mapping[k]
        srcs = [Image.open(COLOUR[j]).convert("RGB") for j in cols]
        sw = sum(c.width for c in srcs) + 0  # source px, gap added after scaling
        sh = max(c.height for c in srcs)
        s = min((W - GAP * (len(srcs) - 1)) / sw, H / sh)
        total_w = round(sw * s) + GAP * (len(srcs) - 1)
        x = (W - total_w) // 2
        canvas = Image.new("RGB", (W, H), "white")
        place = {}  # coloured page -> (ox, oy, scale)
        for j, c in zip(cols, srcs):
            cw, ch = round(c.width * s), round(c.height * s)
            oy = (H - ch) // 2
            canvas.paste(c.resize((cw, ch), Image.LANCZOS), (x, oy))
            place[j] = (x, oy, s)
            x += cw + GAP
        canvas.save(out / "colour" / f"{n:02d}.jpg", quality=85)

        balloon, person, frame_px = np.zeros((H, W), bool), np.zeros((H, W), bool), np.zeros((H, W), np.uint8)
        frames, balloons, characters = [], [], []
        for i in sorted(b for b, j in page_of.items() if j in place):
            ox, oy, s = place[page_of[i]]
            by = chapter[i]["strip"]["y"] - tops[page_of[i]]
            box = ep.box(i)
            bw, bh = chapter[i]["size"]["w"], chapter[i]["size"]["h"]
            tx, ty = ox, oy + by * s  # box px -> page px: (tx + x*s, ty + y*s)
            dst = (round(ty), round(ty + bh * s), round(tx), round(tx + bw * s))

            def paste(mask: np.ndarray, into: np.ndarray) -> None:
                m = cv2.resize(mask.astype(np.uint8), (dst[3] - dst[2], dst[1] - dst[0]), interpolation=cv2.INTER_AREA)
                h, w = min(m.shape[0], H - dst[0]), min(m.shape[1], W - dst[2])
                into[dst[0]:dst[0] + h, dst[2]:dst[2] + w] |= m[:h, :w] > 0

            for f in box.letters() or []:
                paste(f.mask, balloon)
            for f in box.characters() or []:
                paste(f.mask, person)
            fmasks = box.frames().masks
            pid = f"p{i:03d}"
            who = cast_cards(zumi, pid)
            for layer in (box.scene().layers if who else []):
                k = who.get(layer.card)
                k = SAME.get(k, k)
                if layer.kind != "character" or k is None or k in GROUP:
                    continue
                m = layer.mask((bh, bw))
                if isinstance(layer.frame, int) and layer.frame < len(fmasks):
                    m &= fmasks[layer.frame]  # what shows through its window
                ys, xs = np.nonzero(m)
                if not len(xs) or min(xs.max() - xs.min(), ys.max() - ys.min()) * s < MIN_CHAR:
                    continue
                characters.append({"cast": k, "name": CAST[k][0],
                                   "box": [round(tx + xs.min() * s), round(ty + ys.min() * s),
                                           round(tx + (xs.max() + 1) * s), round(ty + (ys.max() + 1) * s)],
                                   "centre": [round(tx + xs.mean() * s), round(ty + ys.mean() * s)],
                                   "panel": pid, "card": layer.card})
            for fm in fmasks:
                m = np.zeros((H, W), bool)
                paste(fm, m)
                cs, _ = cv2.findContours(m.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                cs = [c for c in cs if cv2.contourArea(c) >= MIN_FRAME * W * H]  # slivers the downscale left
                if not cs:
                    continue
                cv2.drawContours(frame_px, cs, -1, 1, 4)
                x0, y0 = np.min([c.min(0)[0] for c in cs], 0)
                x1, y1 = np.max([c.max(0)[0] for c in cs], 0)
                frames.append([int(x0), int(y0), int(x1) + 1, int(y1) + 1])
            where[pid] = (n, tx, ty, s, bw, bh)
            geo = {b["id"]: b for b in (box.bubbles() or {"bubbles": []})["bubbles"]}
            for b in panels[pid]["bubbles"]:
                x0, y0, x1, y1 = geo[int(b["id"][1:])]["bbox"]
                balloons.append({"box": [round(tx + x0 * s), round(ty + y0 * s), round(tx + x1 * s), round(ty + y1 * s)],
                                 "text": b["text"], "speaker": SHORT.get(b.get("speakerId")), "kind": b["kind"],
                                 "panel": pid, "bubble": b["id"]})
        rgba = np.zeros((H, W, 4), np.uint8)
        rgba[person] = (*TEAL, ALPHA)
        rgba[balloon] = (*CORAL, ALPHA)
        rgba[frame_px > 0] = (*FRAME, 255)
        Image.fromarray(rgba, "RGBA").save(out / "masks" / f"{n:02d}.png", optimize=True)
        pages.append({"index": n, "pencil": f"pencil/{n:02d}.jpg", "colour": f"colour/{n:02d}.jpg",
                      "masks": f"masks/{n:02d}.png", "size": [W, H], "colourPages": [j + 1 for j in cols],
                      "frames": frames, "balloons": balloons, "characters": characters})
        print(f"pencil {n} <- colour {[j + 1 for j in cols]}: {len(frames)} frames, {len(balloons)} balloons, "
              f"{len(characters)} characters")

    def bubble(pid, bid):
        return next(b for b in panels[pid]["bubbles"] if b["id"] == bid)

    dn, tx, ty, s, bw, bh = where[PICKS["depth"]]
    vp, vb = PICKS["voice"]
    fp, fb = PICKS["sfx"]
    v, f = bubble(vp, vb), bubble(fp, fb)
    doc = {"title": "Dan & Buck", "pages": pages,
           "depth": {"panel": PICKS["depth"], "page": dn,
                     "box": [round(tx), round(ty), round(tx + bw * s), round(ty + bh * s)]},
           "voice": {"panel": vp, "bubble": vb, "speaker": SHORT.get(v.get("speakerId")), "text": v["text"],
                     "audio": v.get("audio")},
           "sfx": {"panel": fp, "bubble": fb, "text": f["text"], "audio": f.get("audio")},
           "music": final["episode"]["music"][0]["id"],
           "place": final["episode"]["places"]["meshes"][0]["setting"],
           "cover": "the cover will be on the book"}
    shown = {c["cast"] for p in pages for c in p["characters"]}
    doc["cast"] = [{"id": k, "name": name, "colour": colour} for k, (name, colour) in CAST.items() if k in shown]
    (out / "making-of.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
    if args.preview:
        preview(out, args.preview)


if __name__ == "__main__":
    main()
