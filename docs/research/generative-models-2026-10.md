# Generative models for the Zumi pipeline — state of the market, 2026-10-15

Research date: 2026-10-15. Primary sources only (model cards, provider docs, pricing pages, licences). Where a provider's pricing page is client-rendered and the number could not be read from the page itself, that is flagged as "unverified" and the best secondary figure is given.

## Executive summary

1. The user's assumption holds: no open-weight model is in the top 15 of the Artificial Analysis image-editing arena (v2.1, read 2026-10-15). Best open model (Qwen-Image-2.1, Elo 1080) sits ~120 Elo below the leader (GPT Image 2.5 Sunburst, 1199), and Qwen-Image-2.1 is research-licence only.
2. Closed leaders for sketch→styled panel with reference images: OpenAI gpt-image-2.5 (Sunburst/Flare, up to 16 input images, prompt-based masks, ~$0.05 per 1024² at "high"), Google Nano Banana 2.1 (up to 14 refs incl. 3 style refs, $0.0336 per 1K image), and Meta Muse Image on Meta Model API ($0.01/image, OpenAI-compatible endpoints, edit+compose with reference images).
3. None of the closed APIs expose ControlNet-style edge conditioning; structural fidelity to the sketch is achieved by passing the sketch as a reference/edit input plus prompt. The only API with explicit sketch-marker editing is ByteDance Seedream 5.0 Pro (BytePlus ModelArk).
4. OpenRouter does serve image generation: `POST /api/v1/images` with `input_references`, 57 models listed on 2026-10-15 (gpt-image-2.5, nano-banana-2.1, flux-3-image, seedream-5, mai-image-2.6, muse-image, recraft, qwen-image-3…). Pricing is per endpoint, all-or-nothing billing.
5. Open-weight stack that is commercially clean: FLUX.2 [klein] 4B (Apache 2.0, multi-ref, ~13 GB VRAM), HiDream-O1-Image 8B (MIT, up to 10 refs, skeleton/layout conditioning), FLUX.1 [schnell] (Apache 2.0). FLUX.2 [dev] 32B, klein 9B and Kontext [dev] need BFL's $999/month self-serve licence; Qwen-Image-2.1 is non-commercial; HunyuanImage 3.0-Instruct excludes EU/UK/KR and needs 8×80 GB.
6. Layering: Meta SAM 3 (Nov 2025, SAM 3.1 Mar 2026) does text-prompted concept segmentation under the permissive SAM License and is also hosted on Meta Model API at $2.50/1000 images. Depth: Depth Anything 3 (ByteDance, Apache 2.0 for Small/Base/Mono-Large/Metric-Large). Meta has no open depth model. Inpainting: LaMa (Apache 2.0) for cheap fills; FLUX.1 Fill [dev] is non-commercial; FLUX.1 Fill [pro] / gpt-image-2.5 masks via API.
7. Hosting: Modal H100 $0.001097/s ($3.95/h) vs RunPod serverless H100 $4.79/h flex; L40S $1.95/h vs $1.75/h. Modal: Python-defined images (`apt_install("blender")` works), 24 h max timeout, 7-day result retention, no webhook primitive. RunPod: Dockerfile-native, 7-day max execution, native `webhook` field on `/run`, FlashBoot.
8. For the Meta competition angle: Muse Image (API), SAM 3.1 (open weights + API) and Muse Glimmer (30B, Apache 2.0, Aug 2026, Meta's current open-weight LLM for the Blender MCP driver) give a coherent Meta-first story; Llama is no longer listed on Meta Model API.
9. Recommendation: closed API for generation; A/B gpt-image-2.5-sunburst vs Nano Banana 2.1 vs Muse Image on 20 sketches × 3 style modes, routed via OpenRouter for one integration. Keep FLUX.2 klein 4B as the self-hosted fallback.
10. Biggest uncertainties: no published benchmark isolates "sketch structural fidelity + style reference"; Muse Image's reference-image limit and output-rights terms are not documented; BFL/Ideogram pricing pages are client-rendered and could not be read verbatim.

---

## 1. Generation step

### 1.1 Leaderboards (dated)

| Board | Date read | #1 | Best open-weight | Source |
|---|---|---|---|---|
| Artificial Analysis AA-Image-Editing v2.1 (overall) | 2026-10-15 | GPT Image 2.5 Sunburst (max) 1199; Flare 1178; MAI-Image-2.6 1151; Nano Banana 2.1 1150; Seedream 5.0 Pro 1126; Muse Image 1126 | none in top 15 | https://artificialanalysis.ai/image/leaderboard/editing |
| AA-Image-Editing open-weights board | 2026-10-15 | Qwen-Image-2.1 1080±14; HunyuanImage 3.0 Instruct 1063; FLUX.2 [dev] Flash 1021; FLUX.2 [klein] 9B 1011; FLUX.2 [dev] 1000 (anchor); HiDream-O1-Image 953; klein 4B 935 | — | https://artificialanalysis.ai/image/leaderboard/editing/open-weights |
| LMArena / arena.ai Image Edit | could not fetch (HTTP 403) | Third-party mirrors dated 2026-09-21/22 put GPT Image 2.5 Sunburst #1 (1526) and Qwen-Image-2.1 as top non-proprietary at rank 16 (1367). Unverified. | | https://arena.ai/leaderboard/image-edit (blocked); mirrors: https://models.fru.dev/boards/lmarena-image-edit , https://www.orcarouter.ai/blog/qwen-image-2-1-arena-first-open-source |

Neither arena measures sketch-conditioned generation specifically; both are general edit-instruction preference votes.

### 1.2 Closed models

Price column is for a ~1024² output unless stated. "Routable" = listed on OpenRouter `/api/v1/images/models` on 2026-10-15 (see §2), plus fal/Replicate where confirmed.

| Model | Sketch/edge conditioning | Reference-image style transfer | Multi-image consistency | API | Price (~1K) | Commercial use of outputs | Routable |
|---|---|---|---|---|---|---|---|
| OpenAI gpt-image-2.5 Sunburst / Flare (snapshot 2026-09-08) | No ControlNet. Edit endpoint takes up to 16 input images; masks are "entirely prompt-based" (model may not follow mask shape). `input_fidelity` not accepted on 2/2.5 (refs processed at high fidelity automatically). Consumer "Sketch" feature exists in ChatGPT; no API-level sketch parameter documented. | Yes via reference images in `images.edits` | Up to 16 refs; quality tiers low/medium/high/xhigh/max; custom sizes to 3840×2160 | Images API (`generations`, `edits`, batch); Responses/Chat not supported for 2.5 | Token-billed: $8/M image-in, $30/M image-out (batch $15/M). Per-image for 2.5 not published by OpenAI; fal computes 1024² ≈ $0.0041 low / $0.0133 medium / $0.0528 high. GPT Image 2 official table: $0.006 / $0.053 / $0.211. | Yes (OpenAI terms; no model licence) | OpenRouter, fal, Replicate |
| Google Nano Banana 2.1 (`gemini-nano-banana-2.1`, released ~2026-10-06) | No ControlNet / edge control documented. Sketch must be passed as a reference image. | Yes: up to 3 style reference images | Up to 14 refs per request (≤10 objects, 4–5 characters); multi-turn editing via `previous_interaction_id`; SynthID watermark on all outputs | Gemini API, Vertex | $0.0336 (1K), $0.0504 (2K), $0.113 (4K); batch half. Nano Banana Pro (`gemini-3-pro-image`) $0.134 1K/2K. No free tier for image output. `gemini-2.5-flash-image` shut down 2026-10-02; Imagen 4 earliest shutdown 2026-08-17. | Yes (Gemini terms) | OpenRouter, Replicate (official), fal |
| Meta Muse Image (`muse-image-1.0`, Meta Model API GA 2026-08-25) | None documented. Edit/compose endpoint accepts a list of images; "anchored composition" keeps character/style/setting consistent across a series. | Yes (reference images) | Multi-image compose; max ref count not stated (examples use 2–3). Output up to 1600 px. | `POST https://api.meta.ai/v1/images/generations` and `/edits`, OpenAI-SDK compatible | $0.01 per image flat; 150 RPM | Not specified on model page (only general Meta ToS) — needs checking | OpenRouter (`meta/muse-image`), fal, Runway |
| Black Forest Labs FLUX 3 Image (released 2026-10-01) | Not documented on BFL docs read; press reports JSON bounding-box layout control and mask-free localized editing (unverified) | Yes via up to 10 `input_references` | Up to 10 refs; 768–4K tiers | BFL API; OpenRouter | BFL pricing page is client-rendered; could not read. OpenRouter sample `usage.cost` 0.04 (illustrative). | Yes (BFL API includes commercial rights) | OpenRouter |
| BFL FLUX.2 [pro] / [flex] / [max] (2025-11-25) | No canny/depth/sketch endpoints documented for FLUX.2 | Yes (multi-reference) | Up to 10 refs (BFL blog), 8 on OpenRouter; up to 4 MP | BFL API | Per-megapixel; "from $0.03/MP" for pro (secondary); editing adds input-MP charge. Unverified from primary page. | Yes | OpenRouter, fal, Replicate |
| BFL FLUX.1 Kontext [pro]/[max] | No | Yes (single ref) | Successive edits with low drift | BFL API, fal | $0.04 / $0.08 per image (BFL credits, confirmed via fal page) | Yes | fal, Replicate (not OpenRouter) |
| ByteDance Seedream 5.0 Pro (`dola-seedream-5-0-pro-260628`) | Yes: "interactive editing" — draw a sketch/doodle/circle/box on the image and describe the change. Only API with explicit sketch-marker editing. Also layer decomposition (one input). | Yes | Up to 10 refs (Pro); Lite: refs+outputs ≤15; OpenRouter lists 14 | BytePlus ModelArk; OpenRouter; fal | fal: $0.0675 (≤1536²), $0.135 (≤2048²), +$0.0045 per extra input image; OpenRouter listed $0.045 (secondary). BytePlus price page not read. | Yes | OpenRouter, fal (no standalone Replicate page found) |
| Microsoft MAI-Image-2.6 / -Flash | No | Yes, up to 5 refs | 5 refs | Microsoft Foundry (preview); OpenRouter | OpenRouter: $8/M in, $38/M out tokens (secondary) | Preview terms | OpenRouter |
| Ideogram 4.5 (2025-09-30 → 2026-09-30 per AA tweet) | No | Style reference images supported (≤25 MB each); character reference: 1 image | Character reference priced separately | Ideogram API; fal | Official pricing page client-rendered. fal: $0.03 low / $0.06 medium / $0.22 high. 3.0 character-reference surcharge $0.10–0.20 (secondary). AA ranks it #23 on editing. | Yes | fal; not on OpenRouter list |
| Recraft V4 Styles (2026-08-26) | No | Yes: style created from 1–10 refs, `style_id` reused | Style ID is the consistency mechanism | Recraft API | $0.035 raster, $0.05 vector, Pro $0.10/$0.12, +$0.005 per style creation | Yes | OpenRouter, fal |
| Midjourney | — | — | — | No public API; ToS forbids automation. Unverified beyond third-party reports. | $10/mo subscription | — | No |
| Qwen-Image-3 / 3-pro (API-only, 2026-08-05) | No | Yes | Refs supported | Alibaba Cloud; OpenRouter from $0.03 | — | No open weights | OpenRouter |
| Tencent Hy Image 3.5 preview (`hy-image-v3.5-preview`, 2026-09-22) | No | Yes | Up to 20 refs (secondary) | Tencent Cloud; OpenRouter | $0.024/image (Tencent X post) | Not open | OpenRouter |

### 1.3 Open-weight models

| Model | Params / VRAM | Sketch/edge conditioning | Reference style / multi-ref | Licence | Hosted API | AA open-edit Elo |
|---|---|---|---|---|---|---|
| FLUX.2 [klein] 4B (2026-01-15) | 4B, ~13 GB; FP8/NVFP4 variants | None native; no FLUX.2 ControlNet found | T2I, I2I, multi-reference in one model | Apache 2.0 (4B and 4B-Base) | BFL API, OpenRouter, fal | 935±18 |
| FLUX.2 [klein] 9B | 9B | None | Multi-ref | FLUX Non-Commercial License (NCL); commercial via BFL licence | BFL API | 1011±14 |
| FLUX.2 [dev] (2025-11-25) | 32B | None | Up to 10 refs; character/object/style refs without finetune | FLUX NCL; commercial self-host = BFL self-serve $999/mo for 100k images (+$0.01/image) per 2025-09 help article | fal (Flash/Turbo variants) | 1000 (anchor) |
| FLUX.1 [dev] + ControlNet / IP-Adapter | 12B | Yes: Shakker-Labs ControlNet-Union-Pro-2.0 (canny, soft-edge, depth, pose; 3.98 GB) | XLabs flux-ip-adapter-v2 (beta) | All under FLUX.1 [dev] Non-Commercial License → same $999/mo path | fal, Replicate | not on board |
| FLUX.1 [schnell] | 12B | Via community ControlNets | weak | Apache 2.0 | fal, Replicate | — |
| FLUX.1 Kontext [dev] (2025-06) | 12B | No | Single ref, low drift across edits | FLUX.1 [dev] NCL | fal, Replicate | — |
| Qwen-Image-2.1 (2026-09-20) | 7B | Local edits via circles/painted annotations/masks | Up to 10 refs; RGBA output | Qwen Research License — "NON-COMMERCIAL PURPOSES ONLY", commercial licence by email | none official | 1080±14 (#1 open) |
| Qwen-Image-Edit-2511 / Qwen-Image-2512 | 20B | No | Multi-image | Apache 2.0 (per model cards cited by secondary sources; verify) | fal, Replicate | 991±20 |
| HunyuanImage 3.0-Instruct (2026-01-26) | 80B MoE (13B active); ≥8×80 GB GPUs | No | Up to 3 refs; CoT prompt rewrite | Tencent Hunyuan Community License: not valid in EU/UK/South Korea; >100M MAU needs licence | fal | 1063±14 |
| HiDream-O1-Image (2026-05-08) | 8B | Yes: skeleton and layout conditioning | Up to 10 refs; instruction editing | MIT (prompt agent uses Gemma-4-31B, separate licence) | — | 953±15 |
| Stable Diffusion 3.5 Large | 8B | Community ControlNets | weak | Stability Community License: free under $1M annual revenue | Stability API, fal, Replicate | not on board |
| Muse Glimmer (Meta, 2026-08-10) | ~30B VLM, text-out only | n/a — not an image generator | — | Apache 2.0 | self-host | — |

Observations
- Open models with permissive licences are 150–250 Elo behind closed leaders on editing. Qwen-Image-2.1 narrows the gap but is non-commercial.
- Edge/sketch ControlNets exist only for the FLUX.1-dev family (non-commercial) and SD 3.5; nothing comparable for FLUX.2 or Qwen-Image-2.1 was found.
- The Artificial Analysis boards are general-edit preference votes, not sketch-fidelity measurements. Treat them as a prior, not a verdict.

## 2. OpenRouter and image generation

Yes. OpenRouter has a dedicated Image API (docs read 2026-10-15):

- `POST /api/v1/images` — `model`, `prompt`, optional `input_references[]` (`{"type":"image_url","image_url":{"url":...}}`, HTTP(S) or base64), `n`, `resolution`, `aspect_ratio`, `size`, `quality`, `seed`, `stream` (SSE `image_generation.partial_image` / `completed`), `provider` routing. Output `data[].b64_json`.
- `GET /api/v1/images/models` lists models accepted by that endpoint; `GET /api/v1/images/models/{id}/endpoints` gives per-provider pricing (`unit`: image | megapixel | token, `cost_usd`). `GET /api/v1/models?output_modalities=image` returns the broader set including chat-completions-only image models.
- Billing is per endpoint and "all-or-nothing": failed/cancelled generations are not billed.
- Chat Completions / Responses also emit images for Gemini image models and `openai/gpt-5-image`, and a server tool `openrouter:image_generation` lets any text model call an image model.

`GET /api/v1/images/models` returned 57 ids on 2026-10-15, including: `openai/gpt-image-2.5-sunburst`, `openai/gpt-image-2.5-flare`, `openai/gpt-image-2`, `google/gemini-nano-banana-2.1`, `google/gemini-3-pro-image`, `black-forest-labs/flux-3-image`, `flux.2-pro`, `flux.2-flex`, `flux.2-max`, `flux.2-klein-4b`, `bytedance-seed/seedream-5-0-pro|lite|flash`, `seedream-4.5`, `microsoft/mai-image-2.6|-flash|2.5-pro`, `meta/muse-image`, `qwen/qwen-image-3|-pro`, `tencent/hy-image-v3.5-preview`, `x-ai/grok-imagine-image-2.0`, `recraft/recraft-v4-styles*`, `krea/krea-2-*`, `sourceful/riverflow-*`. All but `recraft-v4.1-flash` and `meta/muse-image` list `input_references`. Not on the list: Ideogram, FLUX.1 Kontext, Midjourney.

Caveat: the public list did not include `cost_usd`; prices are on each model's endpoints page.

## 3. Layering stack

| Step | Model | Owner | Release | Licence | Notes |
|---|---|---|---|---|---|
| Segmentation | SAM 3 (848M) / SAM 3.1 "Object Multiplex" | **Meta** | 2025-11-19 / 2026-03-27 | SAM License: royalty-free use/modify/distribute, no MAU cap, no commercial prohibition; bans military/ITAR/weapons uses; attribution in publications; redistribute with licence copy. HF checkpoints gated (request access). | Promptable Concept Segmentation: noun phrase or exemplar → all instances; points/boxes/masks; video tracking. Also hosted on Meta Model API as `sam-3.1` at $2.50/1000 images, 3000 RPM. Needs Python ≥3.12, PyTorch ≥2.7, CUDA ≥12.6. |
| Segmentation (legacy) | SAM 2 | Meta | 2024 | Apache 2.0 | No text prompts; still fine for point/box refinement. |
| Inpainting (cheap, local) | LaMa | Samsung AI | 2021 | Apache 2.0 | Fourier-conv large-mask inpainting, generalizes to ~2K; CPU-feasible. Good for behind-cutout fills in flat comic art. |
| Inpainting (diffusion, open) | FLUX.1 Fill [dev] | BFL | 2024-11 | FLUX.1 [dev] Non-Commercial | 12B; ~10–36 GB VRAM. Needs BFL licence for commercial self-host. |
| Inpainting (API) | FLUX.1 Fill [pro]; FLUX Eraser (BFL); gpt-image-2.5 `edits` with alpha mask; Recraft V3 inpaint $0.04 | — | — | API terms | gpt-image masks are prompt-guided, not pixel-exact. |
| Inpainting (open, permissive) | FLUX.2 [klein] 4B I2I with mask prompt; HiDream-O1-Image edit | BFL / HiDream | 2026 | Apache 2.0 / MIT | Not purpose-built fill models; quality untested here. |
| Monocular depth | Depth Anything 3 (DA3) | ByteDance | 2025-11-14 | Apache 2.0: DA3-SMALL, DA3-BASE, DA3MONO-LARGE, DA3METRIC-LARGE. CC BY-NC 4.0: DA3-LARGE, DA3-GIANT, DA3NESTED-GIANT-LARGE. Prefer `-1.1` checkpoints. | DA3MONO-LARGE predicts depth (not disparity). Claims to "significantly outperform" DA V2. |
| Monocular depth (older) | Depth Anything V2 | HKU/ByteDance | 2024-06 | Small Apache 2.0; Base/Large CC-BY-NC | Superseded by DA3. |
| Monocular depth (metric) | Depth Pro | Apple | 2024-10 | Apple sample-code licence: use/modify/redistribute permitted, attribution; "personal, non-exclusive" wording — legal review advised | 2.25 MP depth in 0.3 s, focal-length estimate. |
| Depth, Meta | none | — | — | — | Meta has no open monocular-depth model; Sapiens2 (2026-05) covers human pose/normals only. |

Meta models in this stack: SAM 3 / 3.1 (open weights + API). Everything else is non-Meta.

## 4. Hosting: RunPod Serverless vs Modal

| Criterion | RunPod Serverless | Modal |
|---|---|---|
| H100 | $4.79/h flex (pricing page, 2026-10-15); per-second billing rounded up to the second; active-worker discount by sales quote | $0.001097/s = $3.95/h (H100 SXM5) |
| A100 80 GB | $2.72/h | $0.000694/s = $2.50/h |
| L40S / 48 GB class | $1.75/h (L40, L40S, 6000 Ada) | $0.000542/s = $1.95/h |
| Cheaper tiers | A6000/A40 $1.22/h; 4090 $1.10/h; L4/A5000/3090 $0.69/h | A10 $1.10/h; L4 $0.80/h; T4 $0.59/h |
| CPU/RAM | included in GPU rate; container disk ~$0.10/GB/mo | $0.047/core/h + $0.008/GiB/h, billed separately |
| Cold start | Billed from worker start to ready (image pull and cached-model download are not billed). FlashBoot on by default keeps worker state after spin-down; model caching; `active workers ≥1` removes cold starts. No official latency figure. | Containers "boot in about one second"; warm-up (imports, weights) seconds to minutes; memory snapshots; `min_containers`, `buffer_containers`; `scaledown_window` 2 s–20 min (default 60 s). |
| Image flexibility | Native Dockerfile; any base image; apt packages (Blender) trivial; GitHub-repo build | Python-defined images: `Image.debian_slim().apt_install("blender", ...)`, `run_commands`, `from_dockerfile` (own Dockerfile implementation; `EXPOSE/HEALTHCHECK/VOLUME/USER` unsupported, must be linux/amd64, python+pip on PATH or `add_python`), `from_registry`. |
| Max run duration | `executionTimeout` default 600 s, range 5 s – 7 days; job `ttl` default 24 h, max 7 days | Function `timeout` default 300 s, max 24 h |
| Queue / async | Built in: `/run` (async, result kept 30 min) and `/runsync` (1 min); job states IN_QUEUE→RUNNING→COMPLETED; load-balancing endpoints for FastAPI/Flask | `Function.spawn()` → `FunctionCall.from_id().get(timeout=)`; results kept 7 days; up to 1M queued tasks; web endpoints via `@fastapi_endpoint`/`@asgi_app`/`@web_server` (4 GiB bodies, 200 rps account limit) |
| Webhooks | Native: top-level `webhook` URL on `/run`, retried 2× with 10 s delay | No built-in webhook; implement in the function (HTTP POST at end) or poll |
| Plans / free credit | Pay-as-you-go; default spend cap $80/h | Starter $30/mo free credit, 10 GPU concurrency; Team $250/mo + $100 credit |

Read: Modal is cheaper per second on H100/A100 and far more pleasant for a Python pipeline (images in code, spawn/get job model, 24 h limit covers any render). RunPod wins when you want an unmodified Dockerfile with Blender + Xvfb and a native webhook, or runs over 24 h. Blender MCP caveat: the ahujasid addon does not start under `blender -b`; headless use needs `xvfb-run blender` or a headless-capable fork (e.g. sandraschi/blender-mcp) — secondary sources, verify on the repo.

## 5. Recommendation

Closed API for the generation step. The gap is not subtle: the best commercially usable open model (FLUX.2 klein 4B, Elo 935) is ~260 Elo below gpt-image-2.5 Sunburst on editing, and the open models that come closest are either non-commercial (Qwen-Image-2.1) or need 8×80 GB (Hunyuan). Per-image API cost ($0.01–$0.05) is below the amortised GPU-second cost of a 32B self-hosted model at low volume anyway.

A/B test first, 20 sketches × {preset prompt, free text, 1–5 style refs}, judged on (a) line/pose fidelity to the sketch, (b) style match to refs, (c) character drift across 6 panels:

1. **OpenAI gpt-image-2.5-sunburst** — board leader on editing precision, 16 input images, custom aspect ratios up to 3840×2160 (useful for wide XR panels). ~$0.05/high image. Risk: prompt-based masking; no explicit structure control.
2. **Google Nano Banana 2.1** — explicit style-reference slot (3 images) plus 10 object/4–5 character refs and multi-turn editing; cheapest strong option at $0.0336; SynthID watermark unavoidable. Risk: 2.1 is nine days old; multi-round drift reported by reviewers (unverified).
3. **Meta Muse Image** — $0.01/image, compose/edit with reference images, OpenAI-compatible API, Elo 1126 (ties Seedream 5 Pro). It is the natural pick for a Meta competition entry. Risk: reference-image limit and output-rights terms undocumented; 150 RPM.

Also worth one round: Seedream 5.0 Pro for its sketch-marker editing (the only API that takes a drawn region as a control), if structural fidelity from the other three disappoints.

Route all three through OpenRouter `/api/v1/images` so the integration is written once; drop to native APIs only for features OpenRouter lacks (Gemini style-ref typing, OpenAI masks).

Self-hosted fallback (and the "Meta open-source" story): FLUX.2 klein 4B on an L40S/A10 for offline or bulk regeneration; SAM 3.1 + DA3 + LaMa for layering; Muse Glimmer (Apache 2.0) as the local MCP driver instead of Llama, since Meta Model API no longer lists Llama.

Uncertainty, stated plainly: no benchmark measured sketch→styled-panel fidelity; the rankings above are general edit-preference Elo. Expect the A/B to reorder them. BFL and Ideogram per-image prices were not readable from their primary pages; figures given are from fal/OpenRouter or secondary sources.

## Sources

Leaderboards
- https://artificialanalysis.ai/image/leaderboard/editing
- https://artificialanalysis.ai/image/leaderboard/editing/open-weights
- https://x.com/ArtificialAnlys/status/2106174147571413371 (Ideogram 4.5 debut)
- https://arena.ai/leaderboard/image-edit (403 at fetch time)

OpenAI
- https://developers.openai.com/api/docs/pricing
- https://developers.openai.com/api/docs/guides/image-generation
- https://developers.openai.com/api/docs/models/gpt-image-2.5-sunburst
- https://developers.openai.com/api/reference/python/resources/images/methods/edit
- https://en.wikipedia.org/wiki/GPT_Image (release dates; OpenAI announcement page returned 403)
- https://fal.ai/gpt-image-2.5 ; https://replicate.com/openai/gpt-image-2.5-sunburst

Google
- https://ai.google.dev/gemini-api/docs/pricing
- https://ai.google.dev/gemini-api/docs/image-generation
- https://ai.google.dev/gemini-api/docs/deprecations
- https://replicate.com/google/nano-banana-2.1

Meta
- https://developer.meta.com/ai/resources/blog/build-with-muse-Image/
- https://dev.meta.ai/models/muse-image/ ; https://dev.meta.ai/docs/models ; https://dev.meta.ai/docs/pricing-rate-limits
- https://github.com/facebookresearch/sam3 ; https://raw.githubusercontent.com/facebookresearch/sam3/main/LICENSE ; https://huggingface.co/facebook/sam3
- Muse Glimmer (secondary, Meta HF card not fetched): https://betanews.com/article/meta-muse-glimmer-open-weight-ai-model/

Black Forest Labs
- https://bfl.ai/blog/flux-2 ; https://bfl.ai/blog/flux2-klein-towards-interactive-visual-intelligence
- https://docs.bfl.ai/quick_start/pricing (prices client-rendered) ; https://bfl.ai/pricing
- https://help.bfl.ai/articles/9272590838-self-serve-dev-license-overview-pricing
- https://huggingface.co/black-forest-labs/FLUX.2-dev ; https://huggingface.co/black-forest-labs/FLUX.2-klein-4B ; https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev ; https://huggingface.co/black-forest-labs/FLUX.1-Fill-dev
- https://openrouter.ai/black-forest-labs/flux-3-image ; https://openrouter.ai/black-forest-labs/flux.2-pro ; https://fal.ai/models/fal-ai/flux-pro/kontext
- https://www.globenewswire.com/news-release/2026/07/23/3332364/0/en/black-forest-labs-unveils-flux-3-a-new-multimodal-frontier-model-for-visual-intelligence.html
- https://huggingface.co/Shakker-Labs/FLUX.1-dev-ControlNet-Union-Pro-2.0 ; https://huggingface.co/XLabs-AI/flux-ip-adapter-v2

ByteDance / Tencent / Alibaba / others
- https://ai.byteplus.com/resources/seedream-5-0-overview-what-we-know-about-this-version
- https://fal.ai/models/bytedance/seedream/v5/pro/text-to-image ; https://fal.ai/models/bytedance/seedream/v5/pro/edit ; https://openrouter.ai/bytedance-seed/seedream-5-0-pro
- https://huggingface.co/tencent/HunyuanImage-3.0-Instruct (+ LICENSE) ; https://x.com/TencentHunyuan/status/2102226552310419473
- https://huggingface.co/Qwen/Qwen-Image-2.1 (+ LICENSE) ; https://openrouter.ai/qwen/qwen-image-3
- https://huggingface.co/HiDream-ai/HiDream-O1-Image
- https://huggingface.co/stabilityai/stable-diffusion-3.5-large
- https://www.recraft.ai/docs/api-reference/pricing
- https://openrouter.ai/microsoft/mai-image-2.6
- Ideogram: https://developer.ideogram.ai/api-reference/api-reference/generate-v3 ; https://ideogram.ai/pricing/?pricing_tab=api (client-rendered) ; https://fal.ai/models/ideogram/v4.5
- Midjourney (no primary API doc exists): https://unifically.com/blogs/midjourney-api

OpenRouter
- https://openrouter.ai/docs/guides/overview/multimodal/image-generation
- https://openrouter.ai/api/v1/images/models (fetched 2026-10-15, 57 ids)
- https://openrouter.ai/docs/guides/features/server-tools/image-generation

Depth / inpainting
- https://github.com/ByteDance-Seed/Depth-Anything-3 ; https://github.com/DepthAnything/Depth-Anything-V2
- https://github.com/apple/ml-depth-pro ; https://raw.githubusercontent.com/apple/ml-depth-pro/main/LICENSE
- https://github.com/advimman/lama ; https://raw.githubusercontent.com/advimman/lama/main/LICENSE

Hosting
- https://www.runpod.io/pricing ; https://docs.runpod.io/serverless/pricing ; https://docs.runpod.io/serverless/overview ; https://docs.runpod.io/serverless/endpoints/endpoint-configurations ; https://docs.runpod.io/serverless/endpoints/send-requests
- https://modal.com/pricing ; https://modal.com/docs/guide/timeouts ; https://modal.com/docs/guide/images ; https://modal.com/docs/guide/existing-images ; https://modal.com/docs/guide/cold-start ; https://modal.com/docs/guide/job-queue ; https://modal.com/docs/guide/webhooks
- Blender headless (secondary): https://github.com/sandraschi/blender-mcp ; https://github.com/nytimes/rd-blender-docker
