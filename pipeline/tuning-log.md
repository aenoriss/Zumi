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
| no-gap-merge | two panels with no blank row between them (diagonal border, bubble bridging the gutter), so one box (lo9 13, u395 72, sh14 60; it0 review). Needs a bubble detector to mask bubbles before the scan. **Amended 2026-10-18 by the user's decision (see end of log): when the link is deliberate overlap (a bubble, burst or SFX laid across the gutter), one long box is correct and is not a defect. Only diagonal or staggered frames with no overlapping element still count** |
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

## Iteration 2 (change: bridge grain breaks of <= 2 non-blank rows inside blank runs)

Rules: iteration 1, plus a run of <= 2 non-blank rows with blank rows on both sides counts as blank before gutters
are found (`bridge_breaks`). The value 2 is the grain measured under sh14 box 27 (isolated failing rows such as
25180, 2 of 700 pixels more than 20 off). Why padded-edge before floaters: the planned floater attachment was tried
first in a scratch sweep, and without this it regresses: grain and speck slabs of 1-9 px stop merging upward and
become boxes of their own (u395 extras 9 -> 16-23, cpc1 13 -> 19-23 against the corrected labels).

| ep | panels | h min/med/max | gutter min/q1/med/q3/max | <300 | >5000 | recall | precision |
|---|---|---|---|---|---|---|---|
| u395 | 122 | 140/1240/4292 | 50/227/369/530/2527 | 8 | 0 | 0.974 | 0.926 |
| tog235 | 95 | 161/1390/5523 | 45/307/414/655/1567 | 7 | 1 | 0.987 | 0.809 |
| lo9 | 80 | 130/774/2369 | 40/113/195/280/1304 | 6 | 0 | 0.919 | 0.861 |
| sh14 | 89 | 234/587/2940 | 54/205/310/384/841 | 4 | 0 | 1.000 | 1.000 |
| cpc1 | 61 | 121/812/2937 | 44/301/388/422/825 | 11 | 0 | 0.979 | 0.783 |

Box edges that moved more than 10 px against iteration 1 (the labels cannot see edges, so these were read from crops):
sh14 27 -228 px, 32 -91, 38 -172, 43 -250, 49 -56, 36 -24 (bottoms now sit on the plate or panel edge, background
trimmed; checked on crops), sh14 26 top +34, 41 top +11; cpc1 24 bottom -234 (the parade's pale ground fade is now
partly dropped as gutter: the fade belongs to the panel, a fade defect); lo9 62 bottom +375 (the drifting petals
below "Gods, he's stupid..." joined that panel instead of standing alone; label 67808 wanted them with the drift
below: misattached); u395 50 top +20.

Illustrator review (Opus 5.5, fresh context): sh14 now has 0 missed and 0 extra and the reviewer judged its edges
right; the dark-page gutters with grain hold. Its findings that change the books:
- **New kind, fade-clip:** where art fades into the page at a panel's top, the fade's last rows read blank and the
  cut lands inside the fade, so the box loses its soft edge (u395 50, tog235 56, 66, 70, cpc1 21, 26). It was there
  in iteration 1 too, unnamed; counted from now on, and back-filled into the iteration-1 comparison below.
- **Labels:** u395 73|74 is a hard cut from a grayscale flashback to the colour present, so the label now has the cut
  (118239; the it1 reviewer called it fragile, both agree it is right). Pacing calls where the two reviewers and the
  labels disagree are now `ambiguous` in the label files and the scorer ignores cuts there: u395 78613 (TAK chain),
  tog235 11632 (isolated thought caption), 37402 (inner-voice bubbles 23/24), lo9 80650, 81006 (CLICK crescendo),
  cpc1 22919, 23623 (voices in the dark).
- **Claim (recorded):** tog235 82/83 is one continuous camera move broken by a 78-px white band; both slabs are large,
  so no small-slab rule touches it (I had it as bridged-sfx KWOOSH; kept there).

Rescored (corrected labels, ambiguous excluded): u395 0.974/0.942, tog235 0.987/0.826, lo9 0.919/0.883,
sh14 1.000/1.000, cpc1 0.979/0.810; iteration 1 identical except lo9 0.932/0.885.

Defects:

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 8 | 12 | 3 | 0 | 9 | 32 |
| missed-gutter | 1 | 0 | 0 | 0 | 0 | 1 |
| merged-title | 2 | 1 | 0 | 0 | 0 | 3 |
| misattached | 0 | 0 | 6 (dog captions, petals 62) | 0 | 3 | 9 |
| split-title | 0 | 1 | 0 | 0 | 1 | 2 |
| fade | 5 | 0 | 0 | 0 | 1 (24 parade fade) | 6 |
| fade-clip | 1 | 3 | 0 | 0 | 2 | 6 |
| fragment | 0 | 0 | 1 (64 speck box) | 0 | 0 | 1 |
| bridged-sfx | 0 | 2 | 0 | 0 | 0 | 2 |
| false-gutter | 0 | 0 | 0 | 0 | 1 | 1 |
| no-gap-merge | 0 | 0 | 1 | 1 | 0 | 2 |
| pan-cut | 0 | 0 | 0 | 0 | 1 | 1 |
| padded-edge | 0 | 0 | 0 | 0 | 0 | 0 |
| total | 17 | 19 | 11 | 1 | 18 | 66 |

Iteration 1 with fade-clip back-filled: 70. So 70 -> 66: padded-edge 5 -> 0, one new fade (cpc1 24).

Illustrator verdict, iteration 2 (verbatim):

> - **Clean material:** the row-gutter approach is already reader-grade on framed panels with clear gutters, which is most of every episode and all of sh14.
> - **Next fix:** with the gap-aware sliver merge plus nearer-gap attachment of small slabs, I'd expect this set to drop to roughly 5–10 misses and 25–30 extras. That is an estimate from the simulation above, not a measurement.
> - **What stays wrong:** most of the remaining errors are the claims above, where the pixels do not carry the artist's intent: sky gradients vs scene fades, letter-spaced sound effects, equal-gap bubbles, continuous camera moves.
> - **Reaching reader-grade:** on free-floating, bleed-heavy material (tog235, cpc1, the dark parts of lo9), it needs a bubble, text and frame detector run before the cut, or per-panel source files. Pixels alone cannot carry it there.
> - **Edges:** box edges are almost always right where panels have frames. Where art fades into the page they are systematically wrong, because the cut lands inside the fade (u395 50, tog235 56/66/70, cpc1 21/26).

