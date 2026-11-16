"""sfx.py on small made-up inputs: the rules, the length, the finish of a synthetic sound, the cache, the stamps and the
offline refusal. No paid call is made (the purchase is replaced by a synthetic sound), nothing outside a temporary
folder is written.

    python test_sfx.py        (or pytest test_sfx.py)
"""
from __future__ import annotations

import io
import json
import struct
import tempfile
from pathlib import Path

import numpy as np

import fal
import fresh
import sfx
import spend
from boxstore import Episode

RATE = 48000


def _tone(seconds: float, lead: float = 0.0, tail: float = 0.0, amp: float = 0.5, rate: int = RATE) -> np.ndarray:
    """A decaying 1 kHz burst with `lead` and `tail` seconds of silence around it, stereo."""
    t = np.arange(int(seconds * rate)) / rate
    burst = amp * np.sin(2 * np.pi * 1000 * t) * np.exp(-3 * t)
    x = np.concatenate([np.zeros(int(lead * rate)), burst, np.zeros(int(tail * rate))])
    return np.stack([x, x], 1)


def _wav(audio: np.ndarray, rate: int = RATE) -> bytes:
    import soundfile as sf
    buf = io.BytesIO()
    sf.write(buf, audio, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def _item(i: int, text: str, slot: float = 1.5, place: str | None = "The cafe: a warm cafe") -> dict:
    return {"id": f"p{i:03d}/b1", "pid": f"ep-p{i:03d}", "bubble": 1, "index": i, "text": text, "frame": 0,
            "slot": slot, "startTime": 10.0 * i, "place": place, "drawn": ["Dan"], "window": (0, 0, 10, 10),
            "before": ["Dan: hello"], "after": ["Robot: no"]}


def test_shape_and_rules():
    """The onomatopoeia's hits and drawn-out letters give the rules' length and preview prompt."""
    assert sfx.shape("CLANC-CLANC-CLANC!") == {"word": "CLANC", "hits": 3, "drawn": 0, "loud": True}
    assert sfx.shape("SHOOOOOSH!")["drawn"] == 4 and sfx.shape("TICK")["hits"] == 1
    assert sfx.rule_seconds("TICK") == 0.35
    assert sfx.rule_seconds("CLANC-CLANC-CLANC!") == 1.05
    assert sfx.rule_seconds("SHOOOOOSH!") == 0.95
    p = sfx.rule_prompt("CLANC-CLANC-CLANC!", "The cafe")
    assert "3 quick hits" in p and "loud" in p and p.endswith("in The cafe")


def test_length_clamp():
    """A length is kept within 0.3-4 s and at most the slot plus RING_S; bought at least 0.5 s, in tenths."""
    assert sfx.target_seconds(0.1, 1.5) == sfx.MIN_S
    assert sfx.target_seconds(9.0, 5.0) == sfx.MAX_S
    assert sfx.target_seconds(3.5, 1.5) == 1.5 + sfx.RING_S
    assert sfx.target_seconds(None, 1.5, "TICK") == 0.35  # no proposal: the rules'
    assert sfx.target_seconds("long", 1.5, "TICK") == 0.35
    assert sfx.request_seconds(0.35) == sfx.API_MIN_S and sfx.request_seconds(1.21) == 1.3 and sfx.request_seconds(1.2) == 1.2


def test_prompt_from_reply_and_context():
    """The model's prompt and seconds win where given (clamped); a sound effect it left out gets the rules'; the
    material names the text, place, who is drawn and the lines around it."""
    its = [_item(4, "CLANC-CLANC-CLANC!"), _item(19, "TICK", place=None)]
    plan = sfx.merge({"sounds": [{"id": "p004/b1", "prompt": "three metal ladle clanks on a steel pot", "seconds": 9,
                                  "source": "ladle"}]}, its)
    assert plan["p004/b1"] == {"prompt": "three metal ladle clanks on a steel pot", "source": "ladle", "seconds": 2.5}
    assert plan["p019/b1"]["source"] is None and plan["p019/b1"]["seconds"] == 0.35
    assert sfx.sound_prompt("a crack of glass.") == f"a crack of glass. {sfx.STYLE}"
    text = sfx.material(its)
    for want in ('p004/b1: "CLANC-CLANC-CLANC!"', "place: The cafe: a warm cafe", "drawn in the frame: Dan",
                 "before: Dan: hello", "after: Robot: no", "place: unknown"):
        assert want in text, want


def test_finish():
    """A sound with silence around it comes out mono at 44.1 kHz, trimmed, cut to its length, faded, at the target
    RMS or held at the peak ceiling."""
    x = sfx.finish(_tone(1.0, lead=0.4, tail=0.6), RATE, 0.8)
    assert x.dtype == np.float32 and x.ndim == 1
    assert len(x) == int(0.8 * sfx.OUT_RATE)  # trimmed then cut: 0.8 s of sound, the lead gone
    assert abs(x[0]) < 1e-3 and abs(x[-1]) < 1e-3  # faded in and out
    peak, rms = float(np.max(np.abs(x))), float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    assert peak <= 10 ** (sfx.PEAK_DB / 20) + 1e-4
    assert abs(20 * np.log10(rms) - sfx.SFX_RMS_DB) < 0.2 or abs(peak - 10 ** (sfx.PEAK_DB / 20)) < 1e-3
    short = sfx.finish(_tone(0.2, lead=0.3, tail=0.3), RATE, 2.0)  # shorter than asked: its own length, no padding
    assert len(short) <= int(0.2 * sfx.OUT_RATE) + int(sfx.PRE_S * sfx.OUT_RATE) + 1
    spike = np.zeros((RATE, 1))
    spike[RATE // 2] = 0.9  # all peak: the ceiling decides, not the RMS
    assert float(np.max(np.abs(sfx.finish(spike, RATE, 1.0)))) <= 10 ** (sfx.PEAK_DB / 20) + 1e-4
    assert len(sfx.finish(np.zeros((RATE, 2)), RATE, 1.0)) == 0


def test_wav_header():
    """The written WAV is 44.1 kHz mono 16-bit PCM behind a plain 44-byte header, nothing after the samples."""
    w = sfx.wav_bytes(np.zeros(441, dtype=np.float32))
    assert w[:4] == b"RIFF" and w[8:16] == b"WAVEfmt " and w[36:40] == b"data" and len(w) == 44 + 882
    fmt, ch, rate, _, _, bits = struct.unpack("<HHIIHH", w[20:36])
    assert (fmt, ch, rate, bits) == (1, 1, 44100, 16)


def test_stamps_stable():
    """A sound's key is the same for the same prompt and bought length, other for another prompt; lengths that buy
    the same seconds share it; the finish's stamp follows the cut length."""
    p = sfx.sound_prompt("a glass cracks")
    assert sfx.sound_key(p, 0.35) == sfx.sound_key(p, 0.4) == sfx.sound_key(p, 0.5)
    assert sfx.sound_key(p, 0.8) != sfx.sound_key(p, 0.5) != sfx.sound_key(sfx.sound_prompt("a door slams"), 0.5)
    k = sfx.sound_key(p, 0.8)
    assert sfx.finish_stamp(k, 0.8) == sfx.finish_stamp(k, 0.8) != sfx.finish_stamp(k, 0.7)
    assert sfx.plan_stamp("a\nb", [["px", [0, 0, 1, 1]]]) == sfx.plan_stamp("a\nb", [["px", (0, 0, 1, 1)]])


def _run(t: Path, plan: dict, its: list[dict], bought: list, refuse: bool = False):
    """sfx_step on a temporary episode with plan_step and the purchase replaced; refuse: the purchase refuses as
    fal.sound_effect does in an offline run (OfflineCall, its first line), whatever ZUMI_OFFLINE this test runs under."""
    real_plan, real_buy = sfx.plan_step, fal.sound_effect

    def buy(prompt, seconds, tag=""):
        if refuse:
            raise spend.OfflineCall(f"{tag}: an offline run, no paid call")
        bought.append((prompt, seconds))
        return _wav(_tone(seconds, lead=0.05)), seconds * fal.SFX_USD_PER_S

    sfx.plan_step = lambda ep, ch, n, dry=False: (its, plan, True)
    fal.sound_effect = buy
    try:
        return sfx.sfx_step(Episode(t, "ep"), None, 30)
    finally:
        sfx.plan_step, fal.sound_effect = real_plan, real_buy


def test_cache_reuse_and_offline():
    """Two balloons with the same description and length buy one sound and share its file; a second run buys
    nothing; an offline run buys nothing and reports the balloons left silent."""
    its = [_item(4, "TICK"), _item(7, "TICK"), _item(10, "SPLAFF")]
    plan = {"p004/b1": {"prompt": "a clock ticks once", "seconds": 0.35, "source": "clock"},
            "p007/b1": {"prompt": "a clock ticks once", "seconds": 0.4, "source": "clock"},
            "p010/b1": {"prompt": "a wet splat of coffee", "seconds": 0.9, "source": "cup"}}
    with tempfile.TemporaryDirectory() as t:
        t, bought = Path(t), []
        assert _run(t, plan, its, bought) == 0
        assert len(bought) == 2 and sorted(s for _, s in bought) == [0.5, 0.9]
        index = json.loads((t / "sfx" / "sfx.json").read_text(encoding="utf-8"))
        assert index["ep-p004.b1"]["key"] == index["ep-p007.b1"]["key"] != index["ep-p010.b1"]["key"]
        assert len(list((t / "sfx" / "sounds").glob("*.wav"))) == 3  # two keys, but p004 and p007 are cut to their own length
        assert set(sfx.sound_of(Episode(t, "ep"))) == {("ep-p004", 1), ("ep-p007", 1), ("ep-p010", 1)}
        assert _run(t, plan, its, bought) == 0 and len(bought) == 2  # current: nothing bought again
    with tempfile.TemporaryDirectory() as t:
        t, bought = Path(t), []
        assert _run(t, plan, its, bought, refuse=True) == 3
        assert not bought and json.loads((t / "sfx" / "sfx.json").read_text(encoding="utf-8")) == {}


if __name__ == "__main__":
    for name, test in list(globals().items()):
        if name.startswith("test_"):
            test()
            print(f"ok  {name}: {test.__doc__.strip().splitlines()[0]}")
