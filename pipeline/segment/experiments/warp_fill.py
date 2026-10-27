"""Fill the holes of point-cloud renders two ways, then paste the result back ONLY inside the holes:
  A  QwenImageEditInpaintPipeline: pre-filled render + mask, no reference
  B  multi-image pipeline, original as style reference, latent blending outside the mask at every step
Both with the Lightning scheduler fix. Writes fillA_<view>.png and fillB_<view>.png (composited) per view.

    python experiments/warp_fill.py <original.png> <warp dir> [--smoke]
"""
import io
import sys
import time
from pathlib import Path

import modal
import numpy as np
from PIL import Image, ImageFilter

CAPTION = ("a fantasy tavern interior: a grey wolf-like man in a brown suit holding a beer mug, a bull warrior in "
           "golden armour, a cheetah and a lizard-like man at a wooden table in an orange booth, plants, windows")
PROMPT_A = f"Perform inpainting on this image. The original caption is: {CAPTION}"
PROMPT_B = ("Picture 1 is a 3D render of the scene in Picture 2 from a slightly different camera angle; some areas are "
            "rough or blurry where nothing was visible. Repaint only those areas as background that continues what is "
            "around them, in the style and colours of Picture 2. Picture 2 is a style reference only: do not copy any "
            "character or object from it into the repaired areas. Do not add characters, objects or text.")


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def composite(render, filled, mask, feather=3):
    """Original rendered pixels outside the mask, the model's pixels inside, soft seam."""
    filled = filled.convert("RGB").resize(render.size, Image.LANCZOS)
    a = mask.convert("L").filter(ImageFilter.GaussianBlur(feather))
    return Image.composite(filled, render.convert("RGB"), a)


def main():
    Cls = modal.Cls.from_name("zumi-qwen-angles", "Angles2509")
    if "--smoke" in sys.argv:
        g = np.linspace(0, 255, 512, dtype=np.uint8)
        a = Image.fromarray(np.stack([np.tile(g, (512, 1))] * 3, 2))
        m = np.zeros((512, 512), np.uint8)
        m[200:300, 200:300] = 255
        mk = Image.fromarray(m)
        t = time.perf_counter()
        ra = Cls().inpaint.remote(png(a), png(mk), "Perform inpainting on this image.", steps=2)
        rb = Cls().edit_blend.remote([png(a), png(a)], png(mk), "Repaint the square.", steps=2)
        print("SMOKE OK A", ra["secs"], "s; B", rb["secs"], "s, tokens", rb["latent_tokens"], "masked", rb["masked_share"],
              "; load", ra["load_s"], "s; wall", round(time.perf_counter() - t), "s")
        return
    orig, d = Path(sys.argv[1]), Path(sys.argv[2])
    ref = png(Image.open(orig).convert("RGB"))
    for v in sorted(d.glob("view_*.png")):
        name = v.stem[len("view_"):]
        render = Image.open(v).convert("RGB")
        pre = Image.open(d / f"prefill_{name}.png")
        mask = Image.open(d / f"mask_{name}.png")
        ra = Cls().inpaint.remote(png(pre), png(mask), PROMPT_A, strength=1.0, steps=8)
        composite(render, Image.open(io.BytesIO(ra["image"])), mask).save(d / f"fillA_{name}.png")
        rb = Cls().edit_blend.remote([png(pre), ref], png(mask), PROMPT_B, steps=8)
        composite(render, Image.open(io.BytesIO(rb["image"])), mask).save(d / f"fillB_{name}.png")
        print(name, "A", ra["secs"], "s; B", rb["secs"], "s, masked tokens", rb["masked_share"])


if __name__ == "__main__":
    main()
