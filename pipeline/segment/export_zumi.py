"""Item 8: an episode processed by episode.py written back into a .zumi the readers open.

Per processed box the panel becomes renderMode "scene3d" with panels/<id>/scene.glb:
  layers     one textured surface per flat layer (cards.py), far to near: each frame's window, the backdrop of each
             frame, then a card per character and erased object, each RGBA (alpha from its mask) and blended; a quad,
             or a grid bulging by its relief map
  camera     the panel's own camera: a perspective camera at the origin looking down -Z (glTF convention), vertical
             field of view from the 55 deg assumed on the long side (view.py); units are shares of the reading
             distance, the frames' windows at 1
Unlit materials (KHR_materials_unlit): the art is already lit. Bubbles go into the manifest as the schema allows
(id, text, kind, position = normalised centre, speakerId from Understand's cast, which is added to the manifest's,
anchor = Understand's point on the speaker); their measured style and placement (shape, colours, font size, depth:
lettering_layer.py) go into panels/<id>/bubbles.style.json next to the scene, until the schema has them. The
lettering is also in the scene, as cards of the original bubbles.
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

from boxstore import Box, load_understanding, pid_of
from view import focal

KIND = {"speech": "speech", "thought": "thought", "caption": "caption", "sfx": "shout", "shout": "shout"}


def write_glb(path: Path, meshes: list[dict], yfov: float, aspect: float) -> None:
    """meshes: [{"name", "pos", "uv", "idx", "png" (bytes), "blend" (bool), optional "extras" (the node's glTF
    extras)}] -> one GLB, each mesh unlit."""
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
        nodes.append({"name": m["name"], "mesh": len(gmeshes) - 1, **({"extras": m["extras"]} if m.get("extras") else {})})
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


def box_cards(box: Box, out_glb: Path) -> bool:
    """The box's flat layers (cards.py) far to near, each at its depth facing the camera: backdrops run past their frame
    by the margin (edge pixels stretched), character and object cards bulge by their relief. The reader clips each
    frame's layers to a window of the frame's shape in front of them (glTF cannot say that), as the browser viewer
    does, so the gutters between frames stay empty: each frame's window comes first, a mesh "window: frame <n>" at the
    window depth textured with the frame's shape (alpha), then the layers. A clipped layer's name ends in
    " [frame <n>]"; lettering has no frame and is never clipped. The same goes into each node's extras
    ({"kind", "frame"})."""
    c, mesh_dir = box.cards(), box.mesh
    w, h, fov = c["w"], c["h"], c["fov"]
    f = focal(w, h, fov)
    meshes = []
    for L in c["layers"]:
        if L.get("window"):
            wx0, wy0, wx1, wy1 = L["window_bbox"]
            pos, uv, idx = card_surface(wx0, wy0, wx1, wy1, L["window_z"], w, h, f)
            meshes.append({"name": f"window: frame {L['frame']}", "pos": pos, "uv": uv, "idx": idx,
                           "png": png_bytes(mesh_dir / L["window"]), "blend": True,
                           "extras": {"kind": "window", "frame": L["frame"]}})
    for L in c["layers"]:
        x0, y0, x1, y1 = L["bbox"]
        relief = (np.asarray(Image.open(mesh_dir / L["relief"]).convert("L"), np.float32) / 255
                  if L.get("relief") else None)
        if L["kind"] == "backdrop":
            # the backdrop's box already runs past its frame by its margin (cards.backdrop_image)
            pos, uv, idx = card_surface(x0, y0, x1, y1, L["z"], w, h, f, relief=relief, amp=L.get("relief_amp", 0),
                                        n=32, cell=L.get("relief_cell", 0))
        else:
            pos, uv, idx = card_surface(x0, y0, x1, y1, L["z"], w, h, f, relief=relief, amp=L.get("relief_amp", 0),
                                        cell=L.get("relief_cell", 0))
        clipped = isinstance(L.get("frame"), int) and L["kind"] != "lettering"
        meshes.append({"name": f"{L['kind']}: {L['name']}" + (f" [frame {L['frame']}]" if clipped else ""),
                       "pos": pos, "uv": uv, "idx": idx, "png": png_bytes(mesh_dir / L["png"]), "blend": True,
                       "extras": {"kind": L["kind"], **({"frame": L["frame"]} if clipped else {})}})
    if not meshes:
        return False
    t = np.tan(np.radians(fov) / 2)
    write_glb(out_glb, meshes, float(2 * np.arctan(t if h >= w else t * h / w)), w / h)
    return True


def main():
    src, ep_out, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    zin = zipfile.ZipFile(src)
    man = json.loads(zin.read("manifest.json"))
    stem = src.stem
    # Understand's cast, so the bubbles can name their speaker (speakerId: a cast id); the schema keeps id and name
    known = {c.get("id") for c in man.setdefault("cast", [])}
    man["cast"] += [{"id": c["id"], "name": c.get("name") or c["id"]} for c in load_understanding(ep_out)["cast"]
                    if c.get("id") and c["id"] not in known]
    tmp = dst.parent / (dst.stem + "_build")
    tmp.mkdir(parents=True, exist_ok=True)
    added: dict[str, bytes] = {}
    done = 0
    for i, p in enumerate(man["panels"]):
        box = Box(ep_out, pid_of(stem, i))
        if box.cards() is None:
            continue
        glb = tmp / f"{p['id']}.glb"
        if not box_cards(box, glb):
            continue
        p["renderMode"] = "scene3d"
        p["scene"] = f"panels/{p['id']}/scene.glb"
        added[p["scene"]] = glb.read_bytes()
        bd = box.bubbles()
        if bd is not None:
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
                if b.get("anchor"):  # Understand's point on the speaker, 0..1 of the box
                    entry["anchor"] = {"x": round(b["anchor"][0], 4), "y": round(b["anchor"][1], 4)}
                p["bubbles"].append(entry)
            added[f"panels/{p['id']}/bubbles.style.json"] = box.bubbles_file.read_bytes()
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
