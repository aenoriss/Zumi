# @zumi/format

The `.zumi` episode file: a zip with `manifest.json` at the root and assets referenced by relative path.

```
manifest.json
cover.png                      series cover, 3:4
thumbnail.png                  episode thumbnail, 3:4
refs/<name>.png                style reference images (snapshot)
episode/music/<trackId>.ogg    instrumental tracks; the first plays from panel 0, panels switch with musicCue
panels/
  <panelId>/                   one folder per panel; the reader streams one folder at a time
    layers/<layerId>.png       RGBA cut-outs at panel size, holes inpainted into the layer below
    depth/<layerId>.png        reserved: per-layer relief
    panorama.jpg               equirectangular 2:1, for renderMode "panorama"
    scene.glb                  Blender export, for renderMode "scene3d"
    voice/<bubbleId>.ogg       one clip per bubble
    ambience.ogg               one loop per panel
```

Panel, layer and bubble ids are `[a-z0-9_-]+` and double as file and folder names. Orb emote lines are not part of an episode file; they ship with the app.

- `schema/zumi.schema.json`: JSON Schema 2020-12 for the manifest. The only normative definition.
- `csharp/ZumiManifest.cs`: hand-kept C# mirror for Unity, plus the pacing rule (`Pacing.Duration`). Copy into `apps/xr/Assets/Zumi/Format/` (a sync script will replace the copy later).
- `fixtures/sample-episode/manifest.json`: a two-panel manifest (one flat panel with layers, bubbles and animations; one panorama) used by the validator and the Unity reader's tests. Asset files are not included; the reader must tolerate missing assets in fixtures.
- `validate.mjs`: `pnpm --filter @zumi/format validate [paths...]` validates against the schema and checks cross-references (speakers, layer targets, unique ids).

Music
- `episode.music[]` lists the tracks (file, loop, gain, optional seamless loop region). Music is a continuous bed; it never restarts per panel.
- A panel's `musicCue` switches tracks when that panel appears: `crossfade` (equal-power overlap, default 2.5 s), `fadeOutIn` (a silence gap), or `cut` for hard scene breaks; `track: "none"` fades out. The reader prefetches the cued track with the panel.
- The reader ducks music under voice lines (about -6 dB while a bubble plays) and keeps ambience under both.

Rules
- Streaming: readers fetch `manifest.json` first, then assets per panel, prefetching one panel ahead.
- Text is data: bubbles are never baked into images. Animations and interactions are data from a fixed vocabulary, never code.
- Depth: `layer.depth` 0..1 plus `panel.depthScale` (metres) lets the XR app tune comfort without changing files.
- Version: `formatVersion` is semver; readers accept any `1.x`, ignoring unknown optional fields.
