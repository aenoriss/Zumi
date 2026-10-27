"""Hidden background for one panel: what is behind the characters and the lettering (bubbles, caption boxes), from a
Qwen-Image-Edit-2509 remove instruction on Modal, pasted back only inside those masks (the rest stays the original art).

    python experiments/room_plate.py <panel.png> <characters npz> <lettering npz> <out dir> "<what to remove / keep>"
Writes plate.png, mask.png and compare.png (original | mask | plate).
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import modal
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import binary_dilation

from bubbles import load_masks


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def match(filled, img, mask):
    """The edit model redraws the whole panel: slightly shifted and scaled, colours warmer. Align it to the original
    (ECC affine on the pixels it should have kept), then correct colour with a smooth per-channel gain map measured
    outside the holes and carried in under them."""
    import cv2
    from depth import fill_under
    a, b = np.asarray(img, np.float32), np.asarray(filled, np.float32)
    ga, gb = (cv2.cvtColor(x.astype(np.uint8), cv2.COLOR_RGB2GRAY) for x in (a, b))
    keep = (~binary_dilation(mask, iterations=20)).astype(np.uint8)
    warp = np.eye(2, 3, dtype=np.float32)
    _, warp = cv2.findTransformECC(ga, gb, warp, cv2.MOTION_AFFINE,
                                   (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-6), keep, 5)
    h, w = mask.shape
    b = cv2.warpAffine(b, warp, (w, h), flags=cv2.INTER_LINEAR | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REFLECT)
    k = keep.astype(bool)
    out = np.empty_like(b)
    for c in range(3):
        sa = cv2.GaussianBlur(np.where(k, a[..., c], 0), (0, 0), 25)
        sb = cv2.GaussianBlur(np.where(k, b[..., c], 0), (0, 0), 25)
        wk = cv2.GaussianBlur(k.astype(np.float32), (0, 0), 25)
        gain = np.where(wk > 0.2, (sa + 1) / (sb + 1), 1.0).astype(np.float32)
        gain = fill_under(gain, wk <= 0.2)
        out[..., c] = b[..., c] * np.clip(gain, 0.5, 2.0)
    return Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)), np.round(warp, 3).tolist()


def main():
    src, chars, letters, out, prompt = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
    out.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    found = load_masks(chars) + load_masks(letters)
    mask = binary_dilation(np.logical_or.reduce([f.mask for f in found]), iterations=6)  # outlines and glow included
    Image.fromarray(mask.astype(np.uint8) * 255).save(out / "mask.png")
    if (out / "edit_raw.png").exists():  # reuse the paid call
        filled = Image.open(out / "edit_raw.png").convert("RGB")
    else:
        r = modal.Cls.from_name("zumi-qwen-angles", "Angles2509")().edit.remote([png(img)], prompt, steps=8)
        print("edit", r["secs"], "s, peak", r["peak_gb"], "GB")
        filled = Image.open(io.BytesIO(r["image"])).convert("RGB").resize(img.size, Image.LANCZOS)
        filled.save(out / "edit_raw.png")
    filled, shift = match(filled, img, mask)
    print("aligned: affine", shift)
    filled.save(out / "edit_matched.png")
    alpha = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(3))
    plate = Image.composite(filled, img, alpha)
    plate.save(out / "plate.png")
    w, h = img.size
    sheet = Image.new("RGB", (w * 3 + 32, h + 24), "white")
    over = Image.composite(Image.new("RGB", img.size, (255, 0, 160)), img, Image.fromarray((mask * 110).astype(np.uint8)))
    for i, (im, label) in enumerate(((img, "original"), (over, "holes to fill"), (plate, "filled (inside holes only)"))):
        sheet.paste(im, (i * (w + 16), 24))
        ImageDraw.Draw(sheet).text((i * (w + 16) + 4, 6), label, fill=(0, 0, 0))
    sheet.save(out / "compare.png")


if __name__ == "__main__":
    main()
