# Step 0 research: from pencil pages to finished colour pages

Read on 2026-11-11. Tags: **[docs]** read in the linked primary source, **[est]** my inference or arithmetic, **[unverified]** seen only in a search snippet or secondary page. All prices were read on 2026-11-11; the vendors' price pages carry no revision date.

## Ranked shortlist

The evidence points one way. No generative model, research or commercial, guarantees that lines stay put or that a colour is exact. Guarantees have to come from construction: the pencil supplies the line layer, a palette table supplies the colours, and the model supplies only proposals (which colour goes where, and where the shadows fall).

**1. Layered "colourist" pipeline with a hosted edit model as proposer.**
What: (a) ink layer derived from the pencil itself by a per-pixel filter; (b) one call to a multi-reference edit model with the bible sheets as references, used only as a colour and light proposal; (c) the line art is cut into regions, each region takes the nearest bible colour of its character; (d) shading is taken as the ratio proposal / flat, smoothed, and multiplied back; (e) ink multiplied on top, lettering restored.
Needs: region segmentation that survives gaps; a per-figure identity decision; a bible with indexed palettes.
Guarantees **[est]**: lines, layout, lettering (they never pass through the model); every flat colour is a bible value. Only likely: the right character per figure, the right palette entry per region, shading quality.
Cost: $0.009 per 1K panel with FLUX 3 Image Klein, references free, or $0.0168 with Nano Banana 2.1 in batch **[docs]** ([BFL pricing](https://bfl.ai/pricing), [Gemini pricing](https://aistudio.google.com/docs/pricing)).
Main risk: the proposal drifts from the pencil geometry, so its shading does not sit under the original lines. Cannot guarantee constraint 3 at the "which character" level.

**2. Same pipeline, local research colouriser as proposer** (Cobra, MangaNinja, or the FLUX.2 klein 9B manga-colourisation LoRA).
Needs: 6 to 10 GB VRAM; line art close to what they were trained on (lines extracted from finished art).
Guarantees: as in 1. Cost: zero API. Main risk: none was tested on pencils; resolution is 512 to 1024; licences are non-commercial (MangaNinja CC BY-NC, klein 9B base). Cannot guarantee identity.

**3. Paint-bucket segment matching from the colour sheet** (inclusion matching: BasicPBC keyframe model, DACoN) as the assignment step.
What: each closed line-art segment is matched to a segment of the coloured design sheet and takes its colour index. Exact colours by construction.
Needs: closed regions, one design sheet per character, a figure crop per character.
Only likely: segment accuracy is about 68 to 74 % on keyframes (pixel accuracy 97 %) **[docs]** ([DACoN](https://arxiv.org/html/2509.14685v1)). No shading, no backgrounds, single characters only.
Cost: zero API, about 3 to 6 GB. Main risk: pencils are not closed line art. Use it as a second opinion inside 1, not alone **[est]**.

**4. Direct multi-reference edit, then re-composite the pencil ink and lettering on top.**
What: one call, the model colours and shades the whole panel; the original lines are multiplied back.
Guarantees: lettering and the ink layer only. Colours are approximate; the design may change underneath the lines (double contours).
Cost: $0.009 to $0.134 per panel **[docs]**. Main risk: fails constraints 1 and 3 silently. Useful as the baseline to beat.

**5. Per-series LoRA** (style plus characters) on an open edit model, added to 1 or 2.
Needs: FLUX.2 klein 4B Base trains on 12 GB in 1 to 3 hours **[docs]** ([BFL training guide](https://docs.bfl.ai/flux_2/flux2_klein_training.md)); or about $13 to $26 hosted (1,500 to 3,000 steps at $0.0086 per step **[unverified]**, [fal trainer](https://fal.ai/models/fal-ai/flux-2-klein-9b-base-trainer/llms.txt)).
Guarantees nothing; raises the proposer's hit rate. Main risk: a bible of a few sheets is far below the 15 to 30 varied images community guides ask for **[unverified]**; overfits to sheet poses.

**6. Learned layer decomposition after generation** (line / flat / shadow / highlight) to swap flats for palette values.
Needs: a large GPU; about 2 minutes per image **[docs]** ([arXiv 2603.14925](https://arxiv.org/html/2603.14925)).
Guarantees nothing: recomposition is PSNR 27.8, not exact. Main risk: cost and speed. The ratio trick in 1(d) is the cheap substitute; keep this as fallback.

## 1. Reference-based line-art colourisation, 2024-2026

| Method | Input and references | Which reference goes to which figure | Release, licence, size | Stated failures |
|---|---|---|---|---|
| [MangaNinja](https://arxiv.org/html/2501.08332v1) (CVPR 2025) | Lines from LineartAnimeDetector on finished frames; one reference, or several pasted together | User-clicked point pairs; nothing automatic | Code and weights, [CC BY-NC 4.0](https://github.com/ali-vilab/MangaNinjia), SD 1.5, 512×512, a port runs in 6 GB | Points work only where the model "is aware of local semantics"; expects grey float lines, binarised lines need a fine-tune |
| [ColorFlow](https://arxiv.org/html/2412.11815) (2024/25) | B&W manga, line art; a pool of colour pages | CLIP patch retrieval, top 3 patches per quarter of the page; no explicit instance mapping | [Inference code and weights](https://github.com/TencentARC/ColorFlow), incl. a sketch model; licence text not read; SD 1.5, trained 512×800, tested to 1280×2000 | Depends on the reference pool; 36.4 GB with 12 references per [Cobra's table](https://arxiv.org/html/2504.12240v1) |
| [Cobra](https://arxiv.org/html/2504.12240v1) (SIGGRAPH 2025) | Line art plus optional colour hints; 3 to 36 references evaluated, "over 200" claimed | Retrieval per patch, attention does the rest | PixArt-Alpha plus LoRA, 640×1024, 9.3 GB and 0.31 s per step set with 12 references; [weights](https://huggingface.co/JunhaoZhuang/Cobra), licence **[unverified]** | "Fails to generalize when references depict different characters" |
| [Follow-Your-Color / MagicColor](https://arxiv.org/html/2503.16948v2) (2025) | Line art plus N instance references **with masks** | By instance mask and box; who pairs them at inference is not stated | SD 1.5, 512; [weights released 2025-06-27](https://github.com/ari185/MagicColor) **[unverified]** | Many objects or occlusion: "inter-object colors may not be well maintained" |
| [MangaDiT](https://arxiv.org/html/2508.09709v1) (2025) | Extracted line art plus one reference | None; built for one character | FLUX.1-dev LoRA; code promised, not released | Struggles "where the line art does not clearly convey the underlying semantics"; small reference regions |
| [BasicPBC](https://github.com/ykdai/BasicPBC), [design-sheet version](https://arxiv.org/html/2410.19424v1), [DACoN](https://arxiv.org/html/2509.14685v1) | Closed segments; a coloured sheet or frame; 1 to 16 references | Segment-to-segment matching; single character | S-Lab non-commercial; DACoN code public, 3 to 6 GB | New segments, extreme poses, cropped bodies, tiny segments |
| [AniDoc](https://github.com/yihao-meng/AniDoc) (CVPR 2025) | 14-frame sketch video plus one character design | Automatic, single character | Apache-2.0, 14 GB | Video tool, not a page tool |
| [FLUX.2 klein 9B manga colourisation LoRA](https://huggingface.co/milo01/FLUX.2-klein-9B-manga-colorization-by-reference-LORA) (community, 2026) | B&W page plus one colour reference that may hold several characters | Automatic, undocumented | LoRA Apache-2.0, base under the FLUX non-commercial licence | No evaluation published |

All rows **[docs]** except where marked. Three findings matter here.

- **Nobody evaluated on rough pencils.** Training and test lines are extracted from finished colour art. The one hand-drawn test I found: Follow-Your-Color drops from PSNR 23.8 / FID 29 on animation frames to PSNR 10.6 / FID 251 on 100 real user sketches **[docs]** ([paper](https://arxiv.org/html/2503.16948v2)). Expect a large gap on pencils **[est]**.
- **No method decides identity for you.** It is clicked points (MangaNinja), supplied masks (Follow-Your-Color), or implicit attention (ColorFlow, Cobra). ColorFlow reports 97 % top-1 retrieval on grey images **[docs]**, but on 10 well-separated anime characters; your measured 70 % on line-only crops is the harder, more relevant number **[est]**.
- **2026 successors**: only [InstanceAnimator](https://arxiv.org/html/2603.25357v1) (March 2026, multi-instance sketch video) surfaced **[unverified]**. I found no 2026 page-level manga method. LVCD, ToonCrafter, AnimeColor and ColorizeDiffusion were not read in primary sources; ColorizeDiffusionXL weights are CC BY-NC-SA **[unverified]** ([card](https://huggingface.co/tellurion/ColorizeDiffusionXL/blob/main/README.md)).

## 2. Sketch cleanup and inking

- [Simo-Serra et al.](https://github.com/bobbens/sketch_simplification) is still the reference raster cleaner: code and models free for non-commercial use, Torch7 models loaded through legacy PyTorch **[docs]**. It redraws the image; it gives no bound on line displacement **[est]**.
- The [rough-sketch cleanup benchmark](https://cragl.cs.gmu.edu/sketchbench/) (Yan et al., 2020): 281 wild rough sketches, artist-made clean versions for 101, and it "identifies shortcomings among state-of-the-art cleanup algorithms" **[docs]**.
- 2024-2026 diffusion work is adjacent, not on target: SketchRefiner (TVCG 2025, text-guided refinement) and CoProSketch (generation) **[unverified]** ([search hit](https://doi.org/10.1109/tvcg.2025.3613388), [arXiv 2504.08259](https://arxiv.org/abs/2504.08259)).
- **I found no method with a fidelity guarantee** (lines only removed or thinned, never moved).
- The guarantee can be built **[est]**: use any cleaner only as a mask over the original pencil pixels. Final ink = pencil darkness where the mask says "line", white elsewhere, then a levels curve. Strokes can vanish or thin; none can move or appear. The price: line weight stays the pencil's; a true re-ink (new stroke weight) is outside any guarantee.

## 3. General image-editing models today

| Model | References | Consistency documented? | Structure lock | Price per image | Open weights on 12 GB |
|---|---|---|---|---|---|
| [FLUX 3 Image Klein](https://huggingface.co/black-forest-labs/flux-3-image-klein) | up to 10 | No; "reference images anchor content, they do not lock structure" | Boxes on a 0-1000 grid, "not hard masks, and edits can change content outside the requested region" | [$0.009 at 1K, $0.014 at 2K, references free](https://bfl.ai/pricing) | 5.6 B, Kommunity licence (free commercial under $5M revenue); card shows 25 to 31 GB peak; 8 GB INT8 claimed by press **[unverified]** ([VentureBeat](https://venturebeat.com/technology/black-forest-labs-opens-flux-3-image-klein-weights-with-free-commercial-use-limited-to-smaller-businesses)) |
| FLUX 3 Image | same family | same | same | [$0.048 at 1K](https://bfl.ai/pricing) | hosted |
| [FLUX.2 klein 4B / 9B](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B) | [8 by API](https://docs.bfl.ai/flux_2/flux2_image_editing); klein 4 **[unverified]** | Not on the editing page | None official; community [lineart-plus-reference LoRA](https://huggingface.co/thedeoxen/refcontrol-FLUX.2-klein-9B-reference-lineart-lora) for 9B | [$0.014 / $0.015 first MP, plus $0.001 / $0.002 per reference MP](https://bfl.ai/pricing) | 4B Apache-2.0, about 13 GB; 9B non-commercial |
| FLUX.1 Kontext pro / max | not read | not read | none | [$0.04 / $0.08](https://bfl.ai/pricing) | superseded |
| [Nano Banana 2.1](https://aistudio.google.com/docs/image-generation) | 14 total: 10 objects, 4 characters | Yes: character references "maintain character consistency" | none documented | [$0.0336 at 1K; batch $0.0168](https://aistudio.google.com/docs/pricing) | no |
| Nano Banana Pro | 6 objects, 5 characters, 3 style | Yes | none | [$0.134 at 1K/2K](https://aistudio.google.com/docs/pricing) | no |
| [gpt-image-2.6](https://developers.openai.com/api/docs/pricing) (flare, sunburst) | at least 4 shown; maximum not found | not found | Mask is "guidance, but may not follow its exact shape" ([guide](https://developers.openai.com/api/docs/guides/image-generation)) | Token-billed: $8 per M image-input, $30 per M image-output tokens; per-image figure not read | no |
| [Qwen-Image-Edit-2511](https://huggingface.co/Qwen/Qwen-Image-Edit-2511) | multi-image, maximum not stated | "character consistency has been significantly improved" | [Union ControlNet](https://huggingface.co/InstantX/Qwen-Image-ControlNet-Union) for base Qwen-Image: canny, soft edge, depth, pose; no lineart **[unverified]** | hosted price not read | Apache-2.0; 12 GB fit **[unverified]** |
| Seedream 5.0 Pro | not read | not read | not read | $0.045, extra references $0.003 **[unverified]**, resellers only ([one](https://www.atlascloud.ai/blog/ai-updates/seedream-5-0-pro-price)) | no |

Rows **[docs]** unless marked. Notes:

- **No vendor documents a "colour only, keep these exact lines" mode.** Every structural input is described as guidance. I found no benchmark of these models on line-art colourisation. The nearest evidence: [PaintBench](https://arxiv.org/abs/2606.00188) (2026), 11 editing models on precise edits scored per pixel, best model 17.1 % mIoU **[docs]**. Exact, pixel-true editing is where these models are weakest; treat any output as approximate geometry **[est]**.
- A possible newer open Qwen-Image release in September 2026 is **[unverified]** ([secondary](https://invideo.io/blog/qwen-image-ai-generator/)).
- Arithmetic **[est]**: 100 panels a day cost $0.90 on FLUX 3 Klein at 1K, $1.68 on Nano Banana 2.1 batch, $3.36 at its standard rate, $13.40 on Nano Banana Pro.

## 4. Flatting

- Practice: flat, anti-alias-free colour regions under a multiplied line layer, rendering on separate layers above. [FlatMagic](https://cragl.cs.gmu.edu/flatmagic/) (CHI 2022) names flatting the labour bottleneck and automates it with a "bucket then tweak" interaction; it "significantly reduced professionals' real and perceived effort", and no code is linked **[docs]**.
- [G'MIC Smart Coloring](https://gmic.eu/reference/scientific_publications.html) (Fourey, Tschumperlé, Revoy, VMV 2018): open source, fills every region with random or user-spotted colours, handles anti-aliased lines and tries to close open regions **[unverified]** (the paper PDF did not parse).
- [Krita colorize mask](https://docs.krita.org/en/reference_manual/tools/colorize_mask.html): user key strokes, blur prefilter plus "gap close hint" ("a too high value can lead to other errors"), and "the colorize mask algorithm is slow" **[docs]**. Its LazyBrush origin is **[unverified]**.
- [Clip Studio Colorize](https://tips.clip-studio.com/en-us/articles/3167): server-side, technology preview, hint colours optional, at most 10 colours analysed, results need correction and drift pastel **[docs]**. It has no notion of a character or a bible **[est]**.
- Gaps: every tool closes them heuristically (trapped-ball in [BasicPBC](https://github.com/ykdai/BasicPBC), blur in Krita). None guarantees a leak-free region **[docs]**.
- Propagating flats by region matching exists, but for animation, not across unrelated panels: consecutive-frame accuracy is 85 to 87 % of segments, and it "requires that all segments in the target frame also appear in the reference frame" **[docs]** ([DACoN](https://arxiv.org/html/2509.14685v1), [design-sheet paper](https://arxiv.org/html/2410.19424v1)).
- "Flatting by region merging": I found no paper under that name. Split Filling (CVPR 2021) is the closest user-guided method **[unverified]** ([page](https://lllyasviel.github.io/SplitFilling)).

## 5. How consistency is enforced in practice

- **I found no published studio account or paper with measurements over hundreds of panels.** The results are vendor blogs and one-person write-ups.
- One developer reports hair-colour drift of 9 per 100 panels with a LoRA setup against 2 with fixed prompt slots plus references **[unverified]**, anecdote ([post](https://dev.to/qcrao/character-consistency-in-ai-comics-3-tricks-that-beat-lora-training-for-me-3ad7)).
- LoRA: BFL gives 1,500 to 3,000 steps for a character and asks for varied poses and angles, with no image count **[docs]** ([guide](https://docs.bfl.ai/flux_2/flux2_klein_training.md)). A LoRA from a handful of approved sheets is untested territory **[est]**.
- Reference conditioning is now built into the edit models (section 3), which replaces IP-Adapter for this use **[est]**.
- Palette locking after generation: no primary source describes it for comics. It is plain image processing and is the only step here that turns "likely" into "exact" **[est]**.

## 6. Splitting flat colour from shading

- [Workflow-Aware Structured Layer Decomposition](https://arxiv.org/html/2603.14925) (March 2026): line, flat, shadow, highlight from one illustration; Qwen-Image-Layered plus LoRA; [code](https://github.com/zty0304/Anime-layer-decomposition), licence not stated; 768×1152; about 2 minutes per image on an RTX PRO 6000; recomposition PSNR 27.8, errors in small parts "such as the eyes" **[docs]**. The authors say physical intrinsic decomposition fails on cel shading **[unverified]**.
- Nothing else with released code for cartoon art surfaced.
- Cheap substitute **[est]**: with known flats, shading = proposal ÷ flat per region, clamped and blurred; final = palette flat × shading. This keeps the model's light and discards its colours. It breaks where the region map is wrong.

## 7. Evaluation

- **Line preservation**: no paper measures it directly. They report PSNR, SSIM, MS-SSIM, LPIPS against the colour original ([MangaNinja](https://arxiv.org/html/2501.08332v1), [Cobra](https://arxiv.org/html/2504.12240v1)) **[docs]**. For this project, compare edges of the output with the ink layer: chamfer distance and edge F-score at a 1 to 2 px tolerance **[est]**.
- **Colour fidelity per region**: MSE on 3×3 patches at 50 annotated point pairs ([MangaNinja](https://arxiv.org/html/2501.08332v1)); MSE_CR over segmented colour regions ([MangaDiT](https://arxiv.org/html/2508.09709v1)); segment metrics Acc, Acc-Thres (segments over 10 px), Pix-Acc, Pix-F-Acc, Pix-B-MIoU ([paint-bucket papers](https://arxiv.org/html/2410.19424v1)) **[docs]**. The paint-bucket metrics fit a palette-index pipeline directly **[est]**.
- **Consistency across pages**: CLIP image similarity, DINO similarity, FID, and user-study votes on "color ID consistency" (Cobra won 79.1 %) **[docs]**. No automatic per-character metric exists; per-character ΔE against the bible is the obvious one **[est]**.
- **Benchmarks**: [ColorFlow-Bench](https://arxiv.org/html/2412.11815) (30 chapters, 50 pages and 40 references each), Cobra-Bench (30 chapters, 100 references), PaintBucket-Character (3,000 rendered plus 200 hand-drawn frames, not downloadable) **[docs]**. **None has pencil input.** The only rough-input sets are the [cleanup benchmark](https://cragl.cs.gmu.edu/sketchbench/) (no colour) and Follow-Your-Color's 100 user sketches.

## Three tests on five real pencil pages that decide the architecture

1. **Geometry drift of the proposer.** Run FLUX 3 Klein, Nano Banana 2.1 and one local colouriser (Cobra or the klein LoRA) on the cleaned pencils. Measure edge displacement between each output and the pencil ink. Under about 2 px: the proposal's shading can sit under the original lines (approach 1 or 2 holds). Above: the model can vote on colours only, and shading needs another source.
2. **Region closure on pencils.** After the mask-only cleanup, segment with trapped-ball and G'MIC. Count regions that leak or shatter (hatching, open strokes). Low leak rate: per-region palette snapping gives exact flats. High: fall back to per-pixel soft snapping, which weakens "exact colours" at edges.
3. **Who is who, before and after colour.** For every figure, record the character chosen (a) from the line crop, (b) by the proposer given all sheets, (c) from the proposal's colours, (d) by DACoN-style segment matching. If (b) or (c) clearly beats the 70 % line baseline, identity can emerge from the proposal and be confirmed by vote. If not, identity must be fixed first (story context, boxes or masks per figure) and passed to the proposer, and small figures need their own crops.
