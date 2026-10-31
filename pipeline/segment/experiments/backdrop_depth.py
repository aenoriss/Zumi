"""Is there a usable depth range in a frame's background? For each frame of the given boxes: the original, DA3MONO
on the frame normalised over the whole frame (what orders the cards), and the background's depth: for a frame that
passes cards.back_range_ok the relief map the backdrop gets (DA3MONO on the erased backdrop, white = near), for one
that fails the frame's depth on the background alone (the frame minus the cards, grown a few px) normalised over its
own 2-98th percentiles, cards red. Prints the background's share of the frame and its spread as a share of the
frame's. Runs the layers step once per box (episode.layers_step: the saved masks, frames and plate, the depth model;
no objects picked, no erase, no paid call) and records what cards.order and cards.backdrop_relief see. Boxes without
current frames are skipped. Writes one sheet per box and overview.png (every frame, one tile each).

    uv run python experiments/backdrop_depth.py <episode.zumi> <out dir> <sheet dir> --panels 2,8,13,24 | all
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import cards as CD  # noqa: E402
import depth as DP  # noqa: E402
import episode  # noqa: E402
from boxstore import Episode  # noqa: E402
from chapter import Chapter  # noqa: E402

GROW = 4     # px the cards are grown before the background is taken: their feathered outlines are not background
TILE_H = 170  # px, height of a frame's tile in the overview
RED = (128, 40, 40)


def grey(v: np.ndarray, valid: np.ndarray) -> np.ndarray:
    lo, hi = np.percentile(v[valid], [2, 98])
    g = np.clip((hi - v) / max(hi - lo, 1e-6), 0, 1)  # near = white (depth grows away from the camera)
    out = np.dstack([g * 255] * 3).astype(np.uint8)
    out[~valid] = RED
    return out


def label(im: Image.Image, text: str, ok: bool) -> Image.Image:
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, im.width, 14], fill=(0, 90, 0) if ok else (90, 0, 0))
    d.text((4, 1), text, fill=(255, 255, 255))
    return im


def main():
    from scipy.ndimage import binary_dilation
    ch, out, sheets = Chapter(Path(sys.argv[1])), Path(sys.argv[2]), Path(sys.argv[3])
    ep = Episode(out, ch.stem)
    arg = sys.argv[sys.argv.index("--panels") + 1]
    picks = range(len(ch)) if arg == "all" else [int(v) for v in arg.split(",")]
    mono = DP.load()
    transcripts = ep.transcripts()
    seen = []
    order, relief = CD.order, CD.backdrop_relief

    def spy_order(M, masks, area, behind=()):
        cov = np.logical_or.reduce(masks) if masks else np.zeros_like(area)
        seen.append({"M": M.copy(), "area": area.copy(), "cov": cov, "relief": None})
        return order(M, masks, area, behind)

    def spy_relief(area, Mb, eb):
        im = relief(area, Mb, eb)
        seen[-1]["relief"], seen[-1]["eb"] = (im * 255).astype(np.uint8), eb
        return im

    CD.order, CD.backdrop_relief = spy_order, spy_relief
    sheets.mkdir(parents=True, exist_ok=True)
    tiles = []
    for p in picks:
        seen.clear()
        box = ep.box(p)
        letters, chars, fr = box.letters(), box.characters(), box.frames()
        if letters is None or chars is None or not (fr and fr.current):
            print(f"p{p}: no saved masks or no current frames, skipped")
            continue
        episode.layers_step(ep, {p: ch.image(p)}, {p: letters}, {p: chars}, transcripts,
                            lambda rgb: DP.frame_infer(mono, rgb), objects=box.plate() is not None)
        img = np.asarray(ch.image(p))
        rows = []
        for k, s in enumerate(seen):
            M, area, cov = s["M"], s["area"], s["cov"]
            ys, xs = np.nonzero(area)
            y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
            sl = np.s_[y0:y1, x0:x1]
            a, bg = area[sl], (area & ~binary_dilation(cov, iterations=GROW))[sl]
            m = M[sl]
            fl, fh = np.percentile(m[a], [2, 98])
            share = bg.sum() / max(a.sum(), 1)
            spread = (np.subtract(*np.percentile(m[bg], [98, 2])) / max(fh - fl, 1e-6)) if bg.sum() >= 50 else 0.0
            ok = s["relief"] is not None
            orig = img[sl].copy()
            orig[~a] = RED
            if ok:  # the relief the backdrop gets, cropped from its box (frame + margin) to the frame
                ex0, ey0 = s["eb"][0], s["eb"][1]
                r = s["relief"][y0 - ey0:y1 - ey0, x0 - ex0:x1 - ex0]
                back = np.dstack([r] * 3).astype(np.uint8)
                back[~a] = RED
            else:
                back = grey(m, bg) if bg.sum() >= 50 else np.full(orig.shape, RED, np.uint8)
            text = f"p{p:03d} f{k}  bg {share:.0%} of frame, spread {spread:.0%}  -> {'relief' if ok else 'flat'}"
            print(text)
            row = Image.fromarray(np.concatenate([orig, grey(m, a), back], 1))
            rows.append(label(row.copy(), text, ok))
            t = Image.fromarray(np.concatenate([orig, back], 1))
            t = t.resize((max(1, round(t.width * TILE_H / t.height)), TILE_H))
            tiles.append(label(t, text, ok))
        if rows:
            W = max(r.width for r in rows)
            sheet = Image.new("RGB", (W, sum(r.height + 6 for r in rows)), (20, 20, 20))
            y = 0
            for r in rows:
                sheet.paste(r, (0, y))
                y += r.height + 6
            sheet.save(sheets / f"{ch.pid(p)}-backdrop-depth.png")
    if len(tiles) > 1:  # every frame, packed left to right in rows
        W, gap, lines, line, x = 2400, 6, [], [], 0
        for t in tiles:
            if line and x + t.width > W:
                lines.append(line)
                line, x = [], 0
            line.append(t)
            x += t.width + gap
        lines.append(line)
        ov = Image.new("RGB", (W, len(lines) * (TILE_H + gap)), (20, 20, 20))
        for j, ln in enumerate(lines):
            x = 0
            for t in ln:
                ov.paste(t, (x, j * (TILE_H + gap)))
                x += t.width + gap
        ov.save(sheets / "overview.png")


if __name__ == "__main__":
    main()
