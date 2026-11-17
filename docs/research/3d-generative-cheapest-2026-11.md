# Generated props at the lowest cost per usable mesh: hosted APIs, open weights on Modal, stylised output, a 2 USD test — 2026-11-07

Research date: 2026-11-07. Primary sources only (vendor pricing and API pages, fal `llms.txt` model sheets, GitHub READMEs and raw LICENSE files, model cards, arXiv, Modal docs), read by four parallel agents and spot-checked. The model survey with quality evidence is in `3d-sets-and-props-2026-11.md` § 3 (TRELLIS.2 66.5% preference vs Hunyuan3D 2.1, 3D Arena ELOs, the Pixal3D painterly failures); this note does not repeat it, it goes deeper on price per mesh and on what to run. Context: the hand-modelled Blender primitives for the tavern props were dropped today **[in-house]**; target 1–8 props per setting, stylised, GLB with PBR or albedo, ≤ 50k tris, inside the 2 USD/day cap of `pipeline/segment/spend.py` (`reserve(worst_usd)` before a call, `record(service, usd)` after) **[in-house]**.

Conventions: **[docs]** copied from the cited page. **[est]** my arithmetic from [docs] figures. **[vendor]** a vendor's claim about quality. **[secondary]** not the owner's page. **[unverified]** could not be opened or confirmed. Prices in USD.

## Summary