Next: replace the sliver rule with floater attachment that uses a second signal, flatness. A slab is a floater when
it is under 700 px and its four most frequent colours (5-bit quantised) cover >= 85 % of its pixels: bubbles,
captions, lettering and specks are a fill, an outline and text; art is not (measured on it2 slabs: known floaters
0.73-0.99, mostly >= 0.93; sh14 red plates 0.23-0.41; lo9 tiny reaction panels 0.53-0.67). Consecutive floaters closer
than the cap group first (title cards, speck trails), then the group joins the nearer non-floater neighbour if that gap
is under 0.75 x the strip's median gutter, else stands alone. Scratch sweep on it2's slabs: 10 missed / 27 extra
against 11 / 51 now. Height alone (the reviewer's simulation and mine) could not separate floaters from short panels.

## Iteration 3 (change: flatness-based floater attachment replaces the always-up sliver rule)

Rules: iteration 2, with the sliver rule (< 120 px merges into the slab above, across any gap) replaced by
`attach_floaters`: a slab is a floater when it is under 120 px, or under 700 px with its 4 most frequent colours
(5-bit) covering >= 85 % of its pixels; consecutive floaters closer than the cap group; a floater group joins its
nearer non-floater neighbour if that gap is under 0.75 x the strip's median gutter, else stays a box. (The "under
120 px is always a floater" clause was added before the review, after the first run showed a 23-px credit line on
sh14's grainy brown, flatness 0.61, standing alone.) Flatness at coarser quantisation was measured and rejected:
at 3 bits sh14's red plates reach 0.88 while textured parchment captions only reach 0.80-0.90, so no threshold
separates them.

| ep | panels | h min/med/max | gutter min/q1/med/q3/max | <300 | >5000 | recall | precision |
|---|---|---|---|---|---|---|---|
| u395 | 117 | 39/1255/2508 | 53/282/422/538/2734 | 6 | 0 | 0.965 | 0.957 |
| tog235 | 83 | 164/1544/5523 | 66/335/436/724/1567 | 2 | 1 | 1.000 | 0.975 |
| lo9 | 75 | 30/795/2369 | 41/140/206/290/1304 | 3 | 0 | 0.973 | 0.986 |
| sh14 | 89 | 234/587/2940 | 54/205/310/384/841 | 4 | 0 | 1.000 | 1.000 |
| cpc1 | 58 | 165/825/2046 | 70/353/397/486/1976 | 8 | 0 | 1.000 | 0.906 |

Label changes from this review (all reviewer-judged, applied before the scores above; iteration 2 on the same labels:
u395 0.965/0.932, tog235 0.987/0.835, lo9 0.919/0.883, sh14 1/1, cpc1 0.958/0.793): u395 -197498 (inside the credits
card), 60361 -> 59995 (a boundary inside one continuous black run; the box starts 50 px higher, in solid black),
16537 and 82777 ambiguous (debris field; caption-or-dissolve pacing); tog235 145872 ambiguous (KWOOSH dissolving into
the reveal); cpc1 31951 -> 31713 (box starts at the first confetti speck of a panel fading in from white), 13711 and
22160 ambiguous ("rustle" with a 372/384 tie; "pant", same unseen voice as the already-ambiguous 16-18).

New kind, **text-clip**: thin, small type has so few ink pixels per row that its ascender/descender rows pass as
blank, so a box edge clips the line (u395 115 "[end]", tog235 17 "SIU" credit, lo9 11 "Edited by", 12 "Episode 09",
sh14 31 credit line). Present since iteration 1's outlier fraction; first named here. Also folded into padded-edge:
a box that starts at a lone speck far above its frame (u395 100, 101).

Defects:

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 0 | 0 | 0 | 0 | 4 (captions 21, 25, 27, 38: parchment texture, flatness 0.57-0.77) | 4 |
| missed-gutter | 0 | 0 | 0 | 0 | 0 | 0 |
| merged-title | 0 | 0 | 0 | 0 | 0 | 0 |
| misattached | 1 (103: the two growing window frames merged into the apartment shot) | 0 | 1 (61: ash flecks weld the "Sigh" pause beat to the panel above) | 0 | 0 | 2 |
| split-title | 0 | 1 (16/17) | 0 | 0 | 0 | 1 |
| fade | 5 (unchanged mechanism; this reviewer calls them correct transitions) | 0 | 0 | 0 | 1 (23 bottom: cream ground fade) | 6 |
| fade-clip | 2 (47/48 dissolve top; 92/93 cut through the sunset sky under "How did he pass?") | 1 (50/51 misty top) | 0 | 0 | 2 (21, 25) | 5 |
| fragment | 0 | 0 | 0 | 0 | 0 | 0 |
| bridged-sfx | 0 | 1 (72/73 KWOOSH, claim) | 0 | 0 | 0 | 1 |
| false-gutter | 0 | 0 | 0 | 0 | 1 | 1 |
| no-gap-merge | 0 | 0 | 1 (13; also 38, staggered frames, accepted by the labels) | 1 (60) | 0 | 2 |
| pan-cut | 0 | 0 | 0 | 0 | 1 | 1 |
| padded-edge | 2 (100, 101 start at a lone speck) | 0 | 0 | 0 | 0 | 2 |
| text-clip | 1 | 1 | 2 | 1 | 0 | 5 |
| total | 11 | 4 | 4 | 2 | 9 | 30 |

66 -> 30. Fixed: all 12 tog235 floaters and the SLICE split (now grouped), u395 advisory card and title card (now
their own boxes), the cemetery pause, the lo9 dog captions (each with its own dog), cpc1 title card (one box) and the
title ornament weld. Not fixed by design: cpc1 parchment captions (not flat enough), and the u395 window frames, which
are flat navy fills and so read as floaters; the it1 reviewer wanted them with the apartment shot, the it0 and it3
reviewers as panels of their own.

Illustrator verdict, iteration 3 (verbatim):

> I count about 14 reader-visible defects in 422 boxes (my own count): 6 bad cuts or merges, 4 detached captions, and 4 text-clipping edges. That is roughly 97% of boxes a reader would accept. Most of the remaining scorer misses and extras are label strictness, not splitter errors.
>
> Four rules would remove most of what is left:
> 1. **Pad box edges to a fully clean row (zero outliers).** Fixes the clipped text in u395 115, tog 17, lo9 11/12 and sh14 31.
> 2. **Blank means matching the local page colour, not just uniform.** Fixes the cuts through art in u395 92/93 and, partly, tog 50/51.
> 3. **Ignore small isolated components when finding gaps, then reattach them to the nearer box within a distance limit.** Fixes u395 100/101 and lo9 61, but must be checked against the debris in u395 box 10.
> 4. **Attach small caption or bubble boxes to the nearer neighbour, with a text classifier** so that art slivers are left alone. Fixes the four cpc1 captions.
>
> A fifth, smaller fix: treat closed rectangular frames as panels whatever their height (u395 103).
>
> What cannot be recovered from pixels, with tests:
> - cpc1 0/1: one painting whose sky equals the page colour.
> - tog 72/73: an SFX dissolving through white into a reveal.
> - Borderless empty "silence" beats (sh14 12 survives only because of its border).
> - Staggered or diagonal panels (lo9 38, 13): beyond row-based splitting, but a 2D frame detector can handle them.
>
> These need per-panel source files, a script, or a creator override.
>
> So this approach can reach reader-grade on gutter-separated vertical-scroll material once the four rules are in. It cannot reach 100%: the continuous-painting cases need a manual merge/split tool in the creator flow.

Next: text-clip. Pad each box edge outward into its gutter until a row with zero outlier pixels, capped at 16 rows
so grain cannot walk an edge across a dark gutter. Five instances, one mechanism, and a change that cannot move a
cut. The page-colour rule (the reviewer's rule 2, targeting fade-clip and false-gutter) is larger and would turn the
scene-change gradients both reviewers want left outside boxes back into content, so it waits.

## Iteration 4 (change: speck slabs fold back into the gutter)

First attempt, reverted: padding box edges outward to a clean row, aimed at text-clip. It did not move the five
clipped edges, because they were not clipped: the rows next to each edge have zero outliers (lo9 12: ink rows
12048-12077, clean rows on both sides), and the panel PNG in the .zumi holds the whole line (checked lo9 p011/p012).
The report drew its 2-px outline on the box edge, which at 0.25 scale covers 8 strip rows of the box's own first and
last lines. **text-clip is a report artifact, not a defect**: removed from the counts (it3 recount 30 -> 25). The
report now draws the outline just outside the box and the index above it (instrument fix, not the iteration's change).

Change: `drop_specks`: a slab under 300 px whose mean per-row outlier share is under 1.5 % is a speck (sweat drop,
ash fleck, star, debris) and its rows rejoin the gutter instead of a panel. Measured on raw slabs: specks 0.07-1.4 %,
the faintest real slab (tog235's 22-px "SIU" credit line) 1.9 %.

| ep | panels | h min/med/max | gutter min/q1/med/q3/max | <300 | >5000 | recall | precision |
|---|---|---|---|---|---|---|---|
| u395 | 117 | 39/1240/2479 | 53/299/438/540/2734 | 6 | 0 | 0.974 | 0.982 |
| tog235 | 83 | 164/1544/5523 | 66/335/436/724/1567 | 2 | 1 | 1.000 | 0.987 |
| lo9 | 75 | 228/795/2369 | 41/147/214/295/1304 | 2 | 0 | 0.973 | 1.000 |
| sh14 | 89 | 234/587/2940 | 54/205/310/384/841 | 4 | 0 | 1.000 | 1.000 |
| cpc1 | 59 | 165/818/2046 | 70/355/399/514/1976 | 10 | 0 | 1.000 | 0.906 |

Iteration 3 on the same labels: u395 0.965/0.965, tog235 1/0.987, lo9 0.960/0.986, sh14 1/1, cpc1 1/0.906.
Label changes from this review: ambiguous u395 176767, 177073 (growing frames into the apartment: the reviewer notes
the labels treat the identical device at u395 44 as one panel), 195940 ("[end]" line), tog235 30731 and lo9 11730
(title cards: the labels made opposite calls on the two), cpc1 883 (sound-on notice); added lo9 13890 (the diagonal
two-shot and the next panel share box 12; only a ~20-row clean run separates them, the no-gap-merge already counted).

Defects:

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 0 | 0 | 0 | 0 | 4 (parchment captions 22, 26, 28, 39) | 4 |
| misattached | 0 (103 now ambiguous) | 0 | 0 (ash flecks gone; "Sigh" stands with its own beat) | 0 | 0 | 0 |
| split-title | 0 | 0 (ambiguous) | 0 | 0 | 0 | 0 |
| fade | 5 (two reviewers now call these correct transitions; kept for comparability) | 0 | 0 | 0 | 2 (floor bands lost at the bottom of 27 and 29) | 7 |
| fade-clip | 2 (47/48, 92/93) | 1 (50/51) | 0 | 0 | 2 (22/23 sky, 26/27 grey wall) | 5 |
| bridged-sfx | 0 | 1 (72/73, claim) | 0 | 0 | 0 | 1 |
| false-gutter | 0 | 0 | 0 | 0 | 1 | 1 |
| no-gap-merge | 0 | 0 | 1 (12) | 1 (60) | 0 | 2 |
| pan-cut | 0 | 0 | 0 | 0 | 1 (moon cut out of the tilt-down) | 1 |
| padded-edge | 1 (100: a speck at 1.7 % ink, just over the threshold) | 0 | 0 | 0 | 0 | 1 |
| total | 8 | 2 | 1 | 1 | 9 | 22 |

25 -> 22 (u395 101 edge, lo9 61 weld fixed; u395 103 reclassified ambiguous). Risk: specks now sit outside every
panel image, so a reader that shows only panels loses them (debris flying out of u395 box 10, cpc1 stars); the
threshold sits between 1.4 % and 1.9 %, a narrow margin.

Illustrator verdict, iteration 4 (verbatim):

> Cut placement on framed, gutter-separated material is close to reader-grade now. Most flagged errors fall into three rule-fixable classes:
> 1. **Flat art read as gutter.** The blank-row test needs to match the page colour, use frame-line bounds and check for gradients.
> 2. **Specks stretching box edges.**
> 3. **Captions or bubbles straddling a frame**, which should attach to the panel they cross.
>
> Box edges need the same checks as cuts. Lost sky and floor bands at panel tops and bottoms are a separate symptom of the same bug, and the cut-row scorer does not catch them.
>
> Two limits remain beyond pixel rules:
> - **Compound panels joined by SFX that crosses frames** (tog235 box 74), and diagonal or nearly touching frames (lo9 box 12). These need per-layer source files, or a bubble/SFX/frame detector.
> - **Pacing calls**: title cards, cascade frames, frameless establishing shots. The labels themselves contradict each other here (u395 44 vs 103, tog235 16/17 vs lo9 11). Mark all of these `ambiguous` before tuning further, or the tuner will chase noise.

Next: flat art read as gutter (fade-clip 5, false-gutter 1, cpc1 floor bands 2; the reviewer measured the gap rows:
u395 92/93 median (231,208,198) on a #413F40 page, tog235 50/51 (226,239,242) on white, cpc1 22/23 sky (235,255,254)
-> (237,233,232) on white). Rule: a blank run is a gutter only if at least one of its rows matches the local page
colour (the most common blank-row colour within +-4000 rows). A scene-change gradient still passes, because it starts
or ends on the page colour; a run of flat sky that never touches the page colour becomes content.

## Iteration 5 (change: a blank run is a gutter only if it touches the local page colour or is a gradient)

Rules: iteration 4, plus `page_gutters`: a blank run of >= 40 rows stays a gutter only if one of its rows is within
20 of the local page colour (the most common 4-bit blank-row colour within 4000 rows above, or within 4000 rows below,
taken separately) or its median colour travels more than 48 end to end (a fade or scene-change gradient). Otherwise it
is flat art (sky, wall) and stays content. Two refinements were made before the review, both measured: without the
gradient clause, u395's fades to black stopped being gutters and merged three pairs of panels (labels 59995, 64400,
80362 missed); with a single +-4000 window, sh14's first dark gutter after the white-to-dark transition took the
white half's colour as page and merged GRAB with CRASH (label 20838). Both fixed; the final run moves exactly four
boxes against iteration 4, all intended.

| ep | panels | h min/med/max | gutter min/q1/med/q3/max | <300 | >5000 | recall | precision |
|---|---|---|---|---|---|---|---|
| u395 | 116 | 39/1255/2479 | 71/301/439/541/2734 | 5 | 0 | 1.000 | 0.991 |
| tog235 | 82 | 164/1549/5523 | 78/340/439/726/1567 | 2 | 1 | 1.000 | 1.000 |
| lo9 | 75 | 228/795/2369 | 41/147/214/295/1304 | 2 | 0 | 0.986 | 1.000 |
| sh14 | 89 | 234/587/2940 | 54/205/310/384/841 | 4 | 0 | 1.000 | 1.000 |
| cpc1 | 57 | 165/829/2341 | 70/358/399/518/1976 | 8 | 0 | 1.000 | 0.941 |

Scorer fix: a row listed as both a label and `ambiguous` no longer counts as a required cut (it did, so ambiguous
labels still scored as misses). Iteration 4 on the same labels and scorer: u395 1/0.982, tog235 1/0.987, lo9
0.986/1, sh14 1/1, cpc1 1/0.906. Label change: u395 168907 ambiguous (the sweat drop 150 px above box 99 is emanata
belonging to 99, per the reviewer).

Fixed by this change: u395 92/93 ("How did he pass?" now whole with its panel), tog235 50/51, cpc1 22/23 and 26/27
(caption plates now inside their panels, sky and wall kept).

Reclassifications from this review:
- **New kind, frame-eaten:** a framed panel whose top (or bottom) band is a flat colour loses its frame line and that
  band to the gutter: a frame line is one colour across the row, so it is blank, and the flat band next to it is blank,
  and both join the page-coloured gutter run, which touches the page colour and is kept whole. u395 0 (advisory card's
  black field), 1 (frame line), 23 (104 px), 43 (88), 82 (48), 95 (84); cpc1 25 (110 px grey floor band), 27 (50 px
  floor). Present since iteration 1; the two cpc1 floor bands were counted as fade in iteration 4 and move here.
- **fade (u395, 5) is no longer counted.** Four reviews in a row (it0 "right-but-fragile", it3, it4, it5) judge the
  fades to black and the white-to-grey ramp as transitions owned by neither panel. Whether a reader shows gutter
  pixels as an interstitial is a reader-design decision, recorded under needs delivery/product, not a cut error.
- tog235 72/73 KWOOSH (bridged-sfx) is ambiguous in the labels and judged right twice; no longer counted.

Defects:

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 0 | 0 | 0 | 0 | 2 (plates 26, 37: flatness 0.77, 0.68) | 2 |
| fade | 0 | 0 | 0 | 0 | 1 (23: watercolour vignette under the procession) | 1 |
| fade-clip | 1 (47/48 dissolve top) | 0 | 0 | 0 | 0 | 1 |
| frame-eaten | 6 | 0 | 0 | 0 | 2 | 8 |
| no-gap-merge | 0 | 0 | 1 (12) | 1 (60) | 0 | 2 |
| pan-cut | 0 | 0 | 0 | 0 | 1 | 1 |
| padded-edge | 1 (99) | 0 | 0 | 0 | 0 | 1 |
| total | 8 | 0 | 1 | 1 | 6 | 16 |

Iteration 4 on the same books (u395 fades out, frame-eaten back-filled: the boxes did not change there): 23.
So 23 -> 16.

Illustrator verdict, iteration 5 (verbatim):

> On frame-and-gutter material (tog235, sh14, most of u395 and lo9) this approach is at or near reader grade for **where** the cuts go. It is not yet reader grade for **box edges**:
> - Flat art bands and frame lines next to a gutter are being eaten: u395 boxes 0, 1, 23, 43, 82, 95; cpc1 boxes 23, 25, 27.
> - That one bug is rule-fixable: split blank runs at median-colour jumps.
>
> Three cases cannot be recovered from rows of pixels alone:
> 1. **Painted backgrounds vs fades:** a painted sky with sparse marks versus a transition fade with specks (cpc1 0–2 vs u395 35→36).
> 2. **Tiny gaps vs close labels:** a 25 px beat gap versus 31–46 px label-to-art gaps (lo9 box 12 vs boxes 23, 39 and others).
> 3. **Captions vs small panels:** a textured caption plate versus a small flat-colour art panel (cpc1 26/37 vs u395 60/61 and the 102 slivers).
>
> Each needs either a bubble/caption detector that reads text and tail direction, or per-panel files or a script. Expect roughly 1–3 beat errors per episode from these, plus fades that need a reader-side policy (keep as an interstitial or drop).

Needs delivery (claims recorded across reviews, none falsified by a change so far): pan-cut (cpc1 0-2: a painted
gradient sky is the same pixel class as a transition fade with specks, u395 35->36); lo9 12 (a 25-px beat gap vs
31-46-px label-to-art gaps inside lo9 boxes; test: min_gutter 24 adds those as cuts); caption plate vs small flat art
panel (cpc1 26/37 vs u395 60/61); sh14 60 (a burst balloon laid over the gutter). Each needs per-panel files, a script,
or a bubble/caption detector.

Next (iteration 6, the last allowed): frame-eaten (8, the largest class). Split each kept gutter run where the median
colour jumps by more than the tolerance; from each end of the run, segments that are off the page colour and flat
(span <= 48) go back to the adjacent content, stopping at the first page-coloured or gradient segment.

## Iteration 6 (change: frame lines and flat end bands go back to the box they touch)

Rules: iteration 5, plus inside `page_gutters`: each kept gutter run is split where the row median colour jumps by
more than 20; from each end of the run (not at the strip's own ends), segments that neither touch the page colour nor
span more than 48 return to the content they touch, stopping at the first page-coloured or gradient segment.

| ep | panels | h min/med/max | gutter min/q1/med/q3/max | <300 | >5000 | recall | precision |
|---|---|---|---|---|---|---|---|
| u395 | 116 | 39/1256/2479 | 71/299/434/527/2722 | 5 | 0 | 1.000 | 0.991 |
| tog235 | 82 | 164/1551/5529 | 78/340/436/725/1564 | 2 | 1 | 1.000 | 1.000 |
| lo9 | 75 | 228/795/2369 | 41/147/214/295/1304 | 2 | 0 | 0.986 | 1.000 |
| sh14 | 89 | 237/589/2940 | 54/205/309/381/838 | 4 | 0 | 1.000 | 1.000 |
| cpc1 | 57 | 165/829/2345 | 70/355/399/498/1976 | 8 | 0 | 1.000 | 0.941 |

No cut moved (scores identical to iteration 5). Edges that moved by more than 3 px: u395 0 bottom +192 (the advisory
card's black field), 23 top -116, 43 -96, 82 -62, 95 -97 (frame line and flat sky back in), and 50 other u395 boxes
by 12-36 px (their black frame lines and white frame borders, which had been read as gutter on the dark page; checked
on crops of 7, 23, 109); cpc1 25 bottom +119, 27 +53 (floor bands); tog235, sh14 and cpc1 others by 3-11 px.

Defects (the reviewer judged u395 99's top, which includes the sweat drops, right: the drops are emanata of 99):

| kind | u395 | tog235 | lo9 | sh14 | cpc1 | total |
|---|---|---|---|---|---|---|
| floater | 0 | 0 | 0 | 0 | 2 (plates 26, 37) | 2 |
| fade | 0 | 0 | 0 | 0 | 1 (23: ~500 px cream dissolve lost) | 1 |
| fade-clip | 1 (47/48) | 0 | 0 | 0 | 0 | 1 |
| frame-eaten | 2 (0: the card's black field above its text, at the strip's first row; 1: the frame line above the crowd sits across a white band from it) | 0 | 0 | 0 | 0 | 2 |
| no-gap-merge | 0 | 0 | 1 (12) | 1 (60) | 0 | 2 |
| pan-cut | 0 | 0 | 0 | 0 | 1 | 1 |
| padded-edge | 0 | 0 | 0 | 0 | 0 | 0 |
| total | 3 | 0 | 1 | 1 | 4 | 9 |

Iteration 5 on the same books (99 judged right): 15. So 15 -> 9.

Risks: u395 box 10 picks up a couple of rubble specks and leaves the rest of a deliberate debris trail outside every
panel (speck drop); tog235 73 (5529 px) and sh14 60 (2940 px) are single boxes far taller than a screen, correct by
the labels, unreadable as one panel.

Illustrator verdict, iteration 6 (verbatim):

> At the cut level the approach is close to reader-grade on this material. Measured against about 400 labelled cuts, there is 1 genuine miss (lo9 diagonal), 3 genuine extras (cpc1: 2 attachable captions and 1 broken sky pan), and 1 extra that is a label-position artefact (u395).
>
> The remaining failures are of two kinds:
> - **Fixable by rule:** caption attachment, thin gutters under slanted edges, soft fades and speck trails at box edges (cpc1 23, u395 10). These are what currently stop the boxes from matching the artist's frame plus bleed.
> - **Not fixable from rows, by construction:** artists overlap layers across gutters on purpose to link beats. The cases here are a sound effect over a gutter (tog235 73, 5529 px), a burst spanning two frames (sh14 60) and staggered insets (lo9 37).
>   - Row segmentation will always return these as one oversized box. That matches the labels but is too tall to read as a single panel.
>   - Getting them to reader-grade needs information beyond row profiles: a 2D panel-rectangle detector (enough for lo9 37), plus a text/SFX/bubble detector or layered source files (needed for tog235 73 and sh14 60).
>
> One representation gap remains. Transition gradients (u395 after 59, sh14 after 20, cpc1 after 2 and 20) carry meaning: day to night, past to present. The splitter correctly leaves them out of every panel, but then they belong to nothing. A reader will need them as explicit transition elements.

Stop: six iterations (rule 3). Needs delivery or a detector (not stops): pan-cut (cpc1 0-2), no-gap-merge (lo9 12,
sh14 60, tog235 73, lo9 37), caption plate vs small flat art panel (cpc1 26/37), shared bridging SFX. Product
question: transition gradients and fades as explicit elements.

## Decision 2026-10-18 (user): overlap-linked beats are one frame

When an artist overlaps art across a gutter to link two beats (a bubble or dialog sitting across the gutter, a burst
spanning two frames, an SFX laid over the gap), the two frames and the gutter between them are a **single long
frame**. Row segmentation already returns this, so these boxes are correct, not defects: tog235 73 (SFX over the
gutter, 5529 px), sh14 60 ("OF MARIA!!" burst), u395 72 (bubble ladder), and bridged-sfx in general (never cut
lettering that crosses a gutter). The stepped reader already handles panels taller than the view by scrolling through
them in screen-height stops (packages/format README, Layout), so height alone is not a reason to split.

Still defects: diagonal or staggered frames with no overlapping element (lo9 12/13, lo9 37/38), which need a 2D panel
detector or per-panel files. Recount under this rule: iteration 6 goes from 9 to 8 (sh14 60 no longer counted).

## Retest 2026-10-18: final splitter (26d50a4) on the fixtures and 21 unseen episodes

Fixtures reproduce iteration 6 exactly (recall/precision: u395 1.000/0.991, tog235 1/1, lo9 0.986/1, sh14 1/1,
cpc1 1/0.941). Unseen episodes judged by Opus illustrator reviewers (errors only; house rules applied):

| episode | boxes | errors |
|---|---|---|
| omniscient-reader 154 | 62 | 1 |
| omniscient-reader 308 | 62 | 1 |
| omniscient-reader prologue | 28 | 2 (box 1: two missed cuts around a 260 px-isolated caption; box 23: missed cut + 539 px flat grey padding) |
| tower-of-god s2 246 | 109 | 2 (+1 uncertain: title "15" band) |
| sweet-home prologue | 84 | 0 |
| true-beauty 0 | 62 | 1 (staggered insets merged) |
| true-beauty 7 | 85 | 3 (reaction bursts / SFX 41-52 px from their frame, alone) |
| unordinary prologue | 32 | 3 (gutters of 30-36 px never cut) |
| unordinary 201 | 66 | 0 |
| cursed-princess-club 11 | 53 | 0 |
| lore-olympus 1 | 60 | 0 |
| witch-and-her-corgi 1 / 10 / 290 | 9 / 12 / 11 | 0 / 1 (+1 borderline end card) / 0 |
| housecat-philosophy 0 / 09 / 169 | 1 / 2 / 2 | 2 / 6 / ~14 missed cuts (page-style grid, gutters 12-32 px) |
| tower-of-god s1 0 | not run | crash: last slice 800 px wide, others 700 |

Total: 740 boxes, 36 errors; without the Housecat grids, 735 boxes and 14 errors (1.9 %).

New failure kinds on unseen material: narrow gutters under min_gutter 40 (Housecat, unOrdinary prologue);
frame fading to white just before a gutter merges across it (tog s2 71, unordinary prologue 22); flat non-white page
background read as content (tog s2 75, orv prologue 23); lone text 40-62 px from its frame stays alone (true-beauty 7,
orv 308 50; deliberate lone beats sit >= ~130 px from both neighbours, a testable gap rule). Tooling bugs: mixed slice
widths abort intake; the sheets stats line crashes on an episode with no gutters.

## Round 2, iteration 0 (hard set baseline; splitter 26d50a4 plus two tooling fixes)

Hard set (`run_hardset.sh`): hc169, hc09 = Housecat Philosophy 169, 09; uprol = unOrdinary prologue; tb7 = True
Beauty 7; orv0 = Omniscient Reader prologue; tog246 = Tower of God S2 246; tog0 = Tower of God S1 0; wc10 = Witch
and Her Corgi 10; never seen before: hc01, hc02 (Housecat 01, 02), u1 (unOrdinary 1), tb4 (True Beauty 4).
Regression set = the five round-1 fixtures (`run_fixtures.sh`), scored against their labels every iteration.

Tooling fixes, not counted as a change (the splitter's cuts are unchanged; regression scores reproduce exactly):
`stitch` scales a slice of another width to the width covering most rows (tog0: seven 700-px slices and a final
800-px one, which aborted intake); `sheets.stats` prints "no gutters" for a one-box episode instead of crashing.

Labels for the 12 episodes written to `.data/labels/<slug>.json`. Seeded from this run's cuts (the round-1 lesson:
seeded labels are circular), then corrected by hand from crops of every uncut blank run of >= 8 rows and every box
under 300 or over 2500 px, then corrected again from the four reviewers: hc169 +7275 (was ambiguous); tb7 -3527,
-82460 (floaters that belong above), -71988 (the lone HUFF joins the HUFF panel below); tb4 +39950 (95-row black
gutter between two framed panels); tog246 -10280, -48094 (off-panel lines that open the panel below); u1 -457 (the
lecture bubble leads into the classroom shot); tog0 -6415 +6805 (the black credit card belongs to the title card),
-2672 ("REVENGE?" is panel 4's caption, like 1-3), 3343 ambiguous; wc10 -1436 ("CORGIS SHED A LOT." heads box 2).
Reviewers were given sheets, stats, labels and a numeric pre-pass (uncut blank runs, short and tall boxes), never
my defect list; four in parallel, 3 or 4 episodes each, capped at 12 image reads (they used 5-12; 70-125 s each).

| ep | boxes | h min/med/max | gutter min/med/max | recall | precision |
|---|---|---|---|---|---|
| hc169 | 2 | 865/3805/6745 | 49 | 0.062 | 1.000 |
| hc09 | 2 | 480/1921/3363 | 183 | 0.143 | 1.000 |
| hc01 | 2 | 1310/2113/2917 | 49 | 0.125 | 1.000 |
| hc02 | 1 | 4007 | none | 0.000 | - |
| uprol | 32 | 21/299/3442 | 43/222/1694 | 0.886 | 1.000 |
| u1 | 39 | 24/451/1580 | 42/153/1218 | 0.949 | 0.974 |
| tog0 | 15 | 28/307/744 | 118/195/1048 | 1.000 | 0.923 |
| wc10 | 12 | 33/432/805 | 146/245/325 | 1.000 | 0.909 |
| tb7 | 85 | 52/621/1571 | 41/344/801 | 1.000 | 0.940 |
| tb4 | 74 | 168/516/1319 | 42/539/1150 | 0.986 | 0.986 |
| orv0 | 28 | 58/1155/8754 | 62/483/1410 | 0.900 | 1.000 |
| tog246 | 109 | 206/847/2183 | 173/394/1502 | 0.991 | 0.981 |

New kind: **dropped-card**, a flat colour card whose sparse lettering stays under the 0.2 % outlier share, so the
whole card reads as gutter and lies outside every box (tog0 black "story by" card at 6380-6670; tog246 black "15"
band under the title, 8700-8860). Missed-gutter now includes **narrow-gutter** cases (a clean run of 11-36 rows,
under min_gutter 40) and **flat-panel-floaters** (uprol 11: two thin flat sky frames read as floaters and grouped).

Defects (merged: mine and the reviewers'; the reviewers found the tb7 2/49/84, tog246 6/37/44, tog0 7 floaters and
the tb4 black gutter that I missed):

| kind | hc169 | hc09 | hc01 | hc02 | uprol | u1 | tog0 | wc10 | tb7 | tb4 | orv0 | tog246 | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| missed-gutter | 15 | 6 | 7 | 7 | 4 | 2 | 0 | 0 | 0 | 1 | 3 | 1 | 46 |
| floater | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 7 | 1 | 0 | 3 | 14 |
| dropped-card | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 2 |
| total | 15 | 6 | 7 | 7 | 4 | 3 | 2 | 1 | 7 | 2 | 3 | 5 | 62 |

Missed-gutter detail: Housecat grids (35 of 46, gutters 11-31 rows); uprol 16277/17490/21862 (24-36 rows), u1
1672/25552 (12 and 30 rows); uprol 8926 (flat sky frames); orv0 2561/3050 (a caption 265/275 rows from both
neighbours, attached because both gaps are under the floater cap of 362) and 51065 (539-row white run inside box 23);
tog246 91616 (a panel fading to white just before the gutter); tb4 39950 (black gutter on a black page).
Needs meaning, not pixels (counted, flagged): tb7 31 "OR THIS..." and 49 (direction set by punctuation and story),
tog246 44 (equidistant bubble, 356/345 rows), u1 box 34 "...run..." (30 rows from each neighbour; not counted, the
cut that matters, 25552, is counted). Not counted: tog246 75's time-skip line attaches up by the house rule.

Risks: the floater cap is 0.75 x the episode's median gutter, so any change that adds narrow gutters lowers the cap
everywhere in that episode.

Illustrator verdicts (merged; quoted where they agree):
> Group A (Housecat): "none of these errors needs semantic understanding. The main defect is a fixed minimum gutter
> height somewhere between 35 and 49 rows. It is too large for 800-px-wide page strips, where gutters are about 15 rows."
> Group B (unOrdinary, ToG 0, Corgi): "the gap-based approach works on bordered, well-spaced panels. Its errors fall into
> two groups. The first is real gutters narrower than 40 rows ... a cutter that sees frame borders can probably fix
> these. The second is captions on white whose owner is set by rhythm or meaning rather than distance."
> Group C (True Beauty): "the panel cuts themselves are nearly reader-grade on this clean, white-gutter material. 7 of
> the 9 errors are floaters ... The remaining 2 (tb7 boxes 31 and 49) need the meaning of the text, which pixels don't carry."
> Group D (ORV, ToG 246): "Nothing here suggests the row-cut approach has hit a ceiling, apart from equidistant floaters."

Next: narrow gutters (46 missed-gutters, 35 of them Housecat). A fixed lower min_gutter would cut between a
panel and the burst 9-30 rows under it (True Beauty has 14 such runs), so the narrow cut needs a panel edge.

## Round 2, iteration 1 (change: narrow gutters against a panel edge)

Rule added in `page_gutters`: a page-coloured blank run of 8 to 39 rows is a gutter when, within 3 rows above or
below it, one row holds an unbroken stretch of off-page pixels across >= 0.4 of the width (`panel_edge`: a frame line
or a straight panel edge; bubbles, captions and SFX measure mostly under 0.2). Exception: when only one side has the
edge and the other side is a block under 400 rows followed by a gutter of >= 40, that block is a lone burst or bubble
under its panel and the run is not cut. Measured first without the exception: tb7 +4, tb4 +3, sh14 +1 and lo9 +1
extra cuts (bursts 9-30 rows under a frame); two other attempts were rejected on the way (a floater cap computed from
wide gutters only, which let Housecat's flat line-art panels group as floaters across 15-row gutters; a "framed slab is
never a floater" test, which also caught True Beauty's bordered caption boxes: tb7 +11 extras).

| ep | boxes | gutter min/q1/med/q3/max | recall | precision |
|---|---|---|---|---|
| hc169 | 16 | 13/14/16/23/49 | 0.938 | 1.000 |
| hc09 | 9 | 12/15/15/71/183 | 1.000 | 0.875 |
| hc01 | 10 | 11/12/14/25/49 | 1.000 | 1.000 |
| hc02 | 8 | 14/14/15/16/17 | 1.000 | 1.000 |
| uprol | 35 | 24/118/179/489/1694 | 0.971 | 1.000 |
| u1 | 41 | 12/86/147/222/1218 | 1.000 | 0.975 |
| tog0, wc10, tb7, tb4, orv0, tog246 | unchanged | | as iteration 0 | |

Regression set: every box identical to iteration 0 (u395 1.000/0.991, tog235 1/1, lo9 0.986/1, sh14 1/1, cpc1 1/0.941).
Re-reviewed the six changed episodes (two reviewers, 4 and 9 image reads): all nine changed unOrdinary boxes and the
Housecat grids judged right except the two below.

| kind | hc169 | hc09 | hc01 | hc02 | uprol | u1 | tog0 | wc10 | tb7 | tb4 | orv0 | tog246 | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| missed-gutter | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 3 | 1 | 7 |
| floater | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 7 | 1 | 0 | 3 | 14 |
| dropped-card | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 2 |
| fragment | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| total | 1 | 1 | 0 | 0 | 1 | 1 | 2 | 1 | 7 | 2 | 3 | 5 | 24 |

62 -> 24. hc169 1993 (11-row gutter, frame lines on both sides) stays merged: the 300-row panel below it is flat
line art, so it is a floater, and the 11-row gap is just under the floater cap of 0.75 x 15 = 11.25, so it rejoins the
panel above. hc09 box 6 is new: a 4-row rule line under a frame, now cut off as its own box (fragment).

Risks: Housecat panels are flat enough (0.88-0.96) to count as floaters, so on a grid episode the only thing keeping
them apart is that the cap (0.75 x median gutter) sits just under the gutters themselves; hc169 1993 is the first
case where it did not. The lone-block exception is a height guess (400): a real panel under 400 rows with a frame on
one side only and a full gutter below would be merged into its neighbour.

Illustrator verdict, iteration 1 (both reviewers agree):
> "on these clean page-style grids the splitter matches the artist's intent almost everywhere. Both misses are
> threshold problems, not misread storytelling" (Housecat); "Splitter and labels agree everywhere except these two
> boxes ... Both errors are rule-level fixes, not a different reading of the art" (unOrdinary).

Next: floaters (14, now the largest kind): attach by the episode's own gap distribution instead of a flatness test
plus a fixed cap.

## Round 2, iteration 2 (change: tight-gap floaters)

Rule added in `attach_floaters`: a slab under 300 rows that is at least 0.7 flat and sits 40 rows or more but under
0.25 x the episode's median gutter from a neighbour counts as a floater (then joins the nearer panel under the cap as
before). Bursts with dense spiky rims measure 0.77-0.79 flat, under the old 0.85 floater threshold, and sat 41-52 px
under their panel on 324-528 px median gutters. Measured on the way and rejected: the same test for any slab under 700
rows (glued Lore Olympus 9's 662-row "HA HA" panel, 0.74 flat, to the next panel across 41 px: lo9 -2 recall; tb7, tb4
-1 each); across narrow gutters too (undid iteration 1 in u1 and uprol: they are under 0.25 x median); and a second
clause joining a floater to the side at most 0.5 x as far as the other, strip ends counting as infinitely far (fixed
u1 457 and tog246 48094 but merged 6 real cuts in Housecat and orv0 and u395 699 on the regression set).

Changed boxes: tb7 40051 and 41698 (bursts 52 and 41 rows under their panels joined them), cpc1 37494 (a 165-row
narration plate 70 rows above its panel joined it; a round-1 floater). Every other box on all 17 episodes identical.
One reviewer, 3 image reads: "All three joins are right ... none of the three joins put text with the wrong panel."

Regression set: u395 1.000/0.991, tog235 1/1, lo9 0.986/1, sh14 1/1 unchanged; cpc1 1.000/0.941 -> 1.000/0.960.

| kind | hc169 | hc09 | hc01 | hc02 | uprol | u1 | tog0 | wc10 | tb7 | tb4 | orv0 | tog246 | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| missed-gutter | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 3 | 1 | 7 |
| floater | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 5 | 1 | 0 | 3 | 12 |
| dropped-card | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 2 |
| fragment | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 1 |
| total | 1 | 1 | 0 | 0 | 1 | 1 | 2 | 1 | 5 | 2 | 3 | 5 | 22 |

24 -> 22 (plus one regression-set floater fixed). tb4 47 stays: its burst is 422 rows and 0.69 flat.

Remaining floaters are of the kind the round-2 reviewers flagged as spacing-blind: owner set by rhythm or meaning
(tb7 2 at 274/523 rows should join up, while orv0's caption at 265/275 should stand alone; tb7 31, 49 and tog246 44
need the text). Needs a text reader, not a gap rule; recorded under "needs delivery or a detector".

Next: dropped-card (2): a flat off-page band with lettering, lying between two page-coloured stretches of one gutter
run, is kept as gutter today (tog0 black "story by" card, 6383-6669, 19 ink rows of 290; tog246 black "15" band,
8703-8928 between two grey gradients, 23 ink rows).

## Round 2, iteration 3 (change: slivers under 8 rows join the nearer neighbour)

Tried first and reverted: speck slabs must sit on the local page colour (to keep lettering on flat black cards).
It did stop dropping tog0's "story by" card and tog246's "15", but they came out as boxes of their own (tog0: the card
belongs with the title card; tog246: a 23-row "15" sliver, since the black band around it is part of a fade
segment), and on the regression set u395 lost a cut (64400 -> 64084: a speck on the dark page near a page-colour
change was kept) and cpc1's opening stars joined two boxes. Net 0 on the hard set, a recall drop on u395: reverted.
dropped-card needs the band and its lettering kept together as one card, i.e. a card detector, not a speck tweak.

Kept: `join_slivers`, run at the start of `attach_floaters`: a slab under 8 rows joins the nearer neighbour whatever
the gap (no beat is that thin). Only hc09 changed: its 4-row rule line (3063) joined the panel above it (16 rows up,
90 down); checked on a crop, the beat boundaries are unchanged. Every other box on all 17 episodes identical;
regression scores unchanged (u395 1.000/0.991, tog235 1/1, lo9 0.986/1, sh14 1/1, cpc1 1.000/0.960).

| kind | hc169 | hc09 | hc01 | hc02 | uprol | u1 | tog0 | wc10 | tb7 | tb4 | orv0 | tog246 | total |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| missed-gutter | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 3 | 1 | 7 |
| floater | 0 | 0 | 0 | 0 | 0 | 1 | 1 | 1 | 5 | 1 | 0 | 3 | 12 |
| dropped-card | 0 | 0 | 0 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 0 | 1 | 2 |
| fragment | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| total | 1 | 0 | 0 | 0 | 1 | 1 | 2 | 1 | 5 | 2 | 3 | 5 | 21 |

22 -> 21. Stop: round 2's three-iteration limit.

Round 2 summary: 62 -> 21 defects on the hard set (401 -> 439 boxes). Regression set never dropped; cpc1
precision rose 0.941 -> 0.960.

Needs delivery or a detector (not fixable by a gap rule, per the reviewers and the rejected attempts above):
floaters whose owner is set by meaning or rhythm (tb7 2, 31, 49, 75, 84; tog246 6, 37, 44; tog0 5; wc10 1; u1 0;
orv0's standalone caption at 265/275 rows is the mirror case), dropped-card (a card detector), tb4 39950 (a black
gutter on a black stretch of a white page), tog246 91616 (a panel fading to white just before the gutter), uprol
8926 (two thin flat sky frames read as one floater unit), orv0 51065 (539 white rows inside box 23, not page-coloured
by the local mode), hc169 1993 (flat line-art panel rejoining across an 11-row gap just under the 11.25 cap).

## Closed 2026-10-18

Tuning stopped by the user after round 2 (hard set 62 -> 21 defects, regression set unchanged or better). Open items
are recorded above under "needs delivery or a detector": caption ownership at equal spacing, dropped title cards,
diagonal/staggered frames. They move to the bubble/text stage, not to more splitter tuning.
