"""Step 4: depth for one box, as the point cloud and mesh grid step 5 (experiments/hidden_layers.py) builds on.

precise_depth (depth.py: tiled DA3MONO, its shift from DA3METRIC, flying pixels filled) at full resolution, back-
projected with a 55 deg field of view on the long side (an assumption: comics have no camera). The page (gutter) may
be white, grey or black (gutter, page_colour). A box of several drawn frames (frames.py) gets its depth scale and
shift, border settling and floater merging per frame (depth_per_frame); the back-projection stays one camera for the
whole box. Writes, under root:

  cloud2/<id>.bin + .json   one point per pixel: float32 xyz, uint8 rgb, uint8 label
                            (0 character, 1 lettering, 2 gutter, 3 scene)
  mesh/<id>.png             the box image (the mesh texture)
  mesh/<id>.f32 + .json     depth every STRIDE px (0 = gutter, no surface); the viewer cuts a cell where its corner
                            depths differ by more than JUMP
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

import depth as DP

FOV = 55.0
STRIDE = 2
JUMP = 1.03
FRINGE_PX = 12    # px outside a character mask searched for its missed fringe (claim_fringe)
BORDER_BAND = 14  # px along the art's outer edge where the depth model's edge brightening is replaced (settle_border)
APT_RATIO = 1.5   # DA3METRIC far/near (2nd-98th percentile over the art) that marks a frame as having real depth: 1.77-2.10
                  # on boxes with a floor and perspective (ToG 228 p6, p64, TB4 p25), 1.10-1.24 on close-ups (p7, p10,
                  # TB4 p35). Logged only: every frame gets layers (layered_depth)
STEP = 0.08       # layers: each card this share of the backdrop's depth nearer than the one behind it. The depth model only
MAX_STEPS = 4     # orders the cards (user, 2026-10-25): its gaps are noise on close-ups; at most 4 steps (32%) in front
TIE = 0.03        # layers: cards whose median metric depths are within this share of each other share a step
SEG_MIN = 0.005   # layers: segments under this share of the frame stay on the backdrop


PAGE_TOL = 4.0     # CIELAB distance (L 0..100) from the page colour that still counts as page: a flat digital page
                   # varies by under 0.5 (ToG 223 grey 214 +- 1)
PAGE_BORDER = 0.6  # share of the box's border pixels the page colour must hold ...
PAGE_CUT = 0.8     # ... or of each of its top and bottom rows (a box is cut from the strip at page gutters; a bubble
                   # touching the cut leaves 0.90-0.95 page in those rows, ToG 223 p94, p98)


def _lab(img: Image.Image) -> np.ndarray:
    import cv2
    return cv2.cvtColor(np.asarray(img.convert("RGB")).astype(np.float32) / 255, cv2.COLOR_RGB2LAB)


def page_colour(img: Image.Image) -> np.ndarray | None:
    """The page's CIELAB colour when it is not white (light grey ToG 223, black), else None (white or no uniform
    page). Candidates: the most common colour (2-unit Lab bins) of the whole border, and of the top and bottom rows;
    a candidate is the page when it holds PAGE_BORDER of the border or PAGE_CUT of each of the two cut rows, within
    PAGE_TOL. White (min channel >= 245) is left to depth.non_art, so white pages keep today's gutter exactly."""
    lab = _lab(img)
    rgb = np.asarray(img.convert("RGB"))
    border = np.concatenate([lab[0], lab[-1], lab[1:-1, 0], lab[1:-1, -1]])
    cut = np.concatenate([lab[0], lab[-1]])
    for src in (border, cut):
        vals, cnt = np.unique(np.round(src / 2), axis=0, return_counts=True)
        c = vals[cnt.argmax()] * 2
        near = np.linalg.norm(src - c, axis=-1) <= PAGE_TOL
        c = np.median(src[near], axis=0)  # the bin's centre refined to the page's own colour
        share = lambda px: float((np.linalg.norm(px - c, axis=-1) <= PAGE_TOL).mean())
        if share(border) >= PAGE_BORDER or (share(lab[0]) >= PAGE_CUT and share(lab[-1]) >= PAGE_CUT):
            edge = np.concatenate([rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]])
            on = np.linalg.norm(border - c, axis=-1) <= PAGE_TOL
            if np.median(edge[on], axis=0).min() >= 245:
                return None
            return c.astype(np.float32)
    return None


