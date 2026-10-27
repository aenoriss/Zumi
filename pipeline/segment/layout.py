"""Room layout from a box's 3D points: floor, walls and ceiling as planes (RANSAC), and the big objects standing in
front of them (a table, a chair, a desk), as erase candidates for the hidden layer behind objects.

Depth gaps to neighbours could not find objects (a chair 0.8% nearer than the floor beside it, misread page pieces
8-39%); distance to the room's planes can: a chair seat stands a chair's height off the floor plane. Boxes without a
room (close-ups, abstract or speed-line backgrounds) find no planes and so no objects.

    plane fit   up to MAX_PLANES planes, each with at least MIN_PLANE of the scene points within TOL x depth
    objects     scene pixels nearer than the plane behind them along their ray by more than GAP; connected groups of
                at least MIN_OBJECT of the art ("only big objects"), small specks opened away
"""
from __future__ import annotations

import numpy as np
from scipy.ndimage import binary_dilation, binary_opening, label

MAX_PLANES = 4
MIN_PLANE = 0.08   # share of the scene points
TOL = 0.012        # inlier distance, as a share of the median depth
GAP = 0.04         # an object pixel is at least this much nearer than the plane behind it
MIN_OBJECT = 0.03  # share of the art: only big objects
ITERS = 400


def fit_planes(P, scene, rng=None):
    """[(n, d)] with n·X + d = 0, |n| = 1, from the scene points (P: h x w x 3)."""
    rng = rng or np.random.default_rng(0)
    pts = P[scene][::7].astype(np.float64)
    if len(pts) < 500:
        return []
    tol = TOL * float(np.median(-pts[:, 2]))
    total, planes, left = len(pts), [], pts
    for _ in range(MAX_PLANES):
        if len(left) < MIN_PLANE * total:
            break
        best, best_in = None, None
        for _ in range(ITERS):
            a, b, c = left[rng.choice(len(left), 3, replace=False)]
            n = np.cross(b - a, c - a)
            if np.linalg.norm(n) < 1e-12:
                continue
            n /= np.linalg.norm(n)
            inl = np.abs(left @ n - n @ a) < tol
            if best_in is None or inl.sum() > best_in.sum():
                best, best_in = (n, -n @ a), inl
        if best_in is None or best_in.sum() < MIN_PLANE * total:
            break
        q = left[best_in]  # least-squares refit on the inliers
        c = q.mean(0)
        n = np.linalg.svd(q - c)[2][-1]
        planes.append((n, -n @ c))
        left = left[~best_in]
    return planes


def plane_depth(n, d, h, w, f):
    """Depth at which each pixel's viewing ray meets the plane (inf where it does not, in front of the camera)."""
    v, u = np.mgrid[0:h, 0:w].astype(np.float64)
    ray = np.stack([(u - w / 2) / f, -(v - h / 2) / f, -np.ones_like(u)], -1)  # X = depth * ray
    den = ray @ n
    with np.errstate(divide="ignore", invalid="ignore"):
        t = -d / den
    return np.where((t > 0) & np.isfinite(t), t, np.inf)


def objects(P, D, scene, art, fov=55.0):
    """(object mask, planes, plane label per pixel, log). Objects: big connected groups of scene pixels standing in
    front of the plane behind them."""
    h, w = D.shape
    f = max(w, h) / (2 * np.tan(np.radians(fov) / 2))
    planes = fit_planes(P, scene)
    if not planes:
        return np.zeros((h, w), bool), [], np.full((h, w), -1), "no room planes"
    tol = TOL * float(np.median(D[scene]))
    Dp = np.stack([plane_depth(n, d, h, w, f) for n, d in planes])  # k x h x w
    dist = np.stack([np.abs(P.reshape(-1, 3) @ n + d).reshape(h, w) for n, d in planes])
    on = (dist < 2 * tol) & scene
    plane_of = np.where(on.any(0), dist.argmin(0), -1)
    # the plane behind a pixel: the nearest plane surface beyond its depth along its ray
    behind = np.where(Dp > D * (1 + 1e-3), Dp, np.inf).min(0)
    cand = scene & ~on.any(0) & np.isfinite(behind) & (D < behind * (1 - GAP))
    cand = binary_opening(cand, iterations=3)
    lab, k = label(cand)
    sizes = np.bincount(lab.ravel())
    keep = [i for i in range(1, k + 1) if sizes[i] >= MIN_OBJECT * art.sum()]
    mask = np.isin(lab, keep)
    shares = sorted((round(sizes[i] / art.sum() * 100, 1) for i in keep), reverse=True)
    planes_share = [round(float((plane_of == i).sum() / max(1, scene.sum()) * 100), 1) for i in range(len(planes))]
    return (binary_dilation(mask, iterations=6) & art, planes, plane_of,
            f"{len(planes)} planes {planes_share}% of the scene; big objects {shares}% of the art")
