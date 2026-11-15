"""A place's geometry (CONTEXT.md: Place): a setting's wide view lifted to the meshes the reader shows through its walls.
MoGe-3 (Ruicheng/moge-3-vitl, MIT) on the local GPU; it needs a PyTorch build the segment environment cannot hold, so
this module runs in pipeline/.venv-moge as a subprocess of places.py, one command per stage, on one place folder:

    depth DIR   (the model) view.png -> its span (measure_span) in depth.json and its depth (pano_depth) as
                distance-full.npy
    show DIR    (no model) the central SHOWN_DEG of the view (shown.png), distance.npy, erase-mask.png (the near
                objects, for the erase), depth.png, geometry.json (the span shown and how far the place is)
    front DIR   (no model) shown.png, distance.npy -> front.glb (cut at depth edges)
    back DIR    shown.png, distance.npy, plate.png (the erase's output) -> back.glb (the near objects taken out, the
                plate regraded to the view's colour, never cut, BACK_PUSH farther), back-texture.png

Four stages because they cost differently and places.py stamps each by what shapes it (SHAPES): MoGe's depth is not
bit-identical between runs, so running it again moves the erase's mask and the paid erase is made again. Until
2026-11-15 depth, shown window and front mesh were one stage under one stamp, and a change of a mesh constant alone
ran MoGe and cost a place's erase again (0.14 USD for four places, for nothing). Now a change to the meshes builds
only the meshes, and shown.png and erase-mask.png keep their bytes.

The wide view is read as a window of an equirectangular panorama around the seat: FLUX 3 keeps verticals straight and
curves horizontals. Meshes are in three.js axes: the eye at the origin, the view's centre down -z, y up, metres at
MoGe's scale (the reader scales the place to its room), unlit (KHR_materials_unlit: the painting is already lit).

    .venv-moge/Scripts/python.exe segment/place_geometry.py depth <episode>/places/tavern-main
"""
from __future__ import annotations

import json
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("HF_HOME", "D:/hf-cache")
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

MODEL = "Ruicheng/moge-3-vitl"
STRIDE_PX = 720        # the front mesh is thinned (adaptive) from a grid of one vertex every width / STRIDE_PX px (3 px
                       # on a 2160-px view), so a sharper view keeps the same mesh
BACK_STRIDE_PX = 540   # the back layer's grid
FRONT_TOL = 1.0        # px (at QUEST_PPD) the painting may sit off its place on the thinned front mesh. Measured
                       # 2026-11-15 on the tavern, village and terrace against the full grid (492 k faces, 14-15 MB):
                       # 0.25 -> 132-160 k faces, 0.5 -> 105-122 k, 1 -> 82-90 k (5.3-6.2 MB), 2 -> 58-65 k, 4 -> 39-46 k;
                       # outlines from the seat identical at every level. At 1 a render from the seat keeps 44.6-48.5 dB
                       # PSNR and one 0.3 to the side or up 37.7-41.7 dB; at 4 (33-39 and 28-32 dB) floor boards and
                       # roof lines shift
BACK_TOL = 2.0         # the back layer's, coarser: it is only seen through gaps. 2 -> 28-47 k faces (2.8-4.6 MB, the
                       # grid: 288 k, 8.5-10.2 MB); with the front at 1 a place is 110-129 k faces and the pair's
                       # render 0.3 off the seat keeps 38.3-43.8 dB (36.0-42.7 at 4). A coarser grid instead pulled
                       # the layer's outline in by up to 88 px (2026-11-15)
HEAD_MOVE = 0.3        # the head move adaptive allows for, in the mesh's units: 30 cm if the reader shows a place at
                       # MoGe's scale, less of the room if it shows it larger
QUEST_PPD = 25         # px per degree at the centre of a Quest 3's lens, what FRONT_TOL and BACK_TOL count in
RTOL = 0.06            # a face whose farthest corner is this share farther than its nearest is cut (at 0.12 stool
                       # rims stretched into streaks at a 1.5 m head move)
