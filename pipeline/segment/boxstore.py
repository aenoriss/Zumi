"""What the steps leave on disk for one box, in one place: where each artefact lives, how it is encoded and how it is
read back. Steps hand data to each other through these files (a rerun reuses them); no other module knows their
paths or formats.

    out/masks/<pid>-lettering.npz, -characters.npz   masks (masks.save_masks: top_order, bit-packed)
    out/masks/<pid>-objects3.npz + .json             the objects' masks (kind "object", the picker's name) and their
                                                     relations, matched by name
    out/masks/<pid>-frames.npz                       the frame step's frames, which are flat, the page, and whether
                                                     the model answered (frames.split)
    out/parallax/mesh/<pid>.cards.json + PNGs        the flat layers (cards.layers) and the viewer's views
    out/parallax/mesh/<pid>.bubbles.json             the lettering's placement (lettering_layer.build), Transcribe's
                                                     text and kinds joined in (lettering_layer.annotate)
    out/parallax/mesh/<pid>.speakers.json            who speaks each bubble (speakers.run_box)
    out/parallax/plates/<pid>/                       the band erase's plate and paid outputs (band_erase.py)
    out/transcripts.json                             Transcribe's results per box index
    out/run.json                                     the run log: each review's fixes and cost, each step's time

    ep = Episode(out, stem); box = ep.box(i); box.letters(); box.frames().page; box.cards()
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from masks import Found, load_masks, save_masks, top_key

OBJECT_META_KEYS = ("on", "held", "front", "except", "animal")


def pid_of(stem: str, i: int) -> str:
    """A box's id: its episode's stem and its index in the episode."""
    return f"{stem}-p{i:03d}"


def index_of(pid: str) -> int:
    return int(pid.rsplit("-p", 1)[1])


@dataclass
class Frames:
    """The frame step's result for a box: exclusive frame masks in top order, which are flat (text, credits: no
    backdrop relief), the page they leave out (None in files from before 2026-10-30), and whether the panel model
    answered (a box without an answer is one scene for now, and the next run asks again)."""
    masks: list[np.ndarray]
    flat: list[bool]
    page: np.ndarray | None
    answered: bool

    @property
    def current(self) -> bool:
        """Made by today's frame step from a model answer: what the layers are built on."""
        return self.page is not None and self.answered


_TR: dict[Path, dict] = {}


