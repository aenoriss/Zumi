# Intake tuning log

Fixture set (see `.claude/skills/tune-intake/SKILL.md`): u395 = unOrdinary 395, tog235 = Tower of God S3 235,
lo9 = Lore Olympus 9, sh14 = Sweet Home 14, cpc1 = Cursed Princess Club 1. Run: `sh run_fixtures.sh` from
`pipeline/`; sheets and stats via `zumi.sheets`; labels and boundary scores via `zumi.score`.

## Defect taxonomy

| Kind | Meaning |
|---|---|
| floater | a slab that is only text: a bubble, caption box or sound effect sitting in a gutter, kept as its own panel |
| missed-gutter | a real blank gutter not cut, so one box holds two or more panels |
| merged-title | a title card / advisory / logo glued onto an adjacent panel (special case of missed-gutter, cosmetic) |
| fade | a flat or gradient transition region (fade to black, grey wash between scenes): either dropped as gutter or boxed alone as an empty panel |
| fragment | a piece of one panel's art split off as its own sliver (ink splatter trail, pale soft edge, a lone moon) |
| misattached | a short slab (caption, name card, title line, small frame) welded to the wrong neighbour, typically across a long gutter, by the "slivers merge upward" rule (lo9 dog-name captions; it0 review) |
| split-title | one title card cut into pieces at the small gaps between its lines/ornaments (tog235 logo + season card; it0 review) |
| bridged-sfx | lettering that runs across a gutter cut in two (tog235 "SL|ICE"; it0 review) |
| false-gutter | a flat area inside one panel (pale sky) cut as a gutter (cpc1 22/23; it0 review) |
| no-gap-merge | two panels with no blank row between them (diagonal border, bubble bridging the gutter), so one box (lo9 13, u395 72, sh14 60; it0 review). Needs a bubble detector to mask bubbles before the scan |
| pan-cut | one borderless shot over a flat sky cut where the sky is plain (cpc1 0-2; it0 review). Needs delivery: sky rows are pixel-identical to gutter rows |
| padded-edge | a box that runs past its beat's soft fade into flat page background, because isolated grain rows break the blank run (sh14 27 "NOTHING": 228 px of background inside the box, 54 px of a ~280-px pause cut; found by the user in it1) |

Counted per instance (one floater = 1, one missed gutter = 1). "Risk" = right output that depended on a lucky margin.
Not counted: back matter (credits, Patreon, afterword) cut into pieces; it needs a non-story tag, not a better cut.

## Iteration 0 (baseline, commit 5b439d2 + d110e2c)

Rules: row blank when max-min <= tolerance 6 per channel over the whole row; gutter = run >= 40 blank rows;
slabs < 120 px merge upward. Stats:

| ep | panels | h min/med/max | gutter min/med/max | <300 | >5000 |
|---|---|---|---|---|---|
| u395 | 119 | 144/1257/4297 | 48/365/2521 | 7 | 0 |
| tog235 | 91 | 161/1442/5525 | 47/416/1567 | 7 | 1 |
| lo9 | 78 | 131/786/2369 | 41/193/1302 | 4 | 0 |
| sh14 | 23 | 328/511/67066 | 143/289/530 | 0 | 1 |
| cpc1 | 63 | 121/819/2696 | 40/387/825 | 11 | 0 |

Defects:

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 6 (slabs 7,40,44,46,53,90) | 14 (6,7,14,18,22,23,28,34,42,49,56,61,67,81,87) | 3 (46,64,76) | 0 | 9 (16,17,22,24,28,30,41,60,62) | 32 |
| missed-gutter | 1 (slab 103: two dark-scene panels + a long dark gap in one box) | 0 | 0 | ~57 (slab 22 = 67 066 px: the whole dark-background section; gutter rows have per-row spread 21-29, far above tolerance 6: JPEG grain on a dark brown background) | 0 | ~58 |
| merged-title | 2 (slab 0 advisory+first panel; slab 4 panel+episode logo) | 0 | 0 | 0 | 0 | 2 |
| fade | 5 (black fades after 34, 36, 47, 92 dropped; grey gradient after 61 dropped, 2521 px) | 0 | 0 | 0 | 1 (slab 19: 1549 px black-to-white gradient boxed as an empty panel) | 6 |
| fragment | 1 (104) | 0 | 1 (63 ink splatter) | 0 | 2 (1 lone moon, 26 pale tail of 25) | 4 |
| total | 15 | 14 | 4 | ~57 | 12 | ~102 |

