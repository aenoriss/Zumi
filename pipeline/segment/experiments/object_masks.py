"""Objects a language model chose, masked by SAM 3.1: for each {"name", "point": [x, y]} the box is prompted with the
name (square tiles, as characters.py) and the mask that contains the point, best score first, is kept. The point is
the model's way of saying "this one": text prompts alone also returned floors and walls.

    python experiments/object_masks.py <image.png> <objects.json> <out.npz>
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import torch
from PIL import Image

from bubbles import CKPT, tiles
from characters import Sam3Processor, build_sam3_image_model, tile_masks


def main():
    img = Image.open(sys.argv[1]).convert("RGB")
    objs = json.loads(Path(sys.argv[2]).read_text())
    w, h = img.size
    proc = Sam3Processor(build_sam3_image_model(checkpoint_path=str(CKPT), load_from_HF=False), confidence_threshold=0.2)
    found = {o["name"]: [] for o in objs}
    with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
        for top in tiles(h, w):
            tile = img.crop((0, top, w, min(h, top + w)))
            base = proc.set_image(tile)
            for o in objs:
                x, y = o["point"]
                if not top <= y < top + tile.height:
                    continue
                for m, s in tile_masks(proc, base, o["name"], 0.2, tile):
                    if m[y - top, x]:
                        full = np.zeros((h, w), bool)
                        full[top:top + m.shape[0]] = m
                        found[o["name"]].append((s, full))
    masks, names = [], []
    for o in objs:
        cands = sorted(found[o["name"]], key=lambda t: -t[0])
        if cands:
            masks.append(cands[0][1])
            names.append(o["name"])
            print(f"{o['name']}: score {cands[0][0]:.2f}, {cands[0][1].mean() * 100:.1f}% of the box")
        else:
            print(f"{o['name']}: no mask contains the point")
    np.savez_compressed(sys.argv[3], masks=np.array(masks), names=np.array(names))


if __name__ == "__main__":
    main()
