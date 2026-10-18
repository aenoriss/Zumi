# Zumi: how to deliver an episode

For the artist. One page. Everything here exists so the pipeline can cut panels, find dialog and regenerate art without guessing. If something is unclear, ask; do not improvise a format.

## What we need from you

Three things per episode:

1. **Panels** as images.
2. **A script** with the dialog, since text is never baked into the art.
3. **Style references** once per series, not per episode.

Rough is fine. The pipeline regenerates the art in the series style; your sketch sets composition, poses, framing and expressions. Clean lines are not required, but the structure must be readable: who is where, what they do, where the camera is.

## 1. Panels

**Preferred: one file per panel.**

```
ep01/
  p01.png
  p02.png
  ...
  script.md
```

- PNG (or JPG at quality 90 or better), sRGB, at least **1600 px on the long side**. Bigger is fine.
- Any aspect ratio. Tall, wide and square panels all work. Keep each panel a single scene; if two moments share a drawing, make two files.
- **No lettering, no text inside bubbles.** Bubble outlines are allowed if they help you place dialog, but we erase them; the script is the source of truth.
- Numbering is reading order. `p01` is the first panel the reader sees.
- Sound effects drawn as art (an onomatopoeia that is part of the image) are fine; mark them in the script as `sfx` so we know they are not dialog.

**Alternative: a vertical strip, WEBTOON Canvas style.** Only if drawing per panel breaks your flow.

- 800 px wide (1600 is fine, we downscale), one tall PNG/JPG or slices up to 1280 px tall named in order (`ep01-01.png`, `ep01-02.png`, ...).
- **Blank gutters of at least 150 px** between panels, the same flat colour as the margins. Nothing crosses a gutter: no bubble, no character, no gradient. A gutter is how the pipeline knows where a panel ends.
- Two panels side by side only if a vertical blank of at least 60 px separates them.
- Panels without a gutter between them (bleeds, overlaps) will be treated as one panel. If that is the intent, fine; if not, add the gutter.

**Scanned paper sketches**

- 300 dpi or at least 2000 px wide, one page per file.
- Adjust levels so the paper is near white and the pencil clearly darker. No spiral-binding shadow, no fingers.
- Either cut the panels yourself (preferred) or draw the gutters as described above.

## 2. Script

`ep01/script.md`, one line per bubble, in reading order:

```
# ep01 — The King Returns

p01 | caption | — | The castle had been quiet for three years.
p02 | speech  | Gwen | Father? Is that really you?
p02 | speech  | King | Three years, and you still leave the gate open.
p03 | thought | Gwen | He looks older than I remember.
p03 | sfx     | — | CREAK
p04 | shout   | Gwen | Everyone, he is back!
```

Columns, separated by `|`:

| Column | Values |
|---|---|
| panel | `p01`, `p02`, ... matching the file |
| kind | `speech`, `thought`, `shout`, `caption` (narration), `sfx` |
| speaker | a name from the cast list below, or `—` for captions and sfx |
| text | the line, in English for now |

Optional fifth column: where the bubble sits, as percentages of the panel, `x% y%` from the top-left corner (`25 15` means a quarter in from the left, near the top). If you skip it, the pipeline places the bubble next to the speaker's face.

Order of the lines inside a panel is the order they are read and voiced.

## 3. Once per series

A folder `series/` with:

- **Cast list**: `cast.md`, one line per character: name, one or two sentences on who they are, and a voice note ("teenage girl, soft, slightly nervous"; "old man, gravelly, warm"). Names must match the script exactly.
- **Style**: 3 to 6 reference images of the look the finished art should have (your own finished work, or any images you are allowed to share with us), plus one paragraph describing it (line weight, colour palette, shading, mood). A style preset name is enough if you prefer one of ours.
- **Cover**: one image, portrait 3:4, at least 1200 × 1600 px.

## Checklist before sending

- [ ] Every panel file is at least 1600 px on the long side.
- [ ] No text drawn in the art (except sfx marked in the script).
- [ ] Every speaker name in the script is in `cast.md`.
- [ ] Panel numbers in the script match the files.
- [ ] Strips, if any, have blank gutters of at least 150 px and nothing crossing them.

## Why these rules

- Text as data: the reader shows bubbles as live text with voice, so lettering in the art would have to be erased and would leave scars.
- 1600 px: the regeneration and cut-out steps work at 1024 to 2048 px; smaller inputs come back blurry.
- Gutters: the strip splitter looks for rows of flat background colour. Anything crossing them merges two panels.
- Per-panel files: they skip splitting entirely, and splitting is the least reliable step on rough sketches.
