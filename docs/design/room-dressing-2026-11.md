# Room dressing: the setting dresses the reader's room (v7, 2026-11-07)

Status: accepted for the first slice; the agentic loop closed at 9/10 from both the immersive-theatre director and the Quest
engineer. v1 and v2 scored 5/10 from four lenses (MR experience, production design,
narrative, systems); v3 7/10 from a creative director; v4 8/10 from a confirmation judge; v5 6/10 from an immersive-theatre
director and 5/10 from a Quest engineer; v6 7/10 from both (the candle no longer follows the music, the sign, key and
lanterns are gone, the light falls on a relit proxy; but the 40° sightline measured in pitch refused the coffee table
itself, the floor-beside-the-seat fallback sat 90° off axis, the turn dimmed the flame before the silence, the grade used two
colour maps at once, the clock froze while a panel was read, and the breath was too small to see). v7 answers those.
Decisions so far: `CONTEXT.md` (Setting, Span, Mood, Role, Cue, Dressing), `docs/architecture/decisions.md` § 4 step 8
amendment. Test scene: `pipeline/.data/out/set_preview/`.

## 1. What it is

The reader sits in their own room in passthrough and reads the panels on the key wall. When the episode enters a
**setting**, the room becomes that place through one light that belongs to the story and one or two still silhouettes that
name the place. The light is a character: it keeps the story's time, it departs from that time only on the beats the story
marks, and once, it needs the reader. The panels remain the focus; the room is where the eyes rest between them.

## 2. Principles

1. **Light is the instrument; one prop carries it.** A set is its hero light (carrier, spot, colour, level), a grade of the
   passthrough image standing in for the place's fill, and one or two still silhouettes that say where we are. Scatter is
   0 to 4 small pieces and the first thing cut.
2. **The light keeps the clock and departs from it only on marked beats.** Inside its setting the hero's level is the clock
   alone (the candle burns down). It departs on two marked beats only: a `lie` and the `turn`. It never follows the music's
   role or mood, never reacts to a shout, never changes before a line lands: a marked beat starts on the next balloon after
   the mark, or at the start of the silence it needs, so the room answers and never announces. Nothing ever flashes or
   reacts with motion.
3. **The hero keeps the clock.** The candle burns from full at its setting's first frame to a stub at its last, linear in
   episode time: the real minutes become the story's night.
4. **A prop may be a lie, and a lie lands where the reader looks.** Objects can exist only as the story claims them: the axe
   of Pepper's tale lies on the table while she tells it, solid, its shadow thrown by the candle, and it is gone on the
   balloon after the claim fails, so the room's double take lands after the joke, never on it. (The reviewers' version was
   a shadow cast by nothing; the user judged a shadow without an object a cheat, 2026-11-07, and the lie is a solid prop.) A
   lie lies on the hero's own surface, in the candle's light; the hero therefore sits within 40° in yaw of the panel axis
   (§ 3), below the panels, where a change is seen at the edge of the reader's view. With no hero surface the beat changes
   only the light.
