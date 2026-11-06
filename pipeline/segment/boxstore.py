"""What the steps leave on disk for one box, in one place: where each artefact lives, how it is encoded and how it is
read back. Steps hand data to each other through these files (a rerun reuses them); no other module knows their
paths or formats.

    out/masks/<pid>-lettering.npz, -characters.npz   masks (masks.save_masks: top_order, bit-packed)
    out/masks/<pid>-objects3.npz + .json             the objects' masks (kind "object", the picker's name) and their
                                                     relations, matched by name
    out/masks/<pid>-frames.npz                       the frame step's frames, which are flat, the page, and whether
                                                     the model answered (frames.split)
    out/parallax/mesh/<pid>.cards.json + PNGs        the flat layers (cards.layers) and the viewer's views
    out/parallax/mesh/<pid>.bubbles.json             the lettering's placement (layers.place_lettering); Box.bubbles
                                                     joins Transcribe's text and kinds in when read
    out/parallax/mesh/<pid>.speakers.json            who speaks each bubble (speakers.assign_box), stamped with
                                                     the cards.json it was made from
    out/parallax/plates/<pid>/                       the band erase's plate and paid outputs (layers.erase_box)
    out/transcripts.json                             Transcribe's results per box index
    out/run.json                                     the run log: each review's fixes and cost, each step's time

    ep = Episode(out, stem); box = ep.box(i); box.letters(); box.frames().page; box.scene().layers; box.bubbles()
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from masks import Found, load_masks, save_masks, stamp, top_key

OBJECT_META_KEYS = ("on", "held", "front", "except", "animal")


def pid_of(stem: str, i: int) -> str:
    """A box's id: its episode's stem and its index in the episode."""
    return f"{stem}-p{i:03d}"


def index_of(pid: str) -> int:
    return int(pid.rsplit("-p", 1)[1])


def transcribed(e: dict, kind: str | None) -> dict:
    """A bubble's fields from Transcribe's element for it (e, {} when none), `kind` the segmenter's: the text it read
    (none when it dropped the element), its finer kind (speech, caption, shout) when it gave one, how the line is
    said (delivery, the voice step's style note), and whether the text is all capitals."""
    text = (e.get("text") or "") if e.get("keep", True) and e else ""
    return {"text": text, "kind": e.get("kind") or kind, "delivery": (e.get("delivery") or None) if e else None,
            "pace": (e.get("pace") or None) if e else None, "uppercase": (not text) or text == text.upper()}


def lettering_name(b: dict) -> str:
    """A lettering card's name: its bubble's text (shortened), or "lettering <id>" before Transcribe read it."""
    text = (b.get("text") or "").strip()
    return (text[:24] + "…") if len(text) > 24 else (text or f"lettering {b['id']}")


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


@dataclass
class Layer:
    """One layer of a box's saved scene (cards.json, far to near), its files read through the box. bbox in box px
    (a backdrop's runs past its frame by its margin); z the plane's depth, amp its relief (the peak at peak_z); frame
    None for lettering, which no window clips; bubble the lettering's id in bubbles()."""
    kind: str
    name: str
    frame: int | None
    bbox: tuple[int, int, int, int]
    z: float
    amp: float
    cell: int
    bubble: int | None
    flat: bool
    window_bbox: tuple[int, int, int, int] | None
    window_z: float | None
    _files: dict
    _dir: Path

    @property
    def key(self) -> str:
        """The layer's id in its box: its PNG's name, as speakers.json names cards."""
        return self._files["png"]

    @property
    def path(self) -> Path:
        """The layer's PNG on disk (for a step that embeds or copies the card itself)."""
        return self._dir / self._files["png"]

    @property
    def peak_z(self) -> float:
        """The depth of its nearest point: the reader puts the relief peak at z * (1 - amp)."""
        return self.z * (1 - self.amp)

    @property
    def clipped(self) -> bool:
        """Shown through its frame's window (every layer but lettering)."""
        return isinstance(self.frame, int) and self.kind != "lettering"

    def image(self) -> Image.Image:
        return Image.open(self._dir / self._files["png"]).convert("RGBA")

    def relief(self) -> np.ndarray | None:
        """0..1 per px of its bbox, white = nearest; None without relief."""
        f = self._files.get("relief")
        return None if f is None else np.asarray(Image.open(self._dir / f).convert("L"), np.float32) / 255

    def window(self) -> Image.Image | None:
        """A backdrop's window: the frame's shape (alpha) over window_bbox, at window_z."""
        f = self._files.get("window")
        return None if f is None else Image.open(self._dir / f).convert("RGBA")

    def mask(self, shape: tuple[int, int], cut: int = 127) -> np.ndarray:
        """Its pixels on the box: the image's alpha above `cut`, placed at its bbox (which may reach past the box)."""
        h, w = shape
        a = np.asarray(self.image())[..., 3] > cut
        x0, y0, x1, y1 = self.bbox
        m = np.zeros((h, w), bool)
        sx0, sy0, sx1, sy1 = max(0, x0), max(0, y0), min(w, x1), min(h, y1)
        m[sy0:sy1, sx0:sx1] = a[sy0 - y0:sy1 - y0, sx0 - x0:sx1 - x0]
        return m


@dataclass
class Scene:
    w: int
    h: int
    fov: float
    layers: list[Layer]

    def art(self) -> np.ndarray:
        """The box as the reader sees it (h, w, 3 RGB): its layers pasted far to near on white, the gutters white."""
        canvas = Image.new("RGBA", (self.w, self.h), (255, 255, 255, 255))
        for l in self.layers:
            im = l.image()
            canvas.paste(im, l.bbox[:2], im)
        return np.asarray(canvas.convert("RGB"))


_TR: dict[Path, tuple] = {}  # transcripts.json per out dir: (mtime, {box index: result})


class Box:
    def __init__(self, out: Path, pid: str):
        self.out, self.pid = Path(out), pid

    @property
    def index(self) -> int:
        return index_of(self.pid)

    @property
    def _mesh(self) -> Path:
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

    def letters_stamp(self) -> str | None:
        """The saved lettering's stamp (masks.stamp): what bubbles.json and the transcript were made from."""
        found = self.letters()
        return None if found is None else stamp(found)

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
    @property
    def _cards_file(self) -> Path:
        return self._mesh / f"{self.pid}.cards.json"

    def scene(self) -> Scene | None:
        """The saved flat layers (layers.render: cards.json and its PNGs), far to near, or None before the layers; a
        lettering card is named by its bubble's text (bubbles(): "lettering <id>" until Transcribe has read it)."""
        if not self._cards_file.exists():
            return None
        cj = json.loads(self._cards_file.read_text())
        bj = self.bubbles()
        by_id = {b["id"]: b for b in bj["bubbles"]} if bj else {}
        layers = []
        for l in cj["layers"]:
            name = lettering_name(by_id[l["bubble"]]) if l["kind"] == "lettering" and l.get("bubble") in by_id \
                else l["name"]
            layers.append(Layer(l["kind"], name, l.get("frame"), tuple(l["bbox"]), l["z"], l.get("relief_amp", 0.0),
                                l.get("relief_cell", 0), l.get("bubble"), bool(l.get("flat")),
                                tuple(l["window_bbox"]) if l.get("window_bbox") else None, l.get("window_z"),
                                {k: l[k] for k in ("png", "relief", "window") if l.get(k)}, self._mesh))
        return Scene(cj["w"], cj["h"], cj["fov"], layers)

    def save_cards(self, cj: dict) -> None:
        self._mesh.mkdir(parents=True, exist_ok=True)
        self._cards_file.write_text(json.dumps(cj, indent=1))

    def cards_stamp(self) -> str | None:
        """The saved cards.json's identity: what speakers.json was made from (the card PNG names it keys on)."""
        return hashlib.sha1(self._cards_file.read_bytes()).hexdigest()[:16] if self._cards_file.exists() else None

    def card(self, n: int, part: str = "") -> str:
        """Card n's file name in the mesh dir, as cards.json names it: the card itself, or its "window" or "relief"."""
        return f"{self.pid}.card-{n}" + (f".{part}" if part else "") + ".png"

    def clear_cards(self) -> None:
        """This box's card PNGs gone (before a layers run writes its own, so nothing reads a stale one)."""
        self._mesh.mkdir(parents=True, exist_ok=True)
        for old in self._mesh.glob(f"{self.pid}.card-*.png"):
            old.unlink()

    def save_image(self, name: str, image: Image.Image) -> None:
        """A layer file in the mesh dir (a card() name)."""
        self._mesh.mkdir(parents=True, exist_ok=True)
        image.save(self._mesh / name)

    def view_file(self, view: str) -> Path:
        """The browser viewer's image of this box for `view` ("depth", "seg")."""
        return self._mesh / f"{self.pid}.{view}.png"

    def save_view_meta(self, w: int, h: int, fov: float) -> None:
        """<pid>.json, the box's size and field of view, as the browser viewer reads it."""
        self._mesh.mkdir(parents=True, exist_ok=True)
        (self._mesh / f"{self.pid}.json").write_text(json.dumps({"w": w, "h": h, "fov": fov, "cards": True}))

    @property
    def _bubbles_file(self) -> Path:
        return self._mesh / f"{self.pid}.bubbles.json"

    def bubbles(self) -> dict | None:
        """The box's bubbles: layers.place_lettering's placement (bubbles.json: {pid, w, h, fov, font, cap_ratio,
        letters, bubbles: [...]}) with Transcribe's text and kind joined in (transcribed), only when the transcript
        was made from the same lettering masks (the "letters" stamps match): a transcript of other masks numbers other
        bubbles. Without one, text is "" and the kind the segmenter's, which "segmented_as" keeps either way."""
        if not self._bubbles_file.exists():
            return None
        bj = json.loads(self._bubbles_file.read_text(encoding="utf-8"))
        tr = self.transcript()
        same = bool(tr) and tr.get("letters") is not None and tr.get("letters") == bj.get("letters")
        els = {int(e["id"]): e for e in tr.get("elements", []) if "id" in e} if same else {}
        for b in bj["bubbles"]:
            b["segmented_as"] = b.get("kind")  # the segmenter's: bubble, caption or sfx (a balloon or free lettering)
            b.update(transcribed(els.get(b["id"], {}), b.get("kind")))
        bj["transcribed"] = same
        return bj

    def save_bubbles(self, bj: dict) -> None:
        """bj: the placement only (layers.place_lettering), stamped with the masks it was built on."""
        self._mesh.mkdir(parents=True, exist_ok=True)
        self._bubbles_file.write_text(json.dumps(bj, indent=1))

    @property
    def _speakers_file(self) -> Path:
        return self._mesh / f"{self.pid}.speakers.json"

    def speakers(self) -> list[dict] | None:
        """Who speaks each bubble (speakers.assign_box), or None when there is none or it was made from other layers
        than the saved cards.json: its records name card PNGs, which every layers run rewrites."""
        if not self._speakers_file.exists():
            return None
        d = json.loads(self._speakers_file.read_text(encoding="utf-8"))
        return d["records"] if d.get("cards") == self.cards_stamp() else None

    def save_speakers(self, records: list[dict]) -> None:
        """speakers.json, kept apart from cards.json and stamped with it (cards_stamp)."""
        self._mesh.mkdir(parents=True, exist_ok=True)
        self._speakers_file.write_text(json.dumps({"cards": self.cards_stamp(), "records": records}, indent=1,
                                                  ensure_ascii=False), encoding="utf-8")

    # ---- the erase
    @property
    def _plate_file(self) -> Path:
        return self.plates / "band-plate.png"

    def has_plate(self) -> bool:
        return self._plate_file.exists()

    def plate(self) -> np.ndarray | None:
        """The band erase's plate (the whole box, the art outside its cards), or None before the erase."""
        return np.asarray(Image.open(self._plate_file).convert("RGB")) if self.has_plate() else None

    def save_plate(self, rgb: np.ndarray) -> None:
        self.plates.mkdir(parents=True, exist_ok=True)
        Image.fromarray(rgb).save(self._plate_file)

    def erase_output_file(self, frame: int | None = None) -> Path:
        """Where the band erase keeps a paid output (keyed on its mask): the whole box's, or one frame's retry."""
        return self.plates / ("band-raw.npz" if frame is None else f"band-raw-f{frame}.npz")

    # ---- Transcribe
    def transcript(self) -> dict:
        """This box's result in out/transcripts.json ({} when Transcribe has not run on it)."""
        return load_transcripts(self.out).get(self.index, {})

    def transcript_current(self, letters: list[Found]) -> bool:
        """Whether Transcribe's result for this box was made from these lettering masks (their stamp), or there is
        no lettering to read: a box segmented again is read again."""
        return not letters or self.transcript().get("letters") == stamp(letters)


class Episode:
    """An episode's out dir: its boxes (box(i)), Transcribe's results and the run log."""

    def __init__(self, out: Path, stem: str):
        self.out, self.stem = Path(out), stem

    @property
    def run(self) -> Path:
        """The run this episode belongs to: out is <run>/dataset/<episode>. What is shared across a run's episodes
        (the series casts, <run>/cast/<series>/) lives beside dataset/."""
        return self.out.parent.parent

    def box(self, i: int) -> Box:
        return Box(self.out, pid_of(self.stem, i))

    def transcripts(self) -> dict[int, dict]:
        return load_transcripts(self.out)

    def save_transcripts(self, results: dict[int, dict], letters: dict[int, list[Found]]) -> None:
        """Transcribe's results ({box index: result}) saved, each stamped with the lettering masks it was read from
        (letters[i]), so Box.transcript_current and Box.bubbles can tell a current result from a stale one."""
        save_transcripts(self.out, {i: {**r, "letters": stamp(letters[i])} for i, r in results.items()})

    def save_run_log(self, review: dict, times: dict) -> None:
        """out/run.json, merged into the previous runs': each segmentation task's review per box ("p<i> <task>":
        applied, rejected, cost, truncated replies, calls the cap stopped), the sound-effect refinement's statuses per
        box ("p<i> sfx": count per status) and each step's time in seconds."""
        f = self.out / "run.json"
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        d.setdefault("review", {}).update(review)
        d.setdefault("times_s", {}).update({k: round(v, 1) for k, v in times.items()})
        f.write_text(json.dumps(d, indent=1, ensure_ascii=False, default=str), encoding="utf-8")


def _transcripts_file(out: Path) -> Path:
    return Path(out) / "transcripts.json"


def load_transcripts(out: Path) -> dict[int, dict]:
    """Transcribe's results for an episode, {box index: result} (the file: {"panels": {...}}), each stamped with the
    lettering masks it was made from ("letters", masks.stamp); read again when the file changes."""
    f = _transcripts_file(out)
    mtime = f.stat().st_mtime_ns if f.exists() else None
    if f not in _TR or _TR[f][0] != mtime:
        d = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        _TR[f] = (mtime, {int(k): v for k, v in d.get("panels", {}).items()})
    return dict(_TR[f][1])


def save_transcripts(out: Path, results: dict[int, dict]) -> None:
    """Merged into transcripts.json: `results` replace those boxes' results. Written whole and then swapped in:
    episode.py transcribes while the layers step reads the file."""
    panels = dict(sorted((load_transcripts(out) | dict(results)).items()))
    f = _transcripts_file(out)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps({"panels": panels}, indent=1, ensure_ascii=False, default=str), encoding="utf-8")
    tmp.replace(f)
