"""Edge quality of a box's 3D surfaces, offline, from the files the viewer reads: what the reader sees from the front
(the original camera) should be the lettering-free base image exactly. Each surface (scene mesh, figure surface with
its alpha, hidden layers) is composited per pixel the way the viewer draws it: a 2 px grid cell is drawn when the
viewer keeps its triangles (corner depths within the jump ratio, segment rule), the nearest drawn surface wins.

    python experiments/edge_metric.py <box id> [root]
Prints:  holes      share of art pixels where nothing is drawn (black in the viewer)
         halo       mean colour error (0-255, CIELAB distance) against the base image in a 12 px band around the
                    characters, and the share of that band off by more than 12
         seam       the same over every scene pixel within 6 px of a mesh cut
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import cv2
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation

from occlusion_mask import VIEWER


def cells(Dg, cut, sg=None, own=False):
    st = np.stack([Dg[:-1, :-1], Dg[:-1, 1:], Dg[1:, :-1], Dg[1:, 1:]])
    ok = (st > 0).all(0)
    keep = ok.copy()
    if cut:
        keep &= st.max(0) / np.where(ok, st.min(0), 1) <= cut
    if sg is not None:
        ss = np.stack([sg[:-1, :-1], sg[:-1, 1:], sg[1:, :-1], sg[1:, 1:]])
        keep &= (ss.max(0) == 0) if own else (ss.min(0) == ss.max(0))
    return keep


def to_px(cellmask, k, h, w):
    m = np.kron(cellmask, np.ones((k, k), bool))
    return np.pad(m, ((0, max(0, h - m.shape[0])), (0, max(0, w - m.shape[1]))))[:h, :w]


def measure(pid, root=VIEWER, base_png=None):
    M = root / "mesh"
    m = json.loads((M / f"{pid}.json").read_text())
    gw, gh, k, jump = m["gw"], m["gh"], m["stride"], m["jump"]
    h, w = m["h"], m["w"]
    grid = lambda n, dt=np.float32: np.fromfile(M / n, dt).reshape(gh, gw)
    G = grid(f"{pid}.fgclean.f32") if (M / f"{pid}.fgclean.f32").exists() else grid(f"{pid}.f32")
    seg = grid(f"{pid}.seg.u8", np.uint8) if (M / f"{pid}.seg.u8").exists() else None
    fig = grid(f"{pid}.fig.f32") if (M / f"{pid}.fig.f32").exists() else None
    lj = json.loads((M / f"{pid}.layers.json").read_text()) if (M / f"{pid}.layers.json").exists() else {"layers": 0}
    own = fig is not None and seg is not None
    scene_cut = lj.get("scene_seg_cut", True)
    texa = np.asarray(Image.open(M / (f"{pid}.fgclean.png" if (M / f"{pid}.fgclean.png").exists() else f"{pid}.png")).convert("RGB"))
    # candidates per pixel: (depth, colour, drawn)
    big = lambda Dg: cv2.resize(Dg, (w, h), interpolation=cv2.INTER_LINEAR)
    cand = [(big(G), texa, to_px(cells(G, jump, seg if scene_cut else None, own and scene_cut), k, h, w))]
    if own:
        fa = np.asarray(Image.open(M / f"{pid}.fig.png").convert("RGBA"))
        cand.append((big(fig), fa[..., :3], to_px(cells(fig, jump), k, h, w) & (fa[..., 3] >= 128)))
    for i in range(1, lj["layers"] + 1):
        B = grid(f"{pid}.bg{i}.f32")
        cut = lj.get("jump", [jump] * lj["layers"])[i - 1]
        cand.append((big(B), np.asarray(Image.open(M / f"{pid}.bg{i}.png").convert("RGB")), to_px(cells(B, cut), k, h, w)))
    depth = np.full((h, w), np.inf, np.float32)
    col = np.zeros((h, w, 3), np.uint8)
    for d, c, drawn in cand:
        win = drawn & (d < depth)
        depth[win], col[win] = d[win], c[win]
    art = to_px(G > 0, k, h, w) | (G[0:1].size == 0)
    base = np.asarray(Image.open(base_png).convert("RGB")) if base_png else np.asarray(Image.open(M / f"{pid}.png").convert("RGB"))
    lab = lambda a: cv2.cvtColor(a, cv2.COLOR_RGB2LAB).astype(np.float32)
    err = np.linalg.norm(lab(col) - lab(base), axis=-1)
    holes = art & ~np.isfinite(depth)
    out = {"holes_%": round(float(holes.sum() / art.sum() * 100), 3)}
    if seg is not None:
        chars = to_px(seg == 1, k, h, w)
        band = binary_dilation(chars, iterations=12) & ~chars & art
        out["halo_err"] = round(float(err[band].mean()), 2)
        out["halo_off_%"] = round(float((err[band] > 12).mean() * 100), 1)
    cut = ~cells(G, jump) & cells(G, None)
    seam = binary_dilation(to_px(cut, k, h, w), iterations=6) & art
    out["seam_err"] = round(float(err[seam].mean()), 2)
    return out, col, holes


if __name__ == "__main__":
    pid = sys.argv[1]
    root = Path(sys.argv[2]) if len(sys.argv) > 2 else VIEWER
    res, col, holes = measure(pid, root)
    print(json.dumps(res))
    c = col.copy()
    c[holes] = [255, 0, 255]
    Image.fromarray(c).save(Path(sys.argv[3]) if len(sys.argv) > 3 else root / f"{pid}.frontal.png")
