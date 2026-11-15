"""A comic's page images to its finished .zumi on a Modal GPU (user, 2026-11-01: for when the local GPU is busy or
the run is on another machine), as a batch from this machine or as a service another app calls. One container runs
the whole chain of one episode after another: step 1, the intake (pipeline/zumi: the pages stitched and cut into
boxes, the chapter .zumi the rest reads; free), then segment/episode.py (steps 2-10d).

The pages come in one of two ways, both ending as <INPUTS>/<root>/<episode>/0001.png, 0002.jpg, ... in the order
given, with pages.json (where each came from): "pages", https links downloaded by the job (each to a .part file,
checked against its Content-Length, opened and decoded whole, then renamed: a broken one is never kept), or
"pages_dir", a folder already on the volume under INPUTS, read in natural name order (an operator's
`modal volume put`, and the batch's upload). A page there and whole is not fetched again. The intake is stamped
with the pages' content (fresh.py): the same pages keep the chapter, other pages make it again, and every step
after it follows by its own stamp. A job for an episode whose pages.json names other pages is refused unless it
says "replace": true, since the work paid for on the old pages would be redone.

Batch, from this repo:

    modal run pipeline/modal/run_episodes.py --root full-1101 --episodes pepper-carrot-37,pepper-carrot-38 [--args "--no-erase"] [--budget 1.5] [--no-credit-check]

Uploads each episode's pages from .data/webtoons/<episode>/ (PAGES) with the chapters the exemplar bank crops from
(bubbles.Bank, .data/out/chapters) and .data/cache to the zumi-data volume, and the local out dir of an episode the
volume no longer holds; downloads each
episode's out dir to .data/out/<root>/dataset/<episode> whether it finished or not, the series casts to
.data/out/<root>/cast and the new cache entries. Nothing local is ever deleted.

Service, for a caller with no repo and no Python (the web app):

    modal deploy pipeline/modal/run_episodes.py        (again after any change to pipeline/segment, this file or .env)

It serves four HTTPS endpoints, every one behind Modal proxy auth (headers Modal-Key and Modal-Secret of a proxy
auth token made once in the workspace settings; a call without them is refused before it reaches this code):

    POST /jobs                {"episode": "name", "pages": ["https://.../1.png", ...] or "pages_dir": "name/of/folder"
                               (under INPUTS), "replace": false, "args": ["--no-music"], "root": "web",
                               "budget_usd": 0.5, "panels": 28, "no_credit_check": false, "tts": "gemini"}
                              (episode and one of pages, pages_dir are required; both may be left out while the
                              episode's pages are still on the volume, as when a failed job is started again)
                              -> 202 {"job": id, "state": "queued", "warnings": [...]}; 402 with the credits table
                              when a provider is low or depleted; 409 with the running job's id when that episode of
                              that root is queued or running (the second is rejected, never queued: one writer per
                              out dir), and 409 when the pages differ from the ones on the volume without "replace"
    GET  /jobs/{id}           -> {"state": "queued" | "running" | "done" | "failed", "step", "log" (last lines),
                              "usd" (paid API calls so far), "seconds", "exit", "reason", "resumable"}
    GET  /jobs/{id}/result    -> the exported .zumi (export_zumi.py), streamed from the volume; 409 until done
    GET  /credits?panels=28   (or ?pages=11: boxes estimated from the page count; or ?episode=name&root=web) -> {"can_run", "blocking", "warnings", "panels", "basis",
                              "rows": {provider: {"usd", "needed_usd", "state", "source", "as_of", "detail"}}}:
                              credits.py's table and its verdict, the rule POST /jobs starts by
    PUT  /credits/{provider}  {"usd": 12.40} -> the balance its owner reads now, for a provider with no balance
                              API (gemini); the row is then an estimate from it and the ledgers

Resuming. Every step of the chain skips what is current (fresh.py: an output is stamped after it is written, the
stamps themselves written whole), so the same batch command, or a new POST /jobs for the same root and episode,
goes on from what the volume holds and pays for nothing twice. The volume is committed when each step of
episode.py starts (the step before it is whole), every minute, and when an episode ends or is stopped: a container
that dies loses at most a minute. An episode is not done, and says why ("reason", with "resumable": true), when a
step failed (exit code), a provider refused for payment (HTTP 402, also where a step went on without it), the
daily cap refused a call (spend.py's refused.json), a page could not be fetched whole (the reason names each), or
the Modal budget ran out; only a bad input (no pages given and none on the volume) is not resumable. Before a
resumed run, a JSON file a killed run left half-written is removed, so its step
makes it again.

Retention. An episode's files on the volume (its pages, its chapter .zumi, its out dir) go only when its service job is done
and exported, or RETAIN_S (24 hours) after its last activity (<out dir>/.last-activity, kept by the run); a failed
job's record goes with them. The exported .zumi and its job's record stay RESULT_S (7 days). The sweep runs at the
start of every run, batch or service, and every hour once deployed (sweep). The series casts and the cache stay:
later episodes of a series read them.

Spending. Runs, jobs and the sweep take turns on the volume (one writer: LOCK), so batch and service share the
ledgers on it (LEDGERS_DIR), read and written by spend.py as it does locally, under one cap a day (ZUMI_DAILY_USD,
2 USD unless set: in pipeline/.env at deploy for the service, in the environment for the batch). The batch takes
off what this machine spent outside Modal today and brings every new line of the volume's ledgers into the local
ones. What this machine spends outside Modal never reaches the volume, so a service job does not count it: that
part of the cap is not shared. Before a run starts, credits.py's table must show no provider low or depleted
(--no-credit-check, "no_credit_check": true to start anyway).

The Modal budget of a run (BUDGET_USD, --budget or "budget_usd", at most MAX_BUDGET_USD) is the time the episodes
get at the GPU, CPU and memory rates below. Estimated, not measured: a 28-panel episode from scratch takes 45-80
minutes (0.75-1.3 USD), so the default stops it part way. SAM 3.1, DA3MONO-LARGE, MoGe-3 and the identity encoders
are downloaded once into the zumi-models volume (Hugging Face; SAM 3.1 is gated: the local Hugging Face token);
the service needs them and the exemplar bank's chapters there: one batch run, or
`modal run pipeline/modal/run_episodes.py::weights` and `modal volume put zumi-data <chapter>.zumi /chapters/`.
MoGe-3 runs in its own environment (MOGE_PYTHON, as pipeline/.venv-moge locally). The keys come from pipeline/.env
as a Modal secret, never written into the image.
"""
from __future__ import annotations

