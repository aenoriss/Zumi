"""fresh.py's rule on small made-up inputs: a stamp is the same wherever it is computed. No step runs, no call is
made, nothing outside a temporary folder is written.

    python test_fresh.py        (or pytest test_fresh.py)
"""
from __future__ import annotations

import json
import tempfile
import types
from pathlib import Path

import numpy as np
from PIL import Image, ImageFont

import fresh
import places
from boxstore import content_stamp
import props
import settings


def _image(seed: int = 0, size=(96, 64)) -> Image.Image:
    return Image.fromarray(np.random.default_rng(seed).integers(0, 255, (size[1], size[0], 3), np.uint8))


def test_pixels_not_bytes():
    """The same pixels encoded two ways are one stamp; other pixels are another."""
    with tempfile.TemporaryDirectory() as t:
        t, im = Path(t), _image()
        im.save(t / "a.png", compress_level=1)
        im.save(t / "b.png", compress_level=9, optimize=True)
        assert (t / "a.png").read_bytes() != (t / "b.png").read_bytes()
        assert fresh.pixels(t / "a.png") == fresh.pixels(t / "b.png") == fresh.pixels(im)
        other = im.copy()
        other.putpixel((3, 3), (1, 2, 3))
        assert fresh.pixels(other) != fresh.pixels(im)
        clear = im.convert("RGBA")
        clear.putpixel((3, 3), (*im.getpixel((3, 3)), 0))  # the same colours, one pixel transparent
        assert fresh.pixels(clear) != fresh.pixels(im.convert("RGBA")) != fresh.pixels(im)
        # the stamps that name images: a place's erase and geometry, a prop's view
        for level, d in ((1, t / "one"), (9, t / "two")):
            d.mkdir()
            for name, seed in (("shown.png", 1), ("erase-mask.png", 2), ("view.png", 3), ("plate.png", 4), ("view16.png", 5)):
                _image(seed).save(d / name, compress_level=level)
        s = {"name": "A room", "description": "plain"}
        for stamp in (places.plate_stamp, lambda d, **k: places.geometry_stamp("back", d, **k),
                      lambda d, **k: places.pano_stamp(s, [0], d, **k)):
            assert stamp(t / "one") == stamp(t / "two")
            assert stamp(t / "one", as_bytes=True) != stamp(t / "two", as_bytes=True)  # the rule before did differ
        _image(9).save(t / "two" / "erase-mask.png")
        assert places.plate_stamp(t / "one") != places.plate_stamp(t / "two")


def test_source_line_endings():
    """A module checked out with CRLF is the same source as with LF; an edit is another."""
    with tempfile.TemporaryDirectory() as t:
        t, text = Path(t), b"X = 1\n\ndef f():\n    return X\n"
        (t / "lf.py").write_bytes(text)
        (t / "crlf.py").write_bytes(text.replace(b"\n", b"\r\n"))
        (t / "edit.py").write_bytes(text.replace(b"1", b"2"))
        src = {n: fresh.source(types.SimpleNamespace(__file__=str(t / f"{n}.py"))) for n in ("lf", "crlf", "edit")}
        assert fresh.digest(src["lf"]) == fresh.digest(src["crlf"]) != fresh.digest(src["edit"])
        assert fresh.digest("x", src["lf"]) == fresh.digest("x", t / "lf.py")  # an LF file's old stamps still hold
        # a saved JSON (an objects' .json, a box's cards.json) written on Windows is CRLF: the same content
        (t / "lf.json").write_bytes(b'[\n {"a": 1}\n]')
        (t / "crlf.json").write_bytes(b'[\r\n {"a": 1}\r\n]')
        assert content_stamp(t / "lf.json") == content_stamp(t / "crlf.json")


def test_pick_ignores_the_clock_within_a_step():
    """A place open 46 s or 59 s allows the same props and gets the same text and stamp; 61 s is the next step."""
    imgs = [("view", _image(1)), ("p001/f0", _image(2))]
    sources = [fresh.pixels(im) for _, im in imgs]

    def stamp(seconds: float) -> str:
        return props.pick_stamp(sources, props.pick_text(props.max_props(seconds), "A room.", imgs, "p001: hello"))

    assert stamp(46.0) == stamp(59.9) != stamp(61.0)
    assert "Open for" not in props.pick_text(3, "A room.", imgs, "p001: hello")
    assert props.pick_stamp(sources, "t") != props.pick_stamp([sources[0], fresh.pixels(_image(3))], "t")
    # a pick stamped by the rule before (seconds in the text, the images as sent) is recognised, once
    text = props.pick_text(4, "A room.", imgs, "p001: hello")
    head, tail = text.split("\n## The images\n", 1)
    old = {"stamp": props.sent_stamp(imgs, f"{head}Open for 47 s.\n\n## The images\n{tail}"), "seconds": 46.6, "max": 4}
    assert props.stamp_before(old, imgs, text, 4) == old["stamp"]
    assert props.stamp_before(old, imgs, text, 5) is None                    # another number of props allowed
    assert props.stamp_before(old, [imgs[0], ("p001/f0", _image(3))], text, 4) is None  # another image


def test_settings_stamp_not_the_rendered_sheet():
    """Another font renders other sheets; the stamp, taken from the frames and the layout, is the same."""
    items = [(f"p{k:03d}/f0", _image(k, (200, 120))) for k in range(3)]
    stamp, sheet = settings.stamp_of(items), settings.sheets(items)[0][1].tobytes()
    font, settings._font = settings._font, lambda size: ImageFont.load_default(size=size + 6)
    try:
        assert settings.sheets(items)[0][1].tobytes() != sheet
        assert settings.stamp_of(items) == stamp
        assert settings.sheets_stamp([k for k, _ in items], settings.sheets(items)) != \
            settings.sheets_stamp([k for k, _ in items], [("sheet-1.png", Image.frombytes("RGB", settings.sheets(items)[0][1].size, sheet))])
    finally:
        settings._font = font
    assert settings.stamp_of(items[:2] + [("p002/f0", _image(7, (200, 120)))]) != stamp   # a frame redrawn
    assert settings.stamp_of([("p009/f0", im) for _, im in items]) != stamp                # other frame ids


def test_adoption_once():
    """A stamp of the rule before is accepted when that rule still gives it, and saved in today's form."""
    with tempfile.TemporaryDirectory() as t:
        f = Path(t) / "stamps.json"
        f.write_text(json.dumps({"a": "old", "b": "old"}), encoding="utf-8")
        st = fresh.Stamps(f)
        assert not st.current("a", "new")
        assert not st.current("a", "new", legacy=lambda: "other")
        assert st.current("a", "new", legacy=lambda: "old")
        assert json.loads(f.read_text(encoding="utf-8")) == {"a": "new", "b": "old"}
        assert st.current("a", "new") and not st.current("b", "new", Path(t) / "missing.png", legacy="old")
        assert not fresh.holds(None, "new", None)


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print(f"ok  {name}: {test.__doc__.strip().splitlines()[0]}")
