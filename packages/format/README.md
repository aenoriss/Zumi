# @zumi/format

The `.zumi` episode file: a zip with `manifest.json` at the root and assets referenced by relative path.

```
manifest.json
layers/<panel>-<layer>.png     RGBA cut-outs at panel size, holes inpainted
panoramas/<panel>.jpg          equirectangular, for renderMode "panorama"
scenes/<panel>.glb             Blender export, for renderMode "scene3d"
audio/voice/<panel>-<bubble>.ogg
audio/ambience/<panel>.ogg
audio/music/<episode>.ogg
audio/emotes/<id>.ogg          orb emote lines (shared, not per episode; reserved)
thumbs/
refs/                          style reference images (snapshot)
```

- `schema/zumi.schema.json`: JSON Schema 2020-12 for the manifest. The only normative definition.
- `csharp/ZumiManifest.cs`: hand-kept C# mirror for Unity, plus the pacing rule (`Pacing.Duration`). Copy into `apps/xr/Assets/Zumi/Format/` (a sync script will replace the copy later).
- `fixtures/sample-episode/manifest.json`: a two-panel manifest (one flat panel with layers, bubbles and animations; one panorama) used by the validator and the Unity reader's tests. Asset files are not included; the reader must tolerate missing assets in fixtures.
- `validate.mjs`: `pnpm --filter @zumi/format validate [paths...]` validates against the schema and checks cross-references (speakers, layer targets, unique ids).

Rules
- Streaming: readers fetch `manifest.json` first, then assets per panel, prefetching one panel ahead.
- Text is data: bubbles are never baked into images. Animations and interactions are data from a fixed vocabulary, never code.
- Depth: `layer.depth` 0..1 plus `panel.depthScale` (metres) lets the XR app tune comfort without changing files.
- Version: `formatVersion` is semver; readers accept any `1.x`, ignoring unknown optional fields.
