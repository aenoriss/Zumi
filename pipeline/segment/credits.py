"""What every provider of the chain has left against what an episode still asks of it, read before a run so that
none starts on an empty account (a provider out of credit answers HTTP 402 in the middle of a step).

    check(panels, cap_left=None, out=None, tts_sent=None)
        -> {row: {"usd", "needed_usd", "state", "source", "as_of", "detail"}}
    verdict(table) -> {"can_run", "blocking", "warnings"}     the one rule the gates and GET /credits answer by
    set_anchor(provider, usd)                                 a balance its owner states, for a provider with no API

    python credits.py [episode.zumi [episode out dir]]        the table; exit 1 when a run would be refused
    python credits.py set gemini 12.40                        "the account shows 12.40 USD now"

Rows: openrouter, bfl, fal (source "account": their balance read from the account, free calls); gemini and, when
it is the voice backend, inworld, which have no balance endpoint (Gemini's prepaid balance shows only in AI
Studio's Billing tab); and daily-cap: what spend.py's cap leaves today against the whole episode. A provider with
no endpoint is "unknown" (it warns, it does not block) until its balance is stated (set_anchor: ANCHORS, beside
the ledgers, {provider: {"usd", "at"}}); from then its row is an "estimate": the stated balance less what the
ledgers recorded for it since (spent_since), as of the statement. What is spent on the same account outside this
pipeline is not seen. A state is "depleted" (under DEPLETED_USD), "low"
(under needed_usd), "ok" or "unknown". A provider whose last call was refused for payment (spend.depleted: an
HTTP 402 marks it, a later answer or a later stated balance clears it) is "depleted" whatever the estimate says. A
provider low or depleted blocks; a low daily cap only warns (the run stops at the cap and goes on another day), a
depleted one blocks.

The voices follow the backend (ZUMI_TTS, else Gemini, as voices.backend): its lines and voice designs are in that
provider's needed_usd, and on Gemini the row tts-requests counts requests, not money ("left", "needed"): what
today's limit leaves (gemini_tts.requests_left) against the lines and designs to make. When the day does not hold
them it warns, with the days the voices take, and never blocks: the run records what fits and goes on another day.

needed_usd is an estimate from the panel count, the same for a first run and a resumed one (a resumed run needs
less): per provider PER_PANEL a box plus PER_EPISODE, then MARGIN on top. The prices are the ledgers' averages per
call (2026-11-15) and the modules' own constants; the counts are the chain's limits or what its episodes have had.
The voiced lines are counted from the episode's speaker records when its out dir is given and has them (every
balloon with a speaker, less the lines already recorded: at most what a run sends), else estimated as
LINES_PER_PANEL a box. Stdlib only: the service's small container imports it.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import urllib.request
import zipfile
from pathlib import Path

import gemini_tts
import spend

ROOT = Path(__file__).resolve().parent.parent
MARGIN = 0.25         # on top of every estimate
DEPLETED_USD = 0.05   # under this an account pays for nothing the chain asks
DEFAULT_PANELS = 30   # when the episode is not at hand to count
PANELS_PER_PAGE = 2.5  # boxes the intake cuts from a page, before it has run: the one episode delivered as pages (28
                       # boxes from 11); an estimate, a webtoon's slices are cut otherwise
BFL_USD_PER_CREDIT = 0.01  # bfl.py records credits / 100; bfl.ai prices a credit at one cent
PLACES, PROPS = 4, 5  # places built an episode (2-5 so far), props a place (props.MAX_PROPS)
# the voices of the one episode recorded on both backends (pepper-carrot-39: 64 lines in 31 boxes, 6 voices, a
# Gemini line 5.1 s and about 80 characters, an Inworld line 0.0024 USD)
LINES_PER_PANEL, VOICES, LINE_S, LINE_CHARS, INWORLD_LINE_USD = 2.1, 6, 5.1, 80, 0.0024
GEMINI_LINE_USD = LINE_S * gemini_tts.TOKENS_PER_S * gemini_tts.PRICE_AUDIO + LINE_CHARS / 4 * gemini_tts.PRICE_TEXT
# USD a box: the frame layout (0.0043, frames.ask), the three reviews (0.004), the objects' pick (0.002) and
# Transcribe (0.002) on OpenRouter; one FLUX Erase (0.035) on BFL
PER_PANEL = {"openrouter": 0.0123, "bfl": 0.035}
# USD an episode. OpenRouter: Transcribe's second opinions (transcribe.SECOND_USD 0.25), identity (0.23), the voice
# descriptions (0.10), settings and the music reviewer (0.065), a props pick a place (0.012). BFL: a place's two views
# and erase (0.12) and a repaint a prop (0.015). fal: TRELLIS (fal.TRELLIS_USD 0.02) a prop, half of them lifted
# twice. Gemini: six Lyria songs (lyria.PRICE 0.08; score.MAX_TRACKS allows 8).
PER_EPISODE = {"openrouter": 0.645 + PLACES * 0.012, "bfl": PLACES * (0.12 + PROPS * 0.015),
               "fal": PLACES * PROPS * 0.02 * 1.5, "gemini": 6 * 0.08}
# the sound effects (sfx.py): a sound on fal at fal.SFX_USD_PER_S 0.002 a second, bought about SFX_S long, and the
# planning call on OpenRouter (Sonnet, a crop a sound effect: sfx.estimate_plan_usd); SFX_PER_PANEL when the speaker
# records are not at hand (the one episode with them: 6 in 28 boxes)
SFX_PER_PANEL, SFX_S, SFX_USD_PER_S, SFX_PLAN_USD = 0.25, 2.0, 0.002, 0.03
VOICE_USD = {"gemini": (GEMINI_LINE_USD, gemini_tts.DESIGN_USD), "inworld": (INWORLD_LINE_USD, 0.01)}  # (a line, a design)
KEYS = {"openrouter": "OPENROUTER_API_KEY", "bfl": "BFL_API_KEY", "fal": "FAL_KEY", "gemini": "GEMINI_API_KEY",
        "inworld": "INWORLD_API_KEY"}
ANCHORS = spend.SPEND / "credits-anchors.json"  # the stated balances, {provider: {"usd", "at": local ISO time}}

def tts_backend() -> str:
    """The voice backend's name, by voices.backend's rule (that module is not imported here: it needs the image
    libraries)."""
    return os.environ.get("ZUMI_TTS", gemini_tts.NAME)


def _key(provider: str) -> str | None:
    """The provider's key: the environment (a cloud container's secret), else pipeline/.env. Never printed."""
    name = KEYS[provider]
    if os.environ.get(name):
        return os.environ[name]
    env = ROOT / ".env"
    for line in env.read_text().splitlines() if env.exists() else []:
        if line.startswith(name + "="):
            return line.split("=", 1)[1].strip()
    return None


def _get(url: str, headers: dict):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=20) as r:
        return json.loads(r.read().decode())


def _openrouter(key: str) -> float:
    d = _get("https://openrouter.ai/api/v1/credits", {"Authorization": f"Bearer {key}"})["data"]
    return float(d["total_credits"]) - float(d["total_usage"])


def _bfl(key: str) -> float:
    return float(_get("https://api.bfl.ai/v1/credits", {"x-key": key})["credits"]) * BFL_USD_PER_CREDIT


def _fal(key: str) -> float:
    """fal's balance page reads this; it is not a documented endpoint, so its failure is "unknown", like any other."""
    return float(_get("https://rest.alpha.fal.ai/billing/user_balance", {"Authorization": f"Key {key}"}))


