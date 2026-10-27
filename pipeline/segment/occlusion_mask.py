"""Erase mask from depth: besides characters and lettering, every object nearer than what is behind it hides
background that head motion reveals. At each occluding edge (neighbouring depths differ by more than the mesh's cut
ratio) the NEAR side gets a band as wide as the background can slide out from under it for a head shift T:

    band = f * T * (1/D_near - 1/D_far)   pixels, clipped to [MIN_PX, MAX_PX]

(the disocclusion width of a two-depth step; 3D Photo Inpainting, Shih et al. 2020, inpaints the same regions).

    python occlusion_mask.py <panel id> <characters npz> <lettering npz> <out dir> [T]
Writes occlusion_mask.png (white = erase) and occlusion_check.png (magenta: characters/lettering, cyan: depth bands).
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from scipy.ndimage import binary_dilation, binary_erosion, distance_transform_edt

from masks import load_masks

VIEWER = Path(__file__).resolve().parents[1] / ".data" / "out" / "parallax_viewer"
JUMP = 1.03          # the mesh's cut: a depth ratio above this between neighbours is an occluding edge
MIN_PX, MAX_PX = 4, 90  # a depth edge whose band (below) would be narrower than MIN_PX gets none: the background it
                        # hides is never revealed. It used to be widened to 10 px, which erased bands along every small
                        # step of the background (ToG 223 p98)
GROW = 10            # px around characters and lettering: their dark outlines and glow must go with them
MIN_GAP = 0.06       # a whole object sits at least this much nearer than what surrounds it
BORDER_SHARE = 0.10  # a surface running out of frame along more than this share of its outline is background


def depth_bands(D, valid, T, fov=55.0):
    h, w = D.shape
    f = max(w, h) / (2 * np.tan(np.radians(fov) / 2))
    Dp = np.pad(D, 1, mode="edge")
    Vp = np.pad(valid, 1)
    near = np.zeros((h, w), bool)
    width = np.zeros((h, w), np.float32)
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dy == dx == 0:
                continue
            q = Dp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w]  # the neighbour's depth
            e = valid & Vp[1 + dy:1 + dy + h, 1 + dx:1 + dx + w] & (q / D > JUMP)  # this pixel is the near side
            near |= e
            width = np.where(e, np.maximum(width, f * T * (1 / D - 1 / q)), width)
    near &= width >= MIN_PX  # the erased amount follows depth: a small step reveals nothing worth repainting
    width = np.minimum(width, MAX_PX)
    if not near.any():
        return np.zeros((h, w), bool), near
    # every pixel within its nearest edge pixel's band width (measured inward and outward; the erase model only
    # repaints, so a band reaching a little onto the far side costs nothing)
    dist, (iy, ix) = distance_transform_edt(~near, return_indices=True)
    return (dist <= width[iy, ix]) & valid, near


def near_surfaces(D, valid, step=2, min_px=800, max_share=0.2, min_near=0.4):
    """Whole objects: split the depth map into surfaces wherever depth jumps (the mesh's cut, at a 2 px step), then
    keep each surface that is mostly the NEAR side of the edges around it (a table top above the floor, a chair),
    so the erase removes the object itself instead of only a band along its outline. Surfaces whose outline is not
    closed in depth merge with what is behind them and stay with their bands only."""
    from scipy.ndimage import label
    h, w = D.shape
    Dp = np.pad(D, step, mode="edge")
    edge, nearp, farp = (np.zeros((h, w), bool) for _ in range(3))
    for dy in (-step, 0, step):
        for dx in (-step, 0, step):
            if dy == dx == 0:
                continue
            q = Dp[step + dy:step + dy + h, step + dx:step + dx + w]
            nearp |= q / D > JUMP
            farp |= D / q > JUMP
    edge = nearp | farp
    lab, n = label(~binary_dilation(edge, iterations=1) & valid)
    sizes = np.bincount(lab.ravel())
    out = np.zeros((h, w), bool)
    found = []
    frame = np.zeros((h, w), bool)
    frame[:3], frame[-3:], frame[:, :3], frame[:, -3:] = True, True, True, True
    for i in range(1, n + 1):
        if not min_px <= sizes[i] <= max_share * h * w:
            continue
        comp = lab == i
        ring = binary_dilation(comp, iterations=3) & ~comp
        nn, ff = (nearp & ring).sum(), (farp & ring).sum()
        if nn / max(1, nn + ff) <= min_near:
            continue
        # background running out of frame is not an object (a table or a chair sits inside the frame)
        outline = binary_dilation(comp, iterations=1) & ~binary_erosion(comp, iterations=1)
        if (outline & frame).sum() > BORDER_SHARE * outline.sum():
            continue
        # it must stand clearly in front: the median depth of what is behind its outline over its own median depth
        dc = float(np.median(D[comp]))
        behind = ring & valid & (D > dc)
        gap = float(np.median(D[behind])) / dc - 1 if behind.sum() > 50 else 0.0
        if gap < MIN_GAP:
            continue
        out |= comp
        found.append((round(sizes[i] / (h * w) * 100, 1), round(nn / max(1, nn + ff), 2), round(gap, 3)))
    return binary_dilation(out, iterations=8), found


def read_cloud2(pid, root=VIEWER):
    """The panel's precise-depth cloud (one point per pixel, written by parallax.py under root): positions, colours,
    labels and depth, as (h, w) grids."""
    info = json.loads((root / "cloud2" / f"{pid}.json").read_text())
    img = np.asarray(Image.open(root / "mesh" / f"{pid}.png").convert("RGB"))
    h, w = img.shape[:2]
    n = info["count"]
    assert n == w * h, "cloud2 is expected at one point per pixel"
    buf = (root / "cloud2" / f"{pid}.bin").read_bytes()
    P = np.frombuffer(buf, np.float32, n * 3).reshape(h, w, 3)
    C = np.frombuffer(buf, np.uint8, n * 3, n * 12).reshape(h, w, 3)
    L = np.frombuffer(buf, np.uint8, n, n * 15).reshape(h, w)
    return info, img, P, C, L, -P[..., 2].copy()


def build_masks(D, L, chars, letters, T=0.05):
    """(holes, full, parts): holes = characters and lettering grown GROW px (layer 1 erases only these, so the table
    behind a character stays and continues behind him); full = holes + whole near objects + depth bands (layer 2)."""
    holes = binary_dilation(chars | letters, iterations=GROW)
    # edges against characters and lettering are already covered by their own masks; depth bands for the rest
    valid = (L != 2) & ~binary_dilation(holes, iterations=2)
    bands, edges = depth_bands(D, valid, T)
    objects, found = near_surfaces(D, valid)
    return holes, holes | bands | objects, {"bands": bands, "edges": edges, "objects": objects, "found": found}


def check_image(img, holes, parts):
    over = img.astype(np.float32)
    objects, bands = parts["objects"], parts["bands"]
    over[holes] = over[holes] * 0.45 + np.array([255, 0, 160]) * 0.55
    over[objects & ~holes] = over[objects & ~holes] * 0.45 + np.array([0, 255, 120]) * 0.55
    over[bands & ~holes & ~objects] = over[bands & ~holes & ~objects] * 0.45 + np.array([0, 220, 255]) * 0.55
    over[parts["edges"]] = [255, 255, 0]
    return Image.fromarray(over.astype(np.uint8))


def main():
    pid, cpath, lpath, out = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4])
    T = float(sys.argv[5]) if len(sys.argv) > 5 else 0.05
    info, img, P, C, L, D = read_cloud2(pid)
    cm = np.logical_or.reduce([m.mask for m in load_masks(cpath)])
    lm = np.logical_or.reduce([m.mask for m in load_masks(lpath)])
    holes, mask, parts = build_masks(D, L, cm, lm, T)
    Image.fromarray(holes.astype(np.uint8) * 255).save(out / "holes_mask.png")
    Image.fromarray(mask.astype(np.uint8) * 255).save(out / "occlusion_mask.png")
    check_image(img, holes, parts).save(out / "occlusion_check.png")
    objects, bands = parts["objects"], parts["bands"]
    print(f"T={T}: characters+lettering {holes.mean() * 100:.1f}%, whole objects +{(objects & ~holes).mean() * 100:.1f}% "
          f"{parts['found']} (share %, near-side score), depth bands +{(bands & ~holes & ~objects).mean() * 100:.1f}%, "
          f"total {mask.mean() * 100:.1f}% of the panel")


if __name__ == "__main__":
    main()
