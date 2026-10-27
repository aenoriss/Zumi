"""Second hidden layer behind chosen objects: one FLUX Erase call on the lettering-free base with the characters AND
the objects (object_masks.py) erased; exported behind the existing character layer (hidden_layer_export, two layers).

    python experiments/objects_layer.py <box id> <base.png> <characters npz> <lettering npz> <objects.npz> <plate dir>
"""
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

import depth as DP
from flux_erase import erase_panel, spent_today
from hidden_layer_export import export_layers
from hidden_layers import prepare
from masks import load_masks
from occlusion_mask import GROW, VIEWER, read_cloud2


def main():
    pid, base_p, cpath, lpath, opath, pdir = sys.argv[1:7]
    pdir = Path(pdir)
    z = zipfile.ZipFile(Path(__file__).resolve().parents[2] / ".data/out/chapters" / (pid.rsplit("-p", 1)[0] + ".zumi"))
    panels = json.loads(z.read("manifest.json"))["panels"]
    orig = Image.open(io.BytesIO(z.read(panels[int(pid.rsplit("-p", 1)[1])]["layers"][0]["image"]))).convert("RGB")
    union = lambda ms: np.logical_or.reduce([m.mask for m in ms]) if ms else np.zeros((orig.height, orig.width), bool)
    box = prepare(pid, orig, union(load_masks(cpath)), union(load_masks(lpath)), pdir, log=print)
    objs = np.load(opath)["masks"]
    objects = binary_dilation(np.logical_or.reduce(objs), iterations=8) & ~box.gutter
    base = np.asarray(Image.open(base_p).convert("RGB"))
    full2 = (box.full | objects) & ~box.gutter
    y0, y1, x0, x1 = box.crop
    page = base.copy()
    page[box.gutter] = 255
    f = pdir / "erased-objects.png"
    if f.exists():
        crop = np.asarray(Image.open(f).convert("RGB"))
    else:
        crop, _, line = erase_panel(page[y0:y1, x0:x1], full2[y0:y1, x0:x1])
        Image.fromarray(crop).save(f)
        print(line)
    plate2 = base.copy()
    plate2[y0:y1, x0:x1] = crop
    plate2[box.gutter] = base[box.gutter]
    Image.fromarray(plate2).save(pdir / "plate-objects.png")
    plate1 = np.asarray(Image.open(pdir / "plate-full.png").convert("RGB"))
    info, img, P, C, L, D = read_cloud2(pid, VIEWER)
    for line in export_layers(pid, info, P, C, L, D, box.chars, np.zeros_like(box.letters),
                              [(plate1, box.full), (plate2, full2)], DP.load(), VIEWER):
        print(" ", line)
    print(f"objects erased: {objects.mean() * 100:.1f}% of the box; BFL spend today {spent_today():.2f} USD")


if __name__ == "__main__":
    main()
