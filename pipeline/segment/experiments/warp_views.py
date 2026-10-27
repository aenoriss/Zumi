"""Render the panel's 3D point cloud (precise depth) from new camera angles: the camera is exact by construction; the
renders have holes behind outlines and stretched edges, for an image model to clean up with the original as reference.

    uv run python experiments/warp_views.py <panel.png> <out dir>
Writes view_<name>.png (render, holes black) and mask_<name>.png (white = no source pixel) per angle.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image

FOV = 55.0  # assumed, as in the rest of the depth work
VIEWS = {"left12": (-12.0, 0.0), "right12": (12.0, 0.0), "up8": (0.0, 8.0)}  # yaw, pitch in degrees


def render(img, D, yaw, pitch):
    a = np.asarray(img.convert("RGB"))
    h, w = D.shape
    f = max(w, h) / (2 * np.tan(np.radians(FOV) / 2))
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    X, Y, Z = (u - w / 2) * D / f, -(v - h / 2) * D / f, -D
    P = np.stack([X, Y, Z], -1).reshape(-1, 3)
    pivot = np.median(P, 0)  # orbit around the middle of the scene
    cy, sy, cp, sp = np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    Q = (P - pivot) @ (Rx @ Ry).T + pivot
    zc = -Q[:, 2]
    ok = zc > 1e-6
    uu = np.round(f * Q[:, 0] / np.maximum(zc, 1e-6) + w / 2).astype(int)
    vv = np.round(-f * Q[:, 1] / np.maximum(zc, 1e-6) + h / 2).astype(int)
    col = a.reshape(-1, 3)
    out = np.zeros_like(a)
    hit = np.zeros((h, w), bool)
    order = np.argsort(-zc)  # far first, near points paint over them
    for dy in (0, 1):  # 2x2 splat closes the cracks a 1:1 projection leaves
        for dx in (0, 1):
            x, y = uu[order] + dx, vv[order] + dy
            m = ok[order] & (x >= 0) & (x < w) & (y >= 0) & (y < h)
            out[y[m], x[m]] = col[order][m]
            hit[y[m], x[m]] = True
    return Image.fromarray(out), Image.fromarray((~hit).astype(np.uint8) * 255)


def model_size(w, h, area=1024 * 1024, mult=32):
    """The Qwen edit pipelines size their output to ~1 MP at the input's aspect, sides rounded to 32 (1200x434 ->
    1696x608): rendering at that size means the model does not resample the render."""
    r = w / h
    W = round((area * r) ** 0.5 / mult) * mult
    return W, round(W / r / mult) * mult


def main():
    import cv2
    import depth as DP
    from scipy.ndimage import binary_dilation
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    img = Image.open(src).convert("RGB")
    D, valid, st = DP.precise_depth(DP.load(), DP.load(DP.METRIC_ID), img)
    print("depth", st)
    W, H = model_size(*img.size)
    big = img.resize((W, H), Image.LANCZOS)
    Db = np.asarray(Image.fromarray(D).resize((W, H), Image.BILINEAR))
    for name, (yaw, pitch) in VIEWS.items():
        r, m = render(big, Db, yaw, pitch)
        hole = np.asarray(m) > 127
        r.save(out / f"view_{name}.png")
        # mask for the model: holes grown 6 px (torn edges around them); render pre-filled so the model does not read
        # black holes as content
        grown = binary_dilation(hole, iterations=6)
        Image.fromarray(grown.astype(np.uint8) * 255).save(out / f"mask_{name}.png")
        pre = cv2.inpaint(np.asarray(r), grown.astype(np.uint8) * 255, 15, cv2.INPAINT_TELEA)
        Image.fromarray(pre).save(out / f"prefill_{name}.png")
        print(name, (W, H), f"holes {hole.mean() * 100:.1f}%, mask {grown.mean() * 100:.1f}%")


if __name__ == "__main__":
    main()
