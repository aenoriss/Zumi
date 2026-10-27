"""Quick test of the band fill from docs/research/disocclusion-shadow-fill-2026-10.md: behind each card only a band as
wide as a head move uncovers is changed, filled by OpenCV's Telea inpaint (from pixels outside the cards) and darkened
by a shadow ramp (0 at the outline, a at full depth), the original art kept everywhere else. Compared with the FLUX
plate the pipeline uses now, on a simulated lean: every card slid against the backdrop by its parallax at a LEAN head
move (2D, no relief), so the strip it uncovers shows.

    uv run python experiments/shadow_fill.py <episode.zumi> <out dir> <sheet path> --panels 9,20,23,24
"""
from __future__ import annotations

import io
import json
import sys
import zipfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw
from scipy.ndimage import binary_dilation, distance_transform_edt

LEAN = 0.2 / 1.5  # head move in units of d (20 cm at 1.5 m)
A_SHADOW, A_LIGHT = 0.35, 0.15  # shadow strength; on light backgrounds (mean > 0.85 around the card)
ROW_H = 330


def cards_of(cj: dict, mesh: Path) -> tuple[list[dict], dict]:
    """[{mask (box px), rgba, bbox, z, kind, frame}], backdrop z per frame."""
    w, h = cj["w"], cj["h"]
    back_z = {l["frame"]: l["z"] for l in cj["layers"] if l["kind"] == "backdrop"}
    out = []
    for l in cj["layers"]:
        if l["kind"] == "backdrop":
            continue
        rgba = np.asarray(Image.open(mesh / l["png"]).convert("RGBA"))
        x0, y0, x1, y1 = l["bbox"]
        m = np.zeros((h, w), bool)
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        m[sy0:sy1, sx0:sx1] = rgba[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0, 3] > 127
        zb = back_z.get(l.get("frame"), max(back_z.values()))
        peak = l["z"] * (1 - l.get("relief_amp", 0) * 0.5)  # a card's middle, between its plane and its peak
        f = max(w, h) / (2 * np.tan(np.radians(cj["fov"] / 2)))
        out.append({"mask": m, "rgba": rgba, "bbox": l["bbox"], "kind": l["kind"],
                    "shift": f * LEAN * (1 / peak - 1 / zb)})
    return out, back_z


def band_fill(img: np.ndarray, cards: list[dict], g: np.ndarray) -> np.ndarray:
    """The backdrop: the original, with a band inside each card's outline replaced by Telea's fill darkened by a ramp."""
    foot = np.logical_or.reduce([c["mask"] for c in cards])
    tel = cv2.inpaint(img, (foot * 255).astype(np.uint8), 3, cv2.INPAINT_TELEA).astype(np.float32)
    out = img.astype(np.float32).copy()
    for c in sorted(cards, key=lambda c: c["shift"]):  # far to near: a nearer card's band wins
        S = abs(c["shift"]) + 3
        dist = distance_transform_edt(c["mask"])  # px in from the outline
        band = c["mask"] & (dist <= S)
        if not band.any():
            continue
        ring = binary_dilation(c["mask"], iterations=12) & ~foot & ~g
        light = ring.any() and img[ring].mean() / 255 > 0.85
        a = 0.0 if c["kind"] == "lettering" else (A_LIGHT if light else A_SHADOW)
        ramp = 1 - a * np.clip(dist / (0.8 * S), 0, 1) ** 1.5
        out[band] = tel[band] * ramp[band][:, None]
    return np.clip(out, 0, 255).astype(np.uint8)


LIGHT = (-1.0, -1.0)  # the light's direction in the image (upper left): shadows fall down-right
SH_OFFSET, SH_BLUR = 0.02, 0.012  # shadow offset and penumbra blur, shares of the box's long side
SH_DARK, SH_DARK_LIGHT = 0.45, 0.25  # how much the shadow darkens; on light backgrounds
SH_DESAT = 0.3  # shadows lose this much saturation
SH_EDGE = 6  # px over which the fill fades in from the outline


def push_pull(img: np.ndarray, known: np.ndarray) -> np.ndarray:
    """Every unknown pixel a smooth blend of the known ones around it, any hole size: weighted image pyramid down
    (pyrDown of colour * weight and of weight), filled from the coarsest level back up. No streaks, no texture."""
    levels, c, w = [], img.astype(np.float32) * known[..., None], known.astype(np.float32)
    while min(w.shape) > 4:
        levels.append((c, w))
        c, w = cv2.pyrDown(c), cv2.pyrDown(w)
    fill = c / np.maximum(w, 1e-6)[..., None]
    for c, w in reversed(levels):
        up = cv2.resize(fill, (w.shape[1], w.shape[0]), interpolation=cv2.INTER_LINEAR)
        a = np.clip(w * 4, 0, 1)[..., None]  # where this level knows enough, its own blend; else the coarser fill
        fill = a * (c / np.maximum(w, 1e-6)[..., None]) + (1 - a) * up
    return fill


