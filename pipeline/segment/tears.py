"""The scene's tears (where the mesh cuts the scene surface), listed for a judge (scene_judge.judge_tears) and closed on
its decisions.

  list_tears   group the scene's cut cells (outside characters) into tears, write a numbered contact sheet (each tear's
               crop, the tear in red), an overview and tears.json (cells, size, depth ratio)
  close_tears  close the chosen tears: around each, the depth of both sides is replaced by one inverse-depth plane
               fitted to them (the two sides become one surface, no cut); writes the box's grid back (and rebuilds the
               layered mesh, if the box has one)
  fill_tears   behind kept tears (real object edges), the far side's plane into the backdrop layer

    python tears.py list  <box id> <out dir> [viewer root]
    python tears.py apply <box id> <out dir> <decisions.json> [viewer root]   decisions {"close": [ids]}
    python tears.py fill  <box id> <out dir> <decisions.json> [viewer root]   decisions {"fill": [ids]}
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt, label

from occlusion_mask import VIEWER


def load(pid, root=VIEWER):
    M = Path(root) / "mesh"
    m = json.loads((M / f"{pid}.json").read_text())
    gh, gw = m["gh"], m["gw"]
    G = np.fromfile(M / f"{pid}.fgclean.f32", np.float32).reshape(gh, gw)
    S = np.fromfile(M / f"{pid}.seg.u8", np.uint8).reshape(gh, gw)
    return m, G, S


def tears(m, G, S, min_cells=6):
    st = np.stack([G[:-1, :-1], G[:-1, 1:], G[1:, :-1], G[1:, 1:]])
    ok = (st > 0).all(0)
    r = st.max(0) / np.where(ok, st.min(0), 1)
    scene = np.stack([S[:-1, :-1], S[:-1, 1:], S[1:, :-1], S[1:, 1:]]).max(0) == 0
    cut = ok & scene & (r > m["jump"])
    lab, n = label(cut, structure=np.ones((3, 3)))
    out = []
    for i in range(1, n + 1):
        cells = np.argwhere(lab == i)
        if len(cells) < min_cells:
            continue
        out.append({"id": len(out) + 1, "cells": cells.tolist(), "n": len(cells),
                    "ratio": round(float(np.median(r[lab == i])), 3)})
    return out


def list_tears(pid, root=VIEWER, out=None):
    """Writes tears_sheet.png, tears_overview.png and tears.json into `out`; returns the tears."""
    M, out = Path(root) / "mesh", Path(out)
    out.mkdir(parents=True, exist_ok=True)
    m, G, S = load(pid, root)
    T = tears(m, G, S)
    write_sheets(Image.open(M / f"{pid}.png").convert("RGB"), T, m["stride"], out)
    (out / "tears.json").write_text(json.dumps(T))
    print(f"{len(T)} tears (>= 6 cells); sheet: {out / 'tears_sheet.png'}")
    return T


def _crop_box(c, k, w, h, pad=60, aspect=0.6):
    """The tear's bounding box plus `pad` px, its short side grown to at least `aspect` of the long one (a thin crop
    along a table's rim showed too little of the table: read as a light patch on the floor, ToG 228 p6 #8), kept in
    the image."""
    y0, x0 = c.min(0) * k - pad
    y1, x1 = c.max(0) * k + k + pad
    bw, bh = x1 - x0, y1 - y0
    if bw < aspect * bh:
        g = (aspect * bh - bw) / 2
        x0, x1 = x0 - g, x1 + g
    elif bh < aspect * bw:
        g = (aspect * bw - bh) / 2
        y0, y1 = y0 - g, y1 + g
    if x0 < 0:
        x0, x1 = 0, x1 - x0
    if y0 < 0:
        y0, y1 = 0, y1 - y0
    if x1 > w:
        x0, x1 = max(0, x0 - (x1 - w)), w
    if y1 > h:
        y0, y1 = max(0, y0 - (y1 - h)), h
    return int(x0), int(y0), int(x1), int(y1)


def write_sheets(img, T, k, out):
    """tears_sheet.png (one numbered tile per tear, the tear in red, 8 tiles of 190 x 205 per row) and
    tears_overview.png (all tears numbered on the box)."""
    out = Path(out)
    tiles = []
    for t in T:
        c = np.array(t["cells"])
        x0, y0, x1, y1 = _crop_box(c, k, img.width, img.height)
        crop = img.crop((x0, y0, x1, y1)).copy()
        d = ImageDraw.Draw(crop)
        s = 180 / max(crop.size)
        r = max(0, int(np.ceil(1 / s)) - k // 2)  # the red line stays ~2 px wide after the tile's downscale
        for y, x in c:
            d.rectangle((x * k - x0 - r, y * k - y0 - r, x * k - x0 + k + r, y * k - y0 + k + r), fill=(255, 0, 0))
        crop = crop.resize((max(1, int(crop.width * s)), max(1, int(crop.height * s))))
        tile = Image.new("RGB", (190, 205), "white")
        tile.paste(crop, (5, 20))
        ImageDraw.Draw(tile).text((5, 3), f"#{t['id']}  {t['n']} cells  x{t['ratio']}", fill=(0, 0, 0))
        tiles.append(tile)
    cols = 8
    sheet = Image.new("RGB", (cols * 190, max(1, (len(tiles) + cols - 1) // cols) * 205), "white")
    for i, t in enumerate(tiles):
        sheet.paste(t, ((i % cols) * 190, (i // cols) * 205))
    sheet.save(out / "tears_sheet.png")
    # overview: all tears numbered on the box
    ov = img.copy()
    d = ImageDraw.Draw(ov)
    for t in T:
        c = np.array(t["cells"])
        for y, x in c:
            d.rectangle((x * k, y * k, x * k + k, y * k + k), fill=(255, 0, 0))
        y, x = c.mean(0) * k
        d.text((x + 4, y - 6), str(t["id"]), fill=(0, 0, 255))
    ov.save(out / "tears_overview.png")


def close_tears(pid, root=VIEWER, out=None, ids=()):
    """Closes the tears `ids` of out/tears.json (written by list_tears). Returns (tears closed, scene tears left)."""
    M, out = Path(root) / "mesh", Path(out)
    m, G, S = load(pid, root)
    T = {t["id"]: t for t in json.loads((out / "tears.json").read_text())}
    close = [i for i in ids if i in T]
    k, f = m["stride"], max(m["w"], m["h"]) / (2 * np.tan(np.radians(m["fov"]) / 2))
    gh, gw = G.shape
    v, u = np.mgrid[0:gh, 0:gw].astype(np.float64) * k
    rx, ry = (u - m["w"] / 2) / f, -(v - m["h"] / 2) / f
    G2 = G.copy()
    for i in close:
        c = np.array(T[i]["cells"])
        core = np.zeros_like(G, bool)
        core[c[:, 0], c[:, 1]] = True
        band = binary_dilation(core, iterations=8) & (G > 0) & (S == 0)
        A = np.stack([rx[band], ry[band], np.ones(band.sum())], 1)
        p, *_ = np.linalg.lstsq(A, 1.0 / G[band], rcond=None)  # 1/D = a*rx + b*ry + c: a plane through both sides
        fitted = 1.0 / np.maximum(p[0] * rx + p[1] * ry + p[2], 1e-6)
        # blend: the plane at the tear, the original depth 8 cells away (no new seam at the band's edge)
        dist = distance_transform_edt(~core)
        wgt = np.clip(1 - dist / 8, 0, 1)
        G2 = np.where(band, wgt * fitted + (1 - wgt) * G2, G2).astype(np.float32)
    G2.tofile(M / f"{pid}.fgclean.f32")
    if (M / f"{pid}.ldi.bin").exists():  # the layered mesh is built from this grid: rebuild it
        import ldi_mesh
        ldi_mesh.build(pid, root)
    after = tears(m, G2, S)
    print(f"closed {len(close)} tears; scene tears now {len(after)} (were {len(T)})")
    return len(close), len(after)


def fill_tears(pid, root=VIEWER, out=None, ids=(), width=45, far_cells=15):
    """Behind each kept tear `ids` (a real object edge): the background the object hides, put into the backdrop layer.
    Near side = the cells of the tear's band nearer than its far side; behind them, up to `width` grid cells (90 px)
    from the tear, the far side's plane (fitted on the far side within far_cells), kept 2% behind the object; colours
    inpainted from the backdrop around. Writes bg1.f32 / bg1.png back."""
    import cv2
    M, out = Path(root) / "mesh", Path(out)
    m, G, S = load(pid, root)
    T = {t["id"]: t for t in json.loads((out / "tears.json").read_text())}
    ids = [i for i in ids if i in T]
    k, f = m["stride"], max(m["w"], m["h"]) / (2 * np.tan(np.radians(m["fov"]) / 2))
    gh, gw = G.shape
    B = np.fromfile(M / f"{pid}.bg1.f32", np.float32).reshape(gh, gw)
    tex = np.asarray(Image.open(M / f"{pid}.bg1.png").convert("RGB")).copy()
    v, u = np.mgrid[0:gh, 0:gw].astype(np.float64) * k
    rx, ry = (u - m["w"] / 2) / f, -(v - m["h"] / 2) / f
    paint = np.zeros((m["h"], m["w"]), bool)
    added = 0
    # cells the panel surface itself draws (not cut): the backdrop behind them is hidden from the front, and only there
    # may it change. Where the panel is cut (the gap between a desk's legs) the backdrop is what the reader sees, and the
    # plate's colours there were right; repainting them raised the frontal seam error from 2.9 to 5.3
    st = np.stack([G[:-1, :-1], G[:-1, 1:], G[1:, :-1], G[1:, 1:]])
    okc = (st > 0).all(0) & (st.max(0) / np.where((st > 0).all(0), st.min(0), 1) <= m["jump"])
    hidden = np.zeros_like(G, bool)
    hidden[:-1, :-1] |= okc
    hidden = hidden & ~binary_dilation(~hidden & (G > 0), iterations=2)  # 2 cells clear of any visible gap
    for i in ids:
        c = np.array(T[i]["cells"])
        core = np.zeros_like(G, bool)
        core[c[:, 0], c[:, 1]] = True
        dist = distance_transform_edt(~core)
        zone = (dist <= width) & (G > 0)
        ref = np.median(G[core])  # the tear's own depth sits between its two sides
        far = (dist <= far_cells) & (dist > 1) & (G > ref * 1.015) & (S == 0)
        near = zone & (G < ref) & (dist > 0)  # the object's side
        if far.sum() < 30 or not near.any():
            continue
        A = np.stack([rx[far], ry[far], np.ones(far.sum())], 1)
        p, *_ = np.linalg.lstsq(A, 1.0 / G[far], rcond=None)
        plane = 1.0 / np.maximum(p[0] * rx + p[1] * ry + p[2], 1e-6)
        # only under the object (hidden from the front): the tear's own cells show through the cut from the front and
        # keep their colours (repainting them raised the frontal seam error from 2.9 to 4.3)
        sel = near & (dist > 1) & hidden
        newd = np.maximum(plane, G * 1.02)
        # the plane blends into the backdrop already there over the band's last 8 cells: an abrupt end opened new cuts
        wgt = np.clip((width - dist) / 8, 0, 1)
        old = np.where(B > 0, B, newd)
        blended = np.maximum(wgt * newd + (1 - wgt) * old, G * 1.02)
        B = np.where(sel, blended, B).astype(np.float32)
        added += int(sel.sum())
        big = cv2.resize(sel.astype(np.uint8), (m["w"], m["h"]), interpolation=cv2.INTER_NEAREST).astype(bool)
        paint |= big
    tex = cv2.inpaint(np.ascontiguousarray(tex), paint.astype(np.uint8), 7, cv2.INPAINT_TELEA)
    B.tofile(M / f"{pid}.bg1.f32")
    Image.fromarray(tex).save(M / f"{pid}.bg1.png")
    print(f"filled behind {len(ids)} object edges: {added} backdrop cells set, {int(paint.sum())} px repainted")


def main():
    cmd, pid, out = sys.argv[1], sys.argv[2], Path(sys.argv[3])
    if cmd == "list":
        list_tears(pid, sys.argv[4] if len(sys.argv) > 4 else VIEWER, out)
        return
    root = sys.argv[5] if len(sys.argv) > 5 else VIEWER
    dec = json.loads(Path(sys.argv[4]).read_text())
    if cmd == "apply":
        close_tears(pid, root, out, dec["close"])
    elif cmd == "fill":
        fill_tears(pid, root, out, dec["fill"])
    else:
        raise SystemExit(f"unknown command {cmd}")


if __name__ == "__main__":
    main()