class Box:
    def __init__(self, out: Path, pid: str):
        self.out, self.pid = Path(out), pid

    @property
    def index(self) -> int:
        return index_of(self.pid)

    @property
    def mesh(self) -> Path:
        return self.out / "parallax" / "mesh"

    @property
    def plates(self) -> Path:
        return self.out / "parallax" / "plates" / self.pid

    def _mask_file(self, what: str) -> Path:
        return self.out / "masks" / f"{self.pid}-{what}.npz"

    # ---- segmentation masks
    def letters(self) -> list[Found] | None:
        f = self._mask_file("lettering")
        return load_masks(f) if f.exists() else None

    def characters(self) -> list[Found] | None:
        f = self._mask_file("characters")
        return load_masks(f) if f.exists() else None

    def save_letters(self, found: list[Found]) -> None:
        save_masks(self._mask_file("lettering"), found)

    def save_characters(self, found: list[Found]) -> None:
        save_masks(self._mask_file("characters"), found)

    # ---- objects
    def has_objects(self) -> bool:
        return self._mask_file("objects3").exists()

    def objects(self) -> list[dict]:
        """The saved objects: [{"name", "mask", "on", "held", "front", "except", "animal"}], [] when none."""
        f = self._mask_file("objects3")
        if not f.exists():
            return []
        mf = f.with_suffix(".json")
        # matched by name, not position: the masks are saved top to bottom, the metadata in the picker's order, and
        # paired by position P&C 39 p10's bottle took the table's "front" and the table the cup's "on"
        meta = {md["name"]: md for md in json.loads(mf.read_text(encoding="utf-8"))} if mf.exists() else {}
        # files saved before 2026-10-30 kept the name in the kind
        named = [(m.name or m.kind, m.mask) for m in load_masks(f)]
        return [{"name": n, "mask": m, **{k: v for k, v in meta.get(n, {}).items() if k != "name"}} for n, m in named]

    def save_objects(self, per: list[dict]) -> None:
        """per: [{"name", "mask", "score", and the relations}]."""
        f = self._mask_file("objects3")
        save_masks(f, [Found(o["mask"], float(o.get("score", 1.0)), "object", o["name"]) for o in per])
        f.with_suffix(".json").write_text(json.dumps([{"name": o["name"], **{k: o.get(k) for k in OBJECT_META_KEYS}}
                                                      for o in per], indent=1, ensure_ascii=False), encoding="utf-8")

    # ---- frames and the page
    def frames(self) -> Frames | None:
        f = self._mask_file("frames")
        if not f.exists():
            return None
        d = np.load(f)
        if "answered" not in d.files:
            # carved by the page (before 2026-10-30): still read, for the layers built on them (speakers), but no
            # page, so not current: episode --from-masks makes the frames again, cards.layers refuses them
            ms = load_masks(f)
            return Frames([m.mask for m in ms], [m.kind == "flat" for m in ms], None, True)
        h, w = d["shape"]
        unpack = lambda a: np.unpackbits(a, axis=-1, count=w).astype(bool)[..., :h, :]
        masks = list(unpack(d["masks"])) if len(d["masks"]) else []
        return Frames(masks, [bool(x) for x in d["flat"]], unpack(d["page"]), bool(d["answered"]))

    def save_frames(self, masks: list[np.ndarray], flat: list[bool], page: np.ndarray, answered: bool) -> None:
        """In top_order: a frame's index (its cards' "frame") is the same in memory and on disk."""
        order = sorted(range(len(masks)), key=lambda k: top_key(masks[k]))
        f = self._mask_file("frames")
        f.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(
            f, masks=np.packbits(np.stack([masks[k] for k in order]), axis=-1) if masks else np.zeros((0, 0, 0), np.uint8),
            flat=np.array([flat[k] for k in order], bool), page=np.packbits(page, axis=-1),
            shape=np.array(page.shape), answered=np.array(answered))

    # ---- the flat layers
    def cards(self) -> dict | None:
        """cards.json: {w, h, fov, layers: [{png, bbox, z, kind, name, frame, ...}]} far to near."""
        f = self.mesh / f"{self.pid}.cards.json"
        return json.loads(f.read_text()) if f.exists() else None

    def save_cards(self, cj: dict) -> None:
        self.mesh.mkdir(parents=True, exist_ok=True)
        (self.mesh / f"{self.pid}.cards.json").write_text(json.dumps(cj, indent=1))

    def card(self, n: int, part: str = "") -> str:
        """Card n's file name in the mesh dir, as cards.json names it: the card itself, or its "window" or "relief"."""
        return f"{self.pid}.card-{n}" + (f".{part}" if part else "") + ".png"

    def clear_cards(self) -> None:
        """This box's card PNGs gone (before a layers run writes its own, so nothing reads a stale one)."""
        self.mesh.mkdir(parents=True, exist_ok=True)
        for old in self.mesh.glob(f"{self.pid}.card-*.png"):
            old.unlink()

    def save_image(self, name: str, image: Image.Image) -> None:
        """A layer file in the mesh dir (a card() name)."""
        self.mesh.mkdir(parents=True, exist_ok=True)
        image.save(self.mesh / name)

    def view_file(self, view: str) -> Path:
        """The browser viewer's image of this box for `view` ("depth", "seg")."""
        return self.mesh / f"{self.pid}.{view}.png"

    def save_view_meta(self, w: int, h: int, fov: float) -> None:
        """<pid>.json, the box's size and field of view, as the browser viewer reads it."""
        self.mesh.mkdir(parents=True, exist_ok=True)
        (self.mesh / f"{self.pid}.json").write_text(json.dumps({"w": w, "h": h, "fov": fov, "cards": True}))

    def layer_mask(self, layer: dict, shape: tuple[int, int], cut: int = 127) -> np.ndarray:
        """A layer's mask on the box: its PNG's alpha above `cut`, placed at its bbox (which may reach past the box)."""
        h, w = shape
        a = np.asarray(Image.open(self.mesh / layer["png"]).convert("RGBA"))[..., 3] > cut
        x0, y0, x1, y1 = layer["bbox"]
        m = np.zeros((h, w), bool)
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        m[sy0:sy1, sx0:sx1] = a[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        return m

    @property
    def bubbles_file(self) -> Path:
        return self.mesh / f"{self.pid}.bubbles.json"

    def bubbles(self) -> dict | None:
        """bubbles.json: {pid, w, h, fov, font, cap_ratio, bubbles: [...]} (lettering_layer.build, with Transcribe's
        fields joined in by lettering_layer.annotate)."""
        return json.loads(self.bubbles_file.read_text(encoding="utf-8")) if self.bubbles_file.exists() else None

    def save_bubbles(self, bj: dict) -> None:
        self.mesh.mkdir(parents=True, exist_ok=True)
        self.bubbles_file.write_text(json.dumps(bj, indent=1))

    def save_speakers(self, records: list[dict]) -> None:
        """speakers.json: who speaks each bubble (speakers.run_box), kept apart from cards.json, which every layers
        run rewrites."""
        self.mesh.mkdir(parents=True, exist_ok=True)
        (self.mesh / f"{self.pid}.speakers.json").write_text(json.dumps(records, indent=1, ensure_ascii=False),
                                                              encoding="utf-8")

    # ---- the erase
    @property
    def plate_file(self) -> Path:
        return self.plates / "band-plate.png"

    def plate(self) -> np.ndarray | None:
        """The band erase's plate (the whole box, the art outside its cards), or None before the erase."""
        return np.asarray(Image.open(self.plate_file).convert("RGB")) if self.plate_file.exists() else None

    def save_plate(self, rgb: np.ndarray) -> None:
        self.plates.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb).save(self.plate_file)

    def erase_output_file(self, frame: int | None = None) -> Path:
        """Where the band erase keeps a paid output (keyed on its mask): the whole box's, or one frame's retry."""
        self.plates.mkdir(parents=True, exist_ok=True)
        return self.plates / ("band-raw.npz" if frame is None else f"band-raw-f{frame}.npz")

    # ---- Transcribe
    def transcript(self) -> dict:
        """This box's result in out/transcripts.json ({} when Transcribe has not run on it)."""
        return load_transcripts(self.out).get(self.index, {})