def shadow_fill(img: np.ndarray, cards: list[dict], g: np.ndarray) -> np.ndarray:
    """The backdrop under every card replaced by a designed shadow: the background's colour around it (push_pull, no
    texture), darkened where the card's silhouette, offset down-right and blurred, falls, slightly desaturated. Fades
    in over SH_EDGE px from the outline. Behind bubbles no shadow, on light backgrounds a lighter one."""
    h, w = img.shape[:2]
    L = max(h, w)
    foot = np.logical_or.reduce([c["mask"] for c in cards])
    base = push_pull(img, ~foot & ~g)
    shade = np.zeros((h, w), np.float32)
    dx, dy = -np.array(LIGHT) / np.hypot(*LIGHT) * SH_OFFSET * L
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    for c in cards:
        if c["kind"] == "lettering":
            continue
        ring = binary_dilation(c["mask"], iterations=12) & ~foot & ~g
        dark = SH_DARK_LIGHT if ring.any() and img[ring].mean() / 255 > 0.85 else SH_DARK
        s = cv2.warpAffine(c["mask"].astype(np.float32), M, (w, h))
        s = cv2.GaussianBlur(s, (0, 0), SH_BLUR * L)
        shade = np.maximum(shade, dark * s)
    grey = base.mean(-1, keepdims=True)
    sh = (base * (1 - SH_DESAT * shade[..., None] / SH_DARK) + grey * SH_DESAT * shade[..., None] / SH_DARK) * (1 - shade[..., None])
    t = np.clip(distance_transform_edt(foot) / SH_EDGE, 0, 1)[..., None]  # 0 at the outline, 1 inside
    out = np.where(foot[..., None], t * sh + (1 - t) * base, img)
    return np.clip(out, 0, 255).astype(np.uint8)


TEX_SIGMA = 2.5   # px: the brush texture is the image minus its blur at this sigma
TEX_REACH = 40    # px from the outline over which the continued texture fades out
RING_PX = 25      # px around a card where the artist's lit and shadow colours are measured


