# Scene layers beyond characters and lettering: committee synthesis (2026-10-24)

Four research notes, read together:
[decomposition](scene-layers-decomposition-2026-10.md) (image-to-layers models),
[3D photo](scene-layers-3dphoto-2026-10.md) (single-image parallax systems),
[ordering](scene-layers-ordering-2026-10.md) (granularity, occlusion and support),
[comics](scene-layers-comics-2026-10.md) (illustration, anime, motion-comic practice).
Claims below are cited in those notes; the plan at the end is reasoning, not yet measured.

## Where the four agree

1. **Split at boundaries, not by values or names.** No 3D-photo system cuts by depth value. Meta's One Shot 3D
   Photography (Kopf 2020) cuts only where neighbouring pixels jump by more than 0.05 in normalised disparity, so a
   floor never splits. Our depth bands had no notion of neighbours. Naming elements (MuLAn: detector + SAM + depth)
   passed review on 36% of images, close to what our reviewer-picked version showed.
2. **Whole objects come from merging across continuous boundaries.** Two touching regions belong together when
   most of their shared edge has no depth jump: a cup and its table, the tiles of a floor. A table and the floor
   behind it stay apart (a jump along their edge). Fragments go to the neighbour with the longest shared edge;
   pieces under about 1% of the panel are merged or dropped.
3. **Granularity is a setting.** SAM returns three nested masks per point (whole, part, subpart). Our point grid
   kept the highest-scoring one, often a part (each floor tile). Keeping the largest gives the whole level;
   UnSAMv2 (Apache-2.0, on SAM 2) adds a continuous granularity knob.
4. **Order by occlusion first, depth second.** Median depth misorders overlapping pairs (WHDR 39.1 vs 10.8 on
   separated pairs). At each shared edge the side with the depth jump toward the viewer is in front. A VLM is a
   poor occlusion judge (zero-shot F1 34 vs about 81 for expert models).
5. **Few layers, split by what blocks the characters.** Segment-based systems end with 2-4 layers; anime
   production uses a main background plate plus "Book" pieces for background parts that pass in front of a
   character. ComiXR (Quest Pro study) found immersion came from characters and bubbles at their own depths.
6. **One depth per cut-out from contact or a high percentile, never the mean**, and the room shell (floor, walls,
   sky) as one opaque back layer, optionally with its own depth map (the .zumi format reserves one).
7. **Image-to-layers models are not the main path yet.** Qwen-Image-Layered (Apache-2.0, 20B) is the only released
   general model: too large for 12 GB without offload, trained on design files (editing layers, not depth), never
   tested on comics. Worth one upper-bound test on about 10 panels.

## Plan proposed for Zumi (local, no API cost)

| Step | What | Source of the idea |
|---|---|---|
| 1. Regions | SAM 3.1 point grid on the scene, keep the LARGEST of the 3 masks per point, drop under 1% | ordering note (granularity) |
| 2. Merge | Join touching regions whose shared edge has no depth jump (disparity jump < 0.05 along most of it); fragments to the longest-edge neighbour | 3D photo note (Kopf), ordering note |
| 3. Roles | Back plate = the merged region(s) behind everything (the shell); "Book" pieces = regions with a depth jump toward the viewer along an edge shared with a character | comics note (anime practice) |
| 4. Order | Occlusion at shared edges first, depth (75th percentile or contact) second; cap at 3-5 scene layers | ordering note, 3D photo note |
| 5. Evaluate | Hand-label about 30 panels; report order errors separately for touching and separated pairs | ordering note |

Risks named by the notes: every ordering and support model was trained on photographs; depth may jump at ink
lines rather than object edges; painted gradients and screentone break flat-colour tricks; abstract or effect
backgrounds have no objects (fall back to one back plate); holes behind layers still need inpainting.
