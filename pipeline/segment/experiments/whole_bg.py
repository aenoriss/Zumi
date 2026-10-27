"""Whole-background test: the erase model's complete output (characters, objects, lettering erased) is the background,
one surface with one depth estimate; the original's points are used only where they do not overlap it (the erased
characters and objects), at their original depth, cut out by their masks. No patches: the background is never
stitched from pieces (user, 2026-10-25).

    python experiments/whole_bg.py <box id> <characters npz> <lettering npz> <objects.npz> <out dir>
"""
import io
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

import depth as DP
import parallax as PX
from flux_erase import erase_packed, spent_today
from hidden_layer_export import silhouette_grid
from hidden_layers import prepare
from masks import load_masks
from occlusion_mask import VIEWER

lab = lambda a: cv2.cvtColor(np.clip(a, 0, 255).astype(np.uint8), cv2.COLOR_RGB2LAB).astype(np.float32)


def colour_match(raw, ref, where):
    """One global colour transform (3x3 + offset, least squares in RGB) from the raw output to the original, fitted on
    the pixels where both show the same scene; returns the matched image and the median / p90 CIELAB difference there."""
    X = np.c_[raw[where].reshape(-1, 3).astype(np.float64), np.ones(where.sum())]
    sub = np.arange(len(X))[:: max(1, len(X) // 200000)]
    A, *_ = np.linalg.lstsq(X[sub], ref[where].reshape(-1, 3).astype(np.float64)[sub], rcond=None)
    out = np.clip(np.c_[raw.reshape(-1, 3), np.ones(raw.shape[0] * raw.shape[1])] @ A, 0, 255).reshape(raw.shape)
    de = lambda a: np.linalg.norm(lab(a)[where] - lab(ref)[where], axis=-1)
    return out.astype(np.uint8), (np.median(de(raw)), np.percentile(de(raw), 90)), (np.median(de(out)), np.percentile(de(out), 90))


def main():
    pid, cpath, lpath, opath, out = sys.argv[1:6]
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    z = zipfile.ZipFile(Path(__file__).resolve().parents[2] / ".data/out/chapters" / (pid.rsplit("-p", 1)[0] + ".zumi"))
    panels = json.loads(z.read("manifest.json"))["panels"]
    img = Image.open(io.BytesIO(z.read(panels[int(pid.rsplit("-p", 1)[1])]["layers"][0]["image"]))).convert("RGB")
    o = np.asarray(img)
    union = lambda ms: np.logical_or.reduce([m.mask for m in ms]) if ms else np.zeros(o.shape[:2], bool)
    objs = np.logical_or.reduce(np.load(opath)["masks"])
    box = prepare(pid, img, union(load_masks(cpath)), union(load_masks(lpath)), out, log=print, objects=objs)
    y0, y1, x0, x1 = box.crop
    # 1. one call, both copies (full: characters + lettering erased; all: + objects); keep the raw outputs
    if not (out / "raw-all.png").exists():
        plates, line = erase_packed([(box.page, m) for m in box.masks], 48, 2.0)
        print(line)
        for k_, r in zip(box.kinds, erase_packed.last_raw):
            Image.fromarray(r).save(out / f"raw-{k_}.png")
    raw = o.copy()
    raw[y0:y1, x0:x1] = np.asarray(Image.open(out / "raw-all.png"))
    raw[box.gutter] = o[box.gutter]
    # 2. global colour match on everything both images show (outside every mask, not the gutter)
    same = ~binary_dilation(box.every, iterations=6) & ~box.gutter
    bg, before, after = colour_match(raw, o, same)
    print(f"background vs original outside the masks, CIELAB difference: raw median {before[0]:.1f} p90 {before[1]:.1f}; "
          f"after the global colour match median {after[0]:.1f} p90 {after[1]:.1f}")
    Image.fromarray(bg).save(out / "background.png")
    # 3. depths: the background as a whole; the original (lettering replaced by the background) for the foreground
    base = o.copy()
    base[box.lettering] = bg[box.lettering]
    mono, metric = DP.load(), DP.load(DP.METRIC_ID)
    Do, _, _ = DP.precise_depth(mono, metric, Image.fromarray(base), ignore=box.gutter)
    Db, _, _ = DP.precise_depth(mono, metric, Image.fromarray(bg), ignore=box.gutter)
    s, t = DP._robust_fit(Db[same][::5].astype(np.float64), Do[same][::5].astype(np.float64))
    Db = (s * Db + t).astype(np.float32)
    err = np.median(np.abs(Db[same] - Do[same]) / Do[same])
    print(f"background depth fitted to the original outside the masks: median difference {err * 100:.1f}%")
    fg = box.chars | objs  # the original's points that the background does not have
    Db = np.where(binary_dilation(fg, iterations=4), np.maximum(Db, Do * 1.02), Db)  # behind what stands on it
    # 4. viewer files: background = the scene surface (one surface, cut at its own jumps); foreground = the figure
    # surface (alpha at the masks, original texture and depth)
    k = PX.STRIDE
    h, w = Do.shape
    gw, gh = (w + k - 1) // k, (h + k - 1) // k
    G0 = np.where(box.gutter, 0, Db)[::k, ::k][:gh, :gw].astype(np.float32)
    M = VIEWER / "mesh"
    for old in list(M.glob(f"{pid}.*")) + list((VIEWER / "cloud3").glob(f"{pid}.*")):
        old.unlink()
    G0.tofile(M / f"{pid}.f32")
    (M / f"{pid}.json").write_text(json.dumps({"w": w, "h": h, "gw": gw, "gh": gh, "stride": k, "fov": PX.FOV,
                                              "jump": PX.JUMP}))
    Image.fromarray(base).save(M / f"{pid}.png")
    G, seg, Dc, Gfig = silhouette_grid(Do, fg, np.zeros_like(fg), np.where(box.gutter, 0, Do)[::k, ::k][:gh, :gw], k)
    G0.tofile(M / f"{pid}.fgclean.f32")  # the scene surface is the background everywhere
    Image.fromarray(bg).save(M / f"{pid}.fgclean.png")
    seg.tofile(M / f"{pid}.seg.u8")
    Gfig.tofile(M / f"{pid}.fig.f32")
    Image.fromarray(np.dstack([base, (fg * 255).astype(np.uint8)]), "RGBA").save(M / f"{pid}.fig.png")
    (M / f"{pid}.layers.json").write_text(json.dumps({"layers": 0, "jump": [], "scene_seg_cut": False}))
    print(f"foreground (original points): {fg.mean() * 100:.1f}% of the box; BFL spend today {spent_today():.2f} USD")


if __name__ == "__main__":
    main()