import collections
import datetime as dt
import filecmp
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import modal

PIPE = Path(__file__).resolve().parent.parent  # pipeline/
REMOTE = "/root/pipeline"
GPU, CPUS, MEM_MB = "L4", 2, 12288  # L4: 24 GB, bf16 (SAM's autocast); 2 cores and 12 GB carry the per-box CPU work
USD_PER_HOUR = 0.80 + CPUS * 0.0473 + MEM_MB / 1024 * 0.008  # `modal billing rates`, 2026-11-15
BUDGET_USD = 0.5      # a run's Modal budget unless it asks for another (--budget, "budget_usd")
MAX_BUDGET_USD = 2.0  # the most a run may ask for: the GPU function's own time limit
BANK_CHAPTERS = ("tower-of-god-s3-223", "true-beauty-5")  # .data/exemplars/bank.json's sources
SAM = ("facebook/sam3.1", "sam3.1_multiplex.pt")
DA3 = "depth-anything/DA3MONO-LARGE"
# what the later steps read from the Hugging Face cache: MoGe-3 (place_geometry.py), then the identity encoders
# (character_identity.py: CCIP, Magiv2, DINOv3 through timm); (repo, file or None for the whole repo)
WEIGHTS = (("Ruicheng/moge-3-vitl", "model.pt"), ("deepghs/ccip_onnx", "ccip-caformer_b36-24/model.ckpt"),
           ("ragavsachdeva/magiv2", "pytorch_model.bin"), ("timm/vit_large_patch16_dinov3.lvd1689m", None))
CU128 = "https://download.pytorch.org/whl/cu128"
MOGE_PYTHON = "/opt/moge/bin/python"  # places.py finds it by ZUMI_MOGE_PYTHON
# MoGe's environment as pipeline/.venv-moge holds it (`uv pip freeze`, 2026-11-15): MoGe at its commit, which brings
# its own pinned git dependencies, and the packages place_geometry.py imports at the local versions
MOGE_PINS = ("torch==2.10.0+cu128", "torchvision==0.25.0+cu128", "numpy==2.5.4", "scipy==1.18.1", "pillow==12.3.0",
             "trimesh==5.2.0", "opencv-python-headless==5.0.0.93", "huggingface-hub==2.4.0",
             "git+https://github.com/microsoft/MoGe.git@74fbce054ebed49800de42d0ad0e83495065719a")
SERVICE_ROOT = "web"                   # the run a job belongs to unless it names one
VOLUME_LEDGERS = "/spend/ledgers"      # the ledgers batch and service share, as the volume names them
LEDGERS_DIR = "/data" + VOLUME_LEDGERS  # and as a container sees them
STARTING_S = 120                       # a "starting-<time>" lock token older than this was left by a failed start
LOCK = "lock:volume"                   # jobs' key for the volume's one writer: the call id of a run or a sweep
RETAIN_S = 24 * 3600                   # an episode's files stay this long after its last activity
RESULT_S = 7 * 24 * 3600               # an exported .zumi and its job's record stay this long
ACTIVE = ".last-activity"              # in an out dir: the time (epoch seconds) a run last worked on it
NAME = re.compile(r"[a-z0-9][a-z0-9._-]{0,79}")  # an episode or root name: it becomes a folder on the volume
INPUTS = "/data/inputs"                # the pages: <INPUTS>/<root>/<episode>/ per job, operators' folders beside
PAGES = PIPE / ".data/webtoons"        # the batch's pages on this machine: <PAGES>/<episode>/
MAX_PAGES, MAX_PAGE_MB = 200, 64       # the most pages a job may bring, and the largest one
PAGE_EXT = {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}  # a page's file name by what it decodes as (the
                                                             # formats zumi.intake lists)
# the chain's settings a run takes from its caller: the voice backend (voices.backend; Gemini when unset) and the
# backend's requests a day. The batch passes this machine's; a job may name "tts"; the service's others come from
# pipeline/.env at deploy
SETTINGS = ("ZUMI_TTS", "ZUMI_TTS_DAILY_REQUESTS")
TTS = ("gemini", "inworld")            # voices.BACKENDS' names
LOG_LINES = 30                         # a job's last lines of output kept for its status
# an HTTP 402 as the chain's modules word it (bfl.py and lyria.py "HTTP 402", openrouter.py, inworld.py, and
# requests for fal.py): the provider wants payment
PAYMENT = re.compile(r"\b(?:HTTP|OpenRouter|Inworld) 402\b|\b402 Client Error")


def _seconds(usd: float) -> int:
    """The time a Modal budget buys at this container's rates."""
    return int(usd / USD_PER_HOUR * 3600)