Risks: lo9 gutters of 41 px (slabs 6, 39) pass min_gutter 40 by one pixel; cpc1 slab 22 gap 40. tog235 floaters that
touch a panel (no 40-px white between bubble and art) merge by luck of spacing, so bubble attachment is spacing-
dependent, not a rule.

Labels written to `.data/labels/<slug>.json` from this run minus the floaters' smaller gap (the one they should merge
across). sh14 labels cover only the white intro (22 cuts); the dark section gets labels once it is cut at all.

Next: replace the blank-row test. Current test is "every pixel within 6 of the row's extremes", which no noisy row
passes. New test (the research doc's rule): a row is blank when the fraction of pixels farther than `tolerance` from the
row's median colour is < 0.2 %, with tolerance raised to the noise level. Targets missed-gutter (~58, the largest
class and the one that makes sh14 unusable). Floaters (32) need a second signal and come next.

### Iteration 0, illustrator review (added after the fact; sheets re-run from commit 706a6da into `.data/out/it0/`)

The first resumed run found `.data/out/*.png` had been overwritten by uncommitted iteration-1 code (sh14 89 panels), so
iteration 0 was re-run from the committed code into `.data/out/it0/`; its stats match the table above exactly. The
reviewer (Opus 5.5, fresh context, sheets + stats + labels only) found what I missed:

- **The labels were circular.** `score.py --write` derived them from this run, so every box holding two beats was
  invisible to the scorer (100 % recall by construction). Labels corrected by hand from both reviews (it0 and it1),
  backed up before the edit: u395 +699 (advisory | crowd panel), +10389 (cold open | title card), +175276 (cemetery |
  2728 px dark pause), +176767 (between the two window chips, which are real panels); tog235 +87615 (49|50 are two
  panels), +172361 (86|87), +175960 (closing line | afterword), -176409, -178225 (cuts inside the afterword, which is
  one non-story block); lo9 the five dog-name captions belong to the dog *below* them: -45674/+45392, -47072/+46888,
  -48360/+48198, -49351/+49217, -50204/+50047; cpc1 -1739 (stars, moon and mansion are one tilt-down shot), -27709,
  -27953 (cuts inside the title card). Not taken: the it0 reviewer's "87|88 needs no cut", because its own finding on
  88 and the it1 reviewer both call the closing line a beat of its own. sh14 dark-section labels (66 cuts) were seeded from the iteration-1 run after
  both reviewers judged its dark-section boxes right except box 60 (no-gap-merge), so sh14 scores 1.0 on it1 by
  construction until a later iteration disagrees.
- **Scorer:** a label now matches a predicted gutter when it lies anywhere inside that blank run (±20 px), not only
  within 20 px of its centre. A gutter that grows by a faded panel edge (u395 80248 vs 80362) moved its centre by
  more than 20 px and scored as one miss plus one extra.
- **Root cause behind most non-sh14 defects:** the sliver rule (slab < 120 px merges upward, the first one down)
  ignores the gap it merges across. Empty runs >= 40 px inside boxes: u395 0 (822 px), 4 (482), 103 (2734); tog235
  88 (629); lo9 39, 41-44 (99-299); cpc1 19.
- **New kinds:** misattached, split-title, bridged-sfx, false-gutter, no-gap-merge, pan-cut (see taxonomy).
- **Re-classified:** u395 104 is a real framed panel (an expanding "window" chip opening into the apartment), not a
  fragment; cpc1 slab 1 (moon) is part of a pan-cut, not a fragment.
- **Claims recorded as needs delivery / needs detector:** a shared SFX bridging two panels (u395 46: 71 px vs 53 px)
  belongs to neither, so a reader needs SFX as their own layer; off-panel voices (tog235 21-23, cpc1 16-17, sh14 red
  lines) cannot be placed by spacing; cpc1 0-2 sky is pixel-identical to gutter (pan-cut, needs per-panel files);
  lo9 13 and u395 72 have no blank row (needs a bubble detector to mask bubbles first).