class Episode:
    """An episode's out dir: its boxes (box(i)), Transcribe's results and the run log."""

    def __init__(self, out: Path, stem: str):
        self.out, self.stem = Path(out), stem

    def box(self, i: int) -> Box:
        return Box(self.out, pid_of(self.stem, i))

    def transcripts(self) -> dict[int, dict]:
        return load_transcripts(self.out)

    def save_transcripts(self, results: dict[int, dict], drop=()) -> None:
        save_transcripts(self.out, results, drop)

    def save_run_log(self, review: dict, times: dict) -> None:
        """out/run.json, merged into the previous runs': each segmentation task's review per box ("p<i> <task>":
        applied, rejected, cost, truncated replies, calls the cap stopped) and each step's time in seconds."""
        f = self.out / "run.json"
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        d.setdefault("review", {}).update(review)
        d.setdefault("times_s", {}).update({k: round(v, 1) for k, v in times.items()})
        f.write_text(json.dumps(d, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def _transcripts_file(out: Path) -> Path:
    return Path(out) / "transcripts.json"


def load_transcripts(out: Path) -> dict[int, dict]:
    """Transcribe's results for an episode, {box index: result} (the file: {"panels": {...}}); read once per file
    and kept until save_transcripts changes it."""
    f = _transcripts_file(out)
    if f not in _TR:
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        _TR[f] = {int(k): v for k, v in d.get("panels", {}).items()}
    return _TR[f]


def save_transcripts(out: Path, results: dict[int, dict], drop=()) -> None:
    """Merged into transcripts.json: `results` replace those boxes' results, `drop` removes boxes' results (masks
    segmented again: the element ids no longer match)."""
    panels = {k: v for k, v in load_transcripts(out).items() if k not in set(drop)} | dict(results)
    panels = dict(sorted(panels.items()))
    _transcripts_file(out).write_text(json.dumps({"panels": panels}, indent=1, ensure_ascii=False, default=str),
                                      encoding="utf-8")
    _TR[_transcripts_file(out)] = panels