SNAP = 7               # px window (on a 2160-px view, scaled with the width) in which an edge pixel's distance snaps
MERGE = (1440, 720)    # MoGe's panorama merge size for the full canvas: 1920 x 960 ran out of memory here
SKY_FAR = 4.0          # sky (invalid in every view) at this many times the 95th percentile of the rest
CLOSE_WINDOW = 0.12    # near_objects' window, a share of the width (on an equirectangular view a wall's inverse
                       # distance bulges, and a quarter of the width took wall centres)
NEAR_SHARE = 0.06      # a pixel this much nearer than the opened surface belongs to a near object
OBJ_GROW = 4           # px the near objects are grown (on a 2160-px view, scaled), so their anti-aliased rims go too
ERASE_GROW = 6         # px more for the erase's mask (scaled likewise), so it takes the objects' contact shadows
MATCH_SIGMA = 40       # px: the colour correction field's scale; finer is detail, which stays the plate's
MATCH_WIDE = 160       # px: the wider field used where the fine one has no shared pixels nearby
BACK_PUSH = 1.03       # the back layer's distance times this: just behind whatever the front mesh shows
SHOWN_DEG = (140.0, 72.0)  # the most of a view a place shows across and up-down: the tavern's first 2:1 view, the
                           # user's reference (140 x 71); a wider view is cropped to it, centred straight ahead
WORK_W = 2160        # depth, span and masks are computed on a copy this wide; a sharper view only sharpens the
                       # front's texture (MoGe ran out of GPU memory on a 5792-px view)
MATERIAL = "unlit"   # how both meshes are shaded: KHR_materials_unlit, as the panels' scenes (2026-11-15; a lit PBR
                     # material before, which a reader's lights shaded a second time)
SHAPES = {  # the constants each stage's files are shaped by: places.py stamps a stage's outputs with their values
    "depth": ("MODEL", "MERGE", "SKY_FAR", "WORK_W", "RTOL", "SNAP"),
    "show": ("SHOWN_DEG", "WORK_W", "RTOL", "SNAP", "CLOSE_WINDOW", "NEAR_SHARE", "OBJ_GROW", "ERASE_GROW"),
    "front": ("STRIDE_PX", "FRONT_TOL", "HEAD_MOVE", "QUEST_PPD", "RTOL", "MATERIAL"),
    "back": ("BACK_STRIDE_PX", "BACK_TOL", "HEAD_MOVE", "QUEST_PPD", "CLOSE_WINDOW", "NEAR_SHARE", "OBJ_GROW",
             "ERASE_GROW", "MATCH_SIGMA", "MATCH_WIDE", "BACK_PUSH", "MATERIAL"),
}


def recipe(stage: str) -> dict:
    """{constant: value} for what shapes a stage's files (SHAPES), read by places.py in its own environment."""
    return {k: globals()[k] for k in SHAPES[stage]}


def _work(img: Image.Image) -> Image.Image:
    w, h = img.size
    return img if w <= WORK_W else img.resize((WORK_W, round(h * WORK_W / w)), Image.LANCZOS)


def _px(n: int, w: int) -> int:
    """A pixel size tuned on 2160-px views, at this view's width."""
    return max(1, round(n * w / 2160))


def _model():
    import torch
    from moge.model.v3 import MoGeModel
    with torch.device("cuda"):  # built on the GPU: on the CPU it needs ~1.5 GB of commit this machine may not have
        return MoGeModel.from_pretrained(MODEL).eval()


def measure_span(model, img: Image.Image) -> tuple[float, float]:
    """(horizontal, vertical) degrees the wide view spans: MoGe's FOV on the central quarter and third of the width
    gives the angle per pixel at the centre, times the size. (The tavern: 144 and 142 degrees from those crops; the
    first guess, 180 x 90, stretched the sides; user, 2026-11-08.)"""
    import torch
    w, h = img.size
    rates = []
    for share in (0.25, 0.33):
        cw = int(w * share)
        x0 = (w - cw) // 2
        t = torch.tensor(np.asarray(img.crop((x0, 0, x0 + cw, h)), dtype=np.float32) / 255).permute(2, 0, 1).cuda()
        with torch.no_grad():
            o = model.infer(t)
        rates.append(float(o["intrinsics"][0, 0]) * cw)  # focal length in px: px per radian at the centre
    f = float(np.mean(rates))
    return round(float(np.degrees(w / f)), 1), round(float(np.degrees(h / f)), 1)


