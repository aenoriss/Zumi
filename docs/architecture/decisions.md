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
2. **Remove dialog**: mask bubble boxes from the sketch, "no text" instruction, then a fast-model check pass that inpaints any leftover lettering in the finished art.
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

Controls: per-chapter budget cap ($10 default; a 10-page chapter is ~$6), per-step retry limit 2, Blender agent tool-call cap. Jobs are rows in Postgres; Modal functions update rows via service key (Modal has no webhooks); Supabase Realtime pushes status to the editor.

Interactive elements (touch triggers, fixed action enum, AI-suggested never auto-applied, no scripting) are post-MVP; the format reserves the fields.

## 5. Web app

| Decision | Choice |
|---|---|
| Frontend | Next.js on Vercel. |
| API | Bun + Elysia on Render. Orchestrates jobs, talks to Modal, Supabase, OpenRouter, Meta API, Google. |
| Data | Supabase: Auth, Postgres, Storage (signed URLs for the headset), Realtime. |
| Landing | Competition showcase (trailer, pitch, links) + public gallery of chapters with a browser parallax preview (CSS 3D, mouse-move, plays animation tracks). English only. |
| Editor (MVP) | Upload one sketch per panel; style (preset/text/refs); cast list with voice pick and line preview; dialog text fix, speaker reassign, bubble reposition; layer merge + Z nudge; animation instruction per panel with preview; regenerate single panel with tweaked prompt/refs; panel order, render mode, duration override; 2D parallax preview; publish chapter. |
| Language | English for MVP; `language` is a per-comic field for later translation tracks. |

## 6. Repo layout (monorepo)

```
apps/web/                Next.js
apps/api/                Bun + Elysia
apps/xr/                 Unity 6 project (Git LFS for binaries, strict .gitignore)
pipeline/                Python, Modal functions
packages/format/         .zumi JSON Schema -> TS + C# types
packages/design-tokens/  tokens JSON -> CSS vars + Unity ScriptableObject
packages/ui/             Storybook component library (brand grill pending)
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
7. Supabase project.
8. Modal account + token.
9. Vercel project, Render service.

All keys go in untracked `.env` files and are never committed.

## 9. Post-MVP backlog

Interactive elements and AI suggestions; translation tracks; audience-triggerable hooks; scripting; Pico/Android XR; WebGL target; layer split and mask painting; co-location; richer animation (sprite-sheet generation).

## 10. Open items

- Verify which Meta API model accepts images (Muse Wonder vs Spark) and Muse Glimmer's multimodality.
- Panorama generator choice (step 10).
- Brand/design system: separate grill in progress. Decided so far: W3C DTCG JSON in `packages/design-tokens` is the token source of truth (Pencil dropped 2026-10-17) -> Style Dictionary -> CSS, USS, C#; components on Radix Primitives + Tailwind v4 from tokens, catalogued in Storybook 10; ParallaxPreview in react-three-fiber (shares animation/depth math with Unity).
