# Does the LLM reviewer pay off? Held-out test, 2026-10-24

Literature behind the hypothesis: [vlm-review-cost-benefit-2026-10.md](vlm-review-cost-benefit-2026-10.md).
Predictions were written before running: `pipeline/.data/out/heldout/PREREGISTRATION.md`.

## Hypothesis

A review layer pays off in proportion to the base segmenter's rate of **gross, instance-level errors** (a missing
element, a false element, one object in two masks) that the reviewer can judge semantically **and** that an external
signal can carry out (SAM 3.1 re-segmentation, the segmentation rules). It does not improve boundaries, where VLMs are
blind (SAM 3 data engine: AI exhaustivity check +7.2 cgF1 vs mask-quality check +1.1; MQ-RAVSBench: gross errors
caught at F2 74-80, dilation/erosion at F2 0.6-4). If the reviewer's false-change rate is roughly constant, the
absolute gain scales with the base error rate (verifier base-rate argument: Stechly et al. 2024, Tyen et al. 2024).
Self-correction without an outside signal degrades (Huang et al. 2024; Kamoi et al. 2024), so every change goes
through SAM plus a single-mask check.

## Test

- Held-out panels, never used to build the reviewer: lettering 133 (True Beauty 7 all, Tower of God 228 p0-42);
  characters 88 (True Beauty 4 p0-44, an episode never opened; ToG 228 p0-42).
- Pipeline as shipped: SAM 3.1, sound-effect refinement v9, then review of every panel by Claude Haiku 5.5 (high
  reasoning), one run.
- Blind judging: original | A | B with the order randomised per panel. Every panel judged by Claude Sonnet against a
  fixed rubric; the 36 changed panels judged again by a second Sonnet and by Gemini 3.7 Flash (cross-family, to
  rule out shared Claude bias).

## Results

| | Lettering | Characters |
|---|---|---|
| Panels changed by the review | 26 / 133 | 10 / 88 |
| Major errors before -> after (judge 1) | 54 -> 24 (40.6 -> 18.0 per 100) | 9 -> 4 (10.2 -> 4.5 per 100) |
| All errors before -> after | 89 -> 59 | 22 -> 14 |
| Major fixed : introduced, judge 1 / judge 2 / Gemini | 32:2 / 34:4 / 31:2 | 6:1 / 6:0 / 7:1 |
| Changed panels better / same / worse (majority of 3 judges) | 24 / 1 / 1 | 9 / 0 / 1 |
| What it fixed | 22 missed (mostly sound effects, some text), 9 false | 4-5 one character split in two masks, 1 false, 1 missed |
| Boundary errors (partial, leak) | 9 -> 7, 8 -> 8 | 2 -> 2, 4 -> 4 |
| Cost per panel | 0.077 c | 0.053 c |
| Latency per panel, alone / 8 in parallel | 13 s / 2.0 s | 8 s / 1.2 s |
| Cost per major error removed | 0.34 c | about 0.9 c |

Per 100-panel episode: lettering about 8 c and 3.3 min, about 22 major errors removed; characters about 5 c and
2 min, about 6 removed.

The panels made worse:
- Lettering, TB7 p49: dropped the sticky-note message and added CRUNCH printed in the manga page the character holds.
  Decision (user, 2026-10-24): in-world text is never masked, even when the reader must read it. So the drop was
  right (two judges scored it as a miss against the rubric) and only the CRUNCH addition is a reviewer error. The
  lettering prompts now name notes and pages held in the scene as in-world text.
- Characters, ToG 228 p23: dropped a small fragment; the judges split three ways (worse / same / better). Noise level.

## Predictions vs outcome

| Prediction | Outcome |
|---|---|
| P1 lettering: major errors cut by at least 30%, at most 1 introduced per 5 fixed, fixes mostly recall | Confirmed: -56%, 1 per 9-16, 22 of 32 fixes are misses |
| P2 characters: net gain between -2 and +4 major per 100 | Refuted, mildly: +5.7 per 100. Base rate low as predicted (10 vs 41) |
| P3 boundaries barely change | Confirmed |
| P4 gain scales with base error rate | Consistent: same relative cut (-56% both), absolute 22.6 vs 5.7 per 100 |
| Literature: single-mask check accepts over 80% of proposals | Refuted: drops 62-75%, merges 43%, additions 40% accepted |
| Literature: merge/split harmful as often as helpful | Refuted for merge: 4-5 fixes, 0-1 harm (no split was applied) |

Why characters beat the literature's prediction: the dominant base error is not a semantic miss but one character in
two masks (tile seams, two prompts); a merge needs no new pixels, only a yes/no "is this one character" on the union,
which is a gross-error judgement VLMs make well.

## Limits

- No human labels: three LLM judges from two families agree, but a shared VLM blind spot cannot be excluded.
- Characters rest on 10 changed panels and about 6 fixed errors: the direction is clear, the size is not.
- One review run per panel; run-to-run stability measured earlier on the development panels (12/12 and 13/13 same).
- Three series; very different styles (manga, western, chibi) untested.
- Residual lettering errors (24 major) are mostly misses that the reviewer did not report, or that SAM or the
  segmentation rules could not produce (18 "already masked", 8 "failed segmentation rules").

## Decision

Keep the reviewer for both tasks: net major benefit is positive and fixes outnumber introduced errors 8:1 or more for
lettering and 6:1 or more for characters, well above the 3:1 rule, at under 0.1 c per panel. Next levers: decide the
spec for in-world text the reader must read (sticky notes); add an in-world check before adding a sound effect.