BALANCE = {"openrouter": _openrouter, "bfl": _bfl, "fal": _fal}  # the providers whose balance can be read


def _now() -> str:
    return dt.datetime.now().isoformat(timespec="seconds")


def anchors() -> dict:
    try:
        return json.loads(ANCHORS.read_text())
    except (OSError, ValueError):
        return {}


def set_anchor(provider: str, usd: float, at: str | None = None) -> dict:
    """The provider's balance as its owner reads it now (or at `at`), saved; the anchors as they are then. Only for
    a provider whose balance cannot be read."""
    if provider in BALANCE or provider not in KEYS:
        raise ValueError(f"{provider}: not a provider whose balance is stated (" +
                         ", ".join(p for p in KEYS if p not in BALANCE) + ")")
    saved = {**anchors(), provider: {"usd": float(usd), "at": at or _now()}}
    spend.SPEND.mkdir(parents=True, exist_ok=True)
    tmp = ANCHORS.with_suffix(".tmp")
    tmp.write_text(json.dumps(saved, indent=1))
    tmp.replace(ANCHORS)
    return saved


def newest(a: dict, b: dict) -> dict:
    """Two sets of anchors as one: per provider the one stated last (this machine's and the volume's, which the
    batch runner brings together)."""
    return {p: max((x[p] for x in (a, b) if p in x), key=lambda v: v["at"]) for p in {*a, *b}}