def membrane(img: np.ndarray, known: np.ndarray) -> np.ndarray:
    """The smoothest colour field equal to img on `known` (Laplace's equation, membrane interpolation): solved
    exactly on a coarse grid, then each finer level starts from it and relaxes (Jacobi) with the known pixels fixed,
    so the fill meets the art at the outline without a seam."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.linalg import spsolve
    pyr = [(img.astype(np.float32), known)]
    while max(pyr[-1][1].shape) > 160:
        c, k = pyr[-1]
        kk = cv2.resize(k.astype(np.float32), (k.shape[1] // 2, k.shape[0] // 2), interpolation=cv2.INTER_AREA)
        cc = cv2.resize(c * k[..., None], (k.shape[1] // 2, k.shape[0] // 2), interpolation=cv2.INTER_AREA)
        pyr.append((cc / np.maximum(kk, 1e-6)[..., None], kk > 0.5))
    c, k = pyr[-1]
    h, w = k.shape
    idx = -np.ones((h, w), int)
    unk = np.argwhere(~k)
    idx[~k] = np.arange(len(unk))
    rows, cols, vals, rhs = [], [], [], np.zeros((len(unk), 3))
    for n, (y, x) in enumerate(unk):
        nb = [(y + dy, x + dx) for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)) if 0 <= y + dy < h and 0 <= x + dx < w]
        rows.append(n); cols.append(n); vals.append(len(nb))
        for yy, xx in nb:
            if k[yy, xx]:
                rhs[n] += c[yy, xx]
            else:
                rows.append(n); cols.append(idx[yy, xx]); vals.append(-1)
    fill = c.copy()
    if len(unk):
        A = coo_matrix((vals, (rows, cols)), shape=(len(unk), len(unk))).tocsr()
        fill[~k] = np.stack([spsolve(A, rhs[:, ch]) for ch in range(3)], -1)
    for c, k in reversed(pyr[:-1]):
        f = cv2.resize(fill, (k.shape[1], k.shape[0]), interpolation=cv2.INTER_LINEAR)
        f[k] = c[k]
        for _ in range(40):
            avg = cv2.blur(f, (3, 3))
            f = np.where(k[..., None], c, avg)
        fill = f
    return fill


def artist_shadow(img: np.ndarray, ring: np.ndarray) -> np.ndarray:
    """Per channel, how the art darkens in shadow around a card: its darkest 15% over its typical lit colour."""
    px = img[ring].astype(np.float32)
    if len(px) < 200:
        return np.array([0.55, 0.55, 0.62], np.float32)
    lum = px.mean(-1)
    lit = np.median(px[lum >= np.percentile(lum, 50)], 0)
    dark = px[lum <= np.percentile(lum, 15)].mean(0)
    r = np.clip(dark / np.maximum(lit, 1), 0.2, 1.0)
    if r.mean() > 0.8:  # a flat surround: no shading to learn from, a plain cool shadow
        r = np.array([0.55, 0.55, 0.62], np.float32)
    return r


def blended_shadow(img: np.ndarray, cards: list[dict], g: np.ndarray) -> np.ndarray:
    """shadow_fill done to blend in: the membrane fill of the surrounding colour, the surrounding brush texture
    continued over TEX_REACH px, and the shadow (the card's silhouette offset down-right, blurred) in the art's own
    shadow colours (artist_shadow), not a grey multiply."""
    h, w = img.shape[:2]
    L = max(h, w)
    foot = np.logical_or.reduce([c["mask"] for c in cards])
    known = ~foot & ~g
    base = membrane(img, known)
    f = img.astype(np.float32)
    hp = f - cv2.GaussianBlur(f, (0, 0), TEX_SIGMA)
    from scipy.ndimage import distance_transform_edt as edt
    dist, (iy, ix) = edt(~known, return_indices=True)
    Y, X = np.indices(known.shape)
    ry, rx = np.clip(2 * iy - Y, 0, h - 1), np.clip(2 * ix - X, 0, w - 1)
    tex = np.where(known[ry, rx][..., None], hp[ry, rx], 0)
    base = base + tex * np.clip(1 - dist / TEX_REACH, 0, 1)[..., None]
    dx, dy = -np.array(LIGHT) / np.hypot(*LIGHT) * SH_OFFSET * L
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    factor = np.ones((h, w, 3), np.float32)
    for c in cards:
        if c["kind"] == "lettering":
            continue
        ring = binary_dilation(c["mask"], iterations=RING_PX) & known
        r = artist_shadow(img, ring)
        light_bg = ring.any() and img[ring].mean() / 255 > 0.85
        s = cv2.GaussianBlur(cv2.warpAffine(c["mask"].astype(np.float32), M, (w, h)), (0, 0), SH_BLUR * L)
        s *= 0.6 if light_bg else 1.0
        factor = np.minimum(factor, 1 - s[..., None] * (1 - r))
    sh = base * factor
    t = np.clip(edt(foot) / SH_EDGE, 0, 1)[..., None]
    out = np.where(foot[..., None], t * sh + (1 - t) * base, img)
    return np.clip(out, 0, 255).astype(np.uint8)


def lean(back: np.ndarray, cards: list[dict]) -> np.ndarray:
    """2D lean: each card slid sideways by its parallax over the backdrop, far to near."""
    can = Image.fromarray(back).convert("RGBA")
    for c in sorted(cards, key=lambda c: c["shift"]):
        x0, y0 = c["bbox"][:2]
        can.alpha_composite(Image.fromarray(c["rgba"]), (int(round(x0 - c["shift"])), int(y0))) if x0 - c["shift"] >= 0 else \
            can.paste(Image.fromarray(c["rgba"]), (int(round(x0 - c["shift"])), int(y0)), Image.fromarray(c["rgba"]))
    return np.asarray(can.convert("RGB"))


def main():
    zumi, out, sheet = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    picks = [int(v) for v in sys.argv[sys.argv.index("--panels") + 1].split(",")]
    z = zipfile.ZipFile(zumi)
    panels = json.loads(z.read("manifest.json"))["panels"]
    mesh, plates = out / "parallax" / "mesh", out / "parallax" / "plates"
    rows = []
    for i in picks:
        pid = f"{zumi.stem}-p{i:03d}"
        img = np.asarray(Image.open(io.BytesIO(z.read(panels[i]["layers"][0]["image"]))).convert("RGB"))
        cj = json.loads((mesh / f"{pid}.cards.json").read_text())
        cards, _ = cards_of(cj, mesh)
        g = (img.min(-1) > 245)  # the white page around the frames, only to keep it out of the light test
        kind = "all" if (plates / pid / "plate-all.png").exists() else "full"
        plate = np.asarray(Image.open(plates / pid / f"plate-{kind}.png").convert("RGB").resize(img.shape[1::-1]))
        foot = binary_dilation(np.logical_or.reduce([c["mask"] for c in cards]), iterations=2)
        flux = np.where(foot[..., None], plate, img)
        ours = band_fill(img, cards, g)
        shifts = [round(c["shift"]) for c in cards]
        cols = [(img, "source"), (lean(flux, cards), "lean 20 cm, FLUX plate (now)"),
                (lean(ours, cards), "lean 20 cm, Telea band + shadow"), (ours, "new backdrop (cards off)")]
        r = Image.fromarray(np.concatenate([c for c, _ in cols], 1))
        s = ROW_H / r.height
        r = r.resize((round(r.width * s), ROW_H))
        d = ImageDraw.Draw(r)
        for k, (c, t) in enumerate(cols):
            x = round(k * c.shape[1] * s)
            d.rectangle([x, 0, x + 260, 13], fill=(0, 0, 0))
            d.text((x + 3, 1), f"p{i:03d} {t}" if k == 0 else t, fill=(255, 255, 255))
        rows.append(r)
        print(f"p{i:03d}: {len(cards)} cards, shifts {min(shifts)}..{max(shifts)} px")
    W = max(r.width for r in rows)
    sh = Image.new("RGB", (W, len(rows) * (ROW_H + 6)), (20, 20, 20))
    for j, r in enumerate(rows):
        sh.paste(r, (0, j * (ROW_H + 6)))
    sheet.parent.mkdir(parents=True, exist_ok=True)
    sh.save(sheet)
    print(sheet)


if __name__ == "__main__":
    main()
