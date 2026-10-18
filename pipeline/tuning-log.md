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

Counted per instance (one floater = 1, one missed gutter = 1). "Risk" = right output that depended on a lucky margin.

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