def spent_since(provider: str, at: str) -> float:
    """What the provider was paid at `at` or after, as far as this pipeline knows: its ledger's lines (spend.py's:
    "ts", and "cost" or "usd")."""
    ledger = spend.LEDGERS[provider]
    if not ledger.exists():
        return 0.0
    return sum(float(e.get("cost", e.get("usd", 0)) or 0) for e in map(json.loads, ledger.read_text().splitlines())
               if e.get("ts", "") >= at)


def voice_requests(panels: int, out: Path | None = None) -> tuple[int, int, str]:
    """(lines to record, voices to design, how they were counted). With an out dir that has speaker records: its
    balloons with a speaker that are not sound effects, less the lines its backend's lines.json holds, and as many
    designs as the estimate while no line is recorded yet. Else LINES_PER_PANEL a box and VOICES designs."""
    records = sorted(Path(out).glob("parallax/mesh/*.speakers.json")) if out else []
    if not records:
        return math.ceil(LINES_PER_PANEL * panels), VOICES, f"estimated, {LINES_PER_PANEL} lines a box and {VOICES} voices"
    lines = sum(1 for f in records for r in json.loads(f.read_text(encoding="utf-8")).get("records", [])
                if r.get("speakers") and r.get("kind") != "sfx" and (r.get("text") or "").strip())
    index = Path(out) / (gemini_tts.AUDIO_DIR if tts_backend() == gemini_tts.NAME else "audio") / "lines.json"
    made = len(json.loads(index.read_text(encoding="utf-8"))) if index.exists() else 0
    return max(0, lines - made), 0 if made else VOICES, f"counted from the speaker records, {made} lines already recorded"


def sfx_count(panels: int, out: Path | None = None) -> int:
    """The sound effects an episode has: its speaker records' balloons of kind sfx with text when its out dir has
    them, else SFX_PER_PANEL a box. Those already made are not taken off (a sound costs a fraction of a cent)."""
    records = sorted(Path(out).glob("parallax/mesh/*.speakers.json")) if out else []
    if not records:
        return math.ceil(SFX_PER_PANEL * panels)
    return sum(1 for f in records for r in json.loads(f.read_text(encoding="utf-8")).get("records", [])
               if r.get("kind") == "sfx" and (r.get("text") or "").strip())


