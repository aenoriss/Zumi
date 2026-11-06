"""Item 8: an episode processed by episode.py written back into a .zumi the readers open.

Per processed box the panel becomes renderMode "scene3d" with panels/<id>/scene.glb:
  layers     one textured surface per flat layer (layers.py), far to near: each frame's window, the backdrop of each
             frame, then a card per character and erased object, each RGBA (alpha from its mask) and blended; a quad,
             or a grid bulging by its relief map
  camera     the panel's own camera: a perspective camera at the origin looking down -Z (glTF convention), vertical
             field of view from the 55 deg assumed on the long side (view.py); units are shares of the reading
             distance, the frames' windows at 1
Unlit materials (KHR_materials_unlit): the art is already lit. Bubbles go into the manifest as the schema allows
(id, text, kind from Transcribe, position = normalised centre, speakerId = the cast id of the speaker from the
speaker records and the identity, audio = the line recorded in that voice as panels/<id>/voice/<bubble>.mp3), in
the box's reading order with a startOffset and durationHint each (timing: the clips' lengths, a reading time for
bubbles without one, GAP_S between them) and the panel's durationOverride set to the time its bubbles take, so the
reader paces the panel by its voices; their measured style and placement (shape, colours, font size, depth: layers.place_lettering)
and Transcribe's delivery and pace go into panels/<id>/bubbles.style.json next to the scene, until the schema has
them. The manifest's cast is the series cast as of this episode (character_identity): id, name, the Inworld voice
it was designed with; a look sharing another character's voice carries that voice. The lettering is also in the
scene, as cards of the original bubbles. The original flat layer stays as the panel's fallback.

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

from boxstore import Box, Episode, pid_of
from view import focal
from workers import pmap

KIND = {"speech": "speech", "thought": "thought", "caption": "caption", "sfx": "shout", "shout": "shout"}
VOICE_ENGINE = "inworld-tts-2"
GAP_S = 0.6        # between one bubble's end and the next's start, as audio/episode.mp3 spaces the lines
READ_CPS = 15.0    # reading speed for a bubble without a clip (a caption, a sound effect): seconds = chars / READ_CPS
READ_MIN_S = 1.5   # and at least this long
TAIL_S = 1.0       # after the last bubble before the panel may move on


PANEL_MIN_S = 3.0  # a panel with nothing to say (no bubbles, or not processed) holds the clock this long


def timeline(panels: list[dict]) -> float:
    """One clock for the episode, precomputed so a reader needs no pacing logic: each panel's startTime and endTime
    from the episode's start, in index order, its duration what timing() set (durationOverride) or PANEL_MIN_S;
    each bubble's startTime and endTime from its startOffset and durationHint. Returns the episode's length."""
    t = 0.0
    for p in sorted(panels, key=lambda p: p["index"]):
        d = p.get("durationOverride") or PANEL_MIN_S
        p["startTime"], p["endTime"] = round(t, 2), round(t + d, 2)
        for b in p.get("bubbles", []):
            if "startOffset" in b:
                b["startTime"] = round(t + b["startOffset"], 2)
                b["endTime"] = round(b["startTime"] + b.get("durationHint", 0), 2)
        t += d
    return round(t, 2)


def timing(bubbles: list[dict], seconds: dict[int, float]) -> float:
    """startOffset and durationHint on each bubble entry in reading order, from the clips' lengths (seconds: bubble id
    -> clip seconds) and a reading time for bubbles without one; returns the panel's duration: the time its bubbles
    take, plus TAIL_S. The reader then moves on when the voices are done instead of its floor of 20 s a scene."""
    t = 0.0
    for e in bubbles:
        n = int(e["id"][1:])
        d = seconds.get(n) or max(READ_MIN_S, len(e["text"]) / READ_CPS)
        e["startOffset"], e["durationHint"] = round(t, 2), round(d, 2)
        t += d + GAP_S
    return round(t - GAP_S + TAIL_S, 2) if bubbles else 0.0


def voices(ep: Episode) -> tuple[dict, list[dict], dict]:
    """What the voice steps saved for the episode: ({card id: cast id}, the manifest's cast entries for the
    characters of this episode, {(pid, bubble): line record}). Empty when identity or lines were not made."""
    ident_f = ep.out / "identity" / "identity.json"
    if not ident_f.exists():
        return {}, [], {}
    ident = json.loads(ident_f.read_text(encoding="utf-8"))
    cast_f = ep.run / "cast" / ident["series"] / "cast.json"
    chars = json.loads(cast_f.read_text(encoding="utf-8"))["characters"] if cast_f.exists() else []
    by_id = {c["id"]: c for c in chars}

    def voice_of(cid: str, hops: int = 0) -> dict:
        v = (by_id.get(cid) or {}).get("voice") or {}
        if v.get("same_voice_as") and hops < 4:
            return voice_of(v["same_voice_as"], hops + 1)
        return v

    cast = []
    for cid in sorted(set(ident["cards"].values()), key=lambda k: int(k[1:])):
        c = by_id.get(cid)
        if not c:
            continue
        entry = {"id": cid, "name": c["name"]}
        v = voice_of(cid)
        if v.get("id"):
            entry["voice"] = {"engine": VOICE_ENGINE, "voiceId": v["id"], "description": v.get("description") or ""}
        cast.append(entry)
    lines_f = ep.out / "audio" / "lines.json"
    lines = {(l["pid"], l["bubble"]): l for l in json.loads(lines_f.read_text(encoding="utf-8"))} if lines_f.exists() else {}
    return ident["cards"], cast, lines


def mp3_bytes(wav: Path) -> bytes:
    import soundfile as sf
    data, rate = sf.read(wav)
    buf = io.BytesIO()
    sf.write(buf, data, rate, format="MP3")
    return buf.getvalue()


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


def png_bytes(image: Image.Image) -> bytes:
    b = io.BytesIO()
    image.save(b, format="PNG", optimize=True)
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
    sc = box.scene()
    w, h = sc.w, sc.h
    f = focal(w, h, sc.fov)
    meshes = []
    for L in sc.layers:
        win = L.window()
        if win is not None:
            wx0, wy0, wx1, wy1 = L.window_bbox
            pos, uv, idx = card_surface(wx0, wy0, wx1, wy1, L.window_z, w, h, f)
            meshes.append({"name": f"window: frame {L.frame}", "pos": pos, "uv": uv, "idx": idx,
                           "png": png_bytes(win), "blend": True, "extras": {"kind": "window", "frame": L.frame}})
    for L in sc.layers:
        x0, y0, x1, y1 = L.bbox
        # a backdrop's box already runs past its frame by its margin (cards.backdrop_image)
        pos, uv, idx = card_surface(x0, y0, x1, y1, L.z, w, h, f, relief=L.relief(), amp=L.amp,
                                    n=32 if L.kind == "backdrop" else 24, cell=L.cell)
        meshes.append({"name": f"{L.kind}: {L.name}" + (f" [frame {L.frame}]" if L.clipped else ""),
                       "pos": pos, "uv": uv, "idx": idx, "png": png_bytes(L.image()), "blend": True,
                       "extras": {"kind": L.kind, **({"frame": L.frame} if L.clipped else {})}})
    if not meshes:
        return False
    t = np.tan(np.radians(sc.fov) / 2)
    write_glb(out_glb, meshes, float(2 * np.arctan(t if h >= w else t * h / w)), w / h)
    return True


def _build(job: tuple) -> bool:
    """box_cards for one (box, GLB path); False when the box has no layers. A worker of main's pmap."""
    box, glb = job
    return box.scene() is not None and box_cards(box, glb)


