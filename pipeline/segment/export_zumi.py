"""Item 8: an episode processed by steps 2-6 (episode.py) written back into a .zumi the readers open.

Per processed box the panel becomes renderMode "scene3d" with panels/<id>/scene.glb:
  layers     one textured quad per flat layer (cards.py), far to near: the backdrop of each frame, then a card per
             character and erased object, each RGBA (alpha from its mask) and blended
             (LEGACY, legacy_mesh.py: the layered depth mesh and the characters' figure surface instead)
  camera     the panel's own camera: a perspective camera at the origin looking down -Z (glTF convention), vertical
             field of view from the 55 deg assumed on the long side; units are the depth model's (relative)
Unlit materials (KHR_materials_unlit): the art is already lit. Bubbles go into the manifest as the schema allows
(id, text, kind, position = normalised centre); their measured style and placement (shape, colours, font size,
depth: lettering_layer.py) go into panels/<id>/bubbles.style.json next to the scene, until the schema has them.
The original flat layer stays as the panel's fallback.

    python export_zumi.py <chapter.zumi> <episode out dir> <new.zumi>
"""
from __future__ import annotations

import io
import json
import struct
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

KIND = {"speech": "speech", "thought": "thought", "caption": "caption", "sfx": "shout", "shout": "shout"}


def grid_mesh(D: np.ndarray, k: int, w: int, h: int, fov: float, jump: float | None):
    """The viewer's surface(): a vertex every k px where D > 0, two triangles per cell, dropped across depth jumps."""
    gh, gw = D.shape
    f = max(w, h) / (2 * np.tan(np.radians(fov) / 2))
    v, u = np.mgrid[0:gh, 0:gw].astype(np.float32) * k
    pos = np.stack([(u - w / 2) * D / f, -(v - h / 2) * D / f, -D], -1).reshape(-1, 3)
    uv = np.stack([(u + 0.5) / w, (v + 0.5) / h], -1).reshape(-1, 2)  # glTF: v down from the top
    idx = np.arange(gh * gw).reshape(gh, gw)
    tris = []
    for a, b, c in (((0, 0), (1, 0), (0, 1)), ((0, 1), (1, 0), (1, 1))):
        A = idx[a[0]:a[0] + gh - 1, a[1]:a[1] + gw - 1]
        Bq = idx[b[0]:b[0] + gh - 1, b[1]:b[1] + gw - 1]
        C = idx[c[0]:c[0] + gh - 1, c[1]:c[1] + gw - 1]
        da, db, dc = D.ravel()[A], D.ravel()[Bq], D.ravel()[C]
        ok = (da > 0) & (db > 0) & (dc > 0)
        if jump:
            mx, mn = np.maximum(np.maximum(da, db), dc), np.minimum(np.minimum(da, db), dc)
            ok &= mx / np.where(mn > 0, mn, 1) <= jump
        tris.append(np.stack([A[ok], Bq[ok], C[ok]], -1))
    tri = np.concatenate(tris).reshape(-1)
    used = np.unique(tri)
    remap = np.full(gh * gw, -1, np.int64)
    remap[used] = np.arange(len(used))
    return pos[used].astype(np.float32), uv[used].astype(np.float32), remap[tri].astype(np.uint32)


def read_ldi(path: Path):
    buf = path.read_bytes()
    nv, ni = struct.unpack("<II", buf[:8])
    pos = np.frombuffer(buf, np.float32, nv * 3, 8).reshape(-1, 3)
    uv = np.frombuffer(buf, np.float32, nv * 2, 8 + nv * 12).reshape(-1, 2).copy()
    uv[:, 1] = 1 - uv[:, 1]  # three.js flips textures vertically; glTF does not
    idx = np.frombuffer(buf, np.uint32, ni, 8 + nv * 20)
    return pos, uv, idx


