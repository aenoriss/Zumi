# Processing time: what can run in parallel (proposal, 2026-11-08)

Status: **proposed, not started.** From a five-member review of every step of `pipeline/segment` (code, run logs,
spend ledgers; no runs), then a Modal fan-out estimate. Figures are marked **[measured]** (run.json, ledger
timestamps, file times, a CPU benchmark) or **[est]** (reasoned). run.json has no timers inside a step, so every split
inside one (SAM vs review, plan vs erase vs render) is an estimate from ledger timestamps.

## Where the time goes today

A fresh episode (P&C 36, 29 boxes; P&C 39, 31 boxes) takes about **36 min** and **3.2 USD** against the default
2 USD/day cap, so a fresh episode does not finish in one day unless `ZUMI_DAILY_USD` is raised.

| Step | Time | Inside it |
|---|---|---|
| 2a lettering | 253–337 s [measured] | SAM ~125–150 s, review ~130–185 s [est] |
| 2b characters | 204–279 s [measured] | SAM ~95–110 s, review ~110–170 s [est] |
| 1 frames | 3–24 s [measured] | |
| 2c objects | 73 s [measured] | pick ~30, SAM ~60, review ~90 on P&C 39 [est] |
| 3+4 erase and layers | 298 s [measured, P&C 36] | plan ~172 s (DA3 27 s, the rest one CPU thread), erase ~61 s (41 calls), render ~63 s [measured from log and mtimes] |
| 5 Transcribe | 7–85 s, in the background [measured] | never on the critical path |
| 6 speakers | 2–6 s [measured] | |
| 7 identity | ~150 s | Sonnet call 96 s [measured], encoders 20–60 s [est] |
| 8 voices | ~120 s Inworld, ~300 s Gemini | reader 20 s, designs 65 s, lines 34 s (Inworld) / 258 s (Gemini, 160 s of it idle backoff) [measured] |
| 10 settings + score | ~520 s | settings + reviewer 43 s, Lyria 6 tracks one after another, 484 s from the reviewer's end [measured] |
| 10c places | ~360 s [est] | MoGe front+back 74 s a place [measured]; back's colour match ~28 s a place [measured] |
| export | 10 s [measured] | |

Note: the P&C 37–39 and webtoon runs on 2026-11-01/02 were `--no-erase`; their 95–133 s for 3+4 is plan + render only.

## True dependencies (what each step reads)

Every edge before identity is **per box**: box i can go on as soon as box i's inputs exist.

- frame layouts, lettering SAM, **character SAM** and **the object pick call** need only the box image. Characters
  never read the lettering (`characters.py:56`); the pick prompt has no masks (`objects.py:288-292`).
- frames.update needs the reviewed lettering and the layouts. Transcribe needs only the reviewed lettering.
- DA3 depth needs the image, the lettering and the frames; the plan also needs characters and objects; a box's erase
  needs only its own plan; its render needs its plan and plate.
- speakers need the box's cards (after its render), bubbles, Transcribe's kinds and frames.
- identity needs every box's cards and speakers (whole episode). The cards exist only after the render (held objects
  and fringe join in the plan), so identity cannot start earlier.
- **settings need only the erased backdrops and frames**; the **music reviewer** needs settings, speakers and identity's
  names (`score.py:118-131`); **Lyria** needs only the reviewer's spans and the settings. None reads voices or the
  clock: the clock is first used by the envelope, at export.