def main():
    src, ep_out, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    zin = zipfile.ZipFile(src)
    man = json.loads(zin.read("manifest.json"))
    stem = src.stem
    tmp = dst.parent / (dst.stem + "_build")
    tmp.mkdir(parents=True, exist_ok=True)
    added: dict[str, bytes] = {}
    done = 0
    jobs = [(Box(ep_out, pid_of(stem, i)), tmp / f"{p['id']}.glb") for i, p in enumerate(man["panels"])]
    built = pmap(_build, jobs)  # one GLB per box, boxes across processes
    card_char, cast, lines = voices(Episode(ep_out, stem))
    voiced, speaking = 0, set()
    for (box, glb), p, ok in zip(jobs, man["panels"], built):
        if not ok:
            continue
        p["renderMode"] = "scene3d"
        p["scene"] = f"panels/{p['id']}/scene.glb"
        added[p["scene"]] = glb.read_bytes()
        bd = box.bubbles()
        if bd is not None:
            W, H = bd["w"], bd["h"]
            speaker, order = {}, {}
            for r in box.speakers() or []:
                order[r["bubble"]] = r["order"]  # the box's reading order (speakers.reading_order)
                if r.get("speakers"):
                    s = r["speakers"][0]
                    speaker[r["bubble"]] = card_char.get(s if "/" in s else f"{box.pid}/{s}")
            p["bubbles"], seconds = [], {}
            for b in sorted(bd["bubbles"], key=lambda b: (order.get(b["id"], 10**6), b["bbox"][1])):
                x0, y0, x1, y1 = b["bbox"]
                entry = {"id": f"b{b['id']}", "text": b.get("text") or "",
                         "position": {"x": round((x0 + x1) / 2 / W, 4), "y": round((y0 + y1) / 2 / H, 4)}}
                if KIND.get(b.get("kind") or ""):
                    entry["kind"] = KIND[b["kind"]]
                if speaker.get(b["id"]):
                    entry["speakerId"] = speaker[b["id"]]
                    speaking.add(speaker[b["id"]])
                line = lines.get((box.pid, b["id"]))
                if line and (ep_out / "audio" / line["file"]).exists():
                    entry["audio"] = f"panels/{p['id']}/voice/b{b['id']}.mp3"
                    seconds[b["id"]] = float(line.get("seconds") or 0)
                    added[entry["audio"]] = mp3_bytes(ep_out / "audio" / line["file"])
                    voiced += 1
                p["bubbles"].append(entry)
            p["durationOverride"] = timing(p["bubbles"], seconds)
            style = {k: v for k, v in bd.items() if k not in ("letters", "transcribed")}  # the pipeline's own
            style["bubbles"] = [{k: v for k, v in b.items() if k != "segmented_as"} for b in bd["bubbles"]]
            added[f"panels/{p['id']}/bubbles.style.json"] = json.dumps(style, indent=1).encode()
        done += 1
    cast = [c for c in cast if c["id"] in speaking or "voice" in c]  # the characters a reader meets: speakers, voices
    if cast:
        man["cast"] = cast
    man["episode"]["durationHint"] = timeline(man["panels"])
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "manifest.json" or item.filename in added:
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("manifest.json", json.dumps(man, indent=2))
        for name, data in added.items():
            zout.writestr(name, data, compress_type=zipfile.ZIP_STORED if name.endswith(".glb") else zipfile.ZIP_DEFLATED)
    print(f"{done} panels as scene3d, {len(cast)} cast characters, {voiced} voiced bubbles -> {dst} "
          f"({dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
