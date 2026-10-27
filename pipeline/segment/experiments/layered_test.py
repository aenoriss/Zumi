"""Quick test: fill what the point cloud cannot show with a hidden background layer (no new views generated).

  1. character masks (characters.py) -> background plate: the panel inpainted where characters are (Qwen inpaint
     pipeline on Modal, holes pre-filled grey so the model does not keep a blur), original pixels pasted back outside
  2. plate depth: precise depth of the plate, aligned (robust scale/shift) to the panel's depth outside the characters,
     pushed behind the characters where it would come in front
  3. two-layer point cloud: every panel pixel at its depth + plate pixels under the characters at plate depth
  4. renders from 12 deg left / 12 deg right / 8 deg up, single layer vs two layers; cloud3/<id>.bin for the viewer

    python experiments/layered_test.py <panel.png> <out dir> <panel id>
"""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import torch
from PIL import Image, ImageDraw, ImageFilter
from scipy.ndimage import binary_dilation

from warp_views import FOV, VIEWS, model_size

VIEWER = Path(r"D:\Projects\Zumi\pipeline\.data\out\parallax_viewer")
PROMPT = ("Perform inpainting on this image. The original caption is: an empty fantasy tavern interior with an orange "
          "leather booth, a wooden table, wooden pillars, plants and windows, no people")
REMOVE = ("Remove all the people and creatures from this image. Keep the empty tavern exactly as it is: the orange "
          "booth, the wooden table, the pillars, the plants and the windows. Do not add anything.")
PLATES = ["remove8", "full30"]


def png(im):
    b = io.BytesIO()
    im.save(b, format="PNG")
    return b.getvalue()


def project(P, C, h, w, yaw, pitch, pivot):
    f = max(w, h) / (2 * np.tan(np.radians(FOV) / 2))
    cy, sy, cp, sp = np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    R = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Q = (P - pivot) @ R.T + pivot
    zc = -Q[:, 2]
    uu = np.round(f * Q[:, 0] / np.maximum(zc, 1e-6) + w / 2).astype(int)
    vv = np.round(-f * Q[:, 1] / np.maximum(zc, 1e-6) + h / 2).astype(int)
    out = np.zeros((h, w, 3), np.uint8)
    hit = np.zeros((h, w), bool)
    order = np.argsort(-zc)
    for dy in (0, 1):
        for dx in (0, 1):
            x, y = uu[order] + dx, vv[order] + dy
            m = (zc[order] > 1e-6) & (x >= 0) & (x < w) & (y >= 0) & (y < h)
            out[y[m], x[m]] = C[order][m]
            hit[y[m], x[m]] = True
    return out, hit


def backproject(D):
    h, w = D.shape
    f = max(w, h) / (2 * np.tan(np.radians(FOV) / 2))
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    return np.stack([(u - w / 2) * D / f, -(v - h / 2) * D / f, -D], -1).reshape(-1, 3)


