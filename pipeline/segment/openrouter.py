"""OpenRouter chat calls under the shared daily spend cap (spend.py: 2 USD a day, model calls and erases together).

Every call is priced before it is sent (worst case: estimated prompt tokens plus max_tokens at the model's
list price) and reserved with spend.reserve, refused if it could pass the cap. After the call, the cost OpenRouter
reports (usage accounting) goes into `.data/spend/openrouter.jsonl`. The key is read from `pipeline/.env` and never
printed.

    text, usage = chat(model, messages, max_tokens, tag, reasoning, brief)
    reply, cost = ask_json(model, content, tag, max_tokens, reasoning, system, brief)   # a dict; raises Truncated
"""

from __future__ import annotations

import base64
import datetime as dt
import functools
import io
import json
import re
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

from spend import SPEND, BudgetExceeded, reserve, record, spent_today  # noqa: F401  (BudgetExceeded, spent_today: for callers)

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
_PRICING_LOCK = threading.Lock()
API = "https://openrouter.ai/api/v1"
TOKENS_PER_IMAGE = 2500  # conservative estimate for the pre-call worst case
# reasoning tokens on top of every answer budget (chat), by effort. At 4000 Haiku (high) spent the whole budget
# thinking on 17 review calls and wrote no answer, read as "no changes" (P&C 36 p12 kept a whole panel as a caption):
# high doubled, with BRIEF asked. The ledger to 2026-10-30: Sonnet (low) wrote at most 519 completion tokens, Haiku
# (high) at most 6826, so low and medium reserve less and the cap admits more calls at once
REASONING_TOKENS = {"low": 2000, "medium": 4000, "high": 8000}
BRIEF = "Be brief and to the point: keep any reasoning short and reply with only what was asked."


class Truncated(RuntimeError):
    """The reply spent its whole token budget and holds no answer; .cost is what the call cost."""

    def __init__(self, msg: str, cost: float = 0.0):
        super().__init__(msg)
        self.cost = cost


@functools.lru_cache(maxsize=1)
def _key() -> str:
    for line in ENV.read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("OPENROUTER_API_KEY missing from pipeline/.env")


def _request(path: str, body: dict | None = None) -> dict:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {_key()}", "Content-Type": "application/json"},
    )
    for attempt in range(6):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503) and attempt < 5:  # upstream rate limits clear within a minute or two
                time.sleep(10 * 2**attempt)
                continue
            raise RuntimeError(f"OpenRouter {e.code}: {e.read().decode()[:300]}") from None
    raise RuntimeError("unreachable")


def pricing(model: str) -> tuple[float, float]:
    """USD per prompt token and per completion token, from OpenRouter's model list (cached per day)."""
    SPEND.mkdir(parents=True, exist_ok=True)
    cache = SPEND / f"models-{dt.date.today()}.json"
    # one thread fetches, the file appears whole (a parallel review read it half written: JSONDecodeError, P&C 36)
    with _PRICING_LOCK:
        if not cache.exists():
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(_request("/models")))
            tmp.replace(cache)
    for m in json.loads(cache.read_text())["data"]:
        if m["id"] == model:
            return float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])
    raise KeyError(f"unknown model {model}")


def image_part(img: Image.Image, max_side: int = 2048, quality: int = 90) -> dict:
    img = img.convert("RGB")
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}


def chat(model: str, messages: list[dict], max_tokens: int = 2000, tag: str = "", reasoning: str | None = "low",
         brief: bool = True) -> tuple[str, dict]:
    """One chat completion; returns (text, usage). Raises BudgetExceeded before sending if the cap would break.
    max_tokens is the answer's budget; with reasoning, the one budget rule for every caller: REASONING_TOKENS[effort]
    more on top. brief: the model asked to be brief and to the point (BRIEF), off where the answer carries long text
    the brevity line could shorten (Understand's transcriptions). A reply that spends the whole budget has no answer:
    usage["truncated"] is set, the ledger says so and a line is printed (callers read an empty answer as "nothing")."""
    if reasoning:
        max_tokens += REASONING_TOKENS[reasoning]
    if brief:
        messages = _brief(messages)
    p_in, p_out = pricing(model)
    images = sum(1 for m in messages for c in (m["content"] if isinstance(m["content"], list) else []) if c.get("type") == "image_url")
    chars = sum(len(c.get("text", "")) for m in messages for c in (m["content"] if isinstance(m["content"], list) else [{"text": m["content"]}]))
    worst = (images * TOKENS_PER_IMAGE + chars / 3) * p_in + max_tokens * p_out
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "usage": {"include": True}}
    if reasoning:  # reasoning models spend hidden tokens from max_tokens
        body["reasoning"] = {"effort": reasoning}
    with reserve(worst, tag or model):
        resp = _request("/chat/completions", body)
        usage = resp.get("usage", {})
        cost = usage.get("cost")
        if cost is None:
            cost = usage.get("prompt_tokens", 0) * p_in + usage.get("completion_tokens", 0) * p_out
        usage["cost"] = float(cost)
        usage["truncated"] = (usage.get("completion_tokens") or 0) >= max_tokens
        record("openrouter", cost, model=model, tag=tag, prompt_tokens=usage.get("prompt_tokens"),
               completion_tokens=usage.get("completion_tokens"), **({"truncated": True} if usage["truncated"] else {}))
    if usage["truncated"]:
        print(f"openrouter: {tag or model} spent its whole budget ({max_tokens} tokens): no answer")
    return resp["choices"][0]["message"].get("content") or "", usage


def parse_json(text: str) -> dict:
    """The JSON object in a model's reply, {} when there is none: code fences dropped, then from its first { to its
    last }, a stray closing bracket dropped and retried (Muse Spark wrote "}}]" once), or else the first whole object
    (Sonnet once added a second object after it, P&C 39 p14)."""
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M)
    a, b = text.find("{"), text.rfind("}")
    if a < 0 or b < a:
        return {}
    body = text[a: b + 1]
    for _ in range(5):
        try:
            v = json.loads(body)
            return v if isinstance(v, dict) else {}
        except json.JSONDecodeError as e:
            if e.pos < len(body) and body[e.pos] in "}]":
                body = body[: e.pos] + body[e.pos + 1:]
                continue
            break
    try:
        v = json.JSONDecoder().raw_decode(text, a)[0]
    except json.JSONDecodeError:
        return {}
    return v if isinstance(v, dict) else {}


def ask_json(model: str, content: list, tag: str = "", max_tokens: int = 500, reasoning: str | None = "low",
             system: str | None = None, brief: bool = True) -> tuple[dict, float]:
    """One user turn (after an optional system turn) whose reply is a JSON object: (that object, or {} when the
    reply has none; cost in USD). Raises Truncated when the reply spent its whole budget (no answer: read as {} it
    passed for "no changes"), BudgetExceeded before sending. brief: as chat's."""
    messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    text, usage = chat(model, messages, max_tokens=max_tokens, tag=tag, reasoning=reasoning, brief=brief)
    if usage["truncated"]:
        raise Truncated(f"{tag or model}: no answer within {max_tokens} tokens (+ reasoning)", usage["cost"])
    return parse_json(text), usage["cost"]


def _brief(messages: list[dict]) -> list[dict]:
    """The messages with BRIEF appended to the last user turn (a copy: callers reuse theirs)."""
    out = [dict(m) for m in messages]
    for m in reversed(out):
        if m["role"] == "user":
            c = m["content"]
            m["content"] = (c + [{"type": "text", "text": BRIEF}]) if isinstance(c, list) else f"{c}\n\n{BRIEF}"
            break
    return out
