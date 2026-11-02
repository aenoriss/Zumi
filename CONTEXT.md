# Zumi: domain language

Terms the code and its reviews use, so a module is named after the concept it holds. Decisions live in
`docs/architecture/decisions.md`.

## Pipeline (`pipeline/segment`)

- **Box**: one panel of the episode as intake cut it (a webtoon box may hold several frames). Everything a step
  saves for a box is read and written through `boxstore.Box`; no other module knows the paths or formats.
- **Frame**: a drawn panel inside a box (`frames.py`). Each frame is its own scene and camera; depth is only ever
  estimated per frame. The **page** is what lies outside every frame.
- **Lettering**: bubbles, captions and sound effects (`bubbles.py`, `sfx_refine.py`). Their shape rules
  (`shape.py`) are shares of a **tile**, the square one box-width wide that SAM runs on.
- **Stamp**: the identity of a box's lettering masks in their saved order (`masks.stamp`). A result keyed by bubble
  id (the placement in `bubbles.json`, a transcript) carries the stamp of the masks it was made from, and is joined
  only to results with the same stamp.
- **Bubble record**: a bubble's placement joined with its transcript's text and kind (`Box.bubbles()`).
- **Transcript**: what Transcribe read in a box: each lettering element's text, kind and whether it is lettering
  at all. It says nothing about who speaks.
- **Speakers**: which character card(s) speak each bubble (`speakers.py`, rules), within one box. Identity of a
  character across boxes is a separate concept, not built yet.
- **Plan**: a box's flat layers before any pixels are drawn (`cards.plan`): the cards, their depths and the
  bubbles' placement. The erase reads the plan; `cards.render` draws it on the plate.
- **Plate**: the box's art with what the cards hide painted in by the erase (`band_erase.py`).
- **Scene / Layer**: the saved flat layers of a box as the reader gets them (`Box.scene()`, `cards.json` + PNGs).
- **Paid call**: any call to a paid API. All go through the shared daily cap (`spend.py`); a step's calls fan out
  through `spend.paid_map`, and an **offline run** (`spend.offline()`, `ZUMI_OFFLINE=1`) refuses every one.