Iteration 0 defects, recounted with the review and the corrected labels:

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 6 | 14 | 2 (46, 64) | 0 | 9 | 31 |
| missed-gutter | 1 (103) | 0 | 0 | 66 (labels missed by slab 22) | 0 | 67 |
| merged-title | 2 (0, 4) | 1 (88 afterword) | 0 | 0 | 0 | 3 |
| misattached | 0 | 0 | 5 (39, 41-44) | 0 | 2 (9 rustle, 15 pant) | 7 |
| split-title | 0 | 1 (18/19) | 0 | 0 | 1 (19/20/21) | 2 |
| fade | 5 | 0 | 0 | 0 | 1 (19) | 6 |
| fragment | 0 | 0 | 1 (63) | 0 | 1 (26) | 2 |
| bridged-sfx | 0 | 1 (81/82) | 0 | 0 | 0 | 1 |
| false-gutter | 0 | 0 | 0 | 0 | 1 (22/23) | 1 |
| no-gap-merge | 1 (72) | 0 | 1 (13) | 1 (inside 22) | 0 | 3 |
| pan-cut | 0 | 0 | 0 | 0 | 1 (0-2) | 1 |
| total | 15 | 17 | 9 | 67 | 16 | 124 |

(sh14 missed-gutter is now a measurement, 66 labels inside slab 22, replacing the ~57 estimate.)

Illustrator verdict, iteration 0 (verbatim):

> On regular material (lo9 and the white half of sh14), a gap scanner gets about 90% of boxes right. With three rule changes, u395, tog235 and cpc1 would get most of the way there:
>
> - **Sliver merges:** go to the nearer side, never across more than about 300 px, and keep framed slivers as panels.
> - **Text-only slabs:** join the nearer side.
> - **Types:** add transition (gradient/fade), title-card group and non-story card types.
>
> That fixes most of what I tagged `wrong`: about 35 of roughly 50.
>
> It will not reach reader-grade on its own, for five reasons:
>
> - **Gutters are a storytelling surface.** Off-panel voices (tog235 21–23 and 54–56, cpc1 16–17, the sh14 red lines) and SFX that bridge panels (u395 44–47, tog235 80–82, sh14 WHIRRR/PZZZT) belong to no panel. Spacing does not say where they go: margins of 1–18 px decide u395 46, cpc1 9 and cpc1 24.
> - **Some panels have no clean horizontal gap.** Diagonal borders and bubbles bridging the gap (lo9 13, u395 72) leave 0–22 px of blank rows. A bubble detector that masks bubbles before the gap scan would recover these.
> - **Borderless establishing art on a flat sky** (cpc1 0–2) cannot be told from gutter.
> - **Several right answers are threshold luck.** Gutters of 40–49 px sit at a min_gutter of 40 (lo9 6|7, cpc1 22|23 and 20|21), and slivers of 120–160 px sit at a min_panel of 120 (u395 62).
> - **The scorer cannot see merges.** Until the labels are hand-made rather than derived from the run, a fix that splits a merged box can only lower the score.
>
> Reader-grade on this material needs three things beyond pixel rows:
>
> - a bubble/SFX detector, so text elements become their own layer instead of something to attach to a panel;
> - element typing: title, non-story card, transition, off-panel voice;
> - ideally per-panel source files, or a script, for speaker and beat grouping.
>
> The labels need fixing first: tog235 49|50, 86|87 and 87|88, lo9 39–44, u395 103/104, cpc1 0/1 and 19/20/21.

The review does not change which class comes first: missed-gutter in sh14 (66) is still the largest. The reviewer
measured sh14 gutter rows at (44,34,31) with per-channel std about 2 and called them flat, not noisy. Both hold:
measured over 60 dark gutters, per-row std is 3.7 while max-min is 26.7, because ~10 pixels per 700-px row sit
more than 10 away from the median and ~0.05 more than 20. Low variance, heavy tail: max-min sees only the tail.

## Iteration 1 (change: median-colour blank-row test, tolerance 20)

