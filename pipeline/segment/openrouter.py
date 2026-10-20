"""OpenRouter chat calls with a daily spend cap (user rule: at most 2 USD per day on paid model calls).

Every call is priced before it is sent (worst case: estimated prompt tokens plus max_tokens at the model's
list price) and refused if today's ledger plus that worst case would pass the cap. After the call, the cost
OpenRouter reports (usage accounting) is appended to `.data/spend/openrouter.jsonl`. The key is read from
`pipeline/.env` and never printed.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
ENV = ROOT / ".env"
SPEND = ROOT / ".data/spend"
LEDGER = SPEND / "openrouter.jsonl"
DAILY_CAP_USD = 2.0
API = "https://openrouter.ai/api/v1"
TOKENS_PER_IMAGE = 2500  # conservative estimate for the pre-call worst case


class BudgetExceeded(RuntimeError):
    pass


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
    if not cache.exists():
        cache.write_text(json.dumps(_request("/models")))
    for m in json.loads(cache.read_text())["data"]:
        if m["id"] == model:
            return float(m["pricing"]["prompt"]), float(m["pricing"]["completion"])
    raise KeyError(f"unknown model {model}")


def spent_today() -> float:
    if not LEDGER.exists():
        return 0.0
    today = str(dt.date.today())
    return sum(e["cost"] for e in map(json.loads, LEDGER.read_text().splitlines()) if e["date"] == today)


def image_part(img: Image.Image, max_side: int = 2048, quality: int = 90) -> dict:
    img = img.convert("RGB")
    if max(img.size) > max_side:
        s = max_side / max(img.size)
        img = img.resize((max(1, round(img.width * s)), max(1, round(img.height * s))), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}


def chat(model: str, messages: list[dict], max_tokens: int = 2000, tag: str = "", reasoning: str | None = "low") -> tuple[str, dict]:
    """One chat completion; returns (text, usage). Raises BudgetExceeded before sending if the cap would break."""
    p_in, p_out = pricing(model)
    images = sum(1 for m in messages for c in (m["content"] if isinstance(m["content"], list) else []) if c.get("type") == "image_url")
    chars = sum(len(c.get("text", "")) for m in messages for c in (m["content"] if isinstance(m["content"], list) else [{"text": m["content"]}]))
    worst = (images * TOKENS_PER_IMAGE + chars / 3) * p_in + max_tokens * p_out
    today = spent_today()
    if today + worst > DAILY_CAP_USD:
        raise BudgetExceeded(f"spent {today:.3f} USD today; this call could cost up to {worst:.3f}; cap {DAILY_CAP_USD}")
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": 0, "usage": {"include": True}}
    if reasoning:  # reasoning models spend hidden tokens from max_tokens; at 2500 they cut the JSON short
        body["reasoning"] = {"effort": reasoning}
    resp = _request("/chat/completions", body)
    usage = resp.get("usage", {})
    cost = usage.get("cost")
    if cost is None:
        cost = usage.get("prompt_tokens", 0) * p_in + usage.get("completion_tokens", 0) * p_out
    SPEND.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as f:
        f.write(json.dumps({"ts": dt.datetime.now().isoformat(timespec="seconds"), "date": str(dt.date.today()), "model": model,
                            "tag": tag, "prompt_tokens": usage.get("prompt_tokens"), "completion_tokens": usage.get("completion_tokens"),
                            "cost": float(cost)}) + "\n")
    return resp["choices"][0]["message"].get("content") or "", usage
