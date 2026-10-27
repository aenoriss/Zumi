"""Compare the 2025+ masked inpainting models (pipeline/modal/inpaint2025.py) on one panel's character + lettering
holes, next to the Qwen edit plate if room_plate.py made one. Output pasted back only inside the holes.

    python experiments/inpaint2025.py <panel.png> <characters npz> <lettering npz> <out dir> "<empty scene prompt>" [--smoke]
Writes inpaint_<model>.png and compare_2025.png (original | holes | Klein | Z-Image | Qwen edit).
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

MODELS = {"klein": ("Klein", {}), "zimage": ("ZImage", {})}


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def run(cls, img, mask, prompt, W, H, **kw):
    r = modal.Cls.from_name("zumi-inpaint2025", cls)().inpaint.remote(
        png(img.resize((W, H), Image.LANCZOS)), png(Image.fromarray(mask.astype(np.uint8) * 255).resize((W, H))),
        prompt, W, H, **kw)
    print(cls, r["secs"], "s, load", r["load_s"], "s, peak", r["peak_gb"], "GB")
    return Image.open(io.BytesIO(r["image"])).convert("RGB")


def main():
    if "--smoke" in sys.argv:
        g = np.linspace(0, 255, 512, dtype=np.uint8)
        a = Image.fromarray(np.stack([np.tile(g, (512, 1))] * 3, 2))
        m = np.zeros((512, 512), bool)
        m[200:300, 200:300] = True
        for name, (cls, kw) in MODELS.items():
            print("SMOKE", name, run(cls, a, m, "a smooth grey gradient", 512, 512, steps=2, **kw).size)
        return
    src, chars, letters, out, prompt = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]), sys.argv[5]
    out.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    w, h = img.size
    mask = binary_dilation(np.logical_or.reduce([f.mask for f in load_masks(chars) + load_masks(letters)]), iterations=8)
    # ~1 MP at the panel's aspect, sides multiples of 32 (700x2000 -> 608x1728)
    W = round((1024 * 1024 * w / h) ** 0.5 / 32) * 32
    H = round(W * h / w / 32) * 32
    alpha = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(2))
    panes = [(img, "original"),
             (Image.composite(Image.new("RGB", img.size, (255, 0, 160)), img, Image.fromarray((mask * 110).astype(np.uint8))), "holes")]
    for name, (cls, kw) in MODELS.items():
        f = out / f"inpaint_{name}.png"
        if not f.exists():
            filled = run(cls, img, mask, prompt, W, H, **kw).resize(img.size, Image.LANCZOS)
            Image.composite(filled, img, alpha).save(f)
        panes.append((Image.open(f).convert("RGB"), {"klein": "FLUX.2 klein 4B", "zimage": "Z-Image-Turbo + ControlNet"}[name]))
    if (out / "plate.png").exists():
        panes.append((Image.open(out / "plate.png").convert("RGB"), "Qwen edit (earlier)"))
    sheet = Image.new("RGB", (len(panes) * (w + 16), h + 24), "white")
    for i, (p, label) in enumerate(panes):
        sheet.paste(p, (i * (w + 16), 24))
        ImageDraw.Draw(sheet).text((i * (w + 16) + 4, 6), label, fill=(0, 0, 0))
    sheet.save(out / "compare_2025.png")


if __name__ == "__main__":
    main()