def write_glb(path: Path, meshes: list[dict], yfov: float, aspect: float) -> None:
    """meshes: [{"name", "pos", "uv", "idx", "png" (bytes), "blend" (bool)}] -> one GLB, each mesh unlit."""
    blob = bytearray()
    views, accessors, images, textures, materials, gmeshes, nodes = [], [], [], [], [], [], []

    def add_view(data: bytes, target=None):
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob), "byteLength": len(data), **({"target": target} if target else {})})
        blob.extend(data)
        return len(views) - 1

    for m in meshes:
        pv = add_view(m["pos"].tobytes(), 34962)
        accessors.append({"bufferView": pv, "componentType": 5126, "count": len(m["pos"]), "type": "VEC3",
                          "min": m["pos"].min(0).tolist(), "max": m["pos"].max(0).tolist()})
        uv = add_view(m["uv"].tobytes(), 34962)
        accessors.append({"bufferView": uv, "componentType": 5126, "count": len(m["uv"]), "type": "VEC2"})
        iv = add_view(m["idx"].tobytes(), 34963)
        accessors.append({"bufferView": iv, "componentType": 5125, "count": len(m["idx"]), "type": "SCALAR"})
        imv = add_view(m["png"])
        images.append({"bufferView": imv, "mimeType": "image/png"})
        textures.append({"source": len(images) - 1, "sampler": 0})
        materials.append({"name": m["name"], "doubleSided": True,
                          "pbrMetallicRoughness": {"baseColorTexture": {"index": len(textures) - 1},
                                                   "metallicFactor": 0.0, "roughnessFactor": 1.0},
                          "extensions": {"KHR_materials_unlit": {}},
                          **({"alphaMode": "BLEND"} if m["blend"] else {})})
        a0 = len(accessors) - 3
        gmeshes.append({"name": m["name"], "primitives": [{"attributes": {"POSITION": a0, "TEXCOORD_0": a0 + 1},
                                                           "indices": a0 + 2, "material": len(materials) - 1}]})
        nodes.append({"name": m["name"], "mesh": len(gmeshes) - 1})
    nodes.append({"name": "panel_camera", "camera": 0})
    while len(blob) % 4:  # the BIN chunk is 4-byte aligned, and buffers[0].byteLength must equal its length
        blob.append(0)
    gltf = {"asset": {"version": "2.0", "generator": "zumi pipeline export_zumi.py"},
            "extensionsUsed": ["KHR_materials_unlit"], "scene": 0, "scenes": [{"nodes": list(range(len(nodes)))}],
            "nodes": nodes, "meshes": gmeshes, "materials": materials, "textures": textures, "images": images,
            "samplers": [{"magFilter": 9729, "minFilter": 9729, "wrapS": 33071, "wrapT": 33071}],
            "cameras": [{"type": "perspective", "perspective": {"yfov": yfov, "aspectRatio": aspect, "znear": 0.01}}],
            "accessors": accessors, "bufferViews": views, "buffers": [{"byteLength": len(blob)}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    while len(blob) % 4:
        blob.append(0)
    out = struct.pack("<III", 0x46546C67, 2, 12 + 8 + len(js) + 8 + len(blob))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(blob), 0x004E4942) + bytes(blob)
    path.write_bytes(out)


def png_bytes(path: Path) -> bytes:
    b = io.BytesIO()
    Image.open(path).save(b, format="PNG", optimize=True)
    return b.getvalue()


def card_surface(x0, y0, x1, y1, z, w, h, f, u0=0.0, v0=0.0, u1=1.0, v1=1.0, relief=None, amp=0.0, n=24, cell=0):
    """A layer through the pixel rect at depth z, each vertex on its own camera ray (it projects onto the rect at
    rest): a quad, or with a relief map an n x n grid (a vertex every `cell` px when given) bulging toward the camera
    by amp * relief of its depth. uv may run past 0..1 (a backdrop's margin, clamped to its edge pixels)."""
    nx = ny = n if relief is not None else 1
    if relief is not None and cell:
        nx, ny = max(1, int(np.ceil((x1 - x0) / cell))), max(1, int(np.ceil((y1 - y0) / cell)))
    fx, fy = np.meshgrid(np.linspace(0, 1, nx + 1), np.linspace(0, 1, ny + 1))
    x, y = x0 + fx * (x1 - x0), y0 + fy * (y1 - y0)
    zz = np.full_like(fx, z)
    if relief is not None:  # sampled where the texture is: a backdrop's margin repeats its edge, as the texture does
        rh, rw = relief.shape
        ru, rv = np.clip(u0 + fx * (u1 - u0), 0, 1), np.clip(v0 + fy * (v1 - v0), 0, 1)
        zz = z * (1 - amp * relief[np.round(rv * (rh - 1)).astype(int), np.round(ru * (rw - 1)).astype(int)])
    pos = np.stack([(x - w / 2) * zz / f, -(y - h / 2) * zz / f, -zz], -1).reshape(-1, 3).astype(np.float32)
    uv = np.stack([u0 + fx * (u1 - u0), v0 + fy * (v1 - v0)], -1).reshape(-1, 2).astype(np.float32)  # glTF: v down
    k = np.arange((ny + 1) * (nx + 1)).reshape(ny + 1, nx + 1)
    a, b, c, d = k[:-1, :-1], k[:-1, 1:], k[1:, :-1], k[1:, 1:]
    idx = np.stack([a, c, b, b, c, d], -1).reshape(-1).astype(np.uint32)
    return pos, uv, idx


def box_cards(pid: str, mesh_dir: Path, out_glb: Path) -> bool:
    """The box's flat layers (cards.py) far to near, each at its depth facing the camera: backdrops run past their frame
    by the margin (edge pixels stretched), character and object cards bulge by their relief. Each mesh is named
    "<kind>: <name>" and its frame index is in cards.json: the reader clips each frame's layers to a window of the
    frame's shape in front of them (glTF cannot say that)."""
    c = json.loads((mesh_dir / f"{pid}.cards.json").read_text())
    w, h, fov = c["w"], c["h"], c["fov"]
    f = max(w, h) / (2 * np.tan(np.radians(fov) / 2))
    meshes = []
    for L in c["layers"]:
        x0, y0, x1, y1 = L["bbox"]
        relief = (np.asarray(Image.open(mesh_dir / L["relief"]).convert("L"), np.float32) / 255
                  if L.get("relief") else None)
        if L["kind"] == "backdrop":
            m = round(c.get("margin", 0) * max(w, h))
            bw, bh = x1 - x0, y1 - y0
            pos, uv, idx = card_surface(x0 - m, y0 - m, x1 + m, y1 + m, L["z"], w, h, f, -m / bw, -m / bh,
                                        1 + m / bw, 1 + m / bh, relief=relief, amp=L.get("relief_amp", 0), n=32,
                                        cell=L.get("relief_cell", 0))
        else:
            pos, uv, idx = card_surface(x0, y0, x1, y1, L["z"], w, h, f, relief=relief, amp=L.get("relief_amp", 0),
                                        cell=L.get("relief_cell", 0))
        meshes.append({"name": f"{L['kind']}: {L['name']}", "pos": pos, "uv": uv, "idx": idx,
                       "png": png_bytes(mesh_dir / L["png"]), "blend": True})
    if not meshes:
        return False
    t = np.tan(np.radians(fov) / 2)
    write_glb(out_glb, meshes, float(2 * np.arctan(t if h >= w else t * h / w)), w / h)
    return True


def box_scene(pid: str, mesh_dir: Path, out_glb: Path) -> bool:
    if (mesh_dir / f"{pid}.cards.json").exists():
        return box_cards(pid, mesh_dir, out_glb)
    return box_scene_legacy(pid, mesh_dir, out_glb)


def box_scene_legacy(pid: str, mesh_dir: Path, out_glb: Path) -> bool:
    """LEGACY (legacy_mesh.py): the layered depth mesh, or the panel's own grid surface, plus the figure surface."""
    m = json.loads((mesh_dir / f"{pid}.json").read_text())
    w, h, k, fov, jump = m["w"], m["h"], m["stride"], m["fov"], m["jump"]
    meshes = []
    if (mesh_dir / f"{pid}.ldi.bin").exists():
        pos, uv, idx = read_ldi(mesh_dir / f"{pid}.ldi.bin")
        meshes.append({"name": "scene", "pos": pos, "uv": uv, "idx": idx, "png": png_bytes(mesh_dir / f"{pid}.ldi.png"),
                       "blend": False})
    else:  # no hidden layers: the panel's own surface
        D = np.fromfile(mesh_dir / f"{pid}.f32", np.float32).reshape(m["gh"], m["gw"])
        pos, uv, idx = grid_mesh(D, k, w, h, fov, jump)
        meshes.append({"name": "scene", "pos": pos, "uv": uv, "idx": idx, "png": png_bytes(mesh_dir / f"{pid}.png"),
                       "blend": False})
    if (mesh_dir / f"{pid}.fig.f32").exists() and (mesh_dir / f"{pid}.fig.png").exists():
        F = np.fromfile(mesh_dir / f"{pid}.fig.f32", np.float32).reshape(m["gh"], m["gw"])
        if (F > 0).any():
            pos, uv, idx = grid_mesh(F, k, w, h, fov, jump)
            meshes.append({"name": "figure", "pos": pos, "uv": uv, "idx": idx,
                           "png": png_bytes(mesh_dir / f"{pid}.fig.png"), "blend": True})
    if not meshes or not len(meshes[0]["idx"]):
        return False
    t = np.tan(np.radians(fov) / 2)
    yfov = 2 * np.arctan(t if h >= w else t * h / w)
    write_glb(out_glb, meshes, float(yfov), w / h)
    return True


def main():
    src, ep_out, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    mesh_dir = ep_out / "parallax" / "mesh"
    zin = zipfile.ZipFile(src)
    man = json.loads(zin.read("manifest.json"))
    stem = src.stem
    tmp = dst.parent / (dst.stem + "_build")
    tmp.mkdir(parents=True, exist_ok=True)
    added: dict[str, bytes] = {}
    done = 0
    for i, p in enumerate(man["panels"]):
        pid = f"{stem}-p{i:03d}"
        if not (mesh_dir / f"{pid}.json").exists():
            continue
        glb = tmp / f"{p['id']}.glb"
        if not box_scene(pid, mesh_dir, glb):
            continue
        p["renderMode"] = "scene3d"
        p["scene"] = f"panels/{p['id']}/scene.glb"
        added[p["scene"]] = glb.read_bytes()
        bfile = mesh_dir / f"{pid}.bubbles.json"
        if bfile.exists():
            bd = json.loads(bfile.read_text())
            W, H = bd["w"], bd["h"]
            p["bubbles"] = []
            for b in bd["bubbles"]:
                x0, y0, x1, y1 = b["bbox"]
                entry = {"id": f"b{b['id']}", "text": b.get("text") or "",
                         "position": {"x": round((x0 + x1) / 2 / W, 4), "y": round((y0 + y1) / 2 / H, 4)}}
                if KIND.get(b.get("kind") or ""):
                    entry["kind"] = KIND[b["kind"]]
                if b.get("speaker") and b.get("kind") not in ("caption", None) and any(
                        c.get("id") == b["speaker"] for c in man.get("cast", [])):
                    entry["speakerId"] = b["speaker"]
                p["bubbles"].append(entry)
            added[f"panels/{p['id']}/bubbles.style.json"] = bfile.read_bytes()
        done += 1
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "manifest.json" or item.filename in added:
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("manifest.json", json.dumps(man, indent=2))
        for name, data in added.items():
            zout.writestr(name, data, compress_type=zipfile.ZIP_STORED if name.endswith(".glb") else zipfile.ZIP_DEFLATED)
    print(f"{done} panels as scene3d -> {dst} ({dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
