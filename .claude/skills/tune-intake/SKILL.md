---
name: tune-intake
description: Bounded tune-and-inspect loop for the pipeline intake stage (strip splitter). Runs intake on the fixture episodes, inspects the contact sheets with an open mind, fixes one thing per iteration, logs, stops on a rule, and hands a report to the user. Run it in a fresh subagent.
disable-model-invocation: true
---

# tune-intake

Goal: make `zumi intake` cut real webtoon strips correctly, by looking at the results the way a reader would and fixing what is wrong, one change at a time, until a stop rule fires. Then report and stop. Never start the next pipeline stage.

## Fixture set (fixed, do not swap episodes mid-loop)

| Episode folder under `pipeline/.data/webtoons/` | Why |
|---|---|
| `unordinary/Episode_395` | clean gutters, margin colour changes mid-strip, floating sfx |
| `tower-of-god/_Season_3__Ep._235__Season_3_Finale` | 700 px, bordered panels, dense action |
| `lore-olympus/Episode_9` | borderless colour fields |
| `sweet-home/Ep._14` | dark backgrounds |
| `cursed-princess-club/Ep._1_-_The_King_Returns` | bubbles in gutters |

Research-only material: never copy it anywhere, never feed it to a generative model.

## One iteration

1. **Run.** From `pipeline/`: for each episode, `uv run zumi intake <folder> --out .data/out/<slug>.zumi --report .data/out/<slug>-cuts.png`, then build contact sheets (tile the report into 2400 px columns, 13 per sheet) and a stats line: panel count, min/median/max panel height, gutter distribution, panels < 300 px, panels > 5000 px.
2. **Inspect, open-ended.** Read every sheet (the Read tool renders PNGs). Do not work from a checklist: look at each box and ask "would a reader call this one panel, placed where the artist placed it?" Record every way the output is wrong, including kinds nobody has named yet. Known kinds so far, as examples only: cut outside a blank gutter; cut at a slice seam; sliver panel that is only text or a sound effect; one box holding two panels with a visible gutter between them; a scene gap collapsed; a flat colour block inside a panel cut as a gutter; wrong background colour reported. When you find a new kind, name it, add it to the taxonomy section of the log, and count it like the others. Also note anything that looks right but fragile (a cut that only worked because of a lucky margin), as a risk, not a defect. Settled by the user (2026-10-18), not a defect: when art deliberately overlaps a gutter to link two beats (a bubble or dialog across the gutter, a burst spanning two frames, an SFX over the gap), the two frames plus that gutter are one long frame; never split it, and do not count its height against it (the stepped reader scrolls tall panels in stops). Pass this to the illustrator reviewer too.
3. **Illustrator review (adversarial, not contrarian).** Spawn a separate agent (Agent tool, fresh context, `model: "opus"`, i.e. Claude Opus 5.5; never Fable) with this brief, and give it only the sheets, the stats line and the labels, never your own defect list or conclusions:

   > You are a working comic-book and webtoon illustrator with years of experience laying out vertical-scroll episodes. You are reviewing an automatic panel splitter's output on real episodes (contact sheets: red boxes are the panels it found, blue lines are the upload slice seams). For each episode, go box by box and judge from craft: where did the artist intend a beat to start and end, and does the box match? Explain the intent behind what you see: why that gutter is that tall, why a panel bleeds into the next, why a sound effect floats between panels, why a scene change gets a long empty run, why a page goes black. When the splitter is wrong, say what the artist was doing that it misread. When the splitter is right, say so plainly. Where you believe no segmentation rule can recover the intent from pixels alone, state it as a claim with the reason and the specific example, so it can be tested, and say what information would resolve it (a script, per-panel files, a detector that understands bubbles). Do not argue for its own sake, do not invent problems, do not soften real ones. Return: per episode, a list of findings each tagged `wrong`, `right-but-fragile` or `right`, with the box numbers, the artist's intent, and whether a rule could fix it; then a short overall verdict on whether this approach can reach reader-grade on this kind of material.

   Merge its findings with yours: anything it found that you missed is a defect kind (name it, count it). Where it claims segmentation cannot work, test the claim in the next iteration if a change could falsify it; otherwise record it under "needs delivery" with its reasoning. Quote its verdict verbatim in the log.
4. **Log.** Append to `pipeline/tuning-log.md`: iteration number, parameters and rules in force, defect counts per kind per episode, new kinds discovered, risks, and the one change you will make next and why.
5. **Change one thing, at whatever depth it takes.** The change can be a parameter (`--tolerance`, `--min-gutter`, `--min-panel`), one rule in `pipeline/zumi/intake.py`, or a redesign of the algorithm itself: a different blank test (ink density, edge energy, local margin colour), a second signal (column projection for side-by-side panels, connected components, a learned panel or text detector from `docs/research/webtoon-panel-splitting-2026-10.md`), or a different decomposition (detect first, cut second). Pick the smallest change that could remove the largest defect class; when the defects say the row scan is the wrong idea, replace it rather than patching it. Still one change per iteration, so the log can attribute the effect, and still measured on the same five episodes. Use the Edit tool for source edits; new modules go next to `intake.py`.
6. **Labels (first iteration only).** Write the cut rows you judged correct to `pipeline/.data/labels/<slug>.json` as `{"cuts": [y, ...]}` (strip rows, gutter centres). From iteration 2, compute boundary recall and precision at ±20 px against them before reading sheets, and read the sheets for the disagreements and for anything the labels cannot express. If you later decide a label was wrong, fix the label and say so in the log.

## Stop rules (any one ends the loop)

- Zero defects across the set, including the newly discovered kinds.
- Two consecutive iterations without reducing the total defect count.
- Six iterations.
- A defect kind that no change within intake can fix (needs per-panel delivery from the artist). Mark it "needs delivery" in the log, keep going only if other kinds remain. Needing a detector is not a stop: that is a redesign, see step 4.

## Hand-off

Reply with: a before/after table (defects per kind per episode, first vs last iteration), the paths of the last iteration's sheets for the worst episode, the list of defect kinds discovered during the loop, the illustrator's final verdict verbatim and whether you agree with it, and at most one question for the user. Do not propose or begin stage 2. Leave the working tree committed per iteration with messages `intake tune N: <change>` ending in `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

Model: the whole loop (the tuner and every illustrator reviewer) runs on Claude Opus 5.5. Launch the tuner with `model: "opus"`.
