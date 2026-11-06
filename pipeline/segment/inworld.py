"""Inworld TTS-2 calls under the shared daily spend cap (spend.py): voice design and speech. The key is read from
`pipeline/.env` (INWORLD_API_KEY, the Base64 credential the portal gives, sent as-is) and never printed.

    v = design_voice(description, display_name, preview_text, language_code, tag)   # a published voice id, its sample
    wav, cost = speech(text, voice_id, style, tag)                                    # voice: a published voice id

Every call goes into `.data/spend/inworld.jsonl` at list price (PRICE per character of the text sent, the delivery
instruction included: Inworld bills every character of the input). A designed voice is published into the
workspace's library (100 on the free plan) and stays; the delivery note goes in the text as a bracketed instruction
before the words ("[tired, whiny] Can we take a break?"), which TTS-2 follows and TTS-2 Flash ignores.
"""

from __future__ import annotations

import base64
import collections
import functools
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from spend import BudgetExceeded, no_call_offline, record, reserve

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
API = "https://api.inworld.ai"
MODEL = "inworld-tts-2"
PRICE = 25e-6  # USD per character on the On-Demand plan (2026-11-06); TTS-2 Flash 15e-6 but it ignores instructions
SAMPLE_RATE = 24000  # asked for; the API caps at the model's native rate
RESERVE_USD = 0.05  # per call, the worst case reserved before sending (a line costs a fraction of a cent)
DESIGNS_PER_MINUTE = 2  # the free plan's voice design limit
_designs: collections.deque = collections.deque()
_design_lock = threading.Lock()


@functools.lru_cache(maxsize=1)
def _key() -> str:
    if os.environ.get("INWORLD_API_KEY"):
        return os.environ["INWORLD_API_KEY"]
    for line in ENV.read_text().splitlines():
        if line.startswith("INWORLD_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("INWORLD_API_KEY missing from pipeline/.env")


def _post(path: str, body: dict) -> dict:
    req = urllib.request.Request(API + path, data=json.dumps(body).encode(),
                                 headers={"Authorization": f"Basic {_key()}", "Content-Type": "application/json"})
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (429, 500, 502, 503, 504) and attempt < 5:
                told = re.search(r"retry in (\d+)", msg)
                time.sleep(int(told.group(1)) + 2 if told else 10 * 2**min(attempt, 3))
                continue
            raise RuntimeError(f"Inworld {e.code}: {msg}") from None
    raise RuntimeError("unreachable")


def _pace_design() -> None:
    """At most DESIGNS_PER_MINUTE voice designs a minute."""
    while True:
        with _design_lock:
            now = time.monotonic()
            while _designs and now - _designs[0] > 61:
                _designs.popleft()
            if len(_designs) < DESIGNS_PER_MINUTE:
                _designs.append(now)
                return
            wait = 61 - (now - _designs[0])
        time.sleep(max(wait, 0.5))


def design_voice(description: str, display_name: str, preview_text: str, language_code: str = "en-US",
                 tag: str = "") -> dict:
    """One voice from a text description, published into the workspace library: {"id": the voice id to synthesize
    with, "sample": the preview audio bytes (as the API encodes it), "cost": USD at list price}. preview_text (50-400
    characters) is what the preview speaks and shapes the voice: the character's own lines."""
    no_call_offline(tag or "voice design")
    _pace_design()
    body = {"designPrompt": description[:1000], "previewText": preview_text[:400], "languageCode": language_code,
            "designPromptMode": "DESIGN_PROMPT_MODE_ASSISTED", "voiceDesignConfig": {"numberOfSamples": 1}}
    with reserve(RESERVE_USD, tag or "voice design"):
        resp = _post("/voices/v1/voices:design", body)
        draft = (resp.get("previewVoices") or [{}])[0]
        if not draft.get("voiceId"):
            raise RuntimeError(f"Inworld: no preview voice in the reply ({json.dumps(resp)[:300]})")
        published = _post(f"/voices/v1/voices/{draft['voiceId']}:publish",
                          {"displayName": display_name[:80], "description": description[:500]})
        cost = (len(description) + len(preview_text)) * PRICE  # what the pricing page lets one assume (no design price)
        record("inworld", cost, model=MODEL, tag=tag, call="design", voice=published.get("voiceId"))
    return {"id": published.get("voiceId") or draft["voiceId"], "sample": base64.b64decode(draft.get("previewAudio") or b""),
            "cost": cost}


DELIVERY_MODE = "CREATIVE"  # TTS-2's range: STABLE (predictable), BALANCED (default), CREATIVE ("greater emotional
                            # range"); BALANCED sounded flat next to Gemini on P&C 39 (user, 2026-11-06)


SPEAKING_RATE = 1.1  # audioConfig.speakingRate, 0.5-1.5 (Inworld recommends above 0.8): 1.0 felt slow at times, 1.2
                     # slightly hurried for most but right for a voice designed "slow and deliberate" (user,
                     # 2026-11-06), so a character's cast record may carry its own rate


def speech(text: str, voice: str, style: str | None = None, tag: str = "", mode: str = DELIVERY_MODE,
           context: str | None = None, rate: float = SPEAKING_RATE) -> tuple[bytes, float]:
    """One line as a WAV in a published voice, the delivery note as a bracketed instruction before the words
    ("[say it tired, whiny, sulking] ..."), mode the model's deliveryMode, context the previous lines of the scene
    (synthesisContext, helps short lines): (the WAV bytes, the cost in USD, from the characters the API reports
    processed)."""
    no_call_offline(tag or "speech")
    sent = (f"[say it {style.strip()}] " if style and style.strip() else "") + text
    body = {"text": sent[:2000], "voiceId": voice, "modelId": MODEL, "deliveryMode": mode,
            "audioConfig": {"audioEncoding": "WAV", "sampleRateHertz": SAMPLE_RATE, "speakingRate": rate}}
    if context:
        body["synthesisContext"] = {"previousText": context[-600:]}
    with reserve(RESERVE_USD, tag or "speech"):
        for attempt in range(6):  # an empty audioContent with usage null comes back now and then (a voice published a
            resp = _post("/tts/v1/voice", body)  # moment ago, or a transient): the same request succeeds after a wait
            wav = base64.b64decode(resp.get("audioContent") or b"")
            if wav:
                break
            if os.environ.get("ZUMI_DEBUG"):
                print(f"inworld: empty reply for {json.dumps(body)[:400]} -> {json.dumps(resp)[:200]}")
            time.sleep(5 * (attempt + 1))
        if not wav:
            raise RuntimeError(f"Inworld: no audio in the reply ({json.dumps(resp)[:300]})")
        chars = (resp.get("usage") or {}).get("processedCharactersCount") or len(sent)
        cost = chars * PRICE
        record("inworld", cost, model=MODEL, tag=tag, call="speech", voice=voice, chars=chars)
    return wav, cost