- voices need identity; lines need only their voice id (CONTEXT_LINES is text, no neighbour's audio); the clock needs
  every line's length; **places need only the clock and settings**, yet `episode.py` makes them wait for the whole score.

`episode.py` main() imposes edges that are not real: character SAM waits for the lettering review; frames.update waits
for all of 2b; the object pick waits for 2b and frames; inside each step all SAM runs before any review; inside a
review all single-mask checks run one after another; layers runs plan for all boxes, then erase for all, then render
for all; places wait for the score.

## Shared limits

- **GPU**: RTX 3060, 12 GB. SAM 3.1 holds 5.4 GB once loaded; DA3 1.3 GB; MoGe 1.4 GB and already ran out of memory at
  a 1920 x 960 merge. A second SAM is not worth it (memory, and the GPU is compute-bound). DA3 has no lock. MoGe must
  never overlap SAM.
- **Spend cap (fix first)**: `spend.reserve` **refuses** a call when today's spend + in-flight + this call would pass
  the cap (`spend.py:119`), and reservations are worst case (an erase reserves 0.06, costs 0.034). With steps
  overlapping, one step's burst refuses another's call and `paid_map` stops that step for the run. `spent_today()`
  re-reads ~13k ledger lines on every reserve, under the lock: 40 ms [measured]. In-flight reservations live per
  process, so two processes (or Modal containers) can pass the cap together.
- **Network**: WORKERS 16 is per `paid_map`, not global; OpenRouter backs off 10·2^k s while holding its reservation;
  BFL allows 24 in flight; Inworld 5 concurrent; Gemini TTS ~10/min and 100/day (64 lines use 64 of them); Lyria's
  limit is unknown.
- **One writer each**: run.json (read-modify-write), transcripts.json, the series cast (`Cast.save` vs `CI.load`), lines.json;
  speakers.json carries the cards stamp, so a box's speakers must follow its render.

## Proposed changes, ranked

| # | Change | Saving | Effort |
|---|---|---|---|
| 0 | **Spend cap**: keep today's total in memory; a call pushed over only by in-flight reservations waits instead of being refused. Prerequisite for every overlap. | correctness | S |
| 1 | **The end runs concurrently**: settings in the background right after 3+4; reviewer + Lyria in the background after identity (build `material()` before the thread, so the cast is not read mid-write); places stop waiting for the score. A new pool: `net` is shut down at `episode.py:295`. | ~340 s | S |
| 2 | **Lettering review while character SAM runs** (split lettering_step into find and review). Later: one per-box GPU queue for lettering, characters and objects, each box's review starting when its SAM ends (FIFO lock so reviews' SAM zooms are not starved; save letters per box as each review lands). | 100–140 s; later 200–300 s | S–M; later M–L |
| 3 | **Layers**: depth in the main process, the CPU part of plan and render across `workers.pmap` processes; stream each box plan, erase, render; WORKERS 16 to 24 (retries run in the same thread, so at most 16 are in flight today). | 120–160 s + 45–50 s | M |
| 4 | **Places**: one MoGe process for all places; each erase sent as its front exists; back layers (CPU only) in a process pool; `match_colour` computes the weight blur once per sigma (~6 s a place) and the 160 px field at a quarter scale (~20 s a place). | 120–180 s | M (colour match S) |
| 5 | **Review checks of a round asked at once**, applied in their current order (one box chained 15 calls over 143 s). | 30–110 s | S–M |
| 6 | **Gemini voices**: one pacer shared by the workers or honour the 429's retryDelay. | up to ~100 s | S |
| 7 | **Lyria tracks at once** (paid_map, ~3 workers; local CPU per track 0.2 s [measured]). Required for change 1 to keep music off the path. | 150–250 s | S |
| 8 | Small: the object pick sent at the start beside the frame layouts (20–30 s); lines recorded while voices are still designed (~30 s); review workers ≥ box count (0–40 s); cache SAM's text encoding in `instances`/`zoom`; LINE_WORKERS 5 on Inworld (~7 s); fold the voice descriptions into the identity call (~15 s, 0.09 USD; needs the 12-episode identity evaluation rerun). | each < 1 min | S–M |

Not recommended: a second SAM instance; MoGe overlapping SAM; building places from a clock estimated before the voices
(saves ~300 s but each view the real clock later un-earns costs 0.07 USD: a product decision).

First, cheaply: **timers inside the steps** in run.json (SAM vs review, plan vs erase vs render), DA3 load time and peak
VRAM with SAM and DA3 loaded together. They settle the unknowns above before the larger changes.

Local only, all of the above: about **36 min to 20–22 min** [est]; a single-GPU floor of ~18 min.

## Modal fan-out (after the local changes)

`pipeline/modal/run_episodes.py` (untracked) runs a whole episode in one L4 container, one step after another, with
SAM 3.1 and DA3 in the `zumi-models` volume and the keys as a secret: it moves the run, it does not speed it up.

Proposed: a few L4 containers for 2a–2c, each taking several boxes at once (the reviews stay in the same container:
they call SAM to zoom), layers' plan and render across CPU containers or local processes, one container per place for
MoGe (MoGe is not in the volume yet). Identity, voices, music and the export wait on providers; Modal does not help them.

| Stage on the critical path | Time [est] |
|---|---|
| upload, cold start | 1–2 min |
| 2a–2c per box across containers (the slowest box's review chains: lettering 143 s, objects 159 s [measured]) | 4–5 min |
| plan, erase, render per box (erase 5.7 s median, 22 s max [measured]) | 1–1.5 min |
| speakers, identity | 2–2.5 min |
| voices (Inworld; Gemini ~4.5 min, ~3 with a pacer) | ~2 min |
| places, one container each | ~3 min |
| export (10 s) and downloading the 303 MB `.zumi` | 1.5–3 min |
| **total** | **~13–18 min** (Inworld) |

Music stays off the path only with change 7: serial Lyria (484 s) is longer than voices + places. Floor if every
provider answered at once: ~10 min.

Cost: L4 0.80 USD/h; ~10 min of GPU work ≈ 0.13 USD, plus each container's model load and 60 s idle tail (6–8
containers: 0.2–0.4 USD), from Modal's 30 USD monthly credit, not the API cap [est].

Before Modal: change 0, and the cap shared across containers (a fixed slice of the remaining cap each, or paid calls
routed through one place); OpenRouter's account rate limit (unknown) caps how many containers can review at once.
Changing hardware can change masks (L4 bf16 vs the local 3060), and the erase cache is keyed on the masks: re-running
an already-processed episode on Modal could pay its erases again (~1.4 USD). Throughput stays bounded by the cap
(3.2 USD an episode) before time.