def dirs(h: int, w: int, h_deg: float, v_deg: float) -> np.ndarray:
    """Unit rays (h, w, 3) in OpenCV axes (x right, y down, z forward): the centre column straight ahead."""
    lon = ((np.arange(w) + 0.5) / w - 0.5) * np.radians(h_deg)
    lat = (0.5 - (np.arange(h) + 0.5) / h) * np.radians(v_deg)
    lon, lat = np.meshgrid(lon, lat)
    return np.stack([np.sin(lon) * np.cos(lat), -np.sin(lat), np.cos(lon) * np.cos(lat)], -1)


def pano_depth(model, img: Image.Image, h_deg: float, v_deg: float) -> np.ndarray:
    """MoGe-3 distance per pixel, as MoGe's own infer_panorama does it with the v3 model: the view padded onto a full
    360 x 180 canvas, cut into 20 views of 90 degrees (one per icosahedron vertex), each inferred with its known FOV and
    masked to the pixels that came from the image, merged by MoGe's Poisson solve, cropped back; sky far away."""
    import cv2
    import torch
    import utils3d_moge as utils3d
    from moge.utils.panorama import get_panorama_cameras, merge_panorama_depth, split_panorama_image
    rgb = np.asarray(img.convert("RGB"))
    h, w = rgb.shape[:2]
    W, H = round(w * 360 / h_deg), round(h * 180 / v_deg)
    x0, y0 = (W - w) // 2, (H - h) // 2
    canvas = np.zeros((H, W, 3), np.uint8)
    canvas[y0:y0 + h, x0:x0 + w] = rgb
    known = np.zeros((H, W, 3), np.uint8)
    known[y0:y0 + h, x0:x0 + w] = 255
    extr, intr = get_panorama_cameras()
    views = split_panorama_image(canvas, extr, intr, 512)
    vknown = split_panorama_image(known, extr, intr, 512)
    dists, masks = [], []
    for i in range(len(views)):
        k = vknown[i][..., 0] > 127
        if k.mean() < 0.05:
            dists.append(np.ones(k.shape, np.float32))
            masks.append(np.zeros(k.shape, bool))
            continue
        t = torch.tensor(views[i][None] / 255, dtype=torch.float32, device="cuda").permute(0, 3, 1, 2)
        fx, _ = np.rad2deg(utils3d.np.intrinsics_to_fov(np.array(intr[i:i + 1])))
        with torch.no_grad():
            o = model.infer(t, fov_x=torch.tensor(fx, dtype=torch.float32, device="cuda"), apply_mask=False)
        dists.append(o["points"][0].norm(dim=-1).cpu().numpy())
        masks.append(o["mask"][0].cpu().numpy().astype(bool) & k)
    d, m = merge_panorama_depth(MERGE[0], MERGE[1], dists, masks, extr, intr)
    d = cv2.resize(d.astype(np.float32), (W, H), interpolation=cv2.INTER_LINEAR)[y0:y0 + h, x0:x0 + w]
    m = cv2.resize(m.astype(np.uint8), (W, H), interpolation=cv2.INTER_NEAREST)[y0:y0 + h, x0:x0 + w] > 0
    if (~m).any() and m.any():
        d = np.where(m, d, SKY_FAR * np.percentile(d[m], 95))
    return d


def snap_edges(pts: np.ndarray) -> np.ndarray:
    """MoGe ramps depth across an outline over a few pixels, in steps too small to cut, and those faces stretch into
    streaks when the head moves: where the near and far sides within SNAP px differ by more than RTOL, each pixel's
    distance snaps to the side it is closer to, so the ramp becomes one jump the cut finds."""
    from scipy.ndimage import maximum_filter, minimum_filter
    d = np.linalg.norm(pts, axis=-1)
    size = _px(SNAP, d.shape[1]) | 1
    lo, hi = minimum_filter(d, size=size), maximum_filter(d, size=size)
    d2 = np.where(hi > lo * (1 + RTOL), np.where(d - lo < hi - d, lo, hi), d)
    return pts * (d2 / np.clip(d, 1e-6, None))[..., None]


