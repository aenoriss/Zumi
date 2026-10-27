"""Clean up point-cloud renders with Qwen-Image-Edit-2509 (Lightning, 8 steps), the original panel as reference.

    python experiments/warp_cleanup.py <original.png> <warp dir> [--smoke]
--smoke: 2 steps on synthetic images only (checks the deployed app before a real run).
Writes clean_<name>.png next to each view_<name>.png.
"""
import io
import sys
import time
from pathlib import Path

import modal
import numpy as np
from PIL import Image

PROMPT = ("Image 1 is a rough 3D render of the scene in image 2, seen from a slightly different camera angle; black areas "
          "are holes where nothing was visible and some edges are stretched. Redraw image 1 as a clean finished comic panel "
          "in exactly the style, colours and content of image 2. Keep image 1's camera angle, layout and the position of "
          "every character and object. Fill the black holes with plausible continuation of the background behind them. "
          "Do not add new characters, objects or text.")


PROMPT_NOREF = ("This is a rough 3D render of a comic panel seen from a slightly different camera angle; black areas are "
                "holes where nothing was visible and some edges are stretched or torn. Clean it up into a finished comic "
                "panel: fill the black holes with plausible continuation of the background behind them and repair the "
                "stretched areas. Keep the camera angle, the layout, the style and every character and object exactly "
                "where they are. Do not add new characters, objects or text.")


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def main():
    Edit = modal.Cls.from_name("zumi-qwen-angles", "Angles2509")
    if "--smoke" in sys.argv:
        g = np.linspace(0, 255, 512, dtype=np.uint8)
        a = Image.fromarray(np.stack([np.tile(g, (512, 1))] * 3, 2))
        t = time.perf_counter()
        r = Edit().edit.remote([png(a), png(a.transpose(Image.FLIP_LEFT_RIGHT))], "Make image 1 look like image 2.", steps=2)
        print("SMOKE OK", r["secs"], "s run, load", r["load_s"], "s, peak", r["peak_gb"], "GB, wall", round(time.perf_counter() - t), "s")
        return
    orig, d = Path(sys.argv[1]), Path(sys.argv[2])
    noref = "--noref" in sys.argv  # the render alone, no original panel as reference
    ref = png(Image.open(orig).convert("RGB"))
    for v in sorted(d.glob("view_*.png")):
        imgs, prompt = ([v.read_bytes()], PROMPT_NOREF) if noref else ([v.read_bytes(), ref], PROMPT)
        r = Edit().edit.remote(imgs, prompt, steps=8)
        out = d / v.name.replace("view_", "cleannoref_" if noref else "clean_")
        out.write_bytes(r["image"])
        print(v.stem, r["secs"], "s, load", r["load_s"], "s, peak", r["peak_gb"], "GB ->", out.name)


if __name__ == "__main__":
    main()
