"""One coherent mesh from the scene surface and the hidden layers behind it (a layered depth mesh, as in 3D Photo
Inpainting, Shih et al. 2020): each grid cell holds up to one sample per layer, and neighbouring samples are joined
into triangles wherever their depths agree, whichever layer they come from. The floor hidden behind a chair continues
straight into the visible floor around it, instead of being a separate surface floating behind (user, 2026-10-25).

  samples    scene (fgclean.f32) and the hidden layers (bg<k>.f32), every STRIDE px; a layer's sample at a cell where a
             nearer layer already lies on the same surface (depth within SAME) is that sample, not a new one
  triangles  per grid triangle and anchor layer: each corner takes the sample nearest in depth to the anchor's; kept
             when all three agree within the cut ratio (the mesh's jump), so object edges stay open as before
  texture    an atlas of the layers' textures stacked vertically; a triangle is textured from its anchor layer at
             every corner (all plates cover the whole box, and where the depths agree they show the same surface)

Writes mesh/<id>.ldi.bin (uint32 n_vertices, n_indices; float32 xyz per vertex in camera space; float32 uv; uint32
indices) and mesh/<id>.ldi.png (the atlas). The characters keep their own alpha-masked figure surface.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

SAME = 0.01


def build(pid: str, root: Path) -> dict:
    M = root / "mesh"
    m = json.loads((M / f"{pid}.json").read_text())
    gh, gw, k, jump, w, h = m["gh"], m["gw"], m["stride"], m["jump"], m["w"], m["h"]
    lj = json.loads((M / f"{pid}.layers.json").read_text())
    grids = [np.fromfile(M / f"{pid}.fgclean.f32", np.float32).reshape(gh, gw)]
    texs = [M / f"{pid}.fgclean.png"]
    for i in range(1, lj["layers"] + 1):
        grids.append(np.fromfile(M / f"{pid}.bg{i}.f32", np.float32).reshape(gh, gw))
        texs.append(M / f"{pid}.bg{i}.png")
    K = len(grids)
    D = np.stack(grids)  # K x gh x gw, 0 = no sample
    # a deeper layer on the same surface as a nearer one at that cell is not a sample of its own
    own = D > 0
    for kk in range(1, K):
        for j in range(kk):
            same = own[j] & own[kk] & (np.abs(D[kk] / np.where(D[j] > 0, D[j], 1) - 1) < SAME)
            own[kk] &= ~same
    Dz = np.where(own, D, np.inf)
    f = max(w, h) / (2 * np.tan(np.radians(m["fov"]) / 2))
    yy, xx = np.mgrid[0:gh, 0:gw]
    # triangles: (corner offsets) for the two triangles of a cell, as in the viewer
    tris = (((0, 0), (1, 0), (0, 1)), ((0, 1), (1, 0), (1, 1)))
    verts: dict[tuple, int] = {}
    pos, uv, idx = [], [], []

    def vid(layer_pos, y, x, layer_uv):
        key = (layer_pos, y, x, layer_uv)
        v = verts.get(key)
        if v is None:
            v = len(pos)
            verts[key] = v
            d = D[layer_pos, y, x]
            u, vv = x * k, y * k
            pos.append(((u - w / 2) * d / f, -(vv - h / 2) * d / f, -d))
            uv.append(((u + 0.5) / w, 1 - (layer_uv * h + vv + 0.5) / (K * h)))
        return v

    seen = set()
    H, W = gh - 1, gw - 1
    for anchor in range(K):
        for tri in tris:
            (ay, ax), (by_, bx), (cy, cx) = tri
            da = Dz[anchor, ay:ay + H, ax:ax + W]
            valid = np.isfinite(da)
            corner = []
            for (oy, ox) in tri:
                dc = Dz[:, oy:oy + H, ox:ox + W]  # K x H x W
                r = np.abs(dc / da[None] - 1)
                r[~np.isfinite(r)] = np.inf
                lay = r.argmin(0)
                rr = np.take_along_axis(r, lay[None], 0)[0]
                valid &= rr <= jump - 1
                corner.append(lay)
            ys, xs = np.nonzero(valid)
            for y, x in zip(ys.tolist(), xs.tolist()):
                ids = []
                for (oy, ox), lay in zip(tri, corner):
                    ids.append((int(lay[y, x]), y + oy, x + ox))
                key = tuple(sorted(ids))
                if key in seen:
                    continue
                seen.add(key)
                idx.extend(vid(l, cy_, cx_, anchor) for l, cy_, cx_ in ids)
    pos = np.asarray(pos, np.float32)
    uv = np.asarray(uv, np.float32)
    idx = np.asarray(idx, np.uint32)
    with open(M / f"{pid}.ldi.bin", "wb") as fh:
        fh.write(np.array([len(pos), len(idx)], np.uint32).tobytes())
        fh.write(pos.tobytes()); fh.write(uv.tobytes()); fh.write(idx.tobytes())
    atlas = np.concatenate([np.asarray(Image.open(t).convert("RGB")) for t in texs], 0)
    Image.fromarray(atlas).save(M / f"{pid}.ldi.png")
    cross = sum(1 for key in seen if len({l for l, _, _ in key}) > 1)
    return {"layers": K, "vertices": len(pos), "triangles": len(idx) // 3, "joined_across_layers": cross}


if __name__ == "__main__":
    import sys
    from occlusion_mask import VIEWER
    print(build(sys.argv[1], Path(sys.argv[2]) if len(sys.argv) > 2 else VIEWER))
