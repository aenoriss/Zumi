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
- **Track**: one animation on one art layer of a panel, in the format's fixed vocabulary (translate, rotate, scale,
  opacity, sway, shake; spriteCycle later), with a duration, delay, loop and easing; `step` easing is a cut.
- **Beat**: acted motion the motion designer judged the scene allows: a cut of a character to a new place, an object's
  arc, timed to a bubble. Everything else a panel gets is ambient motion that keeps it alive.
- **Hold**: a panel's length set by its motion rather than its voices, for a wordless beat, within 2-8 s.
- **Motion**: step 9 (`motion.py`): the motion designer agent's tracks for every box, reviewed, in `motion/motion.json`.
- **Clock**: when every panel, frame and balloon of an episode is on screen (`clock.py`, step 8b, 2026-11-08), built from
  the layers, the balloons, their reading order and the recorded lines' lengths, before anything that hangs on time
  (music, places, the export). A frame is on screen from its start until the next frame of its panel starts; one
  definition, `clock.times`, for every step.
- **Setting**: a place as the comic draws it (the tavern's main room, the road over the valley), active across the
  boxes that show it. Time of day and weather are attributes of a setting, not new settings. The 3D props of a scene
  will hang on the setting; music hangs on its place (see Place). Read per frame: each frame is in one setting, and a frame joins a
  setting already seen in the episode unless its place is new. Settings belong to an episode, not to the series
  (unlike the cast): a place seen again in a later episode is a new setting there.
- **Span**: a run of the story the music reviewer labels, anchored to bubble and frame ids (never seconds): its
  setting, its mood and its role. The reviewer also marks point events: an entrance, an exit, a button (a punchline
  or an interruption the music must get out of under at once). Decided by a committee of four readings, 2026-11-07.
- **Mood**: the tone of a span, one of light, tense, grave, epic, tender (not a scale: a tale told in the tavern is
  epic while the tavern stays light), with a few free words of colour that shape the clip but never make a new
  track. A place has one track per mood its spans reach while it is open, and the mood picks which track plays. A
  pair of place and mood earns its own track with at least 7 s of music (the place rule's stay; silent spans do not
  count); a shorter pair plays the place's longest-scored track, and a place none of whose pairs reaches 7 s keeps
  its longest one (decided 2026-11-08 at 15 s, lowered with the place rule 2026-11-09).
- **Role**: what the music does in a span: **lead** (it carries the moment: a wordless frame, a performance, an
  arrival), **under** (an underscore beneath the lines), **source** (music heard in the room, the tavern's band),
  **out** (silence, a state of its own and the default for a private earnest scene until its turn). The role
  picks the level; who is speaking shapes it: music ducks before a line and releases after it, stays ducked across
  the short gaps between lines, and rises only in gaps of two seconds or more and on wordless frames. There is no
  tension number: stakes choose the track and the role, never the loudness.
- **Dressing**: what a setting does to the reader's real room (design `docs/design/room-dressing-2026-11.md`, 2026-11-07):
  one **hero light** carried by a prop (the tavern's candle) falling on a relit proxy of the real surface under it, one or
  two still **silhouettes** that name the place, and a **grade** of the passthrough image (one LUT and a brightness target
  per setting). The reader lights the hero in the first-use setup and it is never taken back (a low ember outside its own
  setting). Inside its setting the hero's level is the episode's clock alone (the candle burns down); it departs only on
  two beats the music reviewer marks: a **lie** (a prop that exists only as a character claims it, the axe of the tale lying
  on the table, gone when the claim fails) and the episode's one **turn** (the flame dies at the start of a silence in which the
  reader may relight it; the story never waits).
- **Place**: a setting's surroundings shown through the reader's walls (`places.py`; agreed 2026-11-08): one wide
  painted view of the setting (2:1) lifted to a mesh around the seat, seen through the key wall and bleeding onto the
  side walls and the ceiling (no floor), its gaps backed by an erased copy. The reference for quality is the tavern's
  first 2:1 view (2026-11-07, 140 degrees), and every view is made the way it was: a plain 16:9 view of the setting
  first, then the 2:1 panorama continuing it (asked from comic boxes alone, FLUX invented a projection per place,
  115-324 degrees). Every place shows at most the central 140 x 72 degrees of its view (the
  **shown** window), so all bleed the same short way: FLUX's 2:1 views spanned 115-324 degrees, and the wide ones
  covered the side walls whole and looked worse. A place is earned
  by a **visit** (a run of frames in one setting on the episode clock) of at least 7 s (15 s until 2026-11-09, when
  the user wanted the village's 7.6 s arrival shown), the final visit counting the
  credits after it; a shorter visit keeps the open place if it is that place, else opens the next earned place when
  it begins within 10 s, else keeps the open place. A setting with no earning visit gets no place. Swaps fade out and
  in, never cut. A place's view is empty of figures, and its prompt does not ask for more depth (both tried
  2026-11-08 and dropped): more layers meant more depth edges, each torn into a staircase on the mesh grid, nearer
  layers made the place huge once scaled beyond the walls, crowds broke the erase, and figures came out blocky even
  when flattened onto the surface behind them. Step 10c builds each earned place in `<episode>/places/<setting>/`: the **view** (FLUX 3, prompted from
  the setting's record with boxes that show it), its **front** mesh (MoGe-3 on the local GPU, `place_geometry.py` in
  `.venv-moge`), the **plate** (FLUX Erase without the near objects) and the **back** mesh behind them; the export packs
  both meshes and the timeline of which place shows when, planned on its own clock (`episode.places`). Music comes from
  the place: it is made for the portal, exclusively. A track belongs to a place and a mood, is generated only for
  the time that place is open, and plays spatialised from inside its portal; a moment no portal covers gets no
  music, and a place swap is always a track change (decided 2026-11-08). How it sounds follows its role: **source**
  music plays from a point inside the place (where its players would be), **lead** and **under** as a wide source
  spread across the open walls.
- **Cue**: a moment the music marks: a setting change, a mood or role change, a wordless frame, a marked entrance.
  A track enters on the tail of a line, never under its first word, at its bed level, and settles to a floor over
  about half a minute. No track runs more than about 90 s under continuous dialogue; after an exit the music holds
  silence long enough for the next entrance to land. Within a setting a switch is a crossfade (the setting's tracks
  share tempo, key and instruments); across settings it is a fade out, a breath of silence and an entrance. Never a
  cut, except a button.
- **Voice**: a character's designed voice on a voice **backend** (a stored voice id and sample in the cast), from a
  one-or-two-sentence description the reader writes; **lines** are the recorded balloons of an episode, each in its
  speaker's voice (`voices.py`). Two backends sit behind one seam, Inworld TTS-2 (default; ids under `id`, lines in
  `<episode>/audio/`) and Gemini 3.8 Flash TTS (`ZUMI_TTS=gemini`; `id_gemini`, `audio-gemini/`); each owns how a line
  is directed (a brief and a rate, or a short style and pace words).
- **Plan**: a box's flat layers before any pixels are drawn (`layers.plan`): the cards, their depths and the
  bubbles' placement. The erase reads the plan; `layers.render` draws it on the plate. Plan, erase and render are
  one module and one call (`layers.build`), since none of the three is used without the others.
- **Plate**: the box's art with what the cards hide painted in by the erase (`layers.erase_box`).
- **Scene / Layer**: the saved flat layers of a box as the reader gets them (`Box.scene()`, `cards.json` + PNGs).
- **Paid call**: any call to a paid API. All go through the shared daily cap (`spend.py`); a step's calls fan out
  through `spend.paid_map`, and an **offline run** (`spend.offline()`, `ZUMI_OFFLINE=1`) refuses every one.
