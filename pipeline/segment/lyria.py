"""Google Lyria through the Gemini API (the interactions endpoint): one prompt in, one instrumental song out.

song()  lyria-3.5, a full song of about two minutes, 0.08 USD; clip() lyria-3-clip-preview, 30 s, 0.04 USD (the
aggregators' preview prices, 2026-11-07; Google's page gives none). Length, structure and "instrumental" are asked
for in the prompt: the endpoint has no duration, seed or negative-prompt field. MP3 44.1 kHz stereo. Every call goes
through the shared daily cap (spend.reserve) and the gemini ledger. The key is GEMINI_API_KEY in pipeline/.env.
"""
from __future__ import annotations

import base64
import functools
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from spend import no_call_offline, payment_refused, record, reserve

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
API = "https://generativelanguage.googleapis.com/v1beta/interactions"
REVISION = "2026-05-20"
SONG, CLIP = "lyria-3.5", "lyria-3-clip-preview"
PRICE = {SONG: 0.08, CLIP: 0.04}


@functools.lru_cache(maxsize=1)
def _key() -> str:
    if os.environ.get("GEMINI_API_KEY"):
        return os.environ["GEMINI_API_KEY"]
    for line in ENV.read_text().splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("GEMINI_API_KEY missing from pipeline/.env")


def generate(prompt: str, model: str = SONG, tag: str = "") -> tuple[bytes, float, str]:
    """(the MP3 bytes, the cost in USD, the model's text about the piece: its structure, if any)."""
    no_call_offline(tag or model)
    body = {"model": model, "input": prompt, "response_format": {"type": "audio"}}
    req = urllib.request.Request(API, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Api-Revision": REVISION,
                                          "x-goog-api-key": _key()})
    usd = PRICE[model]
    with reserve(usd, tag or model):
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=600) as r:
                    resp = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                detail = e.read()[:400].decode(errors="replace")
                if e.code in (429, 500, 502, 503, 504) and attempt < 3:
                    time.sleep(10 * (attempt + 1))
                    continue
                payment_refused("gemini", e.code, detail)
                raise RuntimeError(f"Lyria {model}: HTTP {e.code} {detail}") from None
        record("gemini", usd, model=model, tag=tag, call="music")
    audio, texts = [], []
    for s in resp.get("steps", []):
        if s.get("type") != "model_output":
            continue
        for c in s.get("content", []):
            if c.get("type") == "audio" and c.get("data"):
                audio.append(c["data"])
            elif c.get("type") == "text" and c.get("text"):
                texts.append(c["text"])
    if not audio:
        raise RuntimeError(f"Lyria {model}: no audio in the reply ({json.dumps(resp)[:300]})")
    return base64.b64decode(audio[0]), usd, "\n".join(texts)