5. **Once, the reader is needed, and they already know how.** In the first-use setup the reader lights the candle themselves
   ("pinch to light your candle where you want it"): that one gesture places the hero and teaches the relight. The reader's
   flame is never taken back: it burns as a low ember through the settings that are not its own and rises to a flame when its
   setting arrives. At the one `turn` the story asks for courage, the flame dies to almost nothing at the start of a silence
   of at least 4 s (the export holds the turn's panel when the voices give no such silence), and the silence is the grace.
   If the reader does nothing, the first brave word after it relights the flame. The story never waits; the reader is
   offered a part, not a task. Lies and turns are not invented by the dressing pass: the music reviewer marks them as spans,
   like buttons, and the dressing stages only marked beats.
6. **One arrival, quiet exits, and the candle says goodbye.** The hero's setting arrives as the ember rises to a flame over
   2 s on the sound effect or line just before its first panel; every other setting changes only the grade, over 3 s. After
   the credits the reader's candle, burned to its stub, rises from ember to flame and stays lit until the reader leaves.
7. **Still while reading.** No prop moves while a panel is read; motion lives in the grade's transitions and in the flame's
   flicker (under 10 %). Nothing overhead, nothing floating. Reduced motion removes the flicker.
8. **The room keeps its owner.** Nothing on the key wall, within 60 cm of the head, in the seat or on the walked floor;
   every prop rests on a real surface with a contact shadow. One gesture dismisses a prop for good; a palm-menu level sets
   Full / Quiet / Off. The hero is the last thing Quiet keeps.
9. **Merit by weight, reuse before adding.** A set for dialogue or 20 s and more; a grade alone for a passing shot; an
   imagined place inside a real one changes only the light. A series shares a prop pool; a new setting adds one or two props.

## 3. The slot grammar and the room's reality

| Slot | How it is placed | What goes there | Count |
|---|---|---|---|
| hero (light carrier) | the reader aims and pinches in setup; live depth (`EnvironmentRaycastManager.PlaceBox`) accepts a flat, clutter-free, large-enough spot that lies inside the top of a TABLE, STORAGE or FLOOR anchor and within 40° in yaw of the panel axis; the TABLE nearest the seat is suggested; the fallback is the floor ahead at the foot of the key wall, off the walked line; else no hero | the object that carries the set's light | 1 |
| hero surface | the anchor under the hero | a relit proxy of the real surface (§ 4) that the hero light and the lie's shadow fall on | 1 |
| silhouette | FLOOR against a wall, or a free WALL_FACE, within the same yaw | still shapes that name the place | 1 to 2 |
| scatter | the hero's surface | small pieces around the hero | 0 to 4 |
| grade | whole passthrough image | one colour LUT per setting with its brightness baked in (§ 4) | 1 |

Placement is against the room as it is today: a ghost of the candle follows the reader's aim across live depth, upright
(its up axis is the surface normal, not PlaceBox's forward), spots that fail the test are shown as a refused ghost, and the
pinch confirms. MRUK labels are hints, depth is truth, and "no valid spot" is a normal outcome. The spot is stored in its
anchor's frame keyed by that anchor's UUID (anchors persist until Space Setup is re-run, when everything changes together).
At load, depth stays on until the spot is in view, then PlaceBox re-checks it and the hit height is compared with the stored
one (± 3 cm); on a miss the setup asks again. Height and reach are settings so standing, seated and wheelchair readers get
the hero in comfortable sight and reach. In multiplayer only the setting state is shared (setting id and clock); each
headset fills its own room.

## 4. What the headset can actually do (and the fallbacks)

- **Light on the real room**: a Unity light shades only virtual meshes; passthrough is an underlay blended by the eye
  buffer's alpha, so a point light alone leaves the real table unlit and the candle reads as a sticker. The hero light
  therefore falls on a **relit proxy**: the surface anchor's EffectMesh drawn with MRUK's `HighlightsAndShadows` shader
  (`Blend One OneMinusSrcAlpha`), which brightens the camera image inside the anchor's rectangle; the pool of light stays
  inside it. Darkening comes only from alpha decals on the same proxy: the blob under each prop, and the axe's shadow as a
  decal shaped from the candle's direction. No shadow maps anywhere.
- **Grade**: the passthrough layer holds one colour map at a time (brightness/contrast/saturation, or a LUT), so a setting's
  grade is one LUT with its brightness change baked in, applied with a weight; a setting change is `SetColorLut(from, to,
  weight)` over 3 s. The weight is not a perceptual unit (my estimate, unmeasured: a 10 to 15 % warm weight is adapted away
  within a minute), so each setting names a target judged on the headset: the tavern's LUT lowers brightness by 25 to 40 %
  and warms, so the flame reads brighter than the wall; the sky's LUT cools at unchanged brightness. Fallback: no grade,
  the hero light alone.
- **Occlusion**: during setup and the load re-check, live depth; during reading, the scene mesh as a depth-only mask; at the
  relight, the tracked hand mesh occludes the flame. Props rest on surfaces, so a missing occlusion rarely breaks the
  illusion.
- **Nothing computed on the headset**: the hero's level is a 10 Hz curve baked into the `.zumi` per setting (`hero.level[]`)
  from the clock and the marked beats. The reader's clock is the current panel's `startTime` plus the time since that panel
  appeared, clamped to its `endTime`, so the curve plays while a panel is read; the level is the curve interpolated at that
  clock. Testable in the editor behind a placement seam (§ 8).

## 5. The plan for Pepper&Carrot 39

| Setting | On screen | Set | Light and grade | Silhouettes |
|---|---|---|---|---|
| Sky above the clouds | 20 s, opener | grade only | cool LUT, brightness unchanged, over 3 s as the first panel appears; the reader's candle is a low ember; a cloud-edge shadow passes once across the hero surface during the opener's first panel change (`pass_shadow`, so it moves in a transition and shows early where the room speaks) | none |
| Tavern courtyard | 3.5 s | nothing | the grade begins to warm | |
| Upstairs hall | 3.3 s | nothing | | |
| Tavern main room | 276 s, all dialogue | full | the candle in a bottle, 2200 K, the night's clock; warm LUT, brightness −25 to −40 %; the ember rises to a flame over 2 s on the door's first sfx (`lerp_light`) | the big tilted tankard, still; three dice as scatter beside the candle |
| The tale (bard) | `lie` span inside the tavern | a lie | the axe of legend lies on the table behind the candle (`appear` on the balloon after Pepper's first line of the tale), its shadow toward the reader | |
| Exposure | end of the `lie` | | the axe is gone on the balloon after the chief's dismissal | |
| The confession | span | nothing | the candle is simply low by now | |
| Courage | `turn` beat | the reader's turn | the flame dies to almost nothing at the start of a silence of at least 4 s; a pinch near it relights it, else Pepper's first brave word after the silence does | |
| Imagined vision | 45 s inside the tavern | grade only | cool teal LUT over 3 s; the candle holds its clock | |
| Apology | span | nothing | the grade eases back to the tavern's one balloon after the warriors leave | |
| Terrace at night | 2.7 s, closing | grade only | moon-cool LUT | |
| Title, credits | 29 s | the gift | the candle's stub rises from ember to flame and stays lit until the reader leaves | |

Cut from v1: bread, coins, barrel, stool, herbs (kept in the pool for other tavern settings). Cut in v6: the courtyard sign,
the key, the terrace lanterns. Cut in v7: the held breath (a pause of a flicker under 10 %, below the panels, during a
punchline, would not be seen; the axe's shadow vanishing is the exposure the reader can see). New props: the axe (modelled
2026-11-07, `set_preview/props/axe.glb`, 56 cm, bearded head); still to model: the candle in a bottle (a variant of the candle).

## 6. The hero light's rules

Baked offline into `hero.level[]`: the ember (0.2) outside the hero's own setting; inside it the clock, from 1.0 at the
setting's first frame to 0.15 at its last, linear in episode time, with a 2 s rise from the ember at the arrival. Departures
on marked beats only: `turn` drops the level to 0.05 over 1 s at the start of the nearest silence of at least 4 s (the export
inserts a hold at the turn's panel when the voices have none) and fires a `relight` event; the level returns to the clock
over 1 s at the relight. A `lie` changes the light only through what it casts (the shadow decal), not the level. Colour is a
property of the carrier (the candle: 2200 K) and never changes with mood. In reduced motion the flicker is off and the level
still follows.

## 7. Pipeline and data

The settings step names the places and frames; the music reviewer names spans, moods, roles and buttons, and now also the
story's `lie` spans (a thing a character claims that the room may show as untrue) and its one `turn` (the beat that earns the
reader's part). A **dressing pass** (one text-only Sonnet call per episode) fills the grammar from those marks and the prop
pool, stages only marked beats, and writes `settings/dressing.json`, validated against a JSON schema:

```
set: { setting, verdict, hero: { prop, kelvin }?,
       silhouettes: [{ prop, anchor_chain[] }], scatter: [{ prop }],
       grade: { lut, weight },
       arrival: { verb ∈ { lerp_light, appear, pass_shadow }, anchor: sfx id | bubble id | frame id (+ offset) }?,
       beats: [{ span, kind ∈ { lie, turn }, prop_appear?, prop_vanish? }],
       sightline: { max_yaw_deg_from_panel_axis: 40 } }
```

Any unknown verb falls back to a 1.5 s fade. The `.zumi` carries `episode/props/<id>.glb`, `settings[].dressing` and the
baked `hero.level[]`. The Unity reader: PlaceBox setup, the anchor-frame memory with the height re-check, the relit proxy
with blob and lie decals, one point light, one passthrough LUT per setting, fades on the settings' frame times, the clock
from the panel's `startTime` plus time on the panel.

Pepper&Carrot is internal R&D only (its author bans AI derivations), so this plan is the design's test case, not its
showcase: the dressing pass is tested blind on the team's own comic, where the reviewer must find that episode's lies and
turn on its own. The blind test passes when those marks agree with two of three of the team's own readings of the episode,
made before seeing the pipeline's.

## 8. First slice and build order

1. **One tavern candle, lit by the reader.** Behind a placement seam (PlaceBox on device; in the editor a raycast against a
   separate "real room" layer loaded from a JSON room with stable anchor UUIDs, plus a synthetic clutter box): the setup
   ghost, the refused spot, the pinch, the anchor-frame memory with the height re-check, the blob decal, the relit proxy,
   and the level from a baked curve read at the panel clock (an ember until the tavern's first frame). The reader has no
   episode clock yet (panels advance by swipe) and SmithXR has no Zumi profile; both are part of this slice. Asserted in
   SmithXR with the synthetic room and hand: a ray pinch on the room's table puts the candle upright on its top within 2 cm
   (control: a pinch on the clutter box is refused); a room without a TABLE uses the floor at the foot of the key wall,
   within 40° in yaw, clear of the walked line and 60 cm of the head; a replay restores the pose within 1 cm (controls: a
   different room JSON makes the setup ask again; the real-room table lowered 10 cm with its anchor left alone makes it ask
   again, lowered 2 cm restores the pose); the level before flicker equals the curve interpolated at the clock, 0.2 before
   the tavern, advancing while a panel is read and still right after a seek (control: during the 2 s arrival rise, where the
   curve moves 0.04 per sample, a curve shifted by one sample fails; the burn-down moves 0.0003 per sample and cannot carry
   this control). The look (the relit proxy and the grade) is judged once on the headset. Before the replay block is
   written, log the JSON room's anchor UUIDs across two Play sessions to confirm MRUK's loader keeps them; switching
   `ZumiMR.unity` from prefab rooms to the JSON room is part of the slice. The relight at the floor fallback, 2 m or more
   from the seat, is a ray pinch (slice 3).
2. The marked-beat rule on the real spans of Pepper&Carrot 39.
3. The candle clock, the turn's hold in the export, and the reader's relight.
4. The arrival (`lerp_light`), `pass_shadow`, and the axe's shadow decal.
5. The dressing pass prompt and schema. A three.js preview of the whole plan already exists
   (`pipeline/.data/out/set_preview/index.html`, 2026-11-07): it plays the episode's timeline with voices and the music
   envelope, the panels on the key wall, the pinch-to-light setup with its refused spots and remembered spot, the ember,
   the arrival, the clock, the lie's shadow, the turn's relight and the gift, reading the plan from `settings/dressing.json`.
   The room GLB stands in for passthrough and the grade is applied to the room's light, so the look of the relit proxy and
   the grade is still the headset's to judge.

## 9. Open questions

- Does the relight belong to every episode or only where a story earns it? (Proposal: the dressing pass may use it at most
  once per episode, and only on a span the reviewer marked as the turn.)
- Should a dismissed hero still keep the clock (a light with no carrier)?
- How dark may the tavern grade go before the reader's own room stops feeling like theirs? To be set on the headset.
- Is a flame at level 0.05 noticed 37° to 47° below the gaze (a coffee table from a seat; Quest 3's lower view reaches about
  48°, geometry from the published field of view, not measured)? If it is missed in the first slice, add a pitch cap.
- Do readers swipe through the turn's 4 s silent hold? A silent panel reads as a cue to advance; to be watched in the slice.