def main():
    import modal
    import depth as DP
    from bubbles import CKPT
    from characters import segment as char_segment
    from sam3 import build_sam3_image_model
    from sam3.model.sam3_image_processor import Sam3Processor
    src, out, pid = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
    out.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    W, H = model_size(*img.size)
    big = img.resize((W, H), Image.LANCZOS)
    # 1. characters and the background plate
    if (out / "char_mask.png").exists():
        mask = np.asarray(Image.open(out / "char_mask.png")) > 127
    else:
        proc = Sam3Processor(build_sam3_image_model(checkpoint_path=str(CKPT), load_from_HF=False), confidence_threshold=0.3)
        with torch.inference_mode(), torch.autocast("cuda", dtype=torch.bfloat16):
            chars = [c.mask for c in char_segment(proc, big) if c.kind == "character"]
        del proc
        torch.cuda.empty_cache()
        char = np.logical_or.reduce(chars) if chars else np.zeros((H, W), bool)
        mask = binary_dilation(char, iterations=8)
        Image.fromarray(mask.astype(np.uint8) * 255).save(out / "char_mask.png")
    Cls = modal.Cls.from_name("zumi-qwen-angles", "Angles2509")
    alpha = Image.fromarray(mask.astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(3))
    plates = {}
    for name in PLATES:
        f = out / f"plate_{name}.png"
        if not f.exists():
            if name == "remove8":  # an edit instruction on the panel: object removal is what the edit model is trained on
                r = Cls().edit.remote([png(big)], REMOVE, steps=8)
            else:  # inpainting the grey-filled holes: invents new characters (first run)
                pre = np.asarray(big).copy()
                pre[mask] = 128
                kw = {"lightning": True, "steps": 8} if name == "lightning8" else {"lightning": False, "steps": 30, "cfg": 4.0}
                r = Cls().inpaint.remote(png(Image.fromarray(pre)), png(Image.fromarray(mask.astype(np.uint8) * 255)),
                                         PROMPT, strength=1.0, **kw)
            filled = Image.open(io.BytesIO(r["image"])).convert("RGB").resize((W, H), Image.LANCZOS)
            Image.composite(filled, big, alpha).save(f)
            print("plate", name, r["secs"], "s")
        plates[name] = Image.open(f).convert("RGB")
    # 2. depth of the hidden layer: the panel's background depth continued under the characters (the depth model on
    # the plate read the invented characters as characters), kept behind them
    mono, metric = DP.load(), DP.load(DP.METRIC_ID)
    D, _, _ = DP.precise_depth(mono, metric, big)
    Dp = np.maximum(DP.fill_under(D, mask), D * 1.05).astype(np.float32)
    report = {}
    for name, plate in plates.items():
        # 3. clouds and 4. renders
        a, b = np.asarray(big).reshape(-1, 3), np.asarray(plate).reshape(-1, 3)
        P1 = backproject(D)
        Pb = backproject(Dp)[mask.ravel()]
        Pall, Call = np.concatenate([P1, Pb]), np.concatenate([a, b[mask.ravel()]])
        pivot = np.median(P1, 0)
        rows, holes = [], {}
        for v, (yaw, pitch) in VIEWS.items():
            r1, h1 = project(P1, a, H, W, yaw, pitch, pivot)
            r2, h2 = project(Pall, Call, H, W, yaw, pitch, pivot)
            holes[v] = (round(float((~h1).mean() * 100), 1), round(float((~h2).mean() * 100), 1))
            row = Image.new("RGB", (W * 2 + 16, H + 24), "white")
            d = ImageDraw.Draw(row)
            row.paste(Image.fromarray(r1), (0, 24)); row.paste(Image.fromarray(r2), (W + 16, 24))
            d.text((4, 6), f"{v}: one layer (holes {holes[v][0]}%)", fill=(0, 0, 0))
            d.text((W + 20, 6), f"{v}: + background layer from inpainting, {name} (holes {holes[v][1]}%)", fill=(0, 0, 0))
            rows.append(row)
        sheet = Image.new("RGB", (rows[0].width, sum(r.height + 8 for r in rows)), "white")
        y = 0
        for r in rows:
            sheet.paste(r, (0, y)); y += r.height + 8
        sheet.save(out / f"renders_{name}.png")
        report[name] = holes
        # viewer cloud: same layout as cloud/ (positions, colours, labels 3 = scene)
        cdir = VIEWER / "cloud3"
        cdir.mkdir(parents=True, exist_ok=True)
        if name == "remove8":
            lb = np.full(len(Pall), 3, np.uint8)
            with open(cdir / f"{pid}.bin", "wb") as fh:
                fh.write(Pall.astype(np.float32).tobytes()); fh.write(Call.astype(np.uint8).tobytes()); fh.write(lb.tobytes())
            (cdir / f"{pid}.json").write_text(json.dumps({"count": int(len(lb)), "planes": 0, "objects": 0, "plane_share": [],
                                                          "leftover_share": 0, "stride": 1}))
    print("holes % (one layer, two layers):", json.dumps(report))


if __name__ == "__main__":
    main()
