"""Iterate FLUX.2 [klein] 4B on one panel's holes (characters + lettering), one crop per hole at ~1 MP instead of the
whole panel scaled down:

  crop4      inpaint pipeline, distilled 4B, 4 steps, strength 1 (the first run, but per hole and at higher resolution)
  prefill    holes pre-filled with OpenCV Telea first, strength 0.9, 8 steps: the model starts from the right tones
  base50     FLUX.2-klein-base-4B (not distilled), 50 steps, true CFG 4
  edit       the editing pipeline ("remove the person / the text box"): sees the whole crop, pasted back inside the hole

    python experiments/klein_sweep.py <panel.png> <characters npz> <lettering npz> <out dir> "<scene prompt>"
Writes klein_<variant>.png and compare_klein.png.
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import modal
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import binary_dilation, label

from bubbles import load_masks

BASE = "black-forest-labs/FLUX.2-klein-base-4B"
EDIT = {"character": "Remove the person completely. Keep everything else exactly the same: the furniture, the floor, "
                     "the lighting and the drawing style.",
        "lettering": "Remove the black text box and its text completely. Keep everything else exactly the same."}
VARIANTS = ["crop4", "prefill", "base50", "edit"]


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def holes(chars, letters, shape, dil=8, margin=48):
    """One region per connected hole: (box, mask inside the box, kind)."""
    cm = np.logical_or.reduce([f.mask for f in chars]) if chars else np.zeros(shape, bool)
    lm = np.logical_or.reduce([f.mask for f in letters]) if letters else np.zeros(shape, bool)
    full = binary_dilation(cm | lm, iterations=dil)
    lab, n = label(full)
    h, w = shape
    out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        x0, y0 = max(0, xs.min() - margin), max(0, ys.min() - margin)
        x1, y1 = min(w, xs.max() + 1 + margin), min(h, ys.max() + 1 + margin)
        kind = "character" if (cm & (lab == i)).any() else "lettering"
        out.append(((x0, y0, x1, y1), full[y0:y1, x0:x1], kind))
    return out, full


def model_size(w, h, area=1024 * 1024, mult=16):
    s = (area / (w * h)) ** 0.5
    return max(mult, round(w * s / mult) * mult), max(mult, round(h * s / mult) * mult)


def main():
    src, cpath, lpath, out, prompt = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
    img = Image.open(src).convert("RGB")
    arr = np.asarray(img)
    regions, full = holes(load_masks(cpath), load_masks(lpath), arr.shape[:2])
    distilled = modal.Cls.from_name("zumi-inpaint2025", "Klein")()
    base = modal.Cls.from_name("zumi-inpaint2025", "Klein")(model=BASE)
    plates = {v: arr.copy() for v in VARIANTS}
    for (x0, y0, x1, y1), m, kind in regions:
        crop = Image.fromarray(arr[y0:y1, x0:x1])
        W, H = model_size(*crop.size)
        c, mk = crop.resize((W, H), Image.LANCZOS), Image.fromarray(m.astype(np.uint8) * 255).resize((W, H))
        pre = Image.fromarray(cv2.inpaint(np.asarray(c), np.asarray(mk), 9, cv2.INPAINT_TELEA))
        calls = {
            "crop4": lambda: distilled.inpaint.remote(png(c), png(mk), prompt, steps=4, strength=1.0),
            "prefill": lambda: distilled.inpaint.remote(png(pre), png(mk), prompt, steps=8, strength=0.9),
            "base50": lambda: base.inpaint.remote(png(c), png(mk), prompt, steps=50, strength=1.0, guidance=4.0),
            "edit": lambda: distilled.edit.remote(png(c), EDIT[kind], steps=4),
        }
        for v, call in calls.items():
            r = call()
            print(f"{kind} {crop.size}->{W}x{H} {v}: {r['secs']} s (load {r['load_s']} s, peak {r['peak_gb']} GB)")
            got = Image.open(io.BytesIO(r["image"])).convert("RGB").resize(crop.size, Image.LANCZOS)
            a = np.asarray(Image.fromarray(m.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(2)), np.float32)[..., None] / 255
            region = plates[v][y0:y1, x0:x1].astype(np.float32)
            plates[v][y0:y1, x0:x1] = (np.asarray(got, np.float32) * a + region * (1 - a)).astype(np.uint8)
    w, h = img.size
    labels = {"crop4": "per hole, 4 steps", "prefill": "Telea prefill, strength 0.9", "base50": "base 4B, 50 steps",
              "edit": "edit 'remove...'"}
    panes = [(arr, "original")]
    if (out / "inpaint_klein.png").exists():
        panes.append((np.asarray(Image.open(out / "inpaint_klein.png").convert("RGB")), "first run (whole panel)"))
    for v in VARIANTS:
        Image.fromarray(plates[v]).save(out / f"klein_{v}.png")
        panes.append((plates[v], labels[v]))
    sheet = Image.new("RGB", (len(panes) * (w + 16), h + 24), "white")
    for i, (p, lab) in enumerate(panes):
        sheet.paste(Image.fromarray(p), (i * (w + 16), 24))
        ImageDraw.Draw(sheet).text((i * (w + 16) + 4, 6), lab, fill=(0, 0, 0))
    sheet.save(out / "compare_klein.png")


if __name__ == "__main__":
    main()
