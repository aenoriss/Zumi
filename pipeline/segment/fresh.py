"""Is a saved output still current? The one rule every step answers by.

An output is current when its file is there and the stamp saved for it equals the stamp computed now. A stamp is a
digest of what the output is made from: its inputs (files by content, the stamps of the outputs before it) and its
recipe (the prompt, the model, the seeds and constants that shape the result). So a changed input reaches every
output after it, and a changed prompt or model makes the call again instead of leaving an old result in place. Before
2026-11-10 each step had its own rule (none, "the file exists", inputs only), and a changed music prompt kept the old
song while a plain rerun paid for every review again (docs: the chain review of 2026-11-10).

A stamp is taken over what the step's result depends on, in a form that is the same on any machine (2026-11-15: an
episode made on Linux and downloaded here would have paid again for its settings, prop picks and props, none of
whose inputs had changed):

- an image by its decoded pixels (pixels), never by its file's bytes: the same pixels saved by another build of the
  image library are other bytes;
- an image the step renders itself (a contact sheet, a resized copy) by what it is rendered from and the constants
  of the rendering, never by the rendered pixels: fonts and resampling differ between machines;
- a text by its characters with LF line endings (text, source; a str built in Python already is), never a saved
  text file's bytes;
- a number that only jitters (a duration on the clock) rounded to the step it decides by, or left out;
- what a model is told only as context, and would not change its answer, is in neither the prompt nor the stamp.

    digest(*parts) -> str            files (Path) and bytes by content, anything else as JSON
    pixels(image) -> str             an image (or its file) by its decoded pixels, as a digest part
    recipe(module, skip=()) -> str   a module's constants: its UPPERCASE names holding plain values
    text(path) -> bytes              a text file (JSON, code) with LF line endings, as a digest part
    source(module) -> bytes          a module's own text, as a digest part: for a step that costs nothing to run
                                     again, any edit of its code makes it again
    holds(saved, stamp, legacy)      the saved stamp is this one, or the one the rule before gave (below)
    Stamps(path)                     the stamps of one folder's outputs, saved as JSON {key: stamp}
        .current(key, stamp, *files) the saved stamp is this one and every file exists
        .made(key, stamp)            saved, once the output is written
        .drop(key)                   forgotten (its output was removed)

A paid step names its recipe constant by constant, so that only what shapes the result makes it pay again; a step
that costs no money may take recipe(module) or source(module) whole.

When a stamp's rule changes, every saved stamp of that kind stops matching, which would itself make everything
again once. So a check may name the stamp the rule before gives now (`legacy`): a saved stamp equal to it proves the
output current under the old rule on this machine, and it is saved again in the new form, said in the log. Where the
old stamp cannot be computed again here (an output made on another machine under a rule that was not portable),
nothing is adopted silently: adopt_stamps.py lists such outputs with its evidence and writes only when told to.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path


def digest(*parts) -> str:
    """A short hash of files and bytes (by content) and JSON values."""
    h = hashlib.sha256()
    for p in parts:
        h.update(p.read_bytes() if isinstance(p, Path) else p if isinstance(p, bytes)
                 else json.dumps(p, sort_keys=True).encode())
    return h.hexdigest()[:16]


def pixels(image) -> str:
    """An image's identity by its decoded pixels: its shape and raw bytes, RGBA when it has transparency, else RGB.
    `image`: a PIL image or an image file. (A box image's stamp since 2026-11-10, boxstore.image_stamp until
    2026-11-15: the same hash, so those stamps hold.)"""
    from PIL import Image
    opened = None if isinstance(image, Image.Image) else Image.open(image)
    img = opened or image
    a = img.convert("RGBA" if img.mode in ("RGBA", "LA", "PA") or "transparency" in img.info else "RGB")
    if opened:
        opened.close()
    return hashlib.sha1(f"({a.height}, {a.width}, {len(a.getbands())})".encode() + a.tobytes()).hexdigest()[:16]


def _plain(v) -> bool:
    if v is None or isinstance(v, (str, int, float, bool)):
        return True
    if isinstance(v, (list, tuple)):
        return all(_plain(x) for x in v)
    return isinstance(v, dict) and all(isinstance(k, str) and _plain(x) for k, x in v.items())


def recipe(module, skip: tuple[str, ...] = ()) -> str:
    """The digest of a module's constants: every UPPERCASE name holding a plain value (text, numbers, lists and
    dicts of them), except those in `skip` (a constant that does not shape the result, such as a worker count)."""
    names = sorted(k for k, v in vars(module).items() if k.isupper() and k not in skip and _plain(v))
    return digest([[k, getattr(module, k)] for k in names])


def text(path: Path) -> bytes:
    """A text file's bytes with LF line endings, to pass to digest: Python on Windows writes a str's "\\n" as CRLF,
    so the same JSON or code saved or checked out there is other bytes. An LF file gives its own bytes: its stamps
    taken by bytes before 2026-11-15 still hold."""
    return Path(path).read_bytes().replace(b"\r\n", b"\n")


def source(module) -> bytes:
    """The module's own text (text), to pass to digest: a checkout with CRLF is the same code."""
    return text(module.__file__)


def holds(saved, stamp: str, legacy=None, what: str = "") -> bool:
    """The saved stamp is `stamp`, or `legacy`: what the rule before gives now (a stamp, or a function giving it,
    called only when `saved` is not `stamp`). True on `legacy` means the output is current and its stamp is still in
    the old form: the caller saves `stamp` in its place (`what` names the output in the log)."""
    if saved == stamp:
        return True
    if saved is None or legacy is None or saved != (legacy() if callable(legacy) else legacy):
        return False
    print(f"  stamp adopted{': ' + what if what else ''} (current under the rule before, saved in today's form)")
    return True


class Stamps:
    """The stamps of one folder's outputs, a JSON file {key: stamp} read once and written at every change.
    current(..., legacy=) adopts a stamp of the rule before (holds) and saves today's."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._saved = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def get(self, key: str):
        return self._saved.get(key)

    def current(self, key: str, stamp: str, *files: Path, legacy=None) -> bool:
        saved = self._saved.get(key)
        if not all(Path(f).exists() for f in files) or not holds(saved, stamp, legacy, f"{self.path.parent.name} {key}"):
            return False
        if saved != stamp:
            self.made(key, stamp)
        return True

    def made(self, key: str, stamp: str) -> None:
        with self._lock:
            self._saved[key] = stamp
            self._write()

    def drop(self, key: str) -> None:
        with self._lock:
            if self._saved.pop(key, None) is not None:
                self._write()

    def _write(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")  # written whole, then swapped in: a run killed here leaves the old stamps
        tmp.write_text(json.dumps(self._saved, indent=1, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)