def _requirements() -> list[str]:
    """segment's locked dependencies (uv.lock), platform markers kept: pip installs the Linux ones."""
    out = subprocess.run(["uv", "export", "--frozen", "--no-hashes", "--no-emit-project", "--no-header"],
                         cwd=PIPE / "segment", capture_output=True, text=True, check=True).stdout
    return [line.strip() for line in out.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _tz() -> str:
    """This machine's UTC offset as a POSIX TZ ("LCL3:00" for UTC-3): the container dates its ledger lines by the
    local day, the day spend.py's cap counts (in UTC a run near midnight would start a new day's cap)."""
    west = -int(dt.datetime.now().astimezone().utcoffset().total_seconds())
    return f"LCL{'-' if west < 0 else ''}{abs(west) // 3600}:{abs(west) % 3600 // 60:02d}"


# The service's daily cap is spend.py's default unless the deploying shell sets ZUMI_DAILY_USD (the owner's permission
# for that day): `ZUMI_DAILY_USD=6 modal deploy ...` holds until the next deploy without it.
ENV = {"PYTHONUNBUFFERED": "1", "TZ": _tz() if modal.is_local() else "",
       **({"ZUMI_DAILY_USD": os.environ["ZUMI_DAILY_USD"]} if modal.is_local() and os.environ.get("ZUMI_DAILY_USD") else {})}
image = (
    # gcc: triton (SAM 3.1, MoGe's sparse blocks) compiles its kernels' launchers; DejaVu: the identity sheets' labels
    modal.Image.debian_slim(python_version="3.12")
    .apt_install("git", "libgl1", "libglib2.0-0", "gcc", "fonts-dejavu-core")
    .pip_install(*(_requirements() if modal.is_local() else []), extra_index_url=CU128)
    .pip_install("typer>=0.15", "pydantic>=2.9")  # the intake's own (pipeline/pyproject.toml), beside segment's
    .run_commands("python -m venv /opt/moge",
                  f"/opt/moge/bin/pip install --no-cache-dir --extra-index-url {CU128} " + " ".join(MOGE_PINS))
    .env({**ENV, "HF_HOME": f"{REMOTE}/.models/hf", "ZUMI_MOGE_PYTHON": MOGE_PYTHON})
    .add_local_dir(PIPE / "segment", f"{REMOTE}/segment", ignore=["**/__pycache__", "experiments/**"])
    .add_local_dir(PIPE / "zumi", f"{REMOTE}/zumi", ignore=["**/__pycache__"])
    .add_local_dir(PIPE / ".vendor/Depth-Anything-3", f"{REMOTE}/.vendor/Depth-Anything-3", ignore=["**/__pycache__"])
    .add_local_file(PIPE / ".data/exemplars/bank.json", f"{REMOTE}/.data/exemplars/bank.json")
)
api_image = (  # the endpoints and the sweep: no model, only the credits check and the spend guard it reads
    modal.Image.debian_slim(python_version="3.12").pip_install("fastapi[standard]").env(ENV)
    .add_local_file(PIPE / "segment/credits.py", f"{REMOTE}/segment/credits.py")
    .add_local_file(PIPE / "segment/spend.py", f"{REMOTE}/segment/spend.py")
    .add_local_file(PIPE / "segment/gemini_tts.py", f"{REMOTE}/segment/gemini_tts.py")  # its prices and day's count
    .add_local_file(PIPE / "segment/lyria.py", f"{REMOTE}/segment/lyria.py")
)
app = modal.App("zumi-episodes", image=image)
models = modal.Volume.from_name("zumi-models", create_if_missing=True)
data = modal.Volume.from_name("zumi-data", create_if_missing=True)
# "job:<id>": a job's record; "lock:<root>/<episode>": the job that has that episode; LOCK
jobs = modal.Dict.from_name("zumi-jobs", create_if_missing=True)


def _hf_token() -> dict:
    f = Path.home() / ".cache/huggingface/token"
    return {"HF_TOKEN": f.read_text().strip()} if f.exists() else {}


def _env_keys() -> dict:
    """pipeline/.env's KEY=value lines."""
    lines = (PIPE / ".env").read_text().splitlines()
    return dict(l.split("=", 1) for l in (l.strip() for l in lines) if "=" in l and not l.startswith("#"))


keys = modal.Secret.from_dict(_env_keys() if modal.is_local() else {})
hf = modal.Secret.from_dict(_hf_token() if modal.is_local() else {})
SAM_CKPT = Path(f"{REMOTE}/.models/sam3/official") / SAM[1]


@app.function(cpu=1, memory=4096, timeout=3600, volumes={f"{REMOTE}/.models": models}, secrets=[hf])
def weights() -> str:
    """SAM 3.1's checkpoint where sam.py reads it; DA3 and WEIGHTS in the Hugging Face cache (HF_HOME, on the
    volume), where their steps look; skipped when already there."""
    from huggingface_hub import hf_hub_download, snapshot_download
    if not SAM_CKPT.exists():
        hf_hub_download(SAM[0], SAM[1], local_dir=SAM_CKPT.parent)
    snapshot_download(DA3)
    for repo, file in WEIGHTS:
        hf_hub_download(repo, file) if file else snapshot_download(repo)
    models.commit()
    return f"{SAM_CKPT.name} {SAM_CKPT.stat().st_size / 1e9:.2f} GB, {DA3}, " + ", ".join(r for r, _ in WEIGHTS)


# ---------------------------------------------------------------- the volume: one writer, the ledgers, what stays

def _pending(call_id: str) -> tuple[bool, str | None]:
    """(a function call is still queued or running, the error it ended with if any)."""
    try:
        modal.FunctionCall.from_id(call_id).get(timeout=0)
        return False, None
    except TimeoutError:
        return True, None
    except Exception as e:  # the call raised, was stopped at its time limit, or the id is no call
        return False, f"{type(e).__name__}: {e}"


def _take(key: str, owner: str) -> str | None:
    """jobs[key] for `owner` unless a live call has it: returns that call's id (or the "starting-<time>" token of a
    job being started), else None once it is the owner's. A key left by a call that ended without freeing it, or by
    a start that failed (STARTING_S), is taken over."""
    def live(holder: str) -> bool:
        if holder.startswith("starting-"):
            return time.time() - float(holder[len("starting-"):]) < STARTING_S
        return _pending(holder)[0]

    for _ in range(2):
        if jobs.put(key, owner, skip_if_exists=True):
            return None
        holder = jobs.get(key)
        if holder is not None and holder != owner and live(str(holder)):
            return holder
        if holder is not None:
            jobs.pop(key)
    return jobs.get(key)


def _free(key: str, owner: str) -> None:
    if jobs.get(key) == owner:
        jobs.pop(key)


def _ledgers() -> Path:
    """spend.py's ledger folder in this container, as the volume's shared one."""
    Path(LEDGERS_DIR).mkdir(parents=True, exist_ok=True)
    link = Path(f"{REMOTE}/.data/spend")
    link.parent.mkdir(parents=True, exist_ok=True)
    if not link.exists():
        link.symlink_to(LEDGERS_DIR)
    return Path(LEDGERS_DIR)


def _ledger_usd(d: Path) -> float:
    """Every line of the ledgers in d, in USD (spend.py's lines say "cost" or "usd")."""
    return sum(float(e.get("cost", e.get("usd", 0)) or 0)
               for f in d.glob("*.jsonl") for e in map(json.loads, f.read_text().splitlines()))


def _old(marker: Path, limit: float, now: float) -> bool:
    """The time in a marker file is over `limit` seconds ago. A marker missing or unreadable is written now and is
    not old: what carries no time starts its wait, it is never taken for expired."""
    try:
        return now - float(marker.read_text()) > limit
    except (OSError, ValueError):
        marker.write_text(str(now))
        return False


def _drop_episode(root: str, ep: str) -> None:
    """An episode's files off the volume: its out dir, its pages (the job's folder and the batch's upload beside
    it), and its chapter .zumi unless another run's out dir is of the same episode or the exemplar bank crops from
    it."""
    for d in (f"/data/out/{root}/dataset/{ep}", f"{INPUTS}/{root}/{ep}", f"{INPUTS}/{root}/{ep}.src"):
        shutil.rmtree(d, ignore_errors=True)
    if ep not in BANK_CHAPTERS and not list(Path("/data/out").glob(f"*/dataset/{ep}")):
        for f in (Path(f"/data/chapters/{ep}.zumi"), Path(f"/data/chapters/{ep}.seen")):
            f.unlink(missing_ok=True)


def _sweep() -> list[str]:
    """What has had its time, off the volume (the caller holds LOCK): out dirs RETAIN_S after their last activity
    with their .zumi, a .zumi no out dir is of RETAIN_S after it was first seen, exported episodes RESULT_S after
    they were made, and the records of jobs ended that long ago (RESULT_S done, RETAIN_S failed)."""
    now, gone = time.time(), []
    for out in Path("/data/out").glob("*/dataset/*"):
        if jobs.get(f"lock:{out.parts[-3]}/{out.name}") is not None:  # a job has it, queued or running
            continue
        if _old(out / ACTIVE, RETAIN_S, now):
            _drop_episode(out.parts[-3], out.name)
            gone.append(str(out))
    held = {p.name for p in Path("/data/out").glob("*/dataset/*")}
    for z in Path("/data/chapters").glob("*.zumi"):
        if z.stem not in BANK_CHAPTERS and z.stem not in held and _old(z.with_suffix(".seen"), RETAIN_S, now):
            z.unlink()
            z.with_suffix(".seen").unlink(missing_ok=True)
            gone.append(str(z))
    for z in Path("/data/out").glob("*/export/*.zumi"):
        if _old(z.with_suffix(".made"), RESULT_S, now):
            z.unlink()
            z.with_suffix(".made").unlink(missing_ok=True)
            gone.append(str(z))
    for k, rec in list(jobs.items()):
        if str(k).startswith("job:") and isinstance(rec, dict) and rec.get("ended_at") and \
                now - rec["ended_at"] > (RESULT_S if rec.get("state") == "done" else RETAIN_S):
            jobs.pop(k)
    return gone


def _drop_broken(out: Path) -> None:
    """The JSON files of an out dir that do not parse, removed: a run killed while it wrote one left it cut short,
    and its step makes it again (a missing output is not current)."""
    for f in out.rglob("*.json"):
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            print(f"  {f}: cut short by an earlier run, removed")
            f.unlink()


# ---------------------------------------------------------------- the pages

def _natural(name: str) -> list:
    """zumi.intake's order of file names: runs of digits as numbers (2.jpg before 10.jpg)."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", name)]


def _images(folder: Path) -> list[Path]:
    """A folder's image files in natural name order."""
    return sorted((p for p in folder.iterdir() if p.suffix.lower() in {*PAGE_EXT.values(), ".jpeg"}),
                  key=lambda p: _natural(p.name))


def _sources_of(d: Path) -> list[str] | None:
    """Where the pages in a job's folder came from (its pages.json), None when it has none."""
    try:
        return json.loads((d / "pages.json").read_text()).get("sources") or None
    except (OSError, ValueError):
        return None


def _whole(f: Path) -> str:
    """The format of an image file that opens and decodes to its last row (PIL: a file cut short fails here); raises
    otherwise, also for a format the intake does not read."""
    from PIL import Image
    with Image.open(f) as im:
        fmt = im.format
        im.verify()
    with Image.open(f) as im:  # verify leaves the image unusable, and does not decode it
        im.load()
    if fmt not in PAGE_EXT:
        raise ValueError(f"a {fmt} image, not png, jpg or webp")
    return fmt


def _page(src: str, d: Path, n: int, opener=urllib.request.urlopen) -> str:
    """Page n from its source into d as <n, four digits><ext>, returning that name. It is first written to <n>.part
    (a link: streamed, at most MAX_PAGE_MB, its length held against the reply's Content-Length when it states one;
    a "dir:<path>" source: copied), then checked whole (_whole) and only then renamed. Raises RuntimeError saying
    what was wrong with the page, its .part removed."""
    part = d / f"{n:04d}.part"
    try:
        if src.startswith("dir:"):
            shutil.copyfile(src[len("dir:"):], part)
        else:
            size = 0
            req = urllib.request.Request(src, headers={"User-Agent": "zumi-pipeline"})
            with opener(req, timeout=60) as r, part.open("wb") as f:
                stated = r.headers.get("Content-Length")
                while chunk := r.read(1 << 20):
                    size += len(chunk)
                    if size > MAX_PAGE_MB << 20:
                        raise ValueError(f"over {MAX_PAGE_MB} MB")
                    f.write(chunk)
            if stated is not None and int(stated) != size:
                raise ValueError(f"{size} bytes received of {stated}")
        if not part.stat().st_size:
            raise ValueError("an empty file")
        name = f"{n:04d}{PAGE_EXT[_whole(part)]}"
        part.replace(d / name)
        return name
    except Exception as e:
        part.unlink(missing_ok=True)
        raise RuntimeError(f"page {n} ({type(e).__name__}: {str(e)[:120]})") from None


def _pages(d: Path, sources: list[str] | None, opener=urllib.request.urlopen) -> list[Path]:
    """The job's pages in its folder d, in the order of `sources` (links, or "dir:<path>" files; None: the sources
    its pages.json holds from an earlier job), as the files to cut. A page already there and whole (_whole) is
    kept; one missing or broken is fetched again; other sources than pages.json's mean other pages, and none of
    the old files stays. pages.json is saved after every page. Raises ValueError when there are no pages to go by,
    RuntimeError naming every page that could not be fetched whole."""
    saved = _sources_of(d)
    if sources is None:
        if not saved:
            raise ValueError("no pages for this episode on the volume: the job needs pages or pages_dir")
        sources = saved
    d.mkdir(parents=True, exist_ok=True)
    index = d / "pages.json"
    files = json.loads(index.read_text()).get("files", {}) if saved == sources else {}
    if saved != sources:
        for f in d.iterdir():
            if f.is_file():
                f.unlink()

    def save():
        tmp = index.with_suffix(".tmp")
        tmp.write_text(json.dumps({"sources": sources, "files": files}, indent=1))
        tmp.replace(index)

    bad = []
    for n, src in enumerate(sources, 1):
        name = files.get(str(n))
        if name and (d / name).exists():
            try:
                if src.startswith("dir:") and not filecmp.cmp(src[len("dir:"):], d / name, shallow=False):
                    raise ValueError("the folder's file was replaced")
                _whole(d / name)
                continue
            except Exception:  # there, but cut short or no longer the source's: fetched again
                (d / name).unlink()
        files.pop(str(n), None)
        try:
            files[str(n)] = _page(src, d, n, opener)
        except RuntimeError as e:
            bad.append(str(e))
        save()
    save()
    if bad:
        raise RuntimeError("pages not fetched: " + "; ".join(bad))
    return [d / files[str(n)] for n in range(1, len(sources) + 1)]


@app.function(image=api_image, cpu=0.25, memory=512, timeout=600, volumes={"/data": data},
              schedule=modal.Period(hours=1))
def sweep() -> list[str]:
    """_sweep every hour once the app is deployed; skipped while a run has the volume (it swept at its start)."""
    me = modal.current_function_call_id()
    if _take(LOCK, me):
        return []
    try:
        data.reload()
        gone = _sweep()
        data.commit()
        return gone
    finally:
        _free(LOCK, me)


# ---------------------------------------------------------------- the run, on the GPU

@app.function(gpu=GPU, cpu=CPUS, memory=MEM_MB, timeout=_seconds(MAX_BUDGET_USD) + 300, max_containers=1,
              secrets=[keys, hf], volumes={f"{REMOTE}/.models": models, "/data": data})
def run(root: str, episodes: list[str], args: list[str], cap_usd: float | None = None,
        budget_usd: float = BUDGET_USD, sources: dict | None = None, settings: dict | None = None) -> dict:
    """episode.py on each episode in turn, chapters from /data/chapters, out dirs in /data/out/<root>/dataset, until
    the budget's time is spent (the episode running then is stopped, with every process it started). Returns per
    episode {"exit", "s", "usd", "stopped": why it is not done, when it is not}.

    sources: {episode: its pages, links or "dir:<path>" files in order}; an episode not in it goes by the pages its
    folder on the volume has (_pages). settings: SETTINGS' values for the chain's environment. A batch run passes
    cap_usd, the day's cap less what its machine spent outside Modal. A service job passes None (spend.py's own
    cap); each episode it finishes is exported to
    /data/out/<root>/export/<episode>.zumi and its pages, chapter and out dir leave the volume, and the job's record (jobs)
    follows its step, last lines and cost. The module docstring says when the volume is committed and what a
    stopped episode keeps."""
    service = cap_usd is None
    call = modal.current_function_call_id()
    start, began = time.time(), dt.datetime.now().isoformat(timespec="seconds")
    ledgers, usd0 = Path(LEDGERS_DIR), [0.0]
    lock, over, done = threading.Lock(), threading.Event(), {}
    state = {"episode": episodes[0], "root": root, "state": "running", "step": "", "started_at": start}
    tail = collections.deque(maxlen=LOG_LINES)
    now = {"out": None, "payment": None}  # the out dir being worked on; the last line that said a provider wants payment

    def tell(**fields):
        """The job's record with its step, last lines and cost so far."""
        state.update(fields)
        if service:
            jobs[f"job:{call}"] = {**(jobs.get(f"job:{call}") or {}), **state, "log": list(tail),
                                   "usd": round(_ledger_usd(ledgers) - usd0[0], 4), "seconds": round(time.time() - start)}

    def save():
        with lock:
            if now["out"] is not None:
                (now["out"] / ACTIVE).write_text(str(time.time()))
            data.commit()

    def every_minute():
        while not over.wait(60):
            save()
            tell()

    def step(cmd: list[str], env: dict, cwd: str = f"{REMOTE}/segment") -> tuple[int, bool]:
        """One command of the chain with its output passed on line by line; (exit code, stopped by the budget)."""
        left = start + _seconds(budget_usd) - time.time()
        if left <= 0:
            return -1, True
        p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             text=True, errors="replace", start_new_session=True)
        late = threading.Event()

        def stop():  # the whole process group: the MoGe subprocess and the per-box workers with it
            late.set()
            try:
                os.killpg(p.pid, signal.SIGKILL)
            except ProcessLookupError:  # it ended as the time ran out
                pass

        timer = threading.Timer(left, stop)
        timer.start()
        for line in p.stdout:
            print(line, end="")
            tail.append(line.rstrip())
            if PAYMENT.search(line):
                now["payment"] = line.strip()[:300]
            if line.startswith("== "):  # episode.py names each step as it starts: the one before it is whole
                save()
                tell(step=line[3:].strip())
        code = p.wait()
        timer.cancel()
        return code, late.is_set()

    def refused() -> str | None:
        """The call the daily cap refused since this run began (spend.py's refused.json), if any."""
        try:
            r = json.loads((ledgers / "refused.json").read_text())
        except (OSError, ValueError):
            return None
        return r["what"] if r.get("ts", "") >= began else None

    def last_line() -> str:
        return next((l for l in reversed(tail) if l.strip()), "")[:300]

    def intake(ep: str, zumi: Path) -> str | None:
        """Step 1: the episode's pages on the volume (_pages), then cut into the chapter .zumi episode.py reads,
        unless the chapter is the one made from these same pages by this intake (stamped: the pages by content and
        the intake's code; and the chapter's own content, since episodes of one name share its path across roots).
        Returns why it failed, None when the chapter is there."""
        if f"{REMOTE}/segment" not in sys.path:
            sys.path.insert(0, f"{REMOTE}/segment")
        import fresh
        d = Path(f"{INPUTS}/{root}/{ep}")
        line = f"== 1 intake: {ep}'s pages"
        print(line)
        tail.append(line)
        tell(step=line[3:])
        pages = _pages(d, (sources or {}).get(ep))
        stamps = fresh.Stamps(d / "stamps.json")
        stamp = fresh.digest(*pages, *sorted(Path(f"{REMOTE}/zumi").rglob("*.py")))
        if stamps.current("intake", stamp, zumi) and stamps.get("chapter") == fresh.digest(zumi):
            print(f"  {len(pages)} pages, the chapter is current")
            return None
        new = zumi.with_suffix(".new.zumi")
        zumi.parent.mkdir(parents=True, exist_ok=True)
        head, _, number = ep.rpartition("-")  # the series as character_identity.series_of names it
        code, late = step([sys.executable, "-u", "-m", "zumi.cli", "intake", str(d), "--out", str(new), "--series",
                           head if head and number.isdigit() else ep], env, REMOTE)
        if late or code:
            new.unlink(missing_ok=True)
            return "the Modal budget ran out" if late else f"the intake failed (exit {code}): {last_line()}"
        new.replace(zumi)
        stamps.made("intake", stamp)
        stamps.made("chapter", fresh.digest(zumi))
        return None

    env = {**os.environ, "ZUMI_CPUS": str(CPUS), **{k: str(v) for k, v in (settings or {}).items() if k in SETTINGS},
           **({} if service else {"ZUMI_DAILY_USD": f"{cap_usd:.4f}"})}
    failed, resumable, owned = None, True, False
    try:
        holder = _take(LOCK, call)
        for _ in range(12):  # the hourly sweep has it for seconds; a batch run for as long as it runs
            if not holder:
                break
            time.sleep(5)
            holder = _take(LOCK, call)
        if holder:
            raise RuntimeError(f"another run is writing the data volume ({holder}): start this one again when it ends")
        owned = True
        data.reload()  # a container kept from the last job: the volume as it is now
        local = Path(f"{REMOTE}/.data")
        for d in ("cache", "out"):
            (Path("/data") / d).mkdir(parents=True, exist_ok=True)
            if not (local / d).exists():
                (local / d).symlink_to(Path("/data") / d)
        usd0[0] = _ledger_usd(_ledgers())
        tell()
        if not SAM_CKPT.exists():
            raise RuntimeError("no weights on the zumi-models volume: modal run pipeline/modal/run_episodes.py::weights")
        for ep in episodes:  # this run's episodes are active before the sweep looks
            out = Path(f"/data/out/{root}/dataset/{ep}")
            out.mkdir(parents=True, exist_ok=True)
            (out / ACTIVE).write_text(str(time.time()))
        for path in _sweep():
            print(f"swept: {path}")
        threading.Thread(target=every_minute, daemon=True).start()
        for ep in episodes:
            t, spent = time.perf_counter(), _ledger_usd(ledgers)
            zumi, out = Path(f"/data/chapters/{ep}.zumi"), Path(f"/data/out/{root}/dataset/{ep}")
            now.update(out=out, payment=None)
            code, late = -1, False
            why = intake(ep, zumi)
            if why is None:
                _drop_broken(out)
                code, late = step([sys.executable, "-u", "episode.py", str(zumi), str(out), *args], env)
                why = ("the Modal budget ran out" if late else
                       f"a provider refused for payment: {now['payment']}" if now["payment"] else
                       f"the daily API cap: {r}" if (r := refused()) else
                       f"a step failed (exit {code}): {last_line()}" if code else None)
            if service and why is None:
                export = Path(f"/data/out/{root}/export/{ep}.zumi")
                export.parent.mkdir(parents=True, exist_ok=True)
                tell(step="export")
                code, late = step([sys.executable, "-u", "export_zumi.py", str(zumi), str(out), str(export)], env)
                why = "the Modal budget ran out" if late else f"the export failed (exit {code}): {last_line()}" if code else None
                if why is None:  # the result is made: the episode's files leave the volume, the export stays
                    export.with_suffix(".made").write_text(str(time.time()))
                    with lock:  # not while the minute's save marks the out dir
                        now["out"] = None
                        _drop_episode(root, ep)
            done[ep] = {"exit": code, "s": round(time.perf_counter() - t), "usd": round(_ledger_usd(ledgers) - spent, 4),
                        **({"stopped": why} if why else {})}
            print(f"######## {ep}: {why or 'done'} in {done[ep]['s']} s")
            save()
    except Exception as e:
        failed, resumable = f"{type(e).__name__}: {e}", not isinstance(e, ValueError)
        raise
    finally:
        over.set()
        if owned:
            save()
        why = failed or next((d["stopped"] for d in done.values() if d.get("stopped")), None)
        ok = why is None and len(done) == len(episodes)
        tell(state="done" if ok else "failed", ended_at=time.time(), exit=next(reversed([d["exit"] for d in done.values()]), None),
             reason=why, resumable=None if ok else resumable)
        if owned:
            _free(LOCK, call)
        if service:
            for ep in episodes:  # the episode is free for another job
                _free(f"lock:{root}/{ep}", call)
    return done


