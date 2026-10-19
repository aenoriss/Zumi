# Zumi: shared understanding

Status: CONFIRMED 2026-10-15. This is the core reference document; later decisions amend it. Deadline: Meta VR developer competition, ~2026-11-14.
Team: one engineer (AI-assisted build) + one comic artist supplying source material.

Zumi turns rough comic sketches into interactive, parallaxed, voiced, animated XR comics that people read together on Meta Quest 3.
Demo thesis: **"Read comics together in XR."** Presence and sync are first-class, not stretch.

Research backing the model choices: `docs/research/*.md`.

## 0. Non-negotiable rule

Always prioritise Meta models and Meta platform features. Non-Meta only where Meta has nothing, and every such pick is named and justified. As of 2026-10-15 the Meta stack is: Muse Image (generation), Muse Glimmer 30B (open LLM), SAM 3.1 (segmentation), Muse Wonder/Spark (vision, modality to be verified), Meta XR SDK, Meta Platform SDK.
Documented non-Meta picks: depth, inpainting, TTS, ambient audio, 360 panoramas, networking transport.

## 0b. Audience

Primary: daily webtoon readers, 14-30, often male, geek/otaku, large Asian share. Secondary: comic artists using the web tool; competition judges. Brand must feel native to the webtoon habit (see `docs/research/webtoon-platforms-design-2026-10.md`).

## 1. Product hierarchy

- **Author** = web account (Supabase Auth). Profile, display name.
- **Comic** = series. Title, cover, description, style definition (preset + text + reference images), cast list with voices. Shared by all chapters.
- **Chapter** = one release = one `.zumi` file. Panels, audio, scenes, animations. Own publish date. Multiplayer rooms are matchmade per chapter.
- Cast and style are owned by the comic in Postgres and snapshotted into each chapter file at publish.

## 2. XR app (Unity 6000.4.x, Quest 3 only)

| Decision | Choice |
|---|---|
| Runtime | Native OpenXR Android build for Meta Quest 3. No WebGL. |
| SDKs | Meta XR All-in-One SDK (Core, Interaction, Platform, Audio). URP. |
| Space | Mixed reality by default (passthrough). Individual frames may switch to full VR. |
| Input | Hand tracking only. Pinch + ray, radial menus from Interaction SDK. |
| Layout | Carousel: current panel in front at reading distance, previous/next as small faded cards to the sides. |
| Parallax | Discrete RGBA cut-out layers at fixed Z (paper cut-out look). No depth mesh in v1; format reserves an optional per-layer depth map. |
| Full-VR frames | Two tiers: `panorama` (360 equirect, standard) and `scene3d` (glb built by the Blender agent, premium). Both MVP. |
| Animation | Declarative animation tracks per layer, played by the XR app (see section 4, step 9). |
| Pacing | Automated. Per-panel duration = sum of TTS clips + 1.5 s per bubble, min 3 s; immersive frames default 20 s; never shorter than the panel's longest animation. Author can override. |
| Pause | Voting module: majority pauses, majority resumes. Module is generic for later uses (branches, skip). |
| Library | Public in-app library: comics, then chapters, each showing "N reading now". No Zumi account in headset; Meta identity for presence. |
| Rooms | Auto-matchmaking per chapter: join fullest non-full room (cap 8), else new room at panel 1. Meta Group Presence + Destinations for friend invites and "join friend" from Quest home. |
| Sync | Shared current panel index, authoritative in Photon Fusion Shared Mode; late joiners jump to room panel; next panel prefetched. |
| Presence | Readers are glowing orb characters placed around the room. Voice chat via Photon Voice. |
| Emotes | Hearthstone-style fixed preset lines per orb from a radial menu, shown as comic bubbles and played as pre-generated TTS. No free text, no live STT, no moderation needed. |
| Chapter end | End card with two buttons per reader: continue to next chapter with the room, or leave to library. |
| Audio | Voice clips, ambience and music spatialised/mixed at playback with Meta XR Audio SDK. |
| Transport | Photon Fusion (Shared Mode) + Photon Voice. Meta's own samples pair Platform SDK with Photon; Meta deprecated its own P2P/Rooms APIs. |

## 3. File format: `.zumi`

Zip container, JSON manifest, versioned (`formatVersion`). Designed to stream: the XR app reads `manifest.json` first and fetches assets lazily per panel.

```
manifest.json          comicId, chapterIndex, language, cast (snapshot), style (snapshot), panels[]
panels[i]              renderMode: panel | panorama | scene3d; durationOverride?; depthScale; layers[]; bubbles[]; animations[]; ambience; music?; interactions[] (post-MVP)
layers[j]              png path, depth 0..1, band, bbox, interactive? (post-MVP); optional depthMap reserved
bubbles[k]             text, speakerId, anchor, position, audio path, startOffset
animations[m]          targetLayer, track type (translate | rotate | scale | opacity | sway | shake | sprite-cycle), keyframes or params, duration, loop, delay, easing
layers/*.png           RGBA cut-outs, holes inpainted
panoramas/*.jpg        equirect for panorama frames
scenes/*.glb           Blender-exported scenes for scene3d frames
audio/voice/*.ogg      one clip per bubble
audio/ambience/*.ogg   one loop per panel
audio/music/*.ogg      per-scene or per-chapter instrumental tracks
thumbs/
```
Single source of truth: `packages/format` (JSON Schema) generating TypeScript and C# types. Text is data, never baked into images. Depth per layer stored normalised plus a per-panel depth scale so XR can tune comfort without touching files. Animations are data (a fixed track vocabulary), never code.

