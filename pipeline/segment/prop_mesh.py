"""The props' GLB work, no network: reading a TRELLIS GLB, an unlit picture of it, the checks on its shape, and its
colour brought back to the object it was made from (props.py's finish).

TRELLIS's texture bake shifts the colours toward yellow, and most of its texture sheet is surfaces no viewer sees
(insides, undersides, seams). So colour is corrected last, against the cutout from the place's view, measured only
on the texels an unlit render from four sides reaches: lightness takes the cutout's whole distribution, and a and b
take the cutout's value at the same lightness rank, so highlights get the cutout's highlight hue and shadows its
shadow hue. TRELLIS's GLBs state no metalness, which viewers read as metal: the finished material is non-metal and
fully rough, as a painting is.

    on_plate(glb) -> (is a plate, ratio)       a ground slab TRELLIS added under the object
    finish(glb, cutout) -> (glb, pieces dropped) small floating pieces removed, then the texture brought to the
                                                cutout's colours, non-metal
    to_lab(rgb) -> lab                          sRGB to CIE Lab
"""
from __future__ import annotations

import io
import json
import struct

import numpy as np
from PIL import Image
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

SHARE = 0.1      # a loose piece under this share of the largest piece's surface is dropped (a quad between a stool's
                 # legs, 2026-11-10)
PLATE_LOW = 0.04 # the plate check's bottom slab: the lowest 4 % of the height
PLATE = 1.15     # a slab reaching this much farther out than anything above it is a plate
YAWS = (0, 90, 180, 270)  # the sides retex sees the model from, 30 degrees above
SEEN_SIDE = 384  # px of those renders, as validated 2026-11-10


def _split(glb: bytes) -> tuple[dict, bytes]:
    n = struct.unpack_from("<I", glb, 12)[0]
    return json.loads(glb[20:20 + n]), glb[20 + n + 8:]


def _pack(j: dict, binc: bytes) -> bytes:
    s = json.dumps(j, separators=(",", ":")).encode()
    s += b" " * (-len(s) % 4)
    return (struct.pack("<III", 0x46546C67, 2, 28 + len(s) + len(binc)) + struct.pack("<II", len(s), 0x4E4F534A) + s
            + struct.pack("<II", len(binc), 0x004E4942) + bytes(binc))


def to_lab(rgb: np.ndarray) -> np.ndarray:
    """sRGB (0-255, any shape ending in 3) to CIE Lab, D65."""
    c = rgb.astype(np.float64) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    xyz = c @ np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]]) / np.array([0.9505, 1.0, 1.089])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def _to_rgb(lab: np.ndarray) -> np.ndarray:
    fy = (lab[..., 0] + 16) / 116
    f = np.stack([fy + lab[..., 1] / 500, fy, fy - lab[..., 2] / 200], -1)
    xyz = np.where(f > 0.2069, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.9505, 1.0, 1.089])
    c = xyz @ np.linalg.inv(np.array([[0.4124, 0.2126, 0.0193], [0.3576, 0.7152, 0.1192], [0.1805, 0.0722, 0.9505]]))
    c = np.clip(c, 0, 1)
    return np.round(255 * np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)).astype(np.uint8)


def _load(glb: bytes):
    """(positions, uvs, faces, texture): the GLB's one mesh primitive and its base-colour image."""
    j, binc = _split(glb)

    def acc(i):
        a = j["accessors"][i]
        bv = j["bufferViews"][a["bufferView"]]
        dt = {5126: np.float32, 5125: np.uint32, 5123: np.uint16}[a["componentType"]]
        k = {"SCALAR": 1, "VEC2": 2, "VEC3": 3}[a["type"]]
        return np.frombuffer(binc, dt, a["count"] * k, bv.get("byteOffset", 0) + a.get("byteOffset", 0)).reshape(-1, k)

    p = j["meshes"][0]["primitives"][0]
    bv = j["bufferViews"][j["images"][0]["bufferView"]]
    tex = np.asarray(Image.open(io.BytesIO(binc[bv.get("byteOffset", 0):bv.get("byteOffset", 0) + bv["byteLength"]])).convert("RGB"))
    return acc(p["attributes"]["POSITION"]), acc(p["attributes"]["TEXCOORD_0"]), acc(p["indices"]).reshape(-1, 3).astype(np.int64), tex


