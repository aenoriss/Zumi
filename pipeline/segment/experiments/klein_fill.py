"""Fill a panel's holes (characters + lettering) with FLUX.2 [klein] 4B: the whole panel as context, upscaled to
~2.3 MP so the holes get pixels, then each hole's tone matched to its surroundings, pasted back only inside the holes.

    python experiments/klein_fill.py <panel.png> <characters npz> <lettering npz> <out png> "<scene prompt>"
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import modal
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

from bubbles import load_masks
from depth import fill_under


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def match_tone(filled, orig, mask, ring=24, sigma=20):
    """Per-channel gain measured in a ring just outside the holes, smoothed, carried in under them."""
    a, b = orig.astype(np.float32), filled.astype(np.float32)
    known = binary_dilation(mask, iterations=ring) & ~mask
    out = b.copy()
    for c in range(3):
        sa = cv2.GaussianBlur(np.where(known, a[..., c], 0), (0, 0), sigma)
        sb = cv2.GaussianBlur(np.where(known, b[..., c], 0), (0, 0), sigma)
        wk = cv2.GaussianBlur(known.astype(np.float32), (0, 0), sigma)
        ok = wk > 0.05
        gain = np.where(ok, (sa + 1) / (sb + 1), 1.0).astype(np.float32)
        gain = fill_under(gain, ~ok)
        out[..., c] = b[..., c] * np.clip(gain, 0.7, 1.4)
    return np.clip(out, 0, 255).astype(np.uint8)


def main():
    src, cpath, lpath, dst, prompt = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
    img = Image.open(src).convert("RGB")
    arr = np.asarray(img)
    mask = binary_dilation(np.logical_or.reduce([f.mask for f in load_masks(cpath) + load_masks(lpath)]), iterations=8)
    w, h = img.size
    s = (2.3e6 / (w * h)) ** 0.5
    W, H = round(w * s / 16) * 16, round(h * s / 16) * 16
    r = modal.Cls.from_name("zumi-inpaint2025", "Klein")().inpaint.remote(
        png(img.resize((W, H), Image.LANCZOS)), png(Image.fromarray(mask.astype(np.uint8) * 255).resize((W, H))),
        prompt, steps=4, strength=1.0)
    print(f"klein {W}x{H}: {r['secs']} s (load {r['load_s']} s, peak {r['peak_gb']} GB)")
    filled = np.asarray(Image.open(io.BytesIO(r["image"])).convert("RGB").resize((w, h), Image.LANCZOS))
    filled = match_tone(filled, arr, mask)
    a = cv2.GaussianBlur(mask.astype(np.float32), (0, 0), 1.5)[..., None]
    out = (filled * a + arr * (1 - a)).astype(np.uint8)
    Image.fromarray(out).save(dst)
    side = Image.new("RGB", (w * 2 + 16, h), "white")
    side.paste(img, (0, 0)); side.paste(Image.fromarray(out), (w + 16, 0))
    side.save(dst.with_name(dst.stem + "_side.png"))


if __name__ == "__main__":
    main()
