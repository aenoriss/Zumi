"""How many drawn frames does a box hold? Recursive XY-cut over each box of each episode: a band at least BAND px
wide, at least WHITE of it page-white across the current region, splitting it into two parts of at least MIN_PART
px, is a gutter; recurse on both sides. Leaves with art (at least ART of their pixels not page-white and at least
MIN_FRAME px on each side) are frames; a white bubble crossing a gutter is tolerated by the WHITE share.

    python experiments/frame_count.py <out dir> <episode.zumi> [...]
Prints frames per box per episode, writes frames.json and frames_examples.png (multi-frame boxes, frames outlined).
Not detected: inset frames drawn over a larger frame, frames separated by black or coloured gutters.
"""
import io
import json
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

BAND, WHITE, MIN_PART, ART, MIN_FRAME, MID = 5, 0.9, 80, 0.3, 150, 0.25
mid = None


def cuts(white, y0, y1, x0, x1, out):
    sub = white[y0:y1, x0:x1]
    h, w = sub.shape
    for axis in (0, 1):  # 0: horizontal gutter (rows), 1: vertical gutter (columns)
        share = sub.mean(axis=1 - axis)
        run, best = 0, None
        for k, s in enumerate(share):
            run = run + 1 if s >= WHITE else 0
            if run >= BAND:
                a, b = k - run + 1, k + 1
                if a >= MIN_PART and (len(share) - b) >= MIN_PART:
                    best = (a, b)
                    # extend to the whole white run
                    while b < len(share) and share[b] >= WHITE:
                        b += 1
                    best = (a, b)
                    break
        if best:
            a, b = best
            if axis == 0:
                cuts(white, y0, y0 + a, x0, x1, out)
                cuts(white, y0 + b, y1, x0, x1, out)
            else:
                cuts(white, y0, y1, x0, x0 + a, out)
                cuts(white, y0, y1, x0 + b, x1, out)
            return
    if h >= MIN_FRAME and w >= MIN_FRAME and (1 - sub.mean()) >= ART and mid[y0:y1, x0:x1].mean() >= MID:
        out.append((int(x0), int(y0), int(x1), int(y1)))


def frames(img):
    global mid
    a = np.asarray(img.convert("RGB"))
    white = a.min(axis=2) >= 240
    # drawn art has mid-tones and colour; lettering (black caption boxes, white bubbles, speed-line bursts) is black
    # and white only, and the first count took caption boxes and bubble clusters in the page for frames
    mid = (a.max(axis=2) > 40) & (a.min(axis=2) < 215)
    out = []
    cuts(white, 0, white.shape[0], 0, white.shape[1], out)
    return out


def main():
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    report, examples = {}, []
    for zp in map(Path, sys.argv[2:]):
        z = zipfile.ZipFile(zp)
        panels = json.loads(z.read("manifest.json"))["panels"]
        counts = []
        for i, p in enumerate(panels):
            img = Image.open(io.BytesIO(z.read(p["layers"][0]["image"]))).convert("RGB")
            fr = frames(img)
            counts.append(len(fr))
            report[f"{zp.stem}-p{i:03d}"] = fr
            if len(fr) > 1 and len(examples) < 16:
                im = img.copy()
                d = ImageDraw.Draw(im)
                for b in fr:
                    d.rectangle(b, outline=(255, 0, 160), width=6)
                d.text((10, 10), f"{zp.stem} p{i}: {len(fr)} frames", fill=(255, 0, 160))
                examples.append(im)
        hist = {k: counts.count(k) for k in sorted(set(counts))}
        multi = [i for i, c in enumerate(counts) if c > 1]
        print(f"{zp.stem}: {len(counts)} boxes, frames per box {hist}; multi-frame boxes {len(multi)}: {multi}")
    (out / "frames.json").write_text(json.dumps(report))
    if examples:
        H = 600
        row = [e.resize((max(1, int(e.width * H / e.height)), H)) for e in examples]
        sheet = Image.new("RGB", (sum(r.width + 10 for r in row), H), "white")
        x = 0
        for r in row:
            sheet.paste(r, (x, 0))
            x += r.width + 10
        sheet.save(out / "frames_examples.png")


if __name__ == "__main__":
    main()
