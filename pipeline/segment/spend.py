"""The daily spend cap every paid API shares (user rule, 2026-10-30: at most 2 USD a day in all, model calls and
FLUX erases together). A call reserves its worst case before it is sent and is refused if today's spend, plus the
calls in flight, plus its own would pass the cap: the pipeline calls from 8 threads at once, and checking the
ledgers alone let them all pass on the same reading. Each service keeps its own ledger under .data/spend
(openrouter.jsonl, bfl.jsonl, gemini.jsonl); today's spend is all of them, by local date.

    with spend.reserve(worst_usd, "what"):     # raises BudgetExceeded before anything is sent
        ...call...
        spend.record("openrouter", usd, tag=...)  # inside, so the reservation goes only once it is in a ledger

A run may raise the cap only with the user's explicit permission for that day (ZUMI_DAILY_USD=4).

    results, stopped = paid_map(fn, items)   fn over items WORKERS at a time; once the cap refuses one, none starts
    with offline(): ...                      (or ZUMI_OFFLINE=1) every paid call refused: OfflineCall, nothing sent
"""
from __future__ import annotations

import datetime as dt
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEND = ROOT / ".data/spend"
LEDGERS = {"openrouter": SPEND / "openrouter.jsonl", "bfl": SPEND / "bfl.jsonl", "gemini": SPEND / "gemini.jsonl",
           "inworld": SPEND / "inworld.jsonl"}
DAILY_CAP_USD = float(os.environ.get("ZUMI_DAILY_USD", 2.0))
WORKERS = 16  # calls in flight per step: they wait on remote models, not on cores (openrouter backs off on 429s)
_LOCK = threading.Lock()
_INFLIGHT = [0.0]  # USD reserved by calls sent and not yet in a ledger
_OFFLINE = [os.environ.get("ZUMI_OFFLINE") == "1"]


class BudgetExceeded(RuntimeError):
    """The call would pass the daily cap; nothing was sent."""


class OfflineCall(BudgetExceeded):
    """A paid call in a run that allows none (offline(), ZUMI_OFFLINE=1); nothing was sent. Every step treats it as
    the cap: what needs a call is skipped or left for the next run."""


@contextmanager
def offline():
    """No paid call inside: each one raises OfflineCall (baselines and experiments on cached answers)."""
    prev = _OFFLINE[0]
    _OFFLINE[0] = True
    try:
        yield
    finally:
        _OFFLINE[0] = prev


def paid_map(fn, items, workers: int = WORKERS, on_done=None) -> tuple[dict, list]:
    """fn(item) for every item, `workers` at a time (the steps' calls wait on remote models). Once fn raises
    BudgetExceeded (the cap, or an offline run), items not yet started are not started: they and the refused one are
    returned as stopped, for the step to say what that means (one scene for now, not saved, not sent). Any other
    exception propagates. on_done(item, result): called as each finishes. Returns ({item: result}, [stopped])."""
    stop = threading.Event()
    told = threading.Lock()
    results, stopped = {}, []

    def one(item):
        if stop.is_set():
            return item, False, None
        try:
            return item, True, fn(item)
        except BudgetExceeded as e:
            with told:
                if not stop.is_set():
                    print(f"STOP: {e}")
                stop.set()
            return item, False, None

    with ThreadPoolExecutor(workers) as ex:
        for fut in as_completed([ex.submit(one, it) for it in items]):
            item, ok, res = fut.result()
            if ok:
                results[item] = res
                if on_done is not None:
                    on_done(item, res)
            else:
                stopped.append(item)
    return results, stopped


def _usd(e: dict) -> float:
    return float(e.get("cost", e.get("usd", 0)) or 0)  # openrouter's lines say "cost", bfl's "usd"


def _date(e: dict) -> str | None:
    return e.get("date") or e.get("day")  # bfl's older lines have only its UTC "day"


def spent_today(service: str | None = None) -> float:
    """USD spent today (local date), on one service or all."""
    today = str(dt.date.today())
    total = 0.0
    for name, f in LEDGERS.items():
        if (service is None or service == name) and f.exists():
            total += sum(_usd(e) for e in map(json.loads, f.read_text().splitlines()) if _date(e) == today)
    return total


def no_call_offline(what: str = "") -> None:
    """Raises OfflineCall in an offline run: before anything that reaches the network for a paid call."""
    if _OFFLINE[0]:
        raise OfflineCall(f"{what}: an offline run, no paid call")


@contextmanager
def reserve(usd: float, what: str = ""):
    no_call_offline(what)
    with _LOCK:
        today = spent_today()
        if today + _INFLIGHT[0] + usd > DAILY_CAP_USD + 1e-9:
            raise BudgetExceeded(f"{what}: spent {today:.3f} USD today, {_INFLIGHT[0]:.3f} in flight; this call could "
                                 f"cost up to {usd:.3f}; cap {DAILY_CAP_USD}")
        _INFLIGHT[0] += usd
    try:
        yield
    finally:
        with _LOCK:
            _INFLIGHT[0] -= usd


def record(service: str, usd: float, **fields) -> None:
    """A paid call in its service's ledger, dated today (local)."""
    SPEND.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now()
    line = {"ts": now.isoformat(timespec="seconds"), "date": str(now.date()), **fields,
            ("cost" if service == "openrouter" else "usd"): float(usd)}
    with _LOCK, LEDGERS[service].open("a") as f:
        f.write(json.dumps(line) + "\n")
