# Zumi: domain language

Terms the code and its reviews use, so a module is named after the concept it holds. Decisions live in
`docs/architecture/decisions.md`.

## Pipeline (`pipeline/segment`)

- **Box**: one panel of the episode as intake cut it (a webtoon box may hold several frames). Everything a step
  saves for a box is read and written through `boxstore.Box`; no other module knows the paths or formats.
- **Frame**: a drawn panel inside a box (`frames.py`). Each frame is its own scene and camera; depth is only ever
  estimated per frame. The **page** is what lies outside every frame.
- **Lettering**: bubbles, captions and sound effects (`bubbles.py`, which also tightens each sound effect to its
  letters). Their shape rules (`shape.py`) are shares of a **tile**, the square one box-width wide that SAM runs on.
- **Objects**: the movable things in front of the backdrop that become cards of their own (`objects.py`: picked by
  a vision call with a point and its relations on / held / front / except, masked by SAM, reviewed). What is not
  an object stays painted on the backdrop.
- **Stamp**: the identity of a box's lettering masks in their saved order (`masks.stamp`). A result keyed by bubble
  id (the placement in `bubbles.json`, a transcript) carries the stamp of the masks it was made from, and is joined
  only to results with the same stamp.
- **Bubble record**: a bubble's placement joined with its transcript's text and kind (`Box.bubbles()`).
- **Transcript**: what Transcribe read in a box: each lettering element's text, kind and whether it is lettering
  at all. It says nothing about who speaks.
- **Speakers**: which character card(s) speak each bubble (`speakers.py`, rules), within one box; the identity
  reader corrects the links it reviews (`check` balloons: those made without a clear tail), and a speaker may then
  be a card of another box (a voice from the box before or after) or off-panel.
- **Identity**: which cards are one character across boxes and across a series' episodes
  (`character_identity.identity_step`): appearance groups, then one reading of the story. Pass 1 founds the series
  **cast** (`<run>/cast/<series>/`); pass 2 assigns a later episode to it. A deliberately different look of a person
  is a separate character with a shared voice.
- **Voice**: a character's designed Gemini voice (a stored voice id and sample in the cast), from a one-or-two-sentence
  description the reader writes; **lines** are the recorded balloons of an episode (`<episode>/audio/`), each in its
  speaker's voice.
- **Plan**: a box's flat layers before any pixels are drawn (`layers.plan`): the cards, their depths and the
  bubbles' placement. The erase reads the plan; `layers.render` draws it on the plate. Plan, erase and render are
  one module and one call (`layers.build`), since none of the three is used without the others.
- **Plate**: the box's art with what the cards hide painted in by the erase (`layers.erase_box`).
- **Scene / Layer**: the saved flat layers of a box as the reader gets them (`Box.scene()`, `cards.json` + PNGs).
- **Paid call**: any call to a paid API. All go through the shared daily cap (`spend.py`); a step's calls fan out
  through `spend.paid_map`, and an **offline run** (`spend.offline()`, `ZUMI_OFFLINE=1`) refuses every one.