def _render(glb: bytes, size: int = 512, yaw: float = 0.0, pitch: float = 20.0):
    """(rgb, hit mask, texel index per hit pixel): unlit orthographic, z-buffered, nearest texel; the texture as
    painted, the model centred and filling the picture."""
    P, UV, F, T = _load(glb)
    cy, sy, cp, sp = np.cos(np.radians(yaw)), np.sin(np.radians(yaw)), np.cos(np.radians(pitch)), np.sin(np.radians(pitch))
    R = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]]) @ np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Q = (P - (P.max(0) + P.min(0)) / 2) @ R.T
    s = 0.46 * size / np.abs(Q[:, :2]).max()
    X, Y, Z = size / 2 + Q[:, 0] * s, size / 2 - Q[:, 1] * s, Q[:, 2]
    zb = np.full((size, size), -np.inf)
    uv = np.zeros((size, size, 2))
    for f in F:
        x, y, z = X[f], Y[f], Z[f]
        x0, x1, y0, y1 = int(max(np.floor(x.min()), 0)), int(min(np.ceil(x.max()), size - 1)), int(max(np.floor(y.min()), 0)), int(min(np.ceil(y.max()), size - 1))
        if x1 < x0 or y1 < y0:
            continue
        d = (y[1] - y[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (y[0] - y[2])
        if abs(d) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        a = ((y[1] - y[2]) * (gx - x[2]) + (x[2] - x[1]) * (gy - y[2])) / d
        b = ((y[2] - y[0]) * (gx - x[2]) + (x[0] - x[2]) * (gy - y[2])) / d
        c = 1 - a - b
        zz = a * z[0] + b * z[1] + c * z[2]
        sub = zb[y0:y1 + 1, x0:x1 + 1]
        ok = (a >= 0) & (b >= 0) & (c >= 0) & (zz > sub)
        if ok.any():
            sub[ok] = zz[ok]
            w = np.stack([a, b, c], -1)[ok]
            uv[y0:y1 + 1, x0:x1 + 1][ok] = w @ UV[f]
    hit = np.isfinite(zb)
    h, w_ = T.shape[:2]
    tx = np.clip((uv[..., 0] % 1.0) * w_, 0, w_ - 1).astype(int)
    ty = np.clip((uv[..., 1] % 1.0) * h, 0, h - 1).astype(int)
    img = np.full((size, size, 3), 110, np.uint8)
    img[hit] = T[ty[hit], tx[hit]]
    return img, hit, (ty[hit], tx[hit])


def on_plate(glb: bytes) -> tuple[bool, float]:
    """(stands on a plate, ratio) of a lifted GLB."""
    return _plate(_load(glb)[0])


def finish(glb: bytes, cutout: Image.Image) -> tuple[bytes, int]:
    """(the finished GLB, pieces dropped): a raw GLB's loose pieces dropped, then its texture brought to the
    cutout's colours (RGBA), non-metal."""
    main, dropped = _drop_loose(glb)
    return _retex(main, cutout), dropped


def _plate(P: np.ndarray) -> tuple[bool, float]:
    """A bottom slab (the lowest PLATE_LOW of the height) reaching farther out than anything above it: (is one,
    ratio). TRELLIS sometimes stands the object on a round plate the picture never showed."""
    y = P[:, 1]
    h = y.max() - y.min()
    r = np.hypot(P[:, 0] - np.median(P[:, 0]), P[:, 2] - np.median(P[:, 2]))
    low = y < y.min() + PLATE_LOW * h
    ratio = float(r[low].max() / max(r[~low].max(), 1e-6))
    return ratio > PLATE, round(ratio, 2)


def _drop_loose(glb: bytes) -> tuple[bytes, int]:
    """(the GLB with only its main pieces, how many pieces were dropped). Pieces are the mesh's connected parts once
    vertices at one position are welded; a piece under SHARE of the largest piece's surface is dropped."""
    j, binc = _split(glb)
    binc = bytearray(binc)
    prim = j["meshes"][0]["primitives"][0]

    def view(i):
        a = j["accessors"][i]
        bv = j["bufferViews"][a["bufferView"]]
        return a, bv.get("byteOffset", 0) + a.get("byteOffset", 0)

    pa, po = view(prim["attributes"]["POSITION"])
    P = np.frombuffer(binc, np.float32, pa["count"] * 3, po).reshape(-1, 3)
    ia, io_ = view(prim["indices"])
    dt = {5125: np.uint32, 5123: np.uint16}[ia["componentType"]]
    F = np.frombuffer(binc, dt, ia["count"], io_).reshape(-1, 3).astype(np.int64)
    inv = np.unique(np.round(P, 5), axis=0, return_inverse=True)[1].ravel()
    W = inv[F]
    m = int(inv.max()) + 1
    g = coo_matrix((np.ones(len(W) * 3), (np.r_[W[:, 0], W[:, 1], W[:, 2]], np.r_[W[:, 1], W[:, 2], W[:, 0]])), shape=(m, m))
    k, lab = connected_components(g, directed=False)
    if k == 1:
        return glb, 0
    area = 0.5 * np.linalg.norm(np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]]), axis=1)
    part = lab[W[:, 0]]
    a = np.bincount(part, area, k)
    keep = a >= SHARE * a.max()
    if keep.all():
        return glb, 0
    new = F[keep[part]].astype(dt).ravel()
    binc[io_:io_ + new.nbytes] = new.tobytes()   # shorter than before: the bytes after it are left unused
    ia["count"] = int(new.size)
    return _pack(j, binc), int((~keep).sum())