def needed(panels: int, lines: int | None = None, designs: int = VOICES, sfx: int | None = None) -> dict[str, float]:
    """The estimate per provider for an episode of this many boxes, MARGIN included; the voices' lines and designs
    on the backend's provider, the sound effects on fal and their plan on OpenRouter. Only the providers the run
    uses."""
    lines = math.ceil(LINES_PER_PANEL * panels) if lines is None else lines
    sfx = math.ceil(SFX_PER_PANEL * panels) if sfx is None else sfx
    tts = tts_backend()
    usd = {p: PER_PANEL.get(p, 0) * panels + PER_EPISODE.get(p, 0) for p in KEYS if p in PER_EPISODE or p == tts}
    usd[tts] += lines * VOICE_USD[tts][0] + designs * VOICE_USD[tts][1]
    if sfx:
        usd["fal"] += sfx * SFX_S * SFX_USD_PER_S
        usd["openrouter"] += SFX_PLAN_USD
    return {p: round(v * (1 + MARGIN), 2) for p, v in usd.items()}


def _row(usd: float | None, need: float, detail: str, source: str = "unknown", as_of: str | None = None) -> dict:
    state = "unknown" if usd is None else "depleted" if usd < DEPLETED_USD else "low" if usd < need else "ok"
    return {"usd": None if usd is None else round(usd, 2), "needed_usd": need, "state": state, "source": source,
            "as_of": as_of, "detail": detail}


def provider_row(p: str, need: float, anchor: dict | None = None, marked: dict | None = None, read=None) -> dict:
    """One provider's row. read: a call giving its balance from the account, where there is one; anchor: its stated
    balance, else; marked: its record in spend.depleted(), which makes a row not read from the account "depleted"
    unless the balance was stated after it."""
    row = None
    if read is not None:
        try:
            return _row(read(), need, "the account's balance", "account", _now())
        except Exception as e:  # the network, a changed endpoint: not known, never read as empty
            row = _row(None, need, f"balance not read ({type(e).__name__})")
    elif anchor:
        row = _row(anchor["usd"] - spent_since(p, anchor["at"]), need,
                   f"an estimate: {anchor['usd']:.2f} USD stated at {anchor['at']}, less what this pipeline's ledgers "
                   f"recorded since; spend outside this pipeline on the same billing account is not seen",
                   "estimate", anchor["at"])
    else:
        row = _row(None, need, f"no balance endpoint: state it with `python credits.py set {p} <usd>` or "
                               f"PUT /credits/{p}")
    if marked and marked["at"] > (anchor or {}).get("at", ""):
        row.update(state="depleted", detail=f"refused for payment at {marked['at']} ({marked['what'][:80]}); {row['detail']}")
    return row


def tts_row(left: int, lines: int, designs: int, basis: str, limit: int) -> dict:
    """The day's voice requests against the episode's: "ok", or "low" with the days the voices take at `limit` a
    day (today's rest, then whole days)."""
    need = lines + designs
    days = 1 if need <= left else 1 + math.ceil((need - left) / limit)
    return {"usd": None, "needed_usd": 0.0, "left": left, "needed": need, "days": days,
            "state": "ok" if need <= left else "low", "source": "count", "as_of": _now(),
            "detail": f"Gemini TTS requests today of {limit} a day; {lines} lines and {designs} voice designs ({basis})"}


def check(panels: int = DEFAULT_PANELS, cap_left: float | None = None, out: Path | None = None,
          tts_sent: int | None = None) -> dict[str, dict]:
    """The table for an episode of `panels` boxes. cap_left and tts_sent: what today's cap leaves and the voice
    requests already counted today, when the caller knows better than this machine's files (the batch runner, which
    reads the volume's). out: the episode's out dir, to count its lines."""
    lines, designs, basis = voice_requests(panels, out)
    need, table, stated, marked = needed(panels, lines, designs, sfx_count(panels, out)), {}, anchors(), spend.depleted()
    for p in need:
        key = _key(p)
        if key is None:
            table[p] = _row(None, need[p], f"no {KEYS[p]}")
        else:
            table[p] = provider_row(p, need[p], stated.get(p), marked.get(p),
                                    (lambda p=p, key=key: BALANCE[p](key)) if p in BALANCE else None)
    if cap_left is None:
        cap_left = spend.DAILY_CAP_USD - spend.spent_today()
    table["daily-cap"] = _row(cap_left, round(sum(need.values()), 2),
                              f"what today's cap of {spend.DAILY_CAP_USD:g} USD leaves (spend.py, ZUMI_DAILY_USD)",
                              "ledger", _now())
    if tts_backend() == gemini_tts.NAME:
        limit = gemini_tts.TTS_DAILY_REQUESTS
        left = gemini_tts.requests_left() if tts_sent is None else max(0, limit - tts_sent)
        table["tts-requests"] = tts_row(left, lines, designs, basis, limit)
    return table