def grid(pts: np.ndarray, stride: int, rtol: float | None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(vertices, faces, kept) of a grid over a point map: one vertex every stride px, two triangles per square of
    neighbours (the upper-left ones, then the lower-right), faces across a jump of more than rtol cut (None: none);
    kept marks, over all of them, the faces that stayed. Vertices in three's axes."""
    pts = pts[::stride, ::stride]
    gh, gw = pts.shape[:2]
    verts = pts.reshape(-1, 3) * [1, -1, -1]  # OpenCV (x right, y down, z forward) -> three (y up, -z forward)
    idx = np.arange(gh * gw).reshape(gh, gw)
    a, b, c, d = idx[:-1, :-1], idx[:-1, 1:], idx[1:, :-1], idx[1:, 1:]
    faces = np.concatenate([np.stack([a, c, b], -1).reshape(-1, 3), np.stack([b, c, d], -1).reshape(-1, 3)])
    kept = np.ones(len(faces), bool)
    if rtol is not None:
        rf = np.linalg.norm(verts, axis=1)[faces]
        kept = rf.max(1) / np.maximum(rf.min(1), 1e-6) <= 1 + rtol
    return verts, faces[kept], kept


def adaptive(pts: np.ndarray, stride: int, rtol: float | None, tol: float) -> tuple[np.ndarray, np.ndarray]:
    """(vertices, faces) of the grid (grid) with the vertices a reader would not miss left out. Every vertex on an
    open border (the view's outline, the cuts at depth edges) stays, so outlines are the grid's own; the rest are
    triangulated (Delaunay over the grid's columns and rows, which is the view from the seat: no face can fold over
    another) and a vertex comes back, the worst of each triangle per round, while leaving it out would show: the
    painting drawn more than tol px (at QUEST_PPD) from its place, from the seat (the texture is laid straight across
    a face, the view is not) or after a head move of HEAD_MOVE (the face's depth against the vertex's)."""
    from scipy.spatial import Delaunay
    verts, faces, kept = grid(pts, stride, rtol)
    gh, gw = pts[::stride, ::stride].shape[:2]
    n = gh * gw
    ys, xs = np.divmod(np.arange(n), gw)
    # a slight shear makes each square's Delaunay diagonal the grid's own, so the triangulation holds every border edge
    xy = np.stack([xs + 1e-3 * ys, ys], -1).astype(np.float64)
    inv = 1 / np.linalg.norm(verts, axis=1)
    ray = verts * inv[:, None]
    ang = np.degrees(np.stack([np.arctan2(ray[:, 0], -ray[:, 2]), np.arcsin(ray[:, 1])], -1))
    edges = np.sort(faces[:, [0, 1, 1, 2, 2, 0]].reshape(-1, 2), 1)
    code, count = np.unique(edges[:, 0] * n + edges[:, 1], return_counts=True)
    border = code[count == 1]
    chosen = np.zeros(n, bool)
    chosen[border // n] = chosen[border % n] = True
    used = np.zeros(n, bool)
    used[faces] = True
    while True:
        idx = np.flatnonzero(chosen)
        tri = Delaunay(xy[idx])
        if len(tri.coplanar):
            raise RuntimeError(f"adaptive: the triangulation left out {len(tri.coplanar)} vertices")
        rest = np.flatnonzero(used & ~chosen)
        simplex = tri.find_simplex(xy[rest])
        rest, simplex = rest[simplex >= 0], simplex[simplex >= 0]
        corners = idx[tri.simplices[simplex]]
        p = verts[corners]  # each left-out vertex's face: its ray meets it at sum(beta * p)
        with np.errstate(divide="ignore", invalid="ignore"):
            beta = np.stack([(ray[rest] * np.cross(p[:, (i + 1) % 3], p[:, (i + 2) % 3])).sum(1) for i in range(3)],
                            -1) / (p[:, 0] * np.cross(p[:, 1], p[:, 2])).sum(1)[:, None]
            near = beta.sum(1)  # 1 / the face's distance along the ray
            drawn = ((beta / near[:, None])[..., None] * ang[corners]).sum(1)  # the direction painted there
            err = QUEST_PPD * np.maximum(np.hypot(*(drawn - ang[rest]).T),
                                         np.degrees(HEAD_MOVE * np.abs(near - inv[rest])))
        bad = ~(err <= tol)
        if not bad.any():
            break
        order = np.argsort(np.nan_to_num(err[bad], nan=np.inf))
        worst = np.full(len(tri.simplices), -1)
        worst[simplex[bad][order]] = rest[bad][order]  # the last written is each triangle's largest
        chosen[worst[worst >= 0]] = True
    f = idx[tri.simplices]
    cx, cy = xs[f].mean(1), ys[f].mean(1)  # a triangle stays when the grid face under its centre did
    i, j = np.clip(cy.astype(int), 0, gh - 2), np.clip(cx.astype(int), 0, gw - 2)
    f = f[kept.reshape(2, gh - 1, gw - 1)[((cx - j) + (cy - i) > 1).astype(int), i, j]]
    a, b, c = xy[f[:, 0]], xy[f[:, 1]], xy[f[:, 2]]
    turned = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]) > 0
    f[turned] = f[turned][:, [0, 2, 1]]  # wound as the grid's
    return verts, f