## 4. AI pipeline (Python on Modal, per-panel fan-out)

Order per panel:
1. **Understand** (one pass, strong Meta vision model, Muse Wonder/Spark to verify; fallback Gemini 3.8 Flash): structured JSON with scene description, objects, dialog text + bubble boxes + speaker guesses, mood, Blender brief. Cast list and style guide injected for name consistency.
2. **Remove dialog**: mask bubble boxes from the sketch, "no text" instruction, then a fast-model check pass that inpaints any leftover lettering in the finished art. Amendment 2026-10-19: masks come from SAM 3.1 run locally (speech bubbles and caption boxes, text prompts plus exemplar boxes; `pipeline/segment`). Only dialogue is removed; sound effects drawn on the art stay part of the art.
3. **Regenerate**: Muse Image with the sketch as the structural edit/reference input; description used only as nudge; style from preset + text + reference images. Routed through OpenRouter `/api/v1/images` so models swap by string. Week-1 A/B: Muse Image vs gpt-image-2.5 vs Nano Banana 2.1 on the artist's sketches; Muse default if it holds. Seedream 5.0 Pro as fourth if structural fidelity disappoints. Self-host fallback: FLUX.2 klein 4B.
4. **Segment**: SAM 3.1 (Meta API, text-prompted) into cut-outs, grouped into depth bands. Author can merge in editor (no split, no mask painting in MVP).
5. **Inpaint** behind cut-outs: LaMa (Apache 2.0) on Modal.
6. **Depth**: Depth Anything 3 (Apache 2.0), averaged per mask, quantised to band. Meta has no open depth model.
7. **Voices**: cast confirmed once per comic; author picks or describes a voice. Engine: Gemini 3.8 Flash TTS default (voice design from text, persistent voice ID, ~$0.81/h; price doubles 2027-01-01). A/B ElevenLabs v4 Turbo if designed voices drift across lines. Open fallback Qwen3-TTS 1.7B VoiceDesign on Modal. Same engine produces orb emote lines.
8. **Ambience and music** (split): ElevenLabs Sound Effects v2 with `loop: true` for one 10-30 s diegetic ambience loop per panel (rain, sirens, crowd; ~$1.20 per 30 panels), prompted from the panel mood. Google Lyria 3 Clip for instrumental music, one 30 s clip per scene or chapter, cropped and crossfaded (no loop flag; ~$0.04 per clip). Lyria is music-only and cannot produce sound effects. Open fallback on Modal: Stable Audio 3 Small SFX + ACE-Step 1.5.
9. **Animation**: author writes a plain-language instruction per panel ("rain falls, the cape sways, the sign flickers"). Muse Glimmer maps it to animation tracks from the fixed vocabulary over the panel's named layers, with durations and loops. Author previews in the 2D web preview and can regenerate or clear. No code is generated; the XR app only plays tracks it knows.
10. **Panorama frames**: generator TBD at build (Muse Image with equirect prompting first; fal 360 model fallback).
11. **3D scene frames**: Muse Glimmer drives headless Blender through MCP in a Modal container (primitives, curated low-poly library, materials, lights, panel cut-outs placed inside). Export `.glb`, loaded by glTFast. Tool-call cap per scene.
12. **Pack**: `.zumi` built, uploaded to Supabase Storage.

Controls: per-episode budget cap ($10 default; a 10-page episode is ~$6), per-step retry limit 2, Blender agent tool-call cap.

Execution and monitoring (decided 2026-10-17): the pipeline is a Python CLI (`pipeline/`) whose steps run remotely as Modal functions; progress, per-panel artefacts (regenerated image, cut-outs, voice clips, timings, cost) and errors are reported to **Weights & Biases** (one W&B run per episode, one step per panel) so the episode can be watched coming together in the browser. No Postgres job table and no web editor: the CLI packs the `.zumi` and uploads it to Supabase Storage at the end.

Interactive elements (touch triggers, fixed action enum, AI-suggested never auto-applied, no scripting) are post-MVP; the format reserves the fields.

## 5. Web app: DESCOPED 2026-10-17

The creation platform (web editor, creator accounts, portal, Elysia API, Render) is out of the MVP. The competition deliverable is the XR app. The pipeline runs as a command-line tool, operated by us, on the artist's comic to produce the demo episodes. Episodes are uploaded to Supabase Storage by the same tool; the XR app reads a public manifest from there.

