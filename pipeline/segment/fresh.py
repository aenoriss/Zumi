"""Is a saved output still current? The one rule every step answers by.

An output is current when its file is there and the stamp saved for it equals the stamp computed now. A stamp is a
digest of what the output is made from: its inputs (files by content, the stamps of the outputs before it) and its
recipe (the prompt, the model, the seeds and constants that shape the result). So a changed input reaches every
output after it, and a changed prompt or model makes the call again instead of leaving an old result in place. Before
2026-11-10 each step had its own rule (none, "the file exists", inputs only), and a changed music prompt kept the old
song while a plain rerun paid for every review again (docs: the chain review of 2026-11-10).

    digest(*parts) -> str            files (Path) by content, anything else as JSON
    recipe(module, skip=()) -> str   a module's constants: its UPPERCASE names holding plain values
    source(module) -> Path           a module's own file, as a digest part: for a step that costs nothing to run
                                     again, any edit of its code makes it again
    Stamps(path)                     the stamps of one folder's outputs, saved as JSON {key: stamp}
        .current(key, stamp, *files) the saved stamp is this one and every file exists
        .made(key, stamp)            saved, once the output is written
        .drop(key)                   forgotten (its output was removed)

A paid step names its recipe constant by constant, so that only what shapes the result makes it pay again; a step
that costs no money may take recipe(module) or source(module) whole.
"""
from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path


def digest(*parts) -> str:
    """A short hash of files (by content) and JSON values."""
    h = hashlib.sha256()
    for p in parts:
        h.update(p.read_bytes() if isinstance(p, Path) else json.dumps(p, sort_keys=True).encode())
    return h.hexdigest()[:16]


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


def source(module) -> Path:
    """The module's own file, to pass to digest."""
    return Path(module.__file__)


class Stamps:
    """The stamps of one folder's outputs, a JSON file {key: stamp} read once and written at every change."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._saved = json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {}

    def get(self, key: str):
        return self._saved.get(key)

    def current(self, key: str, stamp: str, *files: Path) -> bool:
        return self._saved.get(key) == stamp and all(Path(f).exists() for f in files)

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
        self.path.write_text(json.dumps(self._saved, indent=1, sort_keys=True), encoding="utf-8")
