"""Item 8: an episode processed by episode.py written back into a .zumi the readers open (format FORMAT_VERSION:
packages/format/schema/zumi.schema.json is the contract, its README the conventions).

Per processed box the panel becomes renderMode "scene3d" with panels/<id>/scene.glb:
  layers     one textured surface per flat layer (layers.py), far to near: each frame's window, the backdrop of each
             frame, then a card per character and erased object, each RGBA (alpha from its mask) and blended; a quad,
             or a grid bulging by its relief map. No texture is over TEXTURE_MAX px on its long side
  camera     the panel's own camera: a perspective camera at the origin looking down -Z (glTF convention), vertical
             field of view from the 55 deg assumed on the long side (view.py); units are shares of the reading
             distance, the frames' windows at 1
  extras     what a reader finds a node by: its kind, its frame, its card id (Layer.card), a character's cast id, a
             lettering card's bubble id
Unlit materials (KHR_materials_unlit): the art is already lit. Bubbles go into the manifest as the schema allows
(id, text, kind from Transcribe, sound effects as "sfx", position = normalised centre, speakerCard = the card that
says it, as the speaker records name it, speakerId = that card's cast id from the identity, frame = the frame it is
timed in, audio = the line recorded in that voice as panels/<id>/voice/<bubble>.wav, or for a sound effect its
sound from step 9b as panels/<id>/sfx/<bubble>.wav, sfx.py), in the clock's order with
their times from the episode clock (clock.py: startOffset, durationHint, startTime, endTime; the panel's
durationOverride, frames, startTime and endTime), so the reader paces the episode without logic of its own. Each
panel's animations are the accents motion.py's rules fire on this clock, as tracks. The manifest's cast is every
character a card of this episode is (character_identity): id, name, the voice it was designed with on the
episode's voice backend (voices.py: ZUMI_TTS, else Gemini; its engine, voice id and lines); a look sharing another
character's voice carries that voice. The lettering is also in the scene, as cards of the original bubbles, which
is all a reader shows of a bubble: the measured style of each (bubbles.json) stays in the episode's folder
(panels/<id>/bubbles.style.json was packed until 2026-11-15 and no reader opened it). The original flat layer stays
as the panel's fallback.

An episode with a speaking line that has no audio is not exported (voices.missing_lines): the run says which.

A comic finished from pencil (finish.py, step 0) gives --finish its out dir: its title.json names the comic
(series.title, the title the reader's carousel shows; episode.title, the line under it, "Episode 1 · N pages") and
its cover.png is packed at the root as series.cover.

    python export_zumi.py <chapter.zumi> <episode out dir> <new.zumi> [--finish <step 0 out dir>]
                                                                          (ZUMI_TTS=inworld for Inworld's lines)
"""
from __future__ import annotations

import json
import math
import struct
import sys
import time
import zipfile
from pathlib import Path

import numpy as np

import clock
import motion
import sfx
import voices as VO
from boxstore import Box, Episode, card_id, index_of, pid_of
from view import focal
from workers import pmap

FORMAT_VERSION = "1.1.0"  # the manifest's formatVersion: what this export writes (the schema's $id names the same)
KINDS = ("speech", "thought", "shout", "caption", "sfx")  # Transcribe's kinds are the format's
TEXTURE_MAX = 2048  # px on a texture's long side: over it the image is resampled, under it the file's own bytes
                    # (2026-11-15: a Quest 3 shows a panel at about 25 px a degree, and 4096-px cards were most of
                    # the file)
VOICE_RATE = 24000  # voice clips: WAV, mono, 16-bit PCM at this rate (Unity decodes PCM from memory, not MP3)


def voices(ep: Episode, n_boxes: int, tts) -> tuple[dict, list[dict], dict, list[str]]:
    """What the voice steps saved for the episode on the voice backend tts: ({card id: cast id}, the manifest's cast
    entries for every character a card of this episode is, the line index voices.lines gives, the speaking lines
    still without audio: voices.missing_lines). Empty when identity was not made."""
    import character_identity as CI
    got = CI.load(ep)
    if got is None:
        return {}, [], {}, []
    ident, cast_store = got
    by_id = {c["id"]: c for c in cast_store.chars}
    cast = []
    for cid in sorted({c for c in ident["cards"].values() if c}, key=lambda k: int(k[1:])):
        c = by_id.get(cid)
        if not c:
            continue
        entry = {"id": cid, "name": c["name"]}
        owner, vid = VO.voice_of(by_id, cid, tts.VOICE_ID)
        if vid:
            entry["voice"] = {"engine": tts.ENGINE, "voiceId": vid,
                              "description": ((by_id.get(owner) or {}).get("voice") or {}).get("description") or ""}
        cast.append(entry)
    return ident["cards"], cast, VO.lines(ep, tts), VO.missing_lines(ep, n_boxes, ident, cast_store, tts)


