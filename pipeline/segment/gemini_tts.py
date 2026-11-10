"""Gemini 3.8 Flash TTS, one adapter of the voice seam (voices.py), through the Gemini API (the interactions endpoint,
as lyria.py): designed voices and lines. Its voice ids live in the cast record under "id_gemini", its lines in
<episode>/audio-gemini/.

The model wants the words as a verbatim transcript and the delivery apart from them: a designed voice carries the
permanent traits (age, gender, timbre, accent: POST /v1beta/voices, type "prompted", a persistent voice_... id), a
short `speech_metadata.style` carries this line's emotion, pace and volume ("whispered urgently", "speaking slowly"),
capitals mark stress (so a line lettered in caps goes to sentence case, as for Inworld), and momentary events go as
inline tags (<laugh>, <sigh>, <short pause>). Nothing else: the docs say traits or meta-instructions in the style make
the voice drift. There is no speaking-rate field and no previous-lines context; the rate becomes a pace word in the
style. WAV 24 kHz mono 16-bit. Free of charge on the free tier; on a billed project 9 USD per million audio tokens at
25 tokens a second (2026-11-07), so a line costs a fraction of a cent, recorded in the gemini ledger from the WAV's
length. The key is GEMINI_API_KEY in pipeline/.env (lyria._key).
"""
from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request

from lyria import REVISION, _key
from spend import no_call_offline, record, reserve

API = "https://generativelanguage.googleapis.com/v1beta"
MODEL = "gemini-3.8-flash-tts"
NAME = "gemini"             # the backend's name (voices.backend)
ENGINE = MODEL              # the voice's engine in the .zumi
VOICE_ID = "id_gemini"      # the cast record's key for this backend's voice id
AUDIO_DIR = "audio-gemini"  # <episode>/audio-gemini/: this backend's lines and lines.json
SAMPLE_SUFFIX = ".gemini"   # <cast>/voices/K<n>.gemini.wav
SAMPLE_RATE = 24000
TOKENS_PER_S = 25          # audio output tokens per second of speech (pricing page)
PRICE_AUDIO = 9.0 / 1e6    # USD per audio token through 2026
PRICE_TEXT = 0.5 / 1e6     # USD per text token, about four characters each
DESIGN_USD = 0.01          # a voice design: not priced on the page, a small estimate reserved and recorded
RESERVE_USD = 0.01         # per line, the worst case reserved before sending
SPEAKING_RATE = 1.0        # no rate field: a rate off 1.0 becomes a pace word in the style (pace_words)


def _post(path: str, body: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Api-Revision": REVISION,
                                          "x-goog-api-key": _key()})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read()[:400].decode(errors="replace")
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(15 * (attempt + 1))   # the free tier's requests per minute; a 429 clears in under a minute
                continue
            raise RuntimeError(f"Gemini TTS {path}: HTTP {e.code} {detail}") from None
    raise RuntimeError(f"Gemini TTS {path}: no reply")


def design_voice(description: str, display_name: str, preview_text: str = "", language_code: str = "en-US",
                 gender: str | None = None, tag: str = "") -> dict:
    """A voice designed from a one-or-two-sentence description of its permanent traits, stored in the project:
    {"id": the voice_... id, "sample": the preview WAV bytes, "cost"}. preview_text is unused: the service picks its
    own preview."""
    no_call_offline(tag or "design_voice")
    voice = {"model": MODEL, "type": "prompted", "display_name": display_name[:60], "language_code": language_code,
             "prompted": {"input": description.strip()[:600]}}
    if gender in ("male", "female"):
        voice["gender"] = gender
    with reserve(DESIGN_USD, tag or "design_voice"):
        resp = _post("/voices", {"store": True, "voice": voice})
        record("gemini", DESIGN_USD, model=MODEL, tag=tag, call="design_voice")
    vid = resp.get("id") or (resp.get("voice") or {}).get("id")
    if not vid:
        raise RuntimeError(f"Gemini TTS: no voice id in the reply ({json.dumps(resp)[:300]})")
    sample = base64.b64decode(((resp.get("sample_audio") or {}).get("data")) or b"")
    return {"id": vid, "sample": sample, "cost": DESIGN_USD}


def direct(style: str | None, pace: str | None, factor: float, char: dict | None) -> dict:
    """How one line is directed on Gemini: no brief (the model takes a short style per line, sent by speech), and a
    rate that is only the line's pace factor (the designed voice carries the character's own tempo)."""
    return {"brief": None, "rate": round(SPEAKING_RATE * factor, 3)}


def pace_words(rate: float) -> str | None:
    """The style's pace from a speaking rate: under 0.97 slowly, over 1.05 quickly, else nothing."""
    if rate < 0.97:
        return "speaking slowly"
    if rate > 1.05:
        return "speaking quickly"
    return None


def speech(text: str, voice: str, style: str | None = None, tag: str = "", context: list[str] | None = None,
           rate: float = SPEAKING_RATE, brief: str | None = None) -> tuple[bytes, float, str | None]:
    """One line as a WAV in a designed or prebuilt voice. style is this line's delivery (the balloon's kind and what
    the drawing shows: "shouting, gleeful"), sent as speech_metadata.style with the pace from rate; the text comes as
    the model should read it (voices.spoken); context and brief are not sent (the API has neither). Returns (WAV bytes,
    the cost in USD estimated from the audio's length, None)."""
    no_call_offline(tag or "speech")
    said = text[:2000]
    how = ", ".join(s for s in ((style or "").strip(), pace_words(rate)) if s)
    content = {"type": "text", "text": said}
    if how:
        content["annotations"] = [{"type": "speech_metadata", "style": how}]
    body = {"model": MODEL, "input": [{"type": "user_input", "content": [content]}],
            "response_format": {"type": "audio"}, "generation_config": {"speech_config": [{"voice": voice}]}}
    with reserve(RESERVE_USD, tag or "speech"):
        resp = _post("/interactions", body)
        wav = b""
        for s in resp.get("steps", []):
            if s.get("type") != "model_output":
                continue
            for c in s.get("content", []):
                if c.get("type") == "audio" and c.get("data"):
                    wav = base64.b64decode(c["data"])
        if not wav:
            raise RuntimeError(f"Gemini TTS: no audio in the reply ({json.dumps(resp)[:300]})")
        seconds = max(0, len(wav) - 44) / (SAMPLE_RATE * 2)
        cost = seconds * TOKENS_PER_S * PRICE_AUDIO + len(said) / 4 * PRICE_TEXT
        record("gemini", cost, model=MODEL, tag=tag, call="speech", voice=voice, seconds=round(seconds, 2))
    return wav, cost, None