def blocking(table: dict[str, dict]) -> list[str]:
    """Why a run must not start: every provider low or depleted, and a depleted daily cap."""
    return [f"{p}: {r['state']}, " + ("balance unknown" if r["usd"] is None else f"{r['usd']:.2f} USD left") +
            f", about {r['needed_usd']:.2f} needed ({r['source']})" for p, r in table.items()
            if p != "tts-requests" and (r["state"] == "depleted" or (r["state"] == "low" and p != "daily-cap"))]


def verdict(table: dict[str, dict]) -> dict:
    """Whether a run may start, by the one rule: {"can_run", "blocking", "warnings"}."""
    return {"can_run": not blocking(table), "blocking": blocking(table), "warnings": warnings(table)}


def warnings(table: dict[str, dict]) -> list[str]:
    """What does not stop a run: the balances not known, a daily cap under the episode's whole cost, and voices
    that take more than today's requests."""
    out = [f"{p}: balance unknown ({r['detail']}), about {r['needed_usd']:.2f} USD needed" for p, r in table.items()
           if r["state"] == "unknown"]
    cap, tts = table["daily-cap"], table.get("tts-requests")
    if cap["state"] == "low":
        out.append(f"daily-cap: {cap['usd']:.2f} USD left today, about {cap['needed_usd']:.2f} needed: the run stops "
                   f"at the cap and goes on another day")
    if tts and tts["state"] == "low":
        out.append(f"tts-requests: {tts['left']} left today, {tts['needed']} needed: the voices complete in "
                   f"{tts['days']} days (a run a day), and the steps after them wait")
    return out


def panels_from_pages(pages: int) -> int:
    """The boxes an episode of this many pages is estimated to have, before its intake has cut them."""
    return math.ceil(PANELS_PER_PAGE * pages)


def panels_of(zumi: Path) -> int:
    """The boxes of a .zumi, from its manifest."""
    with zipfile.ZipFile(zumi) as z:
        return len(json.loads(z.read("manifest.json"))["panels"])


def show(table: dict[str, dict]) -> str:
    lines = [f"{'':12s} {'left':>9s} {'needed':>7s}  state"]
    for p, r in table.items():
        left, need = (str(r["left"]), str(r["needed"])) if "left" in r else \
            ("?" if r["usd"] is None else format(r["usd"], ".2f"), format(r["needed_usd"], ".2f"))
        lines.append(f"{p:12s} {left:>9s} {need:>7s}  {r['state']:8s} {r['detail']}")
    return "\n".join(lines) + "\n(USD, but tts-requests: requests)"


if __name__ == "__main__":
    if sys.argv[1:2] == ["set"]:
        print(json.dumps(set_anchor(sys.argv[2], float(sys.argv[3])), indent=1))
        sys.exit(0)
    n = panels_of(Path(sys.argv[1])) if len(sys.argv) > 1 else DEFAULT_PANELS
    t = check(n, out=Path(sys.argv[2]) if len(sys.argv) > 2 else None)
    v = verdict(t)
    print(f"{n} boxes\n{show(t)}")
    for w in v["warnings"]:
        print("warning:", w)
    for b in v["blocking"]:
        print("REFUSED:", b)
    sys.exit(0 if v["can_run"] else 1)
