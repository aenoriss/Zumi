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

The model takes TTS_DAILY_REQUESTS requests a day (100; ZUMI_TTS_DAILY_REQUESTS for a higher tier). Every request
that reaches the service is counted by the quota's day in a file beside the ledgers (COUNTER; the ledger alone has
only the calls that returned audio): lines and voice designs alike, a design counted although it may not draw on
the model's quota, so the count can only run ahead of Google's. requests_left() is what voices.py plans a run by,
and a request that would pass the limit, or a 429 whose body names a per-day quota (daily_quota), raises DailyLimit
with nothing retried: the step stops and the next day's run goes on. A per-minute 429 is waited out as before.
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import threading
import time
import urllib.error
import urllib.request

from lyria import REVISION, _key
from spend import SPEND, BudgetExceeded, no_call_offline, payment_refused, record, reserve

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
TTS_DAILY_REQUESTS = int(os.environ.get("ZUMI_TTS_DAILY_REQUESTS", 100))  # the model's requests a day on this tier
COUNTER = SPEND / "gemini-tts-requests.json"  # {quota day: requests sent}, beside the ledgers (on Modal, the volume)
QUOTA_TZ = dt.timezone(dt.timedelta(hours=-8))  # the quota's day turns at midnight Pacific; standard time all year,
                                                # so in summer the new day is seen an hour late, never early
_COUNT_LOCK = threading.Lock()


class DailyLimit(BudgetExceeded):
    """The day's requests are used up (the count, or the service's own per-day 429); nothing more is sent today.
    A BudgetExceeded, so every step leaves the call for the next run as it does at the spend cap."""


def _counts() -> dict:
    try:
        return json.loads(COUNTER.read_text())
    except (OSError, ValueError):
        return {}


def requests_today() -> int:
    """Requests counted on the quota's current day."""
    return int(_counts().get(str(dt.datetime.now(QUOTA_TZ).date()), 0))


def requests_left() -> int:
    """What today's quota leaves, never under 0."""
    return max(0, TTS_DAILY_REQUESTS - requests_today())


def _count(n: int | None = 1) -> None:
    """n more requests on today's count; None: the day is used up (the service said so)."""
    with _COUNT_LOCK:
        day = str(dt.datetime.now(QUOTA_TZ).date())
        now = int(_counts().get(day, 0))
        SPEND.mkdir(parents=True, exist_ok=True)
        COUNTER.write_text(json.dumps({day: TTS_DAILY_REQUESTS if n is None else now + n}))  # only today is kept


def daily_quota(body: bytes) -> str | None:
    """The per-day quota a 429's body says is exhausted (Google's error: status RESOURCE_EXHAUSTED with a
    QuotaFailure detail whose violations name a quotaId; a per-day one has "PerDay" in it), else None: a per-minute
    limit, or a body that does not say."""
    try:
        err = json.loads(body).get("error") or {}
    except (ValueError, AttributeError):
        return None
    if err.get("status") != "RESOURCE_EXHAUSTED":
        return None
    for d in err.get("details") or []:
        for v in (d.get("violations") or []) if isinstance(d, dict) else []:
            quota = str(v.get("quotaId") or v.get("quotaMetric") or "")
            if "perday" in quota.lower().replace("_", ""):
                return quota
    return None


def _post(path: str, body: dict, timeout: int = 300) -> dict:
    req = urllib.request.Request(f"{API}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Api-Revision": REVISION,
                                          "x-goog-api-key": _key()})
    for attempt in range(5):
        if requests_left() <= 0:
            raise DailyLimit(f"Gemini TTS {path}: the daily limit of {TTS_DAILY_REQUESTS} requests is reached")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                _count()
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            raw = e.read()
            detail = raw[:400].decode(errors="replace")
            if e.code == 429:  # refused before it ran: not counted
                quota = daily_quota(raw)
                if quota:
                    _count(None)
                    raise DailyLimit(f"Gemini TTS {path}: the service's daily quota is used up ({quota})") from None
            else:
                _count()
            if e.code in (429, 500, 502, 503, 504) and attempt < 4:
                time.sleep(15 * (attempt + 1))   # the free tier's requests per minute; a 429 clears in under a minute
                continue
            payment_refused("gemini", e.code, detail)
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
