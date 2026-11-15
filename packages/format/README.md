# @zumi/format

The `.zumi` episode file: a zip with `manifest.json` at the root and assets referenced by relative path. Format
1.1.0 (2026-11-15).

```
manifest.json
cover.png                                series cover, 3:4
thumbnail.png                            episode thumbnail, 3:4
refs/<name>.png                          style reference images (snapshot)
episode/music/<trackId>.wav              instrumental loops (PCM); the score's envelope says which sounds when
episode/places/<setting>/front.glb       a place's painted view as a mesh, unlit
episode/places/<setting>/back.glb        the surface behind its near objects, unlit
episode/places/<setting>/props/<name>.glb  the place's props, lit
panels/
  <panelId>/                             one folder per panel; the reader streams one folder at a time
    scene.glb                            the panel's layers as textured surfaces and its camera, for renderMode "scene3d"
    layers/<layerId>.png                 flat images, for a panel without a scene
    voice/<bubbleId>.wav                 one clip per spoken bubble: 24 kHz mono 16-bit PCM
    depth/<layerId>.png                  reserved: per-layer relief
    panorama.jpg                         equirectangular 2:1, for renderMode "panorama"
    ambience.ogg                         reserved: one loop per panel (the pipeline writes none)
```

Panel, layer and bubble ids are `[a-z0-9_-]+` and double as file and folder names. Orb emote lines are not part of
an episode file; they ship with the app.

## Source of truth

`schema/zumi.schema.json` (JSON Schema 2020-12) is the contract: every field, its unit and the rule a reader
follows are stated in its descriptions, and nothing here overrides it. Four other things repeat it and are kept in
agreement with it by hand, in the same change:

- `validate.mjs`: the schema plus what a schema cannot check (below). The check that the copies agree.
- `csharp/ZumiManifest.cs` and `apps/xr/Assets/Zumi/Format/ZumiManifest.cs`: the C# mirror the Unity reader
  deserialises into (Newtonsoft.Json). The two files are byte-identical; edit one, copy it over the other.
- `pipeline/zumi/manifest.py`: the Pydantic mirror the pipeline's intake builds chapters with.
- `pipeline/segment/export_zumi.py` writes the manifest as plain dicts; its `FORMAT_VERSION` is the schema's.

Fixtures, all validated by `pnpm --filter @zumi/format validate`:

- `fixtures/sample-episode/manifest.json`: two hand-made panels (flat layers with bubbles and looping tracks; a
  panorama). Manifest only, no assets.
- `fixtures/scroll-episode/manifest.json`: a scroll layout. Manifest only.
- `fixtures/motion-episode/`: a whole unpacked episode of one synthetic two-frame panel (37 kB): a `scene.glb`
  written by the export's own writer with every node's extras, bubbles with `speakerCard` and `frame`, and the
  three accents as tracks, decided by the pipeline's motion rules (two pops, a cut, an impact with a pinned card).
  Made by `pipeline/.data/scratch/make_motion_fixture.py`.

`validate.mjs [target...]` takes a `.zumi`, an unpacked episode folder or a `manifest.json`. On any of them:
`formatVersion` (not newer than the schema; fields of 1.1 only in a 1.1 file), unique ids, speakers in the cast,
each bubble's `frame` among its panel's frames, the settings that frames, tracks, places and spans name, envelope
keys among the tracks, the places timeline, animation targets and timing. With the files as well: every path the
manifest names exists; `speakerCard`, animation targets and pinned cards resolve to nodes of the right `scene.glb`;
lettering nodes name a bubble; panel and place materials are unlit; no panel texture is over 2048 px; voices are
24 kHz mono 16-bit WAV.

## A panel's scene

A pipeline-made panel is `renderMode: "scene3d"`. Its `scene.glb` holds one node per layer, far to near, and the
panel's camera (`panel_camera` at the origin, looking down -z; the frames' windows are at distance 1). Materials
are unlit (`KHR_materials_unlit`): the art is already lit. No texture is over 2048 px on its long side; a larger
layer is resampled at export and the rest are packed as they were saved (on the 28-panel test episode: 35 of 153
textures resampled, the scenes 267.0 MB -> 246.0 MB).

Each node says what it is in its glTF `extras`:

| key | on | meaning |
|---|---|---|
| `kind` | every node | `window`, `backdrop`, `character`, `object` or `lettering` |
| `frame` | windows, backdrops, characters, objects | the frame of the panel (`frames[].index`); the reader clips these layers to the frame's window. Lettering has none and is never clipped |
| `card` | every node but windows | the layer's id in its panel, `card-<n>`: what `speakerCard` and an animation's `target` name |
| `cast` | characters | the cast member the card is (`cast[].id`) |
| `bubble` | lettering | the id of the bubble it draws; the reader shows the node from that bubble's `startTime` |

The lettering is drawn: each bubble is in the scene as a card cut from the original art, with its text also in the
manifest as data (`bubbles[].text`). A reader shows the card; it does not typeset the text. (The measured style of
each bubble was packed as `panels/<id>/bubbles.style.json` until 1.1. No reader opened it, and a reader that shows
the lettering cards needs none of it, so it is no longer shipped.)

A panel with a scene carries no flat image: its `layers` is empty and `panels/<id>/layers/base.png` is not packed.
The reader draws the scene alone since 2026-11-15, and that source image was 72.3 MB of the test episode's 386.8 MB.
A panel without a scene (`renderMode: "panel"`) still needs at least one layer.

## Bubbles and voices

- `kind`: `speech`, `thought`, `shout`, `caption` or `sfx` (a sound no character voices; until 1.1 it was written
  as `shout`).
