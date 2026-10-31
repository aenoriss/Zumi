# Frame finder: prompt committee and post-processing audit, 2026-10-30

The frame finder (`pipeline/segment/frames.py`) asks Claude Sonnet 5.5 for the panels of each box, then turns its boxes
into frame masks. Two reviews shaped its second and third versions. Both worked on the 81 Pepper&Carrot boxes of the
speaker dataset (episodes 36-39, internal R&D only).

## The committee (prompt)

Three reviewers (Opus 5.5), 27 boxes each, one image per box: the art beside the frames found with prompt v1. Each
judged every box, the user's proposal to fuse panels joined by a crossing bubble, and proposed prompt changes.
Reports: the session scratchpad (`committee/report_A.md`, `_B`, `_C`); the findings that matter are here.

| Finding | Boxes |
|---|---|
| Missed, split or false panels | 0 |
| Credits or end pages framed as story | 3: 36-p028, 37-p017, 39-p030 |
| Box too small or too big | 4: 39-p025, 38-p018 (vignettes boxed around the main figure), 36-p000 (panel stopped at its inset), 36-p012 (edge 8% off) |
| Slanted panel forced into a rectangle | 36-p008, 36-p025, 39-p012 |
| Frames notched by page removal (code, not prompt) | about 40 |

**Fusing panels joined by a bubble: rejected, unanimously.** 16 crossings in the 81 boxes, none one scene: mostly
shot / reverse shot, two cameras that need their own depth; fusing would also put the other panel's characters in the
speaker rule's candidates exactly where it must tell them apart. The prompt now says the opposite (a crossing bubble
never joins panels), and a straddling bubble belongs to the frame its tail tip lands in (`speakers.bubble_frame`).

Prompt changes taken (v2, then v3): a panel defined by viewpoint and moment, with the border as the usual cue; vignettes
and decorations; not splitting at in-scene dividers; bubbles and art crossing a border never set or join panel edges;
the region's kind (story, title, credits, text) and its text regions, with an empty panel list allowed; whole scenes
for borderless panels; inset extent; shared edges; corner points for slanted panels (v3).

v2 on the 81 boxes (0.44 USD): the 3 credits pages came back with no panels; 39-p026 came back with x in pixels and
y in 0-1000 units, likely from v2's sentence on separately scaled axes. v3 gives the image's size and spells the units
out per axis; an answer with a coordinate outside 0-1000 is asked again once and never cached. v3 is not yet run.

## The audit (post-processing)

One agent traced every consumer of frames and the page mask and measured variants on the cached answers (no paid
call): `pipeline/.data/out/frames_audit/REPORT.md`. Its findings, and what was built from them:

- Taking the page out of every frame (step 5) made vignettes silhouettes, notched frames at bubbles, and left one
  frame too small for a backdrop: removed. Frames keep the page inside them.
- Art outside every box must still join a frame: plain rectangles lost 345k art px (52k character px) on 23 of 62
  multi-frame boxes. Kept, per connected piece: a piece touching a frame joins it; a piece cut off by page (credits
  under the last panel) goes to a flat frame; lettering past every box joins none (the lettering layer draws it).
- `parallax.gutter` misses the dark grey page of episodes 36 and 38: the frame step now learns a flat page colour
  from the pixels outside every box, and saves the page it uses (`masks/<box>-page.npz`) for every later step.
- The layers step took the page out again (`cards.py`): a frame's area is now the frame itself, and the backdrop's
  margin is mirrored from the frame minus the page along its edge.

Beyond the audit: box edges fitted to the gutters (trimmed when they lie on page, snapped out up to 3% when they lie
on art), each frame grown to the rectangle around its box and its joined art, flat frames for credits and text
(backdrop without relief; their characters stay cards: P&C's credits mascots speak, and those bubbles are labelled,
so the committee's "no speaker rules on credits pages" was not taken).

## Measured on the 81 boxes (cached v2 answers, no model call)

- No overlap and no art lost on any box.
- Story frames: area / bounding box median 1.000; below 0.97 only where an inset or a neighbour takes part of the box.
- Flat frames on the 4 credits and end pages only.
- Speakers: 310/333 on the new frames against 316/333 on the saved frames. The 7 losses: two labels naming another
  card of the same man (38-p009), slanted or break-out panels as rectangles (36-p025, 39-p025, 36-p013), a cross-frame
  tail the rules miss (37-p000), a tailed credits caption (36-p028). One fixed: 36-p012 #4.

## Not done

- Prompt v3 has not been run (the user asked for no model calls until everything was implemented).
- No layers rebuilt and nothing seen in XR: old `masks/*-frames.npz` must be deleted first, and each re-layered box
  pays a new band erase.
- All thresholds were tuned on Pepper&Carrot only.