def gutter(img: Image.Image, letters: np.ndarray | None = None, white_share: float = 0.98) -> np.ndarray:
    """The page around the art: depth.non_art (white reaching the box's edge; without its brightened-border band,
    the border is art and keeps its surface), plus every row or column that is page apart from lettering. A caption
    box half in the gutter (ToG 228 p6) is not white, so non_art alone kept its gutter half as art: a floating box in
    the mesh, and an erase mask that had FLUX Erase paint floor tiles into the page.
    A page of another colour (page_colour: light grey ToG 223, black) is added the same way: pixels within PAGE_TOL
    of it connected to the box's edge, grown 4 px like non_art's white; and those pixels count as page in the row and
    column rule. White pages give exactly the old gutter.
    Speech bubbles are white and often touch the box edge, so the white flood took whole bubbles over the art as page:
    never erased, cut out of the mesh as holes behind the redrawn bubble (91% of ToG 228 p10's lettering). The page is
    found without them, then each bubble pixel takes the class of the nearest pixel outside the bubbles: a bubble on
    the art is art, a bubble on the page is page, one hanging off the art onto the page is split where it crosses."""
    from scipy.ndimage import binary_dilation, distance_transform_edt, label
    bub = binary_dilation(letters, iterations=3) if letters is not None and letters.any() else None
    g = DP.non_art(img, border=0.0, exclude=bub)
    page = None
    pc = page_colour(img)
    if pc is not None:
        page = np.linalg.norm(_lab(img) - pc, axis=-1) <= PAGE_TOL
        lab, _ = label(page & ~bub if bub is not None else page)
        ids = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
        g = g | binary_dilation(np.isin(lab, ids[ids > 0]), iterations=4)
    if bub is None:
        return g
    if not bub.all():
        _, (iy, ix) = distance_transform_edt(bub, return_indices=True)
        g = np.where(bub, g[iy, ix], g)
    else:  # the box is all lettering: page
        g = np.ones_like(g)
    white = np.asarray(img.convert("RGB")).min(axis=2) >= 245
    if page is not None:
        white = white | page
    # lettering grown 3 px: the box's outline sits just outside its mask (gutter rows read 0.975 white without it, 1.0
    # with it)
    art = ~binary_dilation(letters, iterations=3)
    rows = ((white & art).sum(1) >= white_share * art.sum(1)) & (art.sum(1) > 0)
    cols = ((white & art).sum(0) >= white_share * art.sum(0)) & (art.sum(0) > 0)
    return g | rows[:, None] | cols[None, :]


def settle_border(D: np.ndarray, g: np.ndarray, band: int) -> np.ndarray:
    """The depth model brightens (pulls near) a thin band along every panel edge (depth.non_art), which drew a false
    depth jump along the frame: a mesh cut and a "revealed" strip of over 100 px on ToG 228 p6's top border. Inside
    `band` px of the art's outer edge (the box edge or the gutter) each pixel takes the depth of the nearest pixel just
    inside the band, so the surface runs flat to the frame."""
    from scipy.ndimage import distance_transform_edt
    art = ~g
    edge = np.zeros_like(art)
    edge[0, :], edge[-1, :], edge[:, 0], edge[:, -1] = True, True, True, True
    dist = distance_transform_edt(art & ~edge)  # px to the nearest gutter or box edge
    inner = art & (dist > band)
    if not inner.any():
        return D
    _, (iy, ix) = distance_transform_edt(~inner, return_indices=True)
    rim = art & ~inner
    out = D.copy()
    out[rim] = D[iy[rim], ix[rim]]
    return out