def write_mesh(verts: np.ndarray, faces: np.ndarray, h_deg: float, v_deg: float, texture: Image.Image,
               out: Path) -> tuple[int, int]:
    """The mesh as a .glb with the view on it, unlit: a vertex's place on the texture is its direction from the eye
    (dirs, inverted). Vertices no face uses are left out. Returns (vertices, faces)."""
    import trimesh
    used, faces = np.unique(faces, return_inverse=True)
    verts, faces = verts[used], faces.reshape(-1, 3)
    lon = np.arctan2(verts[:, 0], -verts[:, 2])
    lat = np.arcsin(verts[:, 1] / np.linalg.norm(verts, axis=1))
    uvs = np.stack([0.5 + lon / np.radians(h_deg), 0.5 + lat / np.radians(v_deg)], -1)
    m = trimesh.Trimesh(vertices=verts, faces=faces, process=False,
                        visual=trimesh.visual.TextureVisuals(uv=uvs, material=trimesh.visual.material.PBRMaterial(
                            baseColorTexture=texture, metallicFactor=0.0, roughnessFactor=1.0, doubleSided=True)))
    m.export(out)
    _unlit(out)
    return len(verts), len(faces)


def _unlit(path: Path) -> None:
    """A written GLB's materials marked KHR_materials_unlit (trimesh writes none): its JSON chunk rewritten, the
    binary chunk as it was."""
    b = path.read_bytes()
    n = struct.unpack_from("<I", b, 12)[0]
    j = json.loads(b[20:20 + n])
    for mat in j.get("materials", []):
        mat.setdefault("extensions", {})["KHR_materials_unlit"] = {}
    j["extensionsUsed"] = sorted(set(j.get("extensionsUsed", [])) | {"KHR_materials_unlit"})
    js = json.dumps(j, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    rest = b[20 + n:]
    path.write_bytes(struct.pack("<III", 0x46546C67, 2, 20 + len(js) + len(rest)) +
                     struct.pack("<II", len(js), 0x4E4F534A) + js + rest)


def near_objects(d: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(the near-object mask, the surface behind them as a distance): on the inverse distance, linear across a flat
    surface, a grey opening over CLOSE_WINDOW removes every peak narrower than the window (stools, tables, posts) while
    floors, walls and ceilings pass through; the image padded with an odd mirror, which continues a ramp straight (a
    plain mirror made the near floor a peak at the border)."""
    from scipy.ndimage import binary_dilation, grey_opening
    inv = 1.0 / np.clip(d, 1e-3, None)
    k = max(3, int(CLOSE_WINDOW * d.shape[1]))
    p = k // 2 + 1
    opened = grey_opening(np.pad(inv, p, mode="reflect", reflect_type="odd"), size=(k, k))[p:-p, p:-p]
    obj = binary_dilation(inv > opened * (1 + NEAR_SHARE), iterations=_px(OBJ_GROW, d.shape[1]))
    return obj, 1.0 / np.clip(opened, 1e-6, None)


def match_colour(plate: np.ndarray, orig: np.ndarray, known: np.ndarray) -> np.ndarray:
    """The plate regraded to the view: FLUX Erase re-renders the whole image (on the tavern, outside the mask: green and
    blue 11 % and 10 % low, brightness 0.88 to 1.12 by region). A per-channel gain field, view / plate, from the pixels
    both show (known) by normalised blurring at MATCH_SIGMA, MATCH_WIDE where the fine one has no support."""
    from scipy.ndimage import gaussian_filter
    w = known.astype(np.float32)
    s1, s2 = _px(MATCH_SIGMA, plate.shape[1]), _px(MATCH_WIDE, plate.shape[1])
    out = np.empty_like(plate)
    for c in range(3):
        o, p = orig[..., c] + 1.0, plate[..., c] + 1.0
        fields = [(gaussian_filter(o * w, s) / np.maximum(gaussian_filter(p * w, s), 1e-3), gaussian_filter(w, s))
                  for s in (s1, s2)]
        (fine, dfine), (wide, _) = fields
        t = np.clip(dfine / 0.2, 0, 1)
        out[..., c] = p * np.clip(fine * t + wide * (1 - t), 0.5, 2.0) - 1.0
    return out.clip(0, 255)


def depth_png(dist: np.ndarray, path: Path) -> None:
    inv = 1 / np.clip(dist, 1e-3, None)
    lo, hi = np.percentile(inv, [2, 98])
    Image.fromarray((np.clip((inv - lo) / (hi - lo), 0, 1) * 255).astype(np.uint8)).save(path)


def depth(d: Path) -> dict:
    """The view's span and its distance per pixel, the only stage that runs the model -> depth.json ({"view_deg"}),
    distance-full.npy."""
    img = _work(Image.open(d / "view.png").convert("RGB"))
    model = _model()
    h_deg, v_deg = measure_span(model, img)
    dist = pano_depth(model, img, h_deg, v_deg)  # on the whole view, for MoGe's context
    pts = snap_edges(dirs(img.height, img.width, h_deg, v_deg) * dist[..., None])
    np.save(d / "distance-full.npy", np.linalg.norm(pts, axis=-1).astype(np.float32))
    meta = {"view_deg": [h_deg, v_deg]}
    (d / "depth.json").write_text(json.dumps(meta), encoding="utf-8")
    return meta


def show(d: Path) -> dict:
    """The place shown, from the depth stage's files (no model): the central SHOWN_DEG of the view, so every place
    bleeds the same way onto the side walls and ceiling (spans came out 115-324 degrees; at 324 magic-vision covered
    the side walls whole, user 2026-11-08) -> shown.png, distance.npy, erase-mask.png, depth.png, geometry.json
    (near_m, median_m, far_m: the 5th, 50th and 95th percentile of the distance from the eye over the shown view,
    which a reader scales the place by)."""
    from scipy.ndimage import binary_dilation
    view_deg = json.loads((d / "depth.json").read_text(encoding="utf-8"))["view_deg"]
    h_deg, v_deg = view_deg
    full = Image.open(d / "view.png").convert("RGB")
    img = _work(full)
    w, h = img.size
    dist = np.load(d / "distance-full.npy")
    fx, fy = min(1.0, SHOWN_DEG[0] / h_deg), min(1.0, SHOWN_DEG[1] / v_deg)
    x0, y0 = round(w * (1 - fx) / 2), round(h * (1 - fy) / 2)
    X0, Y0 = round(full.width * (1 - fx) / 2), round(full.height * (1 - fy) / 2)
    full = full.crop((X0, Y0, full.width - X0, full.height - Y0))
    full.save(d / "shown.png")
    img, dist = img.crop((x0, y0, w - x0, h - y0)), dist[y0:h - y0, x0:w - x0]
    h_deg, v_deg = round(h_deg * img.width / w, 1), round(v_deg * img.height / h, 1)
    w, h = img.size
    pts = snap_edges(dirs(h, w, h_deg, v_deg) * dist[..., None])
    dist = np.linalg.norm(pts, axis=-1).astype(np.float32)
    np.save(d / "distance.npy", dist)
    obj, _ = near_objects(dist)
    mask = binary_dilation(obj, iterations=_px(ERASE_GROW, w))
    Image.fromarray((mask * 255).astype(np.uint8)).save(d / "erase-mask.png")
    depth_png(dist, d / "depth.png")
    meta = {"h_deg": h_deg, "v_deg": v_deg, "view_deg": view_deg, "px_per_deg": round(full.width / h_deg, 1),
            "near_m": round(float(np.percentile(dist, 5)), 3), "median_m": round(float(np.median(dist)), 3),
            "far_m": round(float(np.percentile(dist, 95)), 3), "near_share": round(float(obj.mean()), 3)}
    (d / "geometry.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def _mesh_meta(d: Path, part: str, nv: int, nf: int) -> dict:
    """geometry.json with a mesh's size under `part` ("front", "back"), saved."""
    meta = json.loads((d / "geometry.json").read_text(encoding="utf-8"))
    meta[part] = {"vertices": nv, "faces": nf, "mb": round((d / f"{part}.glb").stat().st_size / 1e6, 1)}
    (d / "geometry.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    return meta


def front(d: Path) -> dict:
    """The shown view as a mesh cut at depth edges, from show's files (no model): shown.png on distance.npy ->
    front.glb."""
    meta = json.loads((d / "geometry.json").read_text(encoding="utf-8"))
    dist = np.load(d / "distance.npy")  # the shown window at work size, its edges already snapped (show)
    h, w = dist.shape
    pts = dirs(h, w, meta["h_deg"], meta["v_deg"]) * dist[..., None]
    nv, nf = write_mesh(*adaptive(pts, max(1, round(w / STRIDE_PX)), RTOL, FRONT_TOL), meta["h_deg"], meta["v_deg"],
                        Image.open(d / "shown.png").convert("RGB"), d / "front.glb")
    return _mesh_meta(d, "front", nv, nf)


def back(d: Path) -> dict:
    from scipy.ndimage import binary_dilation, gaussian_filter
    meta = json.loads((d / "geometry.json").read_text(encoding="utf-8"))
    dist = np.load(d / "distance.npy")  # the shown window at work size: the back layer is only seen through gaps
    img = Image.open(d / "shown.png").convert("RGB").resize((dist.shape[1], dist.shape[0]), Image.LANCZOS)
    w, h = img.size
    obj, behind = near_objects(dist)
    shell = np.where(obj, gaussian_filter(behind, _px(8, w)), dist)
    orig = np.asarray(img, np.float32)
    plate = np.asarray(Image.open(d / "plate.png").convert("RGB").resize((w, h), Image.LANCZOS), np.float32)
    known = ~binary_dilation(obj, iterations=_px(ERASE_GROW + 8, w))
    tex = Image.fromarray(match_colour(plate, orig, known).astype(np.uint8))  # the whole back layer: one image, no paste
    tex.save(d / "back-texture.png")
    pts = dirs(h, w, meta["h_deg"], meta["v_deg"]) * (shell * BACK_PUSH)[..., None]
    nv, nf = write_mesh(*adaptive(pts, max(1, round(w / BACK_STRIDE_PX)), None, BACK_TOL), meta["h_deg"],
                        meta["v_deg"], tex, d / "back.glb")
    return _mesh_meta(d, "back", nv, nf)


if __name__ == "__main__":
    stage, folder = sys.argv[1], Path(sys.argv[2])
    print(json.dumps({"depth": depth, "show": show, "front": front, "back": back}[stage](folder)))