The only web surface is `apps/landing`: a single static "coming soon" page with the Zumi mark and the official "Available on Meta Quest" store badge (asset from Meta's brand resources, linked to the Horizon Store listing once it exists). Static HTML on the token CSS, hosted on Vercel or GitHub Pages.

`apps/web`, `packages/ui` and the web-only skills were removed on 2026-10-17 (history: commits 0fd1c89, 94ea37e). `packages/design-tokens` stays: its USS and C# outputs feed the Unity UI and the CSS feeds the landing.

## 6. Repo layout (monorepo)

```
apps/xr/                 Unity 6 project (Git LFS for binaries, strict .gitignore)   <- the product
pipeline/                Python CLI + Modal functions: sketches -> .zumi episode -> upload
packages/format/         .zumi JSON Schema -> C# types (and TS for the pipeline's validator)
packages/design-tokens/  tokens JSON (colour, type, space, radius, motion) -> USS + C# for Unity; CSS kept for any future web surface
```

All frontend was removed on 2026-10-17 (apps/web, packages/ui, apps/landing; history in commits 0fd1c89, 94ea37e, a53f611). The design system survives as the token package plus `docs/design/brief.md`; web surfaces return only when the XR app is done.

```
docs/                    research, architecture, format spec
```

## 7. Dev loop

Unity Play mode with Quest Link daily; device builds occasionally over adb. Multiplayer tested with a second editor instance (ParrelSync) or device + editor.

## 8. Accounts and keys to create (none exist yet)

1. Meta developer org + app ID in the Horizon dashboard (Platform SDK, Group Presence, Destinations, store upload).
2. Meta Model API key (Muse Image, SAM 3.1, Glimmer, vision).
3. OpenRouter key (image A/B).
4. Google AI Studio key (Gemini TTS, Lyria 3, vision fallback).
5. ElevenLabs key (Sound Effects v2 ambience; TTS A/B).
6. Photon: Fusion app ID + Voice app ID.
7. Supabase project (Storage + one Postgres table for the episode manifest; no Auth).
8. Modal account + token.
9. Vercel project or GitHub Pages for the landing only. Meta Quest store badge from Meta's brand resources page.

All keys go in untracked `.env` files and are never committed.

## 9. Post-MVP backlog

Interactive elements and AI suggestions; translation tracks; audience-triggerable hooks; scripting; Pico/Android XR; WebGL target; layer split and mask painting; co-location; richer animation (sprite-sheet generation).

## 10. Open items

- Verify which Meta API model accepts images (Muse Wonder vs Spark) and Muse Glimmer's multimodality.
- Panorama generator choice (step 10).
- Brand/design system: brief locked in `docs/design/brief.md`. Tokens: W3C DTCG JSON in `packages/design-tokens` -> Style Dictionary -> USS + C# (CSS kept). The design system now lives in the XR space itself (midnight library lighting, orbs, paper panels) and in headset panels built on Meta's UI Set (uGUI Canvas + TextMeshPro prefabs with Theme ScriptableObjects), with the DTCG tokens exported to C# theme values. Unity UI Toolkit in world space is still pre-release (no ray input, no Meta ISDK path) so it is not used for headset panels; the USS export stays for editor tooling only. Screens are designed by the user in Pencil and copied into code by Claude (see `docs/design/brief.md`, "Screen design"). impeccable was tried on 2026-10-17 and removed the same day. Research: `docs/research/design-quality-tooling-2026-10.md`, `docs/research/pencil-claude-collab-2026-10.md`.

## 11. Build order after the descope (2026-10-17)

1. `packages/format`: `.zumi` schema + C# types, and a hand-built sample episode from 3 to 5 of the artist's panels (cut-outs made manually if needed) so Unity work never waits on the pipeline.
2. `apps/xr`: Unity 6 + Meta XR SDK. Passthrough room, `.zumi` streaming from Supabase, carousel of paper panels with parallax layers, voices + ambience, automated pacing. Single reader first.
3. Multiplayer: Photon Fusion rooms with the shared panel index, Zumi orbs, emotes, pause vote, Meta Group Presence invites.
4. `pipeline/`: Muse Image A/B, SAM 3.1 cut-outs, depth, inpainting, voices, ambience, animation tracks, Blender scenes, packer, uploader. Produces the real demo episodes.
5. Immersive frames (panorama, 3D scene) in Unity once the pipeline emits them.
6. Trailer, `apps/landing` coming-soon page, store submission.

Amendment 2026-10-18: the pipeline comes first and is built step by step (each step approved before the next; see `docs/pipeline/`). Its output is checked in a **local web demo** before anything is tried in XR: a developer-only browser viewer under `apps/preview` that opens a `.zumi` file and shows panels, layers with parallax, bubbles with voice, ambience and music cues. Iterating in a browser tab takes seconds; a Quest build takes minutes. The viewer is a tool, not product UI, and does not revive the descoped web platform. The Unity reader follows once a pipeline-made episode plays correctly in the viewer.