def wav_bytes(wav: Path) -> bytes:
    """A recorded line as the format's voice clip: mono 16-bit PCM at VOICE_RATE behind a plain 44-byte RIFF header,
    nothing after the samples (Gemini's files carry 7.6 kB past their data chunk, which a reader that plays to the
    end of the file would play as noise)."""
    import soundfile as sf
    data, rate = sf.read(wav, dtype="float32", always_2d=True)
    data = data.mean(1)
    if rate != VOICE_RATE:
        from scipy.signal import resample_poly
        g = math.gcd(int(rate), VOICE_RATE)
        data = resample_poly(data, VOICE_RATE // g, int(rate) // g)
    pcm = np.round(np.clip(data, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    return (b"RIFF" + struct.pack("<I", 36 + len(pcm)) + b"WAVEfmt " +
            struct.pack("<IHHIIHH", 16, 1, 1, VOICE_RATE, VOICE_RATE * 2, 2, 16) + b"data" +
            struct.pack("<I", len(pcm)) + pcm)


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


def _long_side(png: bytes) -> int:
    """A PNG's longer side in px, from its header."""
    return max(struct.unpack(">II", png[16:24]))


def box_cards(box: Box, out_glb: Path, cast_of: dict[str, str]) -> dict | None:
    """The box's flat layers (cards.py) far to near, each at its depth facing the camera: backdrops run past their frame
    by the margin (edge pixels stretched), character and object cards bulge by their relief. The reader clips each
    frame's layers to a window of the frame's shape in front of them (glTF cannot say that), as the browser viewer
    does, so the gutters between frames stay empty: each frame's window comes first, a mesh "window: frame <n>" at the
    window depth textured with the frame's shape (alpha), then the layers. A clipped layer's name ends in
    " [frame <n>]"; lettering has no frame and is never clipped. Each node's extras say the same and name it:
    {"kind", "frame" (windows and clipped layers), "card" (every layer: Layer.card, what a bubble's speakerCard and
    an animation's target name), "cast" (a character card with an identity: cast_of, {layer key: cast id}),
    "bubble" (a lettering card: its bubble's id in the manifest)}.
    A texture over TEXTURE_MAX px is resampled to it (uv is unaffected); the rest are the saved files' bytes.
    Returns {"textures", "resampled", "saved" (bytes the cap took off)}, or None for a box without layers."""
    sc = box.scene()
    w, h = sc.w, sc.h
    f = focal(w, h, sc.fov)
    meshes = []
    stats = {"textures": 0, "resampled": 0, "saved": 0}

    def capped(png_of) -> bytes | None:
        png = png_of(TEXTURE_MAX)
        if png is None:
            return None
        stats["textures"] += 1
        if _long_side(png) == TEXTURE_MAX and _long_side(full := png_of()) > TEXTURE_MAX:
            stats["resampled"] += 1
            stats["saved"] += len(full) - len(png)
        return png

    for L in sc.layers:
        win = capped(L.window_png)
        if win is not None:
            wx0, wy0, wx1, wy1 = L.window_bbox
            pos, uv, idx = card_surface(wx0, wy0, wx1, wy1, L.window_z, w, h, f)
            meshes.append({"name": f"window: frame {L.frame}", "pos": pos, "uv": uv, "idx": idx,
                           "png": win, "blend": True, "extras": {"kind": "window", "frame": L.frame}})
    for L in sc.layers:
        x0, y0, x1, y1 = L.bbox
        # a backdrop's box already runs past its frame by its margin (cards.backdrop_image)
        pos, uv, idx = card_surface(x0, y0, x1, y1, L.z, w, h, f, relief=L.relief(), amp=L.amp,
                                    n=32 if L.kind == "backdrop" else 24, cell=L.cell)
        extras = {"kind": L.kind, "card": L.card, **({"frame": L.frame} if L.clipped else {})}
        if L.kind == "character" and cast_of.get(L.key):
            extras["cast"] = cast_of[L.key]
        if L.kind == "lettering" and L.bubble is not None:
            extras["bubble"] = f"b{L.bubble}"
        meshes.append({"name": f"{L.kind}: {L.name}" + (f" [frame {L.frame}]" if L.clipped else ""),
                       "pos": pos, "uv": uv, "idx": idx, "png": capped(L.image_png), "blend": True, "extras": extras})
    if not meshes:
        return None
    t = np.tan(np.radians(sc.fov) / 2)
    write_glb(out_glb, meshes, float(2 * np.arctan(t if h >= w else t * h / w)), w / h)
    return stats


def _build(job: tuple) -> dict | None:
    """box_cards for one (box, GLB path, {layer key: cast id}); None when the box has no layers. A worker of main's
    pmap."""
    box, glb, cast_of = job
    t = time.time()
    got = box_cards(box, glb, cast_of) if box.scene() is not None else None
    print(f"  {glb.stem}: {'scene' if got else 'no layers'}, {time.time() - t:.1f} s", flush=True)
    return got


def speaker_card(s: str, box: Box, panel_ids: list[str]) -> str:
    """A speaker as the manifest names it, from a speaker record's entry: "card-2" for a card of the bubble's own
    panel, "<panel id>/card-2" for a card of another panel (the reader's correction: a voice from the box before or
    after)."""
    if "/" not in s:
        return card_id(s)
    pid, key = s.split("/", 1)
    return card_id(key) if pid == box.pid else f"{panel_ids[index_of(pid)]}/{card_id(key)}"


def main():
    src, ep_out, dst = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
    finished = Path(sys.argv[sys.argv.index("--finish") + 1]) if "--finish" in sys.argv else None
    zin = zipfile.ZipFile(src)
    man = json.loads(zin.read("manifest.json"))
    stem = src.stem
    ep = Episode(ep_out, stem)
    n = len(man["panels"])
    panel_ids = [p["id"] for p in man["panels"]]
    tts = VO.backend()  # the voice backend the episode was recorded on (ZUMI_TTS, else Gemini)
    card_char, cast, lines, missing = voices(ep, n, tts)
    if missing:  # a speaking character is never shipped silent: the voices step finishes first
        raise SystemExit(f"export refused: {len(missing)} speaking lines or characters have no audio "
                         f"({'; '.join(missing[:8])}{' ...' if len(missing) > 8 else ''}). Run the voices step "
                         f"(episode.py) until it reports none missing.")
    tmp = dst.parent / (dst.stem + "_build")
    tmp.mkdir(parents=True, exist_ok=True)
    added: dict[str, bytes] = {}
    flat: set[str] = set()  # the flat images of the boxes that got a scene, left out of the file
    done = 0
    boxes = [Box(ep_out, pid_of(stem, i)) for i in range(n)]
    jobs = [(box, tmp / f"{p['id']}.glb", {k.split("/", 1)[1]: v for k, v in card_char.items()
                                           if k.startswith(box.pid + "/")}) for box, p in zip(boxes, man["panels"])]
    built = pmap(_build, jobs)  # one GLB per box, boxes across processes
    clk = clock.build(ep, n, tts)  # the episode clock, fresh from the saved steps
    name = motion.preset()
    moves = motion.accents(ep, clk, set(lines), name)  # step 9's rules on this clock
    tracks = motion.tracks(moves, clk)
    voiced, sounded = 0, 0
    sounds = sfx.sound_of(ep)  # step 9b: {(box pid, bubble id): its sound's WAV}
    known = {c["id"] for c in cast}
    for (box, glb, _), p, got, cp in zip(jobs, man["panels"], built, clk["panels"]):
        p["startTime"], p["endTime"] = cp["startTime"], cp["endTime"]
        if not got:
            continue
        p["renderMode"] = "scene3d"
        p["scene"] = f"panels/{p['id']}/scene.glb"
        added[p["scene"]] = glb.read_bytes()
        # the box's flat source image is not packed with its scene: no reader shows it (72.3 MB of 386.8, 2026-11-15)
        flat.update(layer["image"] for layer in p.get("layers") or [])
        p["layers"] = []
        bd = box.bubbles()
        if bd is not None:
            W, H = bd["w"], bd["h"]
            said = {r["bubble"]: r["speakers"][0] for r in box.speakers() or [] if r.get("speakers")}
            p["bubbles"] = []
            for b in bd["bubbles"]:
                x0, y0, x1, y1 = b["bbox"]
                entry = {"id": f"b{b['id']}", "text": b.get("text") or "",
                         "position": {"x": round((x0 + x1) / 2 / W, 4), "y": round((y0 + y1) / 2 / H, 4)}}
                if b.get("kind") in KINDS:
                    entry["kind"] = b["kind"]
                s = said.get(b["id"])
                if s:  # the card that says it, and the cast member that card is
                    entry["speakerCard"] = speaker_card(s, box, panel_ids)
                    who = card_char.get(s if "/" in s else f"{box.pid}/{s}")
                    if who in known:
                        entry["speakerId"] = who
                line = lines.get((box.pid, b["id"]))
                sound = sounds.get((box.pid, b["id"])) if b.get("kind") == "sfx" else None
                if line:
                    entry["audio"] = f"panels/{p['id']}/voice/b{b['id']}.wav"
                    added[entry["audio"]] = wav_bytes(Path(line["path"]))
                    voiced += 1
                elif sound:  # step 9b's sound, already in the format's sound-effect WAV (sfx.finish, sfx.wav_bytes)
                    entry["audio"] = f"panels/{p['id']}/sfx/b{b['id']}.wav"
                    added[entry["audio"]] = sound.read_bytes()
                    sounded += 1
                p["bubbles"].append(entry)
            when = {b["id"]: (k, b) for k, b in enumerate(cp["bubbles"])}  # the clock's order, frame by frame
            for e in p["bubbles"]:
                e.update({k: v for k, v in when[e["id"]][1].items() if k != "id"})
            p["bubbles"].sort(key=lambda b: when[b["id"]][0])
        p["durationOverride"], p["frames"] = cp["duration"], cp["frames"]
        p["animations"] = tracks.get(p["id"], [])
        done += 1
    man["formatVersion"] = FORMAT_VERSION
    if cast:
        man["cast"] = cast
    man["episode"]["durationHint"] = clk["duration"]
    import score
    import settings
    st = settings.load(ep)
    if st:  # step 10a: the settings and each frame's setting; 10c: the places shown through the walls; 10d: props
        settings.into(man, st)
        import places
        import props
        places.into(man, ep, clk, st.get("frame_setting") or {}, added)
        props.into(man, ep, added)
    sc = score.load(ep)
    if sc:  # step 10b: the tracks and the music envelope on this clock
        score.music_into(man, sc, ep_out, added)
    if finished:  # step 0: the comic's name and cover
        named = json.loads((finished / "title.json").read_text(encoding="utf-8"))
        man["series"]["title"], man["episode"]["title"] = named["title"], named["line"]
        man["series"]["cover"] = "cover.png"
        added["cover.png"] = (finished / "cover.png").read_bytes()
    # the manifest alone beside the episode's outputs: the parallax viewer plays the episode from it (cast, timeline,
    # speakers, clips, animations) without opening the .zumi
    (ep_out / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    for path, data in added.items():  # and the tracks at the paths the manifest names, for the same viewer
        if path.startswith("episode/music/"):
            (ep_out / path).parent.mkdir(parents=True, exist_ok=True)
            (ep_out / path).write_bytes(data)
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename == "manifest.json" or item.filename in added or item.filename in flat:
                continue
            zout.writestr(item, zin.read(item.filename))
        zout.writestr("manifest.json", json.dumps(man, indent=2))
        for path, data in added.items():
            zout.writestr(path, data, compress_type=zipfile.ZIP_STORED if path.endswith(".glb") else zipfile.ZIP_DEFLATED)
    tex = {k: sum(g[k] for g in built if g) for k in ("textures", "resampled", "saved")}
    print(f"  textures: {tex['resampled']} of {tex['textures']} over {TEXTURE_MAX} px resampled, "
          f"{tex['saved'] / 1e6:.1f} MB off the scenes")
    print(f"  motion ({name}): " + ", ".join(f"{k} {v}" for k, v in motion.counts(moves).items()))
    print(f"{done} panels as scene3d, {len(cast)} cast characters, {voiced} voiced bubbles, {sounded} sound effects -> {dst} "
          f"({dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