def _retex(glb: bytes, ref: Image.Image) -> bytes:
    """The GLB with its texture brought to the colours of `ref` (the cutout, RGBA), measured on the texels seen from
    YAWS, and its materials non-metal and fully rough."""
    T = _load(glb)[3]
    seen = np.zeros(T.shape[:2], bool)
    for yaw in YAWS:
        ty, tx = _render(glb, SEEN_SIDE, yaw, 30)[2]
        seen[ty, tx] = True
    r = np.asarray(ref.convert("RGBA"))
    rl = to_lab(r[..., :3][r[..., 3] > 127])
    lab = to_lab(T)
    v = lab[seen]
    qs = np.linspace(0, 1, 257)
    q = np.interp(lab[..., 0], np.quantile(v[:, 0], qs), qs)
    vq = np.interp(v[:, 0], np.quantile(v[:, 0], qs), qs)
    rq = np.interp(rl[:, 0], np.quantile(rl[:, 0], qs), qs)
    lab[..., 0] = np.interp(q, qs, np.quantile(rl[:, 0], qs))
    mid = (np.arange(12) + 0.5) / 12   # a and b matched in 12 lightness bands; the spread around each band's mean
    for k in (1, 2):                   # follows the cutout's too, at most 1.5 times the model's
        sm = np.array([v[:, k][np.abs(vq - m) <= 1 / 12].mean() for m in mid])
        rm = np.array([rl[:, k][np.abs(rq - m) <= 1 / 12].mean() for m in mid])
        gain = min((rl[:, k] - np.interp(rq, mid, rm)).std() / max((v[:, k] - np.interp(vq, mid, sm)).std(), 1e-6), 1.5)
        lab[..., k] = (lab[..., k] - np.interp(q, mid, sm)) * gain + np.interp(q, mid, rm)
    buf = io.BytesIO()
    Image.fromarray(_to_rgb(lab)).save(buf, "PNG")
    png = buf.getvalue() + b"\0" * (-len(buf.getvalue()) % 4)
    j, binc = _split(glb)
    bv = j["bufferViews"][j["images"][0]["bufferView"]]
    off, old = bv.get("byteOffset", 0), bv["byteLength"] + (-bv["byteLength"] % 4)
    for b in j["bufferViews"]:
        if b.get("byteOffset", 0) > off:
            b["byteOffset"] += len(png) - old
    binc = binc[:off] + png + binc[off + old:]
    bv["byteLength"] = len(buf.getvalue())
    j["buffers"][0]["byteLength"] = len(binc)
    j["images"][0]["mimeType"] = "image/png"
    for m in j["materials"]:
        m.setdefault("pbrMetallicRoughness", {}).update(metallicFactor=0.0, roughnessFactor=1.0)
    return _pack(j, binc)
