"""Per-box CPU work across processes: boxes are independent, and the image operations (distance transforms,
morphology, mask sums) hold Python's GIL long enough that threads gain little. The core count is read on the machine
the run is on, one core left for the main process (and the GPU work it drives).

    out = pmap(fn, items)          [fn(item) for item in items], in order, over cpu_workers() processes

fn must be a module-level function and items picklable: every worker starts fresh ("spawn", on Linux too) and imports
fn's module. Forking would copy the background network threads' locks and the CUDA context mid-use.
GPU models stay in the main process: a worker that loaded SAM or DA3 would hold its own copy in the 12 GB.
"""
from __future__ import annotations

import multiprocessing
import os
from concurrent.futures import ProcessPoolExecutor

MIN_ITEMS = 4  # fewer items run in the main process: starting a worker (imports included) costs about a second


def cpu_workers(reserve: int = 1) -> int:
    """Processes for CPU work on this machine: its cores, minus `reserve` for the main process. ZUMI_CPUS overrides
    the count where the machine reports more cores than the run may use (a cloud container sees its host's)."""
    cores = int(os.environ.get("ZUMI_CPUS") or 0)
    if not cores:
        cores = len(os.sched_getaffinity(0)) if hasattr(os, "sched_getaffinity") else os.cpu_count() or 1
    return max(1, cores - reserve)


def pmap(fn, items, workers: int | None = None) -> list:
    """[fn(item) for item in items] across processes, results in the items' order."""
    items = list(items)
    workers = min(workers or cpu_workers(), len(items))
    if workers <= 1 or len(items) < MIN_ITEMS:
        return [fn(it) for it in items]
    # a worker is one task: numpy's and scipy's OpenBLAS each commit buffers for every core at import (0.97 GB a
    # worker on 16 cores, 33 MB with one thread; 16 workers ran Windows out of commit). Read at the worker's start.
    os.environ["OPENBLAS_NUM_THREADS"] = "1"
    with ProcessPoolExecutor(workers, mp_context=multiprocessing.get_context("spawn")) as ex:
        return list(ex.map(fn, items))