Rules: a row is blank when < 0.2 % of its pixels are farther than 20 (any channel) from the row's median colour;
gutter = run >= 40 blank rows; slabs < 120 px merge upward. Tolerance 20 is the knee measured on sh14's dark section
(share of rows passing: 0.1 % at 6, 0.8 % at 10, 26 % at 15, 32 % at 20, 32 % at 30). The interrupted run had also
bundled a floater-attachment rewrite of `find_slabs` into the same uncommitted diff; it was backed out so this
iteration changes one thing.

| ep | panels | h min/med/max | gutter min/q1/med/q3/max | <300 | >5000 | recall | precision |
|---|---|---|---|---|---|---|---|
| u395 | 122 | 140/1240/4292 | 50/221/369/530/2527 | 8 | 0 | 0.974 | 0.926 |
| tog235 | 95 | 161/1390/5523 | 45/307/414/655/1567 | 7 | 1 | 0.987 | 0.809 |
| lo9 | 81 | 130/767/2369 | 40/109/193/276/1304 | 7 | 0 | 0.932 | 0.863 |
| sh14 | 89 | 234/595/2940 | 54/192/295/377/834 | 3 | 0 | 1.000* | 1.000* |
| cpc1 | 61 | 121/812/2937 | 44/301/388/422/825 | 11 | 0 | 0.979 | 0.783 |

(*sh14 dark labels seeded from this run; it0 on the same labels: recall 0.250.) Iteration 0 on the corrected labels:
u395 0.974/0.949, tog235 0.987/0.844, lo9 0.932/0.896, cpc1 1.000/0.774.

Defects:

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 8 (7, 40, 44, 46, 49, 54, 92, 96) | 12 (3, 6, 8, 15, 29, 35, 42, 56, 58, 63, 66, 70) | 3 (46, 64, 74) | 0 | 9 | 32 |
| missed-gutter | 1 (106: cemetery + 2734 px pause + chip) | 0 | 0 | 0 | 0 | 1 |
| merged-title | 2 (0, 4) | 1 (92 afterword) | 0 | 0 | 0 | 3 |
| misattached | 0 | 0 | 5 (dog captions) | 0 | 3 (9 rustle, 15 pant, 18: title ornament welded across 1948 px of gradient) | 8 |
| split-title | 0 | 1 (19/20) | 0 | 0 | 1 | 2 |
| fade | 5 | 0 | 0 | 0 | 0 | 5 |
| fragment | 0 | 0 | 2 (63, 65 petals) | 0 | 0 | 2 |
| bridged-sfx | 0 | 2 (82/83 KWOOSH, 85/86 SLICE) | 0 | 0 | 0 | 2 |
| false-gutter | 0 | 0 | 0 | 0 | 1 (21/22 pale sky) | 1 |
| no-gap-merge | 0 | 0 | 1 (13) | 1 (60: "OF MARIA!!" burst over the gutter) | 0 | 2 |
| pan-cut | 0 | 0 | 0 | 0 | 1 | 1 |
| padded-edge | 0 | 0 | 0 | 5 (27, and boxes ending at 29286, 34640, 39344, 44779: 56-250 px of background) | 0 | 5 |
| total | 16 | 16 | 11 | 6 | 15 | 64 |

124 -> 64. What changed and why:
- sh14: the dark section went from one 67 066-px box to 66 more boxes; both reviewers judged them right except 60.
- New splits elsewhere came from the same mechanism, more rows now pass as blank: a bubble now separates from pale
  art it used to touch (u395 49|50 and 96|97, tog235 3|4, 56|57, 66|67, lo9 64|65, 74|75, 77|78), while others that were boxed alone in it0 now count as one; floater total 31 -> 32), and
  u395 73|74 (grey flashback dissolving into the dark page) is now cut, fixing that no-gap-merge.
- cpc1: the black-to-white gradient (old box 19, boxed alone as a fade) now passes as blank end to end (rows
  25700-27560: per-row max deviation 0-5), so it became one 1900-px gutter; the 117-px title ornament below it is then
  a sliver and the sliver rule welds it onto the scream panel across that whole gutter (misattached, box 18 = 2937 px).
  The fade and fragment 26 (pale tail rejoined its parade panel) are fixed.