1. **Cheapest usable mesh, hosted: fal.ai `fal-ai/trellis`, 0.02 per generation**: image in, textured GLB out, `texture_size` 512–2048, `mesh_simplify` 0.9–0.98, MIT model ([sheet](https://fal.ai/models/fal-ai/trellis/llms.txt), [MIT](https://github.com/microsoft/TRELLIS/blob/main/LICENSE)) **[docs]**; on Replicate "approximately $0.040", ~29 s on an A100 ([firtoz/trellis](https://replicate.com/firtoz/trellis)) **[docs]**. TRELLIS held 3D Arena ELO 1306 for meshes, above Hunyuan3D-2 (1298) and InstantMesh (1278) ([3D Arena](https://arxiv.org/html/2506.18787)) **[docs]**.
2. **Cheapest from text: fal `hyper3d/rodin/v2.5/text-to-3d/fast`, 0.10**, ≤ 20k tris ([sheet](https://fal.ai/models/fal-ai/hyper3d/rodin/v2.5/text-to-3d/fast/llms.txt)); then Tripo H3.1 text-to-model, 20 credits = 0.20 with PBR, `face_limit`, `auto_size` and `delight` free ([H3.1](https://developers.tripo3d.ai/en/models/v3-1), [pricing](https://developers.tripo3d.ai/en/pricing)) **[docs]**. A concept image first (FLUX.2 [klein] 4B, 0.014 per MP on the BFL API the pipeline already calls ([BFL pricing](https://bfl.ai/pricing))) plus fal TRELLIS is cheaper than any text route and controls the look **[est]**.
3. **Cheapest open route: TRELLIS.2-4B on a Modal L40S, ~0.03 per mesh amortised over 8** (8 × ~40 s + 60 s load + 60 s idle ≈ 440 s × 0.000542) **[est]**. Only H100 timings exist (3 / 17 / 60 s at 512 / 1024 / 1536³); a 23 GB A10 "reliably OOMs" at 1024 ([README](https://github.com/microsoft/TRELLIS.2), [issue 188](https://github.com/microsoft/TRELLIS.2/issues/188)); weights 16.2 GB ([HF](https://huggingface.co/microsoft/TRELLIS.2-4B/tree/main/ckpts)) **[docs]**. SF3D/SPAR3D on a T4 cost < 0.001 but rank 1190 / 1144, bottom of the arena **[docs]**.
4. **Hunyuan licences do not reach Argentina**: the Territory is "the worldwide territory, excluding the territory of the European Union, United Kingdom and South Korea" ([2.1 LICENSE](https://raw.githubusercontent.com/Tencent-Hunyuan/Hunyuan3D-2.1/main/LICENSE)) **[docs]**. Hunyuan3D-2 (16 GB shape+texture) fits an L4 at ~0.01–0.02 per mesh **[secondary timing, est]**.
5. **No current generator has a style switch**: Meshy `art_style` is "Deprecated… Meshy ignores it" ([docs](https://docs.meshy.ai/en/api/text-to-3d)); Tripo v3 has no `style` field ([text-to-model](https://developers.tripo3d.com/en/docs/generation-text-to-model)); Tencent 3.1 drops `Sketch` and `LowPoly` ([API](https://www.tencentcloud.com/document/api/1284/75540)) **[docs]**. Style enters through the input image, the prompt, or a retexture (Tripo 10 credits with a `style_image`, Meshy 10 credits).
6. **Flat comic colour hurts geometry**: image-to-3D models "struggle… when the reference image is flat-colored like hand drawings"; Art3D fixes it by re-shading the image before lifting ([Art3D](https://arxiv.org/abs/2504.10466)) **[docs]**. Shade the concept image; add flatness after, by posterising the de-lit albedo into `KHR_materials_unlit` (free).
7. **Meshy is the wrong fit**: API only on Pro (20/month), 30 credits ≈ 0.60 per textured mesh, free tier has no API and licenses outputs CC BY 4.0, API outputs are deleted after 3 days ([free plan](https://help.meshy.ai/en/articles/15696428-what-is-included-on-the-free-plan), [ToS §2.5](https://www.meshy.ai/terms-of-use)) **[docs]**.
8. **Test plan**: three props on fal TRELLIS (0.12), Tripo H3.1 (1.50), SPAR3D's 25 free credits (0), optional TRELLIS.2 on Modal's free credit; 1.62 paid **[est]**.
9. **Recommendation**: FLUX.2 klein → fal TRELLIS (~0.035 per prop, hours to wire); fallback Tripo H3.1 image-to-model (0.30); TRELLIS.2 on Modal when quality or volume justify 1–2 days.

## 1. Hosted APIs, cheapest first

One textured mesh under 50k tris; prices as the vendor's page states them; "free" is the grant's capacity in props **[est]**.

| Route | USD per mesh | Input | Output | Poly control | Latency [docs] | Free tier | Output licence |
|---|---|---|---|---|---|---|---|
| **fal `fal-ai/trellis`** | **0.02** | image | GLB, baked texture 512/1024/2048 | `mesh_simplify` 0.9–0.98 only | none stated | signup credit not stated [unverified] | fal ToS assigns no output rights; model MIT ([ToS](https://fal.ai/terms)) |
| Stability SPAR3D | 0.04 (4 cr × 0.01) | image | GLB albedo + normal, 512–2048 | `target_count` 100–20,000 | "0.7 seconds" [vendor] | 25 credits = 6 meshes | API ToS §4a assigns outputs to you ([ToS](http://stability.ai/2025-terms-of-service)) |
| Replicate `firtoz/trellis` | ~0.040 | image | GLB textured | `mesh_simplify` | "within 29 seconds", A100 | none on page | MIT model |
| Stability SF3D | 0.10 (10 cr) | image | GLB, delit albedo + material | `vertex_count` ≤ 20,000, quad/tri | ~1 s | shares the 25 credits | as above |
| fal `rodin/v2.5/text-to-3d/fast` | 0.10 | text | GLB, Shaded or PBR | ≤ 20k tri | none | — | fal ToS |
| **Tripo H3.1 direct** | **0.20 text / 0.30 image** (20 / 30 cr; PBR, `face_limit`, `auto_size`, `delight` free; +5 quad, +10 smart low-poly, +10 detailed texture) | text, image, multiview | GLB (FBX if quad); base/metal/rough/normal | `face_limit` ≤ 1.5M; `smart_low_poly` 500–20,000 | "about 40s without texture, about 120s with texture" | 2,000 API credits on Tripo's blog [unverified], absent from pricing pages | ToS §5.2: "Free Users" → Tripo retains all rights; "Paid Users" own outputs ([terms](https://developers.tripo3d.ai/en/terms)) |
| fal `tripo3d/h3.1` text / image | 0.20 / 0.30 standard texture | text / image | GLB PBR | `face_limit` 1,000–2M | none | — | fal ToS |
| fal `hunyuan-3d/v3.1/rapid` | 0.225 (+0.15 PBR) | text ≤ 200 chars, or image | GLB (text variant OBJ+MTL) | none | none | — | fal ToS |
| fal `trellis-2` | 0.25 / 0.30 / 0.35 at 512 / 1024 / 1536 | image | GLB, baked texture 1024–4096 | `decimation_target` 5k–2M vertices, "20k–50k for web/mobile" | none | — | MIT model |
| Tencent HY 3D Global, Pro | Normal 25 cr, +10 PBR, +10 custom `FaceCount` → 0.375 / 0.525 / 0.675 prepaid (0.015/cr); 0.50 / 0.70 / 0.90 postpaid | text or image (Sketch only on 3.0) | **OBJ** (+5 cr convert to GLB); Rapid tier 15 cr (+10 PBR) returns GLB | `FaceCount` 3,000–1.5M | none stated | 200 credits once, 1 year = 5 PBR props | AI Service Terms §3.1: you own outputs ([terms](https://www.tencentcloud.com/document/product/301/74049)) |
| fal `hyper3d/rodin/v2.5` | 0.40 | text + ≤ 5 images | glb/usdz/fbx/obj, PBR, quad 4K–200K | yes | none | — | fal ToS |
| Sloyd API | 0.27 image / 0.33 text (75 cr per USD, min 12 USD) | text, image | GLB/FBX/OBJ, textures ≤ 4k | parametric | — | none | not stated |
| Meshy 7.1 direct | 0.60 (30 cr at Pro 0.02/cr) + 20/month | text (20 preview + 10 refine), image 30 | GLB/FBX/OBJ/USDZ, PBR 2K–8K | `target_polycount` 100–300,000 | 75 s preview, 80 s refine | API needs Pro; free is web only, CC BY 4.0 | paid own outputs; deleted after 3 days |
| fal `meshy/v7.1` | 1.20 textured | text, image | as above | yes | — | — | fal ToS |

Sources **[docs]**: fal sheets at `https://fal.ai/models/<id>/llms.txt` ([trellis-2](https://fal.ai/models/fal-ai/trellis-2/llms.txt), [hunyuan 3.1 rapid](https://fal.ai/models/fal-ai/hunyuan-3d/v3.1/rapid/image-to-3d/llms.txt), [tripo h3.1](https://fal.ai/models/tripo3d/h3.1/image-to-3d/llms.txt), [meshy 7.1](https://fal.ai/models/fal-ai/meshy/v7.1/image-to-3d/llms.txt)); [Stability pricing](https://docs.stability.ai/pricing), [SPAR3D API](https://docs.stability.ai/api-reference/3d/stable-point-aware-3d.md); [Replicate pricing](https://replicate.com/pricing) (T4 0.000225/s, L40S 0.000975/s, A100-80 0.0014/s, H100 0.001525/s); Tripo [pricing](https://developers.tripo3d.ai/en/pricing) (packs from 1 USD), [billing](https://developers.tripo3d.com/en/docs/billing) ("Failed and cancelled tasks are not charged"), [rate limits](https://developers.tripo3d.ai/en/docs/rate-limits) (10 concurrent, 429 with `Retry-After`); Meshy [API pricing](https://docs.meshy.ai/en/api/pricing), [plans](https://help.meshy.ai/en/articles/12062933-what-are-your-prices-and-plans-offered-and-do-you-have-monthly-annual-plans), [latency](https://docs.meshy.ai/en/api/task-lifecycle); Tencent [billing](https://www.tencentcloud.com/document/product/1284/75281), [free credits](https://www.tencentcloud.com/document/product/1284/75287), [Pro submit](https://www.tencentcloud.com/document/product/1284/75540), [Pro query](https://www.tencentcloud.com/document/api/1284/75542); [Sloyd](https://www.sloyd.ai/api/pricing). Gone or irrelevant: Rodin direct API needs Business at 120/month ([pricing](https://hyper3d.ai/pricing)); CSM acquired by Google 2026-01-27 ([release](https://www.gunder.com/en/news-insights/client-news/gunderson-dettmer-represents-common-sense-machines-in-acquisition-by-google)), csm.ai dead; Luma Genie [unverified sunset]; Edify NIM retired 2025-06-06 ([blog](https://blogs.nvidia.com/blog/edify-3d-generative-ai-custom-fine-tuning/)).

The two calls that matter. fal TRELLIS, from its sheet:

```python
import fal_client  # FAL_KEY in env
r = fal_client.subscribe("fal-ai/trellis", arguments={
    "image_url": url, "texture_size": 1024, "mesh_simplify": 0.95,
    "ss_sampling_steps": 12, "slat_sampling_steps": 12})
glb = r["model_mesh"]["url"]
```

Tripo v3 (base `https://openapi.tripo3d.ai/v3`, `Authorization: Bearer`), from [image-to-model](https://developers.tripo3d.ai/en/docs/generation-image-to-model/standard), [text-to-model](https://developers.tripo3d.ai/en/docs/generation-text-to-model/standard), [task query](https://developers.tripo3d.ai/en/docs/task-query):

```bash
curl -X POST https://openapi.tripo3d.ai/v3/generation/image-to-model -H "Authorization: Bearer $TRIPO_KEY" \
  -H "Content-Type: application/json" -d '{"input":"https://…/tankard.png","model":"v3.1-20260211",
  "texture":true,"pbr":true,"texture_quality":"standard","face_limit":30000,"auto_size":true}'
# text: POST /v3/generation/text-to-model {"prompt":"…","model":"v3.1-20260211","texture":true,"pbr":true}
# poll: GET /v3/tasks/{task_id} → data.status success, data.output.model_url (expires in 5 min), data.credits_consumed
```

`delight` needs `texture_version: "v3.5-20260815"` ([texture](https://developers.tripo3d.ai/en/models/texture)); the legacy `POST https://api.tripo3d.ai/v2/openapi/task` still runs beside v3 ([migration](https://developers.tripo3d.com/en/docs/migration-v2-to-v3)) **[docs]**.

## 2. Open weights on Modal, cheapest first

Modal per second ([pricing](https://modal.com/pricing)) **[docs]**: T4 0.000164 (0.59/h), L4 0.000222 (0.80), A10 0.000306 (1.10), L40S 0.000542 (1.95), A100-80 0.000694 (2.50), H100 0.001097 (3.95); 30 USD/month Starter credit. Billing "covers application load time" and the 60 s idle tail ([cold start](https://modal.com/docs/guide/cold-start)); Volumes are "designed for up to 2.5 GB/s" ([volumes](https://modal.com/docs/guide/volumes)), so a 16 GB weight read is seconds and CUDA init dominates **[est]**; snapshots "don't speed up loading weights from storage" ([snapshots](https://modal.com/docs/guide/memory-snapshot)) **[docs]**. `pipeline/modal/run_episodes.py` already turns a USD budget into a container timeout and caches weights in the `zumi-models` Volume **[in-house]**.

| Model | Min Modal GPU | VRAM stated | Time per mesh stated | USD per mesh [est] | Texture | Weights | Licence | Quality |
|---|---|---|---|---|---|---|---|---|
| SF3D | T4 | "about 6GB" | "0.5 seconds" | < 0.001 | delit albedo + material, GLB, remesh | 4.0 GB, gated | Stability Community (< 1M USD revenue) | ELO 1190 |
| SPAR3D | T4 | 10.5 GB (7 low) | "0.7 seconds" | < 0.001 | yes, GLB | 7.3 GB, gated | same | ELO 1144 |
| InstantMesh | T4 [est] | not stated | "within 10 seconds" | 0.002 | vertex colour or UV map, OBJ | 3.2 GB subset | Apache-2.0 | ELO 1278 |
| Unique3D | L4 [est] | not stated | "30 seconds" | 0.007 | textured | — | MIT | ELO 1230 |
| TRELLIS (v1) | L4 | "at least 16GB" | not stated; Replicate A100 ~29 s | ~0.01 on L4 | baked texture, GLB, `simplify`, `texture_size` | — | MIT | ELO 1306 |
| Hunyuan3D-2 | L4 | "6 GB … 16 GB for shape and texture" | ~35 s on a 4090 [secondary] | 0.01–0.02 | RGB texture, GLB/OBJ | subset of a 74.9 GB repo | Tencent 2.0 Community; AR fine | ELO 1298 |
| **TRELLIS.2-4B** | **L40S** (A10 OOMs at 1024) | "at least 24GB" | H100 3 / 17 / 60 s | 0.02–0.03 at 1024 on L40S if 2–3× slower than H100; 0.019 on H100 | PBR base/rough/metal/opacity, GLB, `decimation_target`, `texture_size` 4096 | 16.2 GB | MIT | 66.5% pref vs Hunyuan 2.1 |
| Hunyuan3D-2.1 | L40S | 10 / 21 / 29 GB | ~80 s on a 4090 [secondary] | 0.04–0.06 | PBR, GLB | 14.9 GB | Tencent 2.1 Community | — |
| Step1X-3D | L40S | 27–29 GB | 152 s (GPU unnamed) | 0.08 | textured GLB | 19.6 GB | Apache-2.0 | — |
| TripoSG + MV-Adapter | T4 + L4 | ≥ 8 GB; i2mv "about 14G" | not stated | — | geometry GLB (`--faces`); then shaded GLB | 8 + 3.6 GB + SDXL | MIT / Apache-2.0 | — |
| Direct3D-S2, Hi3DGen | T4 / L40S | 10 GB at 512, 24 GB at 1024; not stated | not stated | — | geometry only | 8.5 / 2.7 GB | MIT | 1207 (Hi3DGen) |
| Pixal3D | L40S / H100 [est] | not stated; `--low_vram` → 1024 | not stated | — | PBR GLB | 46 GB | MIT | sets note |
| LGM, Idol, SAM 3D Objects | T4 / L4 | 10 / 7.2 GB | 5 s / L4 54.6 s | < 0.001 / 0.012 | Gaussian splats, no mesh | — | MIT / Apache / SAM | wrong output |

Sources (READMEs) **[docs]**: [SF3D](https://github.com/Stability-AI/stable-fast-3d), [SPAR3D](https://github.com/Stability-AI/stable-point-aware-3d), [Stability licence](https://raw.githubusercontent.com/Stability-AI/stable-fast-3d/main/LICENSE.md), [InstantMesh](https://github.com/TencentARC/InstantMesh), [Unique3D](https://github.com/AiuniAI/Unique3D), [TRELLIS](https://github.com/microsoft/TRELLIS), [Hunyuan3D-2](https://github.com/Tencent-Hunyuan/Hunyuan3D-2), [Hunyuan3D-2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1), [Step1X-3D](https://github.com/stepfun-ai/Step1X-3D), [TripoSG](https://github.com/VAST-AI-Research/TripoSG), [MV-Adapter](https://github.com/huanngzh/MV-Adapter), [Direct3D-S2](https://github.com/DreamTechAI/Direct3D-S2), [Hi3DGen](https://github.com/Stable-X/Hi3DGen), [Pixal3D](https://github.com/TencentARC/Pixal3D), [Idol](https://huggingface.co/speridlabs/idol), [SAM 3D Objects](https://github.com/facebookresearch/sam-3d-objects). ELOs are the 3D Arena paper's May 2025 snapshot; the live leaderboard API returned 404 today, so TRELLIS.2's current ELO is **[unverified]** though it is in the arena dataset ([dataset](https://huggingface.co/datasets/3d-arena/3d-arena)).

Free texturing for a geometry-only mesh (MV-Adapter "about 14G", Paint3D "lighting-less… 2K UV texture maps", TEXTure, Hunyuan3D-Paint 2.1 at 21 GB, UniTEX; [Paint3D](https://github.com/OpenTexture/Paint3D), [UniTEX](https://github.com/YixunLiang/UniTEX)) publishes no seconds per mesh and is more engineering than TRELLIS.2 alone **[docs/est]**. 2026 open releases checked: Hi3D v1.0 (2026-10-23, geometry refiner, "No textures", validated on a 96 GB H20 ([card](https://huggingface.co/hi3d-official/Hi3Dv1.0))), Idol (Gaussians), Hunyuan3D-Omni and -Part, PartCrafter; Hunyuan3D 3.x has no open weights **[docs]**. Nothing beats TRELLIS.2 on textured single-image props.

## 3. Stylised output

- **No style parameter anywhere current.** Tripo v3 lists `texture_quality`, `geometry_quality`, `smart_low_poly`, `quad`, `face_limit`, `delight`, `texture_alignment: original_image | geometry`, nothing for style ([image-to-model](https://developers.tripo3d.com/en/docs/generation-image-to-model)); the v2 `style: cartoon | clay…` enum survives only in third-party wrappers [unverified on v3]; Tripo's stylize task is lego/voxel/voronoi geometry **[docs/secondary]**. Meshy offers prompt recipes instead ("cel shaded, anime art style, sharp lines, vibrant colors, clean edges, stylized") ([help](https://help.meshy.ai/en/articles/11972484)) **[vendor]**. Tencent's product page promises "texture style selection" but the API has no field ([strengths](https://www.tencentcloud.com/document/product/1284/75278)); Rodin's "Sketch" is a quality tier ([features](https://docs.hyper3d.ai/en/get-started/features)) **[docs]**.
- **Open models**: Step1X-3D's README shows "cartoon-style, sketch-style" results, but its LoRA labels are symmetry and sharp/normal/smooth, not style ([paper §5.2](https://arxiv.org/html/2505.07747)) **[docs]**; TripoSG "handles… cartoons, and sketches", geometry only **[vendor]**; TRELLIS.2 was evaluated on "100 AI-generated image prompts" **[docs]**. CharacterGen, StdGEN, DrawingSpinUp are character models.
- **Drawn input**: Art3D (flat colour → implausible geometry; re-shade first), DrawingSpinUp ("contour lines… introduce significant ambiguity in texture synthesis"; remove contours first) ([paper](https://arxiv.org/abs/2409.08615)), Meshy's guide (shadows → "Black patches", strong perspective hurts) ([guide](https://docs.meshy.ai/en/webapp/image-to-3d)) **[docs]**.

So the look is made outside the 3D model:

1. **The concept image**: a shaded painterly 3/4 view on a plain background in the comic's palette, from FLUX.2 [klein] 4B (0.014 per MP) or FLUX.2 [pro] with the panel crop as reference (0.03 + 0.015/MP) ([BFL pricing](https://bfl.ai/pricing)); fal `flux/schnell` is 0.003/MP ([sheet](https://fal.ai/models/fal-ai/flux/schnell)) **[docs]**. The crop is the reference, not the input: flat, inked and in cheated perspective, the three documented failure causes. Then image-to-3D with colour-faithful settings: Tripo `texture_alignment: original_image`, `delight: false`; Meshy `image_enhancement: false`; fal TRELLIS has no switch **[docs]**.
2. **Post-process**, per prop **[est]**: (a) posterise the de-lit base colour (Tripo `delight`, Meshy `remove_lighting`, SF3D) and write `KHR_materials_unlit`, whose spec names "Stylized materials (such as 'anime' or 'hand-drawn' looks)" as its use case ([KHR_materials_unlit](https://github.com/KhronosGroup/glTF/tree/main/extensions/2.0/Khronos/KHR_materials_unlit)): free, seconds **[docs]**; (b) AI retexture with a style prompt or image: Tripo `POST /v3/models/texture`, 10 credits = 0.10, `texture_prompt.text` + `style_image`, `delight: false` ([texture](https://developers.tripo3d.com/en/docs/models-texture)); Meshy Retexture 10 credits ≈ 0.20 ([retexture](https://docs.meshy.ai/en/api/retexture)) **[docs]**; open SyncMVD or Paint3D on an L4, 1–5 min, 0.02–0.10; (c) the sets note's Blender bake-to-unlit, ~1–2 min on an L4 ≈ 0.02; (d) runtime toon in the reader (three.js `MeshToonMaterial`; Unity Toon Shader 0.11 for URP ([UTS](https://docs.unity3d.com/Packages/com.unity.toonshader@0.11/manual/index.html))), free, a shader on Quest **[docs]**.

## 4. A test plan under 2 USD

Props: a pewter tankard with a hinged lid, a fat tavern candle on a pewter plate, an ornate bearded axe with glowing runes. Inputs: one text brief per prop (the vision pass's description plus "hand-painted, stylised, soft shading, 3/4 view, plain background"), one concept image per prop from that brief, and for the tankard the panel crop with alpha, to measure the flat-input failure directly.

| Route | Calls | Cost [est] | What it answers |
|---|---|---|---|
| A. BFL FLUX.2 klein 4B → fal `fal-ai/trellis` | 3 images + 4 meshes (3 concepts + the crop), `texture_size 1024`, `mesh_simplify 0.95` | 3 × 0.014 + 4 × 0.02 = **0.12** | is a 0.02 mesh usable at all |
| B. Tripo H3.1 direct | 3 text (20 cr) + 3 image (30 cr), `pbr, auto_size, face_limit 30000, texture_version v3.5-20260815, delight` | **1.50** (0 if the 2,000-credit grant exists) | the hosted reference; `auto_size`; `delight` |
| C. Stability SPAR3D | 4 images, `target_type face, target_count 20000`, 4 cr each on the 25 free credits | **0** | sub-second draft quality |
| D. TRELLIS.2 on Modal L40S (optional) | one container, 4 images at 1024³, `decimation_target 30000` | ~0.25 of the 30 USD Modal credit, outside the API cap | the open route's quality and the real L40S seconds |

Paid total 1.62 USD; each call goes through `spend.reserve(0.02 | 0.30 | 0.014, …)` **[in-house]**. Run A and C first (0.12), judge, then B only if A fails the checks.

Acceptance per GLB, scripted: loads in three.js GLTFLoader 0.160 (the page's loader) without console errors; triangles ≤ 50k (`gltf-transform inspect`); `baseColorTexture` on every material (B also metallic-roughness and normal); no background slab (bounding-box depth/width ≥ 0.3, no planar face cluster over 20% of the area, checked hardest on the crop); scale in metres (B via `auto_size`; the rest normalise to a unit box, so scale from the brief: tankard 0.18 m, candle and plate 0.15 m, axe 0.8 m, as the page's `SCALE` map does today); +Y up; ≤ 5 MB. Side by side: the GLBs go to `pipeline/.data/out/set_preview/props/` as `tankard_trellis.glb`, `tankard_tripo.glb`, `tankard_spar3d.glb` and `_crop` variants; the page's `load(name)` reads `props/<name>.glb`, so a sibling copy of `index.html` under `set_preview/review/` (the page itself untouched) lists the variants on the table top at the same `pos`, same `RoomEnvironment` light and GTAO, next to the dropped primitives. Score each prop per route: usable, fixable with a repaint, reject.

## 5. Recommendation

**Adopt**: concept image on the BFL API already in the pipeline (FLUX.2 [klein] 4B, 0.014) → `fal-ai/trellis` (0.02) → local decimation and posterise-to-unlit when the comic is flat. ~0.035 per prop, ~0.3 per setting of 8, two REST calls behind the existing `spend` guard, hours of work **[est]**; an order of magnitude cheaper than anything else that returns a textured GLB, MIT model, arena record above Hunyuan3D-2.

**Fallback**: Tripo H3.1 image-to-model at 0.30 (PBR, `auto_size` to metres, `delight`, `face_limit`, `smart_low_poly` +0.10), no subscription, 10 concurrent, failed tasks free, for the props TRELLIS gets wrong or when PBR matters; text-to-model at 0.20 when there is no reference at all.

**Step up** when volume or quality demand it: TRELLIS.2 on an L40S, one container per episode, ~0.03 per prop amortised, the best-rated open model, 1–2 days on the existing Modal runner; or fal `trellis-2` at 0.30 with `decimation_target` if the engineering is not worth it.

Risks: (1) vendor churn: fal's 0.02 TRELLIS is a 2024 model fal could retire or reprice; keep the Tripo adapter alive and the TRELLIS.2 path documented. (2) Licence: fal's ToS assigns no output rights; Tripo gives "Free Users" nothing, so buy the 1 USD pack first; Tencent's clause spares Argentina but not an EU collaborator. (3) Cold starts: a Modal batch pays ~1–2 min of L40S per episode (~0.05); never generate per prop. (4) Stylised input: flat colour degrades geometry (Art3D), ink enters the texture (DrawingSpinUp); always go through a shaded concept image and de-light before posterising. (5) Scale: only Tripo sizes in metres; the vision pass must emit a size per prop.

## Open questions

- Tripo's free API grant (2,000 credits on a blog page that returned 403) and fal's signup credit: both **[unverified]**; the plan assumes neither.
- fal TRELLIS's texture type (baked RGB) and whether `model_mesh` is always GLB: the sheet's example shows a PNG content type; confirm on the first call.
- TRELLIS.2's real L40S seconds at 1024³, and whether `low_vram` lets a 24 GB L4 run it: only H100 timings and the A10 OOM report exist.
- Whether unlit props read well beside PBR library assets in the same room, or the whole set must be unlit.