# ---------------------------------------------------------------- the service: jobs over HTTPS

@app.function(image=api_image, cpu=0.25, memory=512, timeout=900, secrets=[keys], volumes={"/data": data})
@modal.asgi_app(requires_proxy_auth=True)
def api():
    """The endpoints (the module docstring has their shapes). Proxy auth is checked by Modal before a request
    arrives: there is no open route."""
    from fastapi import Body, FastAPI, HTTPException
    from fastapi.responses import FileResponse, JSONResponse

    sys.path.insert(0, f"{REMOTE}/segment")
    import credits

    web = FastAPI(title="zumi-episodes")

    def table(panels: int, out: Path | None = None) -> dict:
        """credits.check on the volume's ledgers, stated balances and counts as they are now."""
        data.reload()
        _ledgers()
        return credits.check(panels, out=out)

    def record(job: str) -> dict:
        rec = jobs.get(f"job:{job}")
        if rec is None:
            raise HTTPException(404, "no such job")
        if rec["state"] in ("queued", "running"):
            pending, error = _pending(job)
            if not pending:  # it ended without saying so: the time limit or a crash
                rec = jobs.get(f"job:{job}")
                if rec["state"] in ("queued", "running"):
                    rec = {**rec, "state": "failed", "ended_at": time.time(), "resumable": True,
                           "reason": error or "the run ended without a result"}
                    jobs[f"job:{job}"] = rec
        return rec

    @web.get("/credits")
    def credit(panels: int = 0, pages: int = 0, episode: str = "", root: str = SERVICE_ROOT):
        """With an episode whose chapter is on the volume (its intake has run), its boxes are counted, and its voiced
        lines when its out dir has speaker records; with its pages there, or a page count, the boxes are estimated
        from the pages; the other needs stay the estimate from the box count ("basis" says which)."""
        if episode and not (NAME.fullmatch(episode) and NAME.fullmatch(root)):
            raise HTTPException(422, "episode and root: lower-case letters, digits, '.', '_' and '-'")
        data.reload()
        zumi, basis, out = Path(f"/data/chapters/{episode}.zumi"), "the box count given", None
        pages = pages or len(_sources_of(Path(f"{INPUTS}/{root}/{episode}")) or []) if episode else pages
        if episode and zumi.exists():
            panels, basis, out = credits.panels_of(zumi), f"{episode}'s boxes", Path(f"/data/out/{root}/dataset/{episode}")
        elif not panels and pages:
            panels = credits.panels_from_pages(pages)
            basis = f"estimated from {pages} pages, {credits.PANELS_PER_PAGE} boxes a page"
        elif not panels:
            panels, basis = credits.DEFAULT_PANELS, "no episode on the volume and no count: the default box count"
        t = table(panels, out)
        return {"panels": panels, "basis": basis, **credits.verdict(t), "rows": t}

    @web.put("/credits/{provider}")
    def state(provider: str, body: dict = Body(...)):
        """The provider's balance as its owner reads it now ({"usd": 12.40}), for a provider with no balance API."""
        try:
            usd = float(body["usd"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, 'body: {"usd": the balance}') from None
        data.reload()
        _ledgers()
        try:
            saved = credits.set_anchor(provider, usd)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        data.commit()  # its own file: no run writes it
        return {"provider": provider, **saved[provider]}

    @web.post("/jobs", status_code=202)
    def start(body: dict = Body(...)):
        ep, root = body.get("episode") or "", body.get("root") or SERVICE_ROOT
        args, budget = body.get("args") or [], float(body.get("budget_usd") or BUDGET_USD)
        pages, pages_dir = body.get("pages"), body.get("pages_dir")
        if not NAME.fullmatch(ep) or not NAME.fullmatch(root):
            raise HTTPException(422, "episode and root: lower-case letters, digits, '.', '_' and '-'")
        if pages is not None and pages_dir is not None:
            raise HTTPException(422, "pages or pages_dir, not both")
        if pages is not None and not (isinstance(pages, list) and 0 < len(pages) <= MAX_PAGES and
                                      all(isinstance(p, str) and p.startswith("https://") for p in pages)):
            raise HTTPException(422, f"pages: 1 to {MAX_PAGES} https links to the page images, in reading order")
        if pages is not None and len(set(pages)) < len(pages):
            raise HTTPException(422, "pages: a link is given twice")
        if body.get("tts") and body["tts"] not in TTS:
            raise HTTPException(422, f"tts: one of {', '.join(TTS)}")
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise HTTPException(422, "args: a list of episode.py arguments")
        if not 0 < budget <= MAX_BUDGET_USD:
            raise HTTPException(422, f"budget_usd: over 0 and at most {MAX_BUDGET_USD}")
        data.reload()
        if pages_dir is not None:  # an operator's folder of pages already on the volume
            folder = (Path(INPUTS) / str(pages_dir)).resolve()
            # both resolved: the volume's mount can be a link, so a resolved folder is not under the unresolved INPUTS
            if not folder.is_relative_to(Path(INPUTS).resolve()) or not folder.is_dir():
                raise HTTPException(422, f"pages_dir: a folder under {INPUTS[len('/data'):]} on the volume")
            pages = ["dir:" + p.as_posix() for p in _images(folder)]
            if not 0 < len(pages) <= MAX_PAGES:
                raise HTTPException(422, f"pages_dir: 1 to {MAX_PAGES} png, jpg or webp files")
        have = _sources_of(Path(f"{INPUTS}/{root}/{ep}"))
        if pages is None and not have:
            raise HTTPException(422, "pages or pages_dir: this episode has no pages on the volume")
        if pages is not None and have and pages != have and not body.get("replace"):
            return JSONResponse({"error": 'this episode has other pages on the volume; "replace": true starts over '
                                          "from the new ones (what was made from the old is made again)"}, 409)
        zumi = Path(f"/data/chapters/{ep}.zumi")
        known = pages == have or pages is None  # the chapter on the volume is of these pages
        panels = int(body.get("panels") or 0) or (credits.panels_of(zumi) if known and zumi.exists() else
                                                  credits.panels_from_pages(len(pages or have)))
        t = table(panels)
        missing = [c for c in BANK_CHAPTERS if not Path(f"/data/chapters/{c}.zumi").exists()]
        if missing:
            raise HTTPException(503, f"the exemplar bank's chapters are not on the volume: {', '.join(missing)}")
        v = credits.verdict(t)
        if not v["can_run"] and not body.get("no_credit_check"):
            return JSONResponse({"error": "credit too low to start", **v, "rows": t}, 402)
        key, token = f"lock:{root}/{ep}", f"starting-{time.time()}"
        holder = _take(key, token)
        if holder:
            return JSONResponse({"error": "this episode is queued or running", "job": holder}, 409)
        try:
            call = run.spawn(root, [ep], args, None, budget, {ep: pages} if pages is not None else None,
                             {"ZUMI_TTS": body["tts"]} if body.get("tts") else None)
        except Exception:
            jobs.pop(key)
            raise
        jobs[key] = call.object_id
        # unless the run has started and written its own record already
        jobs.put(f"job:{call.object_id}", {"episode": ep, "root": root, "state": "queued", "queued_at": time.time()},
                 skip_if_exists=True)
        return {"job": call.object_id, "state": "queued", "warnings": v["warnings"]}

    @web.get("/jobs/{job}")
    def status(job: str):
        return record(job)

    @web.get("/jobs/{job}/result")
    def result(job: str):
        rec = record(job)
        if rec["state"] != "done":
            raise HTTPException(409, f"the job is {rec['state']}")
        data.reload()
        f = Path(f"/data/out/{rec['root']}/export/{rec['episode']}.zumi")
        if not f.exists():
            raise HTTPException(404, "the exported episode is gone (kept RESULT_S after it was made)")
        return FileResponse(f, media_type="application/zip", filename=f.name)

    return web


# ---------------------------------------------------------------- the batch, from this machine

def _download(remote: str, dest: Path) -> int:
    """Every file under the volume path into dest (the same relative paths); returns the count, 0 when the path is
    not on the volume."""
    n = 0
    try:
        entries = data.listdir(remote, recursive=True)
    except (FileNotFoundError, modal.exception.NotFoundError):
        return 0
    for e in entries:
        if e.type == modal.volume.FileEntryType.FILE:
            out = dest / Path(e.path).relative_to(remote.lstrip("/"))
            out.parent.mkdir(parents=True, exist_ok=True)
            with out.open("wb") as f:
                for chunk in data.read_file(e.path):
                    f.write(chunk)
            n += 1
    return n


def _on_volume(path: str) -> bool:
    try:
        return bool(data.listdir(path))
    except (FileNotFoundError, modal.exception.NotFoundError):
        return False


def _volume_ledgers(names: list[str]) -> dict[str, list[bytes]]:
    """The lines of the volume's shared ledgers, by ledger file name."""
    there = {Path(e.path).name for e in data.listdir(VOLUME_LEDGERS)} if _on_volume(VOLUME_LEDGERS) else set()
    return {n: [l for l in b"".join(data.read_file(f"{VOLUME_LEDGERS}/{n}")).splitlines() if l.strip()]
            if n in there else [] for n in names}


@app.local_entrypoint()
def main(root: str, episodes: str, args: str = "--no-erase", budget: float = BUDGET_USD, no_credit_check: bool = False):
    sys.path.insert(0, str(PIPE / "segment"))
    import credits
    from spend import DAILY_CAP_USD, LEDGERS, _date, _usd

    if not 0 < budget <= MAX_BUDGET_USD:
        raise SystemExit(f"--budget: over 0 and at most {MAX_BUDGET_USD} USD (MAX_BUDGET_USD)")
    eps = [e for e in episodes.split(",") if e]
    chapters = PIPE / ".data/out/chapters"
    pages = {ep: _images(PAGES / ep) if (PAGES / ep).is_dir() else [] for ep in eps}
    if not all(0 < len(p) <= MAX_PAGES for p in pages.values()):
        raise SystemExit(f"1 to {MAX_PAGES} page images (png, jpg, webp) are needed in {PAGES}/<episode>/ for: " +
                         ", ".join(ep for ep, p in pages.items() if not 0 < len(p) <= MAX_PAGES))
    holder = jobs.get(LOCK)
    if holder and _pending(holder)[0]:
        raise SystemExit(f"another run is writing the data volume ({holder}): start this one when it ends")
    # one cap a day with the service: the volume's ledgers hold every Modal run's lines, this machine's hold those
    # (merged below) and what it spent outside Modal; the container's cap is the day's less the lines only here
    today = str(dt.date.today())
    names = {ledger.name: ledger for ledger in LEDGERS.values()}
    volume = _volume_ledgers(list(names))

    def only_here(name: str) -> collections.Counter:
        mine = collections.Counter(l for l in names[name].read_bytes().splitlines() if l.strip()) if names[name].exists() else collections.Counter()
        return mine - collections.Counter(volume[name])

    def usd_today(lines) -> float:
        return sum(_usd(e) for e in map(json.loads, lines) if _date(e) == today)

    outside = sum(usd_today(only_here(n).elements()) for n in names)
    cap = DAILY_CAP_USD - outside
    left = cap - sum(usd_today(volume[n]) for n in names)
    def theirs_of(name: str) -> dict:
        """A JSON file kept beside the volume's ledgers, {} when it is not there."""
        try:
            return json.loads(b"".join(data.read_file(f"{VOLUME_LEDGERS}/{name}")))
        except Exception:
            return {}

    # the stated balances, this machine's and the volume's as one: per provider the one stated last
    theirs = theirs_of(credits.ANCHORS.name)
    stated = credits.newest(credits.anchors(), theirs)
    if stated != credits.anchors():
        credits.ANCHORS.parent.mkdir(parents=True, exist_ok=True)
        credits.ANCHORS.write_text(json.dumps(stated, indent=1))
    try:  # the voice requests counted today where the run happens: the volume's count, not this machine's
        counts = json.loads(b"".join(data.read_file(f"{VOLUME_LEDGERS}/{credits.gemini_tts.COUNTER.name}")))
    except Exception:  # no count yet
        counts = {}
    sent = int(counts.get(str(dt.datetime.now(credits.gemini_tts.QUOTA_TZ).date()), 0))
    boxes = credits.panels_from_pages(sum(map(len, pages.values())))
    table = credits.check(boxes, left, None, sent)
    print(f"about {boxes} boxes, estimated from the pages ({credits.PANELS_PER_PAGE} a page)\n{credits.show(table)}")
    v = credits.verdict(table)
    for w in v["warnings"]:
        print("warning:", w)
    if not v["can_run"] and not no_credit_check:
        raise SystemExit("not started, credit too low (--no-credit-check to start anyway):\n  " + "\n  ".join(v["blocking"]))
    with data.batch_upload(force=True) as up:
        if stated != theirs:  # a balance stated on this machine since
            up.put_file(credits.ANCHORS, f"{VOLUME_LEDGERS}/{credits.ANCHORS.name}")
        for name in BANK_CHAPTERS:
            up.put_file(chapters / f"{name}.zumi", f"/chapters/{name}.zumi")
        for ep, files in pages.items():  # beside the job's own folder, which the run fills from it
            for f in files:
                up.put_file(f, f"{INPUTS[len('/data'):]}/{root}/{ep}.src/{f.name}")
        up.put_directory(PIPE / ".data/cache", "/cache")
        for ep in eps:  # an out dir the volume let go (RETAIN_S) and this machine still has: the run goes on from it
            mine = PIPE / f".data/out/{root}/dataset/{ep}"
            if mine.is_dir() and not _on_volume(f"/out/{root}/dataset/{ep}"):
                up.put_directory(mine, f"/out/{root}/dataset/{ep}")
                print(f"  {ep}: local out dir uploaded, the volume had none")
    print("uploaded:", ", ".join(f"{ep} ({len(p)} pages)" for ep, p in pages.items()), "the bank's chapters and .data/cache")
    print("weights:", weights.remote())
    print(f"GPU {GPU}, {CPUS} cores, {MEM_MB // 1024} GB: {USD_PER_HOUR:.3f} USD/h, stopped after "
          f"{_seconds(budget) // 60} min (Modal budget {budget} USD); API cap left today {left:.3f} USD")
    try:
        sources = {ep: [f"dir:{INPUTS}/{root}/{ep}.src/{f.name}" for f in files] for ep, files in pages.items()}
        done = run.remote(root, eps, args.split(), cap, budget, sources, {k: os.environ[k] for k in SETTINGS if k in os.environ})
    except Exception as e:  # the run failed: what it saved is on the volume
        print(f"run stopped: {type(e).__name__}: {e}")
        done = {}
    print("episodes:", done or "none reported")
    for ep in eps:
        n = _download(f"/out/{root}/dataset/{ep}", PIPE / f".data/out/{root}/dataset/{ep}")
        print(f"  {ep}: {n} files -> .data/out/{root}/dataset/{ep}")
    print(f"  cast: {_download(f'/out/{root}/cast', PIPE / f'.data/out/{root}/cast')} files -> .data/out/{root}/cast")
    _download("/cache", PIPE / ".data/cache")
    added = 0
    marked = theirs_of(credits.spend.DEPLETED.name)
    if marked:  # who refused for payment in the run just made
        credits.spend.DEPLETED.write_text(json.dumps(marked, indent=1))
    for name, lines in _volume_ledgers(list(names)).items():  # every line the volume has and this machine has not
        have = collections.Counter(l for l in names[name].read_bytes().splitlines() if l.strip()) if names[name].exists() else collections.Counter()
        new = list((collections.Counter(lines) - have).elements())
        if new:
            names[name].parent.mkdir(parents=True, exist_ok=True)
            with names[name].open("ab") as f:
                f.write(b"\n".join(new) + b"\n")
            added += len(new)
    from spend import spent_today
    print(f"ledger lines added: {added}; spent today {spent_today():.3f} USD")