- `speakerCard`: the card that says the line. `card-3` is a node of this panel's scene; `p006/card-1` is a card
  drawn in another panel (a voice carrying over from the box before or after), so nothing in this panel moves for
  it. With a `speakerId` and no `speakerCard` the cast member speaks from off-panel; with neither, nobody speaks
  (a caption, a sound effect).
- `speakerId`: the cast member that card is. `cast` lists everyone a character card is, speaking or not.
- `frame`: the frame the bubble belongs to and is timed in.
- `audio`: every bubble with a `speakerCard` and words has a clip. By rule these have none and are shown as timed
  text for their `durationHint`: sound effects, the narrator's captions, bubbles of marks alone ("...") and lines
  whose speaker is drawn nowhere. The pipeline does not export an episode in which a speaking line lacks its clip.
- Voice clips are WAV (PCM) because Unity cannot decode MP3 or Ogg from memory: a 44-byte header, then the samples.

## Time

One clock drives the episode: seconds from its start. `panels[].startTime/endTime`, `frames[].startOffset`,
`bubbles[].startTime/endTime` and `animations[].startTime` are all precomputed on it; a reader needs no pacing
logic of its own.

## Animations

Data from a fixed vocabulary, never code. The pipeline writes rule-based accents only, each one track that plays
once (`loop: false`) from its `startTime`:

| accent | when | track |
|---|---|---|
| pop | a speech line whose speaker changed | `scale` on the speaking card, 1 -> peak at 70 ms -> 1 by 450 ms, `easing: "out"` on each segment, `pivot` at the middle of the card's base |
| cut | the first shout of a run | `scale` on the speaking card, held 90 ms then back: `easing: "step"`, same pivot |
| impact | a stretch of sound effects | `shake` on `frame:<n>`, the content of the frame behind its window: 4 px at a 1200-px panel (`amplitude` is a share of the width), 13 Hz, dying out by 350 ms (`decay: 2`); `pin` lists the cards that touch a side of the window and may not be pulled away from it |

A `target` is a card (`card-3`), `frame:<n>` (every node of frame n but its window), or a layer id in a flat panel.
A shake on `frame:<n>` moves every layer of the frame by the same amount as seen from the panel's camera: a layer
farther back is shifted more in the scene, in proportion to its depth, so the frame's content moves as one picture
and no layer slides against another.
1.1 added `startTime`, `pivot`, the `step` easing, the `frame:<n>` target and the `shake` params `axis`, `decay`
and `pin`; the easing curves are now stated. What the pipeline writes, the reader shows.

## Music

- `episode.music[]` lists the tracks. Each file is a loop body in PCM WAV (a lossy codec's padding would open a
  seam).
- `episode.score.envelope` is the whole mix: per track, gain knots on the episode clock, linear between them. It
  already contains each role's level, the ducking under every voiced line, the entrances, crossfades and fades and
  the opening and closing of the place the track belongs to. **The reader multiplies and does not duck again.**
- Playback position: a track is audible while its gain is above 0.001. At clock time t it plays its file at
  `(t - origin) mod duration`, where the origin is the start of the audible span t lies in: the last knot at or
  before t that is silent and followed by a sounding one. So a seek lands where straight play would be, and a
  track that fell silent starts from its beginning when it comes back.
- `score.placement` says how it sits in the room: `wide` across the open walls, or `point`, from one point inside
  the place in the direction `yaw`, `pitch` (the pipeline writes straight ahead).
- `musicCue` on a panel and `music[].gain` are for hand-made files without a score. A file with a score ignores
  both; the pipeline writes no cue.

## Places and props

`episode.places.meshes[]` holds, per place, two unlit meshes in one frame (the seat's eye at the origin, +y up, the
view's centre down -z), the span of the view (`hDeg`, `vDeg`) and how far the place is in the meshes' own units
(`nearM`, `medianM`, `farM`: the 5th, 50th and 95th percentile of the distance from the eye). The meshes are in the
depth model's metres, not the room's. The reader puts the origin at the seat's eye, turns -z to the key wall and
scales both meshes by one factor so the place lies beyond the wall: with a wall D metres ahead,
`(D + 0.25) / nearM`. The schema states the whole rule (`$defs.place`), and what `light.key.yaw` is measured from.

`props[]` lists the objects of the place that stand in the room while it is open: the model's path, its real
`heightM`, the `surface` it rests on (`floor`, `table`, `shelf`) and its `bounds`. No positions: placing them is the
reader's job. A prop model is +y up and centred in a unit cube (its origin is its middle, not its base); the reader
scales it to `heightM` by its bounds and rests it on the surface. Its material is lit PBR (non-metal, rough,
single-sided, no normals), unlike the panels and places: the place's light is meant to fall on it.

## Layout

- `episode.layout.mode` is `scroll` or `carousel` (absent = carousel). Webtoon-born episodes default to `scroll`:
  the reader reassembles the original strip from the panels in order, using each panel's `strip` placement (`y`,
  `h`, `gutterAfter` in source pixels, `layout.width` wide) so the artist's gutters and scene gaps survive.
- `carousel` shows one card per panel; used for per-panel delivery and immersive frames.

## Rules

- Streaming: readers fetch `manifest.json` first, then assets per panel, prefetching one panel ahead.
- Version: `formatVersion` is semver; readers accept any `1.x`, ignoring unknown optional fields. 1.1 changed two
  things a 1.0 reader can trip on: the bubble kind `sfx` (a new enum value) and voices as `.wav` instead of `.mp3`.