def merge_floaters(D: np.ndarray, art: np.ndarray, min_px: int = 1000) -> tuple[np.ndarray, int]:
    """Floaters: groups of pixels connected to nothing around them in depth. Connected components on the pixel grid
    (8 neighbours, joined where depths differ by at most JUMP, the mesh's own cut rule; scipy csgraph, ~0.15 s for
    1.4 M pixels); every component under min_px takes the depth of the nearest pixel of a larger one, so it joins a
    surface instead of hanging in the air, and no hole opens. Returns (depth, pixels merged)."""
    from scipy.ndimage import distance_transform_edt
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    h, w = D.shape
    idx = np.arange(h * w).reshape(h, w)
    rows, cols = [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ys, ye = 0, h - dy
        xs, xe = max(0, -dx), w - max(0, dx)
        a, b = D[ys:ye, xs:xe], D[ys + dy:ye + dy, xs + dx:xe + dx]
        ok = art[ys:ye, xs:xe] & art[ys + dy:ye + dy, xs + dx:xe + dx] & (np.maximum(a, b) / np.minimum(a, b) <= JUMP)
        rows.append(idx[ys:ye, xs:xe][ok])
        cols.append(idx[ys + dy:ye + dy, xs + dx:xe + dx][ok])
    r, c = np.concatenate(rows), np.concatenate(cols)
    _, lab = connected_components(coo_matrix((np.ones(len(r), np.uint8), (r, c)), shape=(h * w, h * w)), directed=False)
    lab = lab.reshape(h, w)
    sizes = np.bincount(lab[art], minlength=lab.max() + 1)
    small = art & (sizes[lab] < min_px)
    big = art & ~small
    if not small.any() or not big.any():
        return D, 0
    _, (iy, ix) = distance_transform_edt(~big, return_indices=True)
    out = D.copy()
    out[small] = D[iy[small], ix[small]]
    return out, int(small.sum())


def merge_coplanar(D: np.ndarray, art: np.ndarray, min_px: int = 3000, agree: float = 0.03, flat: float = 0.012,
                   fov: float = FOV) -> tuple[np.ndarray, int]:
    """One wall, one surface: the depth model splits a wall into pieces at different depths (window panes, a pillar),
    and the mesh cut them apart (pin 261025-190411). Surfaces (grid components joined within JUMP, as merge_floaters)
    of at least min_px get a least-squares plane in 3D; two neighbours whose planes predict each other's depth within
    `agree` along their shared border are one surface; each merged group that is itself flat (median residual under
    `flat` of its depth) is replaced by its plane, so no jump remains inside it. Curved and small surfaces are left
    alone. Returns (depth, pixels replaced)."""
    from scipy.ndimage import binary_dilation, find_objects
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    h, w = D.shape
    f = max(w, h) / (2 * np.tan(np.radians(fov) / 2))
    idx = np.arange(h * w).reshape(h, w)
    rows, cols = [], []
    for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1)):
        ys, ye, xs, xe = 0, h - dy, max(0, -dx), w - max(0, dx)
        a, b = D[ys:ye, xs:xe], D[ys + dy:ye + dy, xs + dx:xe + dx]
        ok = art[ys:ye, xs:xe] & art[ys + dy:ye + dy, xs + dx:xe + dx] & (np.maximum(a, b) / np.minimum(a, b) <= JUMP)
        rows.append(idx[ys:ye, xs:xe][ok]); cols.append(idx[ys + dy:ye + dy, xs + dx:xe + dx][ok])
    r, c = np.concatenate(rows), np.concatenate(cols)
    _, lab = connected_components(coo_matrix((np.ones(len(r), np.uint8), (r, c)), shape=(h * w, h * w)), directed=False)
    lab = np.where(art, lab.reshape(h, w) + 1, 0)
    sizes = np.bincount(lab.ravel())
    big = [i for i in range(1, len(sizes)) if sizes[i] >= min_px]
    if len(big) < 2:
        return D, 0
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    rx, ry = (u - w / 2) / f, -(v - h / 2) / f  # X = D*rx, Y = D*ry, Z = -D
    # plane in inverse depth: 1/D = a*rx + b*ry + c holds exactly for any 3D plane seen through a pinhole
    def fit(mask):
        sel = np.flatnonzero(mask.ravel())[:: max(1, int(mask.sum()) // 20000)]
        A = np.stack([rx.ravel()[sel], ry.ravel()[sel], np.ones(len(sel))], 1)
        y = 1.0 / D.ravel()[sel]
        p, *_ = np.linalg.lstsq(A, y, rcond=None)
        return p
    pred = lambda p, m: 1.0 / np.maximum(p[0] * rx[m] + p[1] * ry[m] + p[2], 1e-6)
    planes = {i: fit(lab == i) for i in big}
    parent = {i: i for i in big}
    find = lambda i: i if parent[i] == i else find(parent[i])
    slices = find_objects(lab)
    for i in big:
        sl = tuple(slice(max(0, s.start - 3), s.stop + 3) for s in slices[i - 1])
        ring = binary_dilation(lab[sl] == i, iterations=3) & (lab[sl] != i)
        for j in set(np.unique(lab[sl][ring])) & set(big):
            if j <= i:
                continue
            mi = np.zeros_like(art); mi[sl] = ring & (lab[sl] == j)  # j's pixels along the shared border
            mj = np.zeros_like(art); mj[sl] = binary_dilation(lab[sl] == j, iterations=3) & (lab[sl] == i)
            if mi.sum() < 20 or mj.sum() < 20:
                continue
            ei = np.median(np.abs(pred(planes[i], mi) - D[mi]) / D[mi])  # i's plane where j is
            ej = np.median(np.abs(pred(planes[j], mj) - D[mj]) / D[mj])
            if ei < agree and ej < agree:
                parent[find(j)] = find(i)
    groups = {}
    for i in big:
        groups.setdefault(find(i), []).append(i)
    out, replaced = D.copy(), 0
    for g in groups.values():
        if len(g) < 2:
            continue
        m = np.isin(lab, g)
        p = fit(m)
        res = np.median(np.abs(pred(p, m) - D[m]) / D[m])
        if res < flat:
            out[m] = pred(p, m).astype(np.float32)
            replaced += int(m.sum())
    return out, replaced


def claim_fringe(img, chars: np.ndarray, g: np.ndarray, reach: int = FRINGE_PX) -> np.ndarray:
    """The character's fringe the mask missed: hair strands, a robe's edge or hem. Within `reach` px outside the mask,
    a pixel whose colour (CIELAB) is closer to the nearest character pixel than to the nearest clear background pixel
    belongs to the character. Left out, those pixels took the floor's depth with the character's colour, and showed as
    a spray of green and white specks behind him from the side (pin 261025-182210: 5973 px on ToG 228 p6)."""
    import cv2
    from scipy.ndimage import binary_dilation, distance_transform_edt
    if not chars.any():
        return np.zeros_like(chars)
    a = cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2LAB).astype(np.float32)
    near = binary_dilation(chars, iterations=reach)
    ring = near & ~chars & ~g
    clear = ~near & ~g
    if not clear.any():
        return np.zeros_like(chars)
    _, (iy, ix) = distance_transform_edt(~chars, return_indices=True)
    _, (by, bx) = distance_transform_edt(~clear, return_indices=True)
    to_char = np.linalg.norm(a - a[iy, ix], axis=-1)
    to_bg = np.linalg.norm(a - a[by, bx], axis=-1)
    return ring & (to_char < to_bg)


def apt(M: np.ndarray, area: np.ndarray) -> tuple[bool, float]:
    """Whether a frame suits model depth: DA3METRIC sees real depth in it (far/near at least APT_RATIO). A close-up has
    no floor, no perspective and flat cel shading; the metric model then sees a flat card (far/near 1.1-1.2)."""
    z = M[area]
    if z.size < 1000:
        return False, 1.0
    lo, hi = np.percentile(z, [2, 98])
    ratio = float(hi / max(lo, 1e-6))
    return ratio >= APT_RATIO, round(ratio, 2)


def layered_depth(D: np.ndarray, M: np.ndarray, segs: np.ndarray, area: np.ndarray) -> np.ndarray:
    """Parallax from segmentation: the backdrop a plane facing the camera at the metric depth of what no mask covers,
    each character and object (connected parts of `segs`) a flat card in front of it. The metric depth only orders
    the cards (median inside each): the farthest card one STEP in front of the backdrop, each nearer one a STEP more,
    at most MAX_STEPS; cards within TIE of each other share a step. Nearer cards are written last, so they win
    where masks overlap."""
    from scipy.ndimage import label
    if area.sum() < 1000:  # no art to stage (a box that is only a bubble on the page, ToG 223 p94)
        return D
    segs = segs & area
    back = area & ~segs
    zb = float(np.median(M[back])) if back.sum() > 500 else float(np.percentile(M[area], 75))
    out = np.where(area, np.float32(zb), D)
    from scipy.ndimage import find_objects
    lab, n = label(segs)
    size = np.bincount(lab.ravel(), minlength=n + 1)
    boxes = find_objects(lab)
    cards = []
    for k in np.flatnonzero(size >= SEG_MIN * area.sum()):  # only the big parts: a mask breaks into thousands of crumbs
        if k == 0:
            continue
        sl = boxes[k - 1]
        s = lab[sl] == k
        cards.append((float(np.median(M[sl][s])), sl, s))
    cards.sort(key=lambda c: -c[0])  # far to near
    step, prev = 0, None
    for med, sl, s in cards:
        if prev is None or med < prev * (1 - TIE):
            step, prev = min(step + 1, MAX_STEPS), med
        out[sl][s] = zb * (1 - STEP * step)
    return out.astype(np.float32)


def depth_per_frame(mono, metric, img: Image.Image, frames: list[np.ndarray]) -> tuple[np.ndarray, dict]:
    """depth.precise_depth for a box of several drawn frames (frames.frames): the models see the whole box (DA3MONO
    tiled and aligned, DA3METRIC for the shift), but mono = s * metric + t is fitted per frame on that frame's
    non-flying pixels, since each frame has its own scene and camera: one fit across them left whichever frame the
    robust fit discounted at a wrong scale and shift. Every pixel outside the frames (the gutter) takes its nearest
    frame's fit, so the 3 px median and fill_flying below never meet a jump that is not in the art."""
    import cv2
    import time
    from scipy.ndimage import distance_transform_edt
    t0 = time.perf_counter()
    m, seams = DP.tiled_depth(mono, img, align=True)
    M, _ = DP.tiled_depth(metric, img, align=False)
    ratio = cv2.dilate(m, np.ones((3, 3), np.uint8)) / np.maximum(cv2.erode(m, np.ones((3, 3), np.uint8)), 1e-6)
    fly = ratio > DP.FLY_RATIO
    lab = np.zeros(m.shape, np.int32)
    for k, f in enumerate(frames, 1):
        lab[f] = k
    _, (iy, ix) = distance_transform_edt(lab == 0, return_indices=True)
    near = lab[iy, ix]
    D = m.astype(np.float32).copy()
    fits = []
    for k in range(1, len(frames) + 1):
        own = lab == k
        use = own & ~fly
        if use.sum() < 1000:
            use = own
        sub = np.flatnonzero(use.ravel())[:: max(1, int(use.sum()) // 60000)]
        s, t = DP._robust_fit(M.ravel()[sub].astype(np.float64), m.ravel()[sub].astype(np.float64))
        sel = near == k
        Dk = ((m[sel] - t) / s).astype(np.float32) if s > 1e-9 else M[sel].astype(np.float32)
        lo = float(np.percentile(Dk, 0.5))
        D[sel] = np.maximum(Dk, lo * 0.5 if lo > 0 else 1e-3)
        fits.append((round(float(s), 4), round(float(t), 4)))
    Ds = DP.fill_flying(cv2.medianBlur(D, 3), ~fly, np.asarray(img.convert("RGB")))
    stats = {"seams": [round(x_, 4) for x_ in seams], "fits": fits, "flying_share": round(float(fly.mean()), 4),
             "secs": round(time.perf_counter() - t0, 2), "metric": M}
    return Ds.astype(np.float32), stats


def build(pid: str, img: Image.Image, chars: np.ndarray, letters: np.ndarray, mono, metric, root: Path,
          g: np.ndarray | None = None, fringe_in: np.ndarray | None = None, objects: np.ndarray | None = None) -> dict:
    """img: normally the lettering-free base image (hidden_layers.finish), so lettering never gets depth; then
    `letters` is empty and the gutter `g` comes from the original box, where captions crossing it are still visible.
    fringe_in: the fringe already claimed into `chars` (hidden_layers.prepare); claimed here when None."""
    w, h = img.size
    g = gutter(img, letters) if g is None else g
    # new depth invalidates whatever step 5 exported for this box before (a box that now erases nothing would show
    # the old hidden layer and figure surface)
    for pat in (f"mesh/{pid}.bg*", f"mesh/{pid}.fig.*", f"mesh/{pid}.fgclean.*", f"mesh/{pid}.seg.u8",
                f"mesh/{pid}.layers.json", f"cloud3/{pid}.*"):
        for old in root.glob(pat):
            old.unlink()
    import frames as FR
    fr = FR.frames(img, g)
    if len(fr) > 1:  # several drawn frames: each its own scene, fitted and cleaned on its own (depth_per_frame)
        D, st = depth_per_frame(mono, metric, img, fr)
        floaters = 0
        for f in fr:
            ys, xs = np.nonzero(f)
            pad = BORDER_BAND + 2
            sl = (slice(max(0, ys.min() - pad), ys.max() + 1 + pad), slice(max(0, xs.min() - pad), xs.max() + 1 + pad))
            fk = f[sl]
            Dk = settle_border(D[sl], ~fk, BORDER_BAND)
            Dk, n = merge_floaters(Dk, fk)
            D[sl] = np.where(fk, Dk, D[sl])
            floaters += n
        areas = fr
    else:
        D, valid, st = DP.precise_depth(mono, metric, img, ignore=g)
        D = settle_border(D, g, BORDER_BAND)
        D, floaters = merge_floaters(D, ~g)
        areas = [~g]
    # every frame as segmented layers, the depth model only placing them (user, 2026-10-25): its own surfaces were
    # right on boxes with a floor and perspective (ToG 228 p6) and a ramp with no figure in it on close-ups (p10)
    segs = chars if objects is None else chars | objects
    judged = [apt(st["metric"], f) for f in areas]  # kept in the log: how much depth DA3METRIC saw in each frame
    layered = list(range(len(areas)))
    for k in layered:
        D = layered_depth(D, st["metric"], segs, areas[k])
    fringe = claim_fringe(img, chars, g) if fringe_in is None else fringe_in
    coplanar = 0  # merge_coplanar (below) is not run: on ToG 228 p6 the wall is already one pixel-connected surface,
                  # its splits are local steps inside it that look exactly like the desk standing in front of it
    if fringe.any():  # the fringe takes its character's depth: the nearest character pixel's
        from scipy.ndimage import distance_transform_edt
        core = chars & ~fringe
        _, (iy, ix) = distance_transform_edt(~core, return_indices=True)
        D = np.where(fringe, D[iy, ix], D)
        chars = chars | fringe
    f = max(w, h) / (2 * np.tan(np.radians(FOV) / 2))
    v, u = np.mgrid[0:h, 0:w].astype(np.float32)
    P = np.stack([(u - w / 2) * D / f, -(v - h / 2) * D / f, -D], -1).astype(np.float32)
    L = np.full((h, w), 3, np.uint8)
    L[letters] = 1
    L[chars] = 0
    L[g] = 2
    rgb = np.asarray(img.convert("RGB"))
    for d in ("cloud2", "mesh"):
        (root / d).mkdir(parents=True, exist_ok=True)
    with open(root / "cloud2" / f"{pid}.bin", "wb") as fh:
        fh.write(P.tobytes()); fh.write(rgb.tobytes()); fh.write(L.tobytes())
    (root / "cloud2" / f"{pid}.json").write_text(json.dumps({"count": w * h, "planes": 0, "objects": 0, "plane_share": [],
                                                            "leftover_share": 0, "stride": 1}))
    gw, gh = (w + STRIDE - 1) // STRIDE, (h + STRIDE - 1) // STRIDE
    G = np.where(g, 0, D)[::STRIDE, ::STRIDE][:gh, :gw].astype(np.float32)
    # one ring of grid points outside the art takes its neighbours' depth: a cell with a corner in the gutter has no
    # triangle, so a ragged 2 px strip was missing along every outer edge of the art (edge_metric holes 0.49%, ToG 228
    # p6); with the ring the outer triangles reach the art's edge
    import cv2
    Gp = cv2.dilate(G, np.ones((3, 3), np.uint8))  # the deepest neighbour (gutter points are 0)
    G = np.where((G == 0) & (Gp > 0), Gp, G).astype(np.float32)
    G.tofile(root / "mesh" / f"{pid}.f32")
    (root / "mesh" / f"{pid}.json").write_text(json.dumps({"w": w, "h": h, "gw": gw, "gh": gh, "stride": STRIDE,
                                                          "fov": FOV, "jump": JUMP}))
    img.convert("RGB").save(root / "mesh" / f"{pid}.png")
    return {"depth_s": st["secs"], "flying": st["flying_share"], "gutter": round(float(g.mean()), 3), "floater_px": floaters,
            "fringe_px": int(fringe.sum()), "coplanar_px": coplanar, "frames": max(1, len(fr)),
            "far_near": [r for _, r in judged], "layered": layered,
            **({"fits": st["fits"]} if "fits" in st else {})}