- padded-edge (new, found by the user, confirmed by a reviewer): the background below sh14 27 passes the test except
  isolated rows such as 25180, where 2 of 700 pixels (0.29 % > 0.2 %) are more than 20 off; each such row splits the
  blank run into pieces under 40. Treating non-blank runs of <= 2 rows between blank rows as blank moves 6 sh14 box
  edges by 24-250 px and 3 edges elsewhere (measured, scratch experiment), so it is cheap and well-targeted.

Risks: the cut inside a dissolve (u395 73|74) lands where the fade's tail crosses the tolerance, which is arbitrary;
tog235 84 (5523 px) is one beat welded by a vertical "FWAAAA" on purpose and is far taller than a screen; gutter
gradients (sh14 21|22, u395 47) are dropped as gutter although both reviewers call them transition content, a product
question (keep gutter pixels) rather than a cut defect.

Illustrator verdict, iteration 1 (verbatim):

> **Gutters are found accurately, but the splitter does not reach reader-grade on these episodes; a proximity merge plus a cap gets most of the way.** It found every real gutter except one, and that miss (cpc1 18) is the sliver rule. Its failures come from deciding what the content between gutters *is*:
>
> 1. **The always-merge-up sliver rule is the biggest single bug.** It welds titles, captions and transition chips to the wrong panel, across gutters of up to 3000 px.
>    - Fix: merge into the *nearer* neighbour, and never across a gutter longer than about 2× the median.
>    - This alone fixes u395 0, 4, 106; tog 92; cpc1 18; and most of the lo9 dog captions.
> 2. **Orphan text or SFX boxes, 44 in all.** Merging every box under a height threshold into its nearest neighbour (a simulation on these manifests) shows height alone cannot separate these from real short panels:
>
>    | Threshold | Extra cuts | Missed label cuts |
>    |---|---|---|
>    | none (current output) | 44 | 1 |
>    | 450 px | 10 | 21 |
>    | 650 px | 7 | 42 |
>
>    lo9 alone goes from 0 misses to 7 at 450 px and to 15 at 650 px.
>    - **Claim:** the remaining step needs a classifier that tells text-only or SFX-only slabs apart from art. A bubble/SFX detector is the natural one, and it is already the planned next step.
> 3. **Cases with no pixel answer:**
>    - near-tie shared SFX (u395 46, 74 vs 54 px);
>    - semantic attachment (lo9 "Russell", 70 vs 77 px, decided only by the name-precedes-dog pattern);
>    - balloons or SFX laid across the gutter (sh14 60; tog "SLICE" is splittable only by luck);
>    - dissolves with no boundary row (u395 73);
>    - continuous-sky pans (cpc1 0–2);
>    - pacing of spaced balloons (tog 22–24, cpc1 15–17, lo9 77–79).
>
>    These need a script or per-panel source files, a bubble detector that produces layers, and a product decision on what counts as a beat.
> 4. **Gutters carry meaning.** Gradients, time-skip runs and black fades should be kept as transition pixels, not flattened to one background colour. Front and back matter should be tagged rather than segmented.
>
> Fixing points 1 and 2 would probably bring these five episodes to "clean, with a handful of judgement calls". That is reasoned from the simulation and the crops, not a measured result. The cases in point 3 are where a human, or the artist's own per-panel files, still has to decide.

Needs delivery (recorded, not a stop: other kinds remain): pan-cut (cpc1 0-2), semantic caption attachment (lo9
"Russell"), shared bridging SFX (u395 46). Needs a detector (a redesign, not a stop): no-gap-merge (lo9 13, sh14 60),
text-only vs art classification for floaters.

Next: replace the sliver rule with nearer-neighbour attachment under a gap cap. A slab shorter than `max_floater`
joins whichever full-height neighbour is closer, only if that gap is under a cap tied to the strip's median gutter;
otherwise it stays alone. Targets floater (32), misattached (8), merged-title (3), missed-gutter u395 106 (the chip
welded across 2734 px): 44 of 64. The reviewer's simulation (no cap) says a pure height threshold costs 21 missed
label cuts at 450 px; the cap and a sweep of `max_floater` against the corrected labels decide the value. padded-edge
(5) follows in iteration 3.
