# Scene layers: single-image to ordered RGBA layers (state of the art, Oct 2026)

Question: can a model take one comic panel and return the scene (everything except characters and
lettering, which we already cut out) as 2-8 whole, ordered RGBA layers, in any environment, on an
RTX 3060 12 GB, preferably under a permissive licence?

Scope: literature and model releases only, nothing was run. Figures are quoted from the cited page.
Anything marked **[estimate]** is my reasoning, not a measurement. **[unverified]** means I found
no primary source for it.

## Bottom line

- **Only one released, permissive, general-domain model decomposes an image straight into N
  ordered RGBA layers: Qwen-Image-Layered** (Alibaba Qwen, Apache-2.0, Dec 2025, CVPR 2026). It is
  20B parameters, so on 12 GB it needs FP8/GGUF plus CPU offload and will take minutes per panel.
  It is the first thing to test.
- The stronger 2026 successors (MRT, RevealLayer, RefLayer, PixelART) have **no released weights**.
- **No paper evaluates scene/background decomposition on comics or webtoons.** The two anime papers
  handle characters (See-through) or render passes like lineart and shadow (Workflow-Aware), not
  scenery.
- Most of the field trains on **graphic-design PSDs** (Crello and similar), so its layers follow
  editing logic (text, shapes, photo) rather than depth. Plan to order layers by DA3 depth ourselves
  instead of trusting the model's stack order as depth.

## What Zumi needs from a layer model

1. Groups things the way a person would (a table with its cups, the floor as one piece), with no
   class list. This is what failures (2) and (3) lacked.
2. Returns a back-to-front order, or at least layers DA3 can order.
3. Fills in the hidden parts of back layers (amodal completion), so moving a front cut-out in
   parallax reveals painted content, not a hole.
4. Runs locally on 12 GB, takes 2-8 layers, has released weights and a permissive licence.

## A. End-to-end image to N layers (one model call)

**Qwen-Image-Layered** — [arXiv 2512.15603](https://arxiv.org/abs/2512.15603),
[repo](https://github.com/QwenLM/Qwen-Image-Layered),
[model card](https://huggingface.co/Qwen/Qwen-Image-Layered), Apache-2.0, weights out since 2025-12-19.
- Output: a variable number of RGBA layers set by the user (`"layers": 4` in the example, showcase
  shows 3 and 8). Any output layer can be decomposed again
  ([repo](https://github.com/QwenLM/Qwen-Image-Layered)). Trained with up to 20 layers
  ([paper HTML](https://arxiv.org/html/2512.15603)).
- Order: layers composite in index order from an empty canvas (C_i = α_i·RGB_i + (1−α_i)·C_{i−1}),
  so layer 1 is the bottom, and the repo says to recombine "from the bottom layer to the top"
  ([paper HTML](https://arxiv.org/html/2512.15603), [repo](https://github.com/QwenLM/Qwen-Image-Layered)).
  That is stacking order, not metric depth.
- Amodal: never stated outright. The optional prompt "describes the overall image, including
  partly hidden elements", but it does not control what goes into each layer
  ([repo](https://github.com/QwenLM/Qwen-Image-Layered)). Whether back layers are filled in on
  painted scenes is **[unverified]**.
- Architecture: an RGBA-VAE plus VLD-MMDiT (a transformer that handles a variable number of
  layers), fine-tuned from Qwen-Image on layers mined from real PSD files
  ([arXiv](https://arxiv.org/abs/2512.15603)). Text encoder: Qwen2.5-VL-7B
  ([ComfyUI wiki](https://comfyui-wiki.com/en/tutorial/advanced/image/qwen/qwen-image-layered)).
- Resolution and speed: 640 recommended, 1024 bucket available, 50 steps at CFG 4. On an RTX Pro
  6000 (96 GB), peak memory reaches 45 GB and a 1024 px run takes 120 s. An FP8 checkpoint exists
  (`qwen_image_layered_fp8mixed`), ComfyUI support is native, and the GGUF workflow was still
  "pending"
  ([model card](https://huggingface.co/Qwen/Qwen-Image-Layered),
  [ComfyUI wiki](https://comfyui-wiki.com/en/tutorial/advanced/image/qwen/qwen-image-layered)).
  A community page lists a 13 GB Q4_K_M GGUF **[unverified]**.
- 12 GB fit **[estimate]**: 20B parameters come to about 40 GB of weights in bf16, about 20 GB in
  FP8 and about 13 GB in Q4. Even Q4 overflows 12 GB, so it has to run with sequential CPU offload.
  Expect several minutes per panel at 640 px. That is fine for offline preprocessing and too slow
  for anything interactive.
- Measured quality: on Crello (designs) it beats LayerD at 0 merges, RGB L1 0.0594 vs 0.0709 and
  alpha soft IoU 0.8705 vs 0.7520 ([paper HTML](https://arxiv.org/html/2512.15603)).
- Known failures, all reported by later papers:
  - **Degenerate layer 0.** On a natural photo, layer 0 came out all black; on a vector
    illustration, a flat cream fill ([Stable-Layers, arXiv 2605.30257](https://arxiv.org/pdf/2605.30257)).
  - **Fixed layer count and over-segmentation.** It needs the count up front and tends to split
    elements too finely ([arXiv 2605.15167](https://arxiv.org/pdf/2605.15167)).
  - **Weak assignment as the count grows.** It struggled to give each layer a meaningful object at
    higher layer counts ([MRT, arXiv 2605.27235](https://arxiv.org/pdf/2605.27235)).
  - **Prompt sensitivity on anime.** Its anime output changed with the prompt
    ([arXiv 2603.14925](https://arxiv.org/html/2603.14925v1)).

**Stable-Layers** (Stability AI, May 2026) — RL fine-tune of Qwen-Image-Layered (Flow-GRPO, LoRA,
VLM-scored). Reports fewer blank or artifact layers and lower per-layer error on Crello
([arXiv 2605.30257](https://arxiv.org/abs/2605.30257)). Release and licence of the LoRA
**[unverified]** (project page stability-ai.github.io/stable-layers.github.io).

**MRT, Masked Region Transformer** (CVPR 2026) — 20B parameters, text-, image- and layers-to-layers.
Claims users preferred it over Qwen-Image-Layered for image-to-layers, with 10-100× faster
inference and 50-90% less activation memory. Trained on 10M+ design samples. No weights found
([arXiv 2605.27235](https://arxiv.org/abs/2605.27235)).

**PixelART** (Sep 2026) — pixel-space rectified-flow transformer trained from scratch. Claims >80%
fewer parameters, 98% lower latency and 85% lower memory than Qwen-Image-Layered. Design-only (4M
templates), no weights found ([arXiv 2609.22789](https://arxiv.org/abs/2609.22789)).

**CLD, Controllable Layer Decomposition** (Nov 2025) — LoRAs (Apache-2.0) on **FLUX.1-dev**, whose
base licence is non-commercial **[unverified here]**
([HF thuteam/CLD](https://huggingface.co/thuteam/CLD)). Reported to beat Qwen-Image-Layered on a
design test set ([arXiv 2605.15167](https://arxiv.org/pdf/2605.15167)). Design domain, 12B base.

**LaDe** (Mar 2026) — unified generation and decomposition of graphic media
([arXiv 2603.17965](https://arxiv.org/pdf/2603.17965)). Release **[unverified]**.

## B. Prompted, one layer per object (natural scenes, amodal)

**RefLayer / RefLade** (ICLR 2026) — image plus prompt (point, box, mask or text) gives one
*complete* RGBA layer for that object or for the background, hidden parts included. Built on SD3.
Zero-shot COCOA mIoU_occ 38.83 (best listed), beats pix2gestalt on its own test set. Dataset of
1.11M layers from real photos. Code "coming soon", "for academic research purposes only"
([arXiv 2602.19358](https://arxiv.org/html/2602.19358v1),
[project](https://yaojie-shen.github.io/project/RLD/)).

**RevealLayer** (ICML 2026, 360 AI Research) — box-guided decomposition of natural scenes into
RGBA layers, with occlusion completion and a 100K-image natural multi-layer dataset. The authors
list failures under bad boxes, heavy occlusion, translucency and dense repetitive textures. No code;
offered only as a hosted 360 service
([arXiv 2605.11818](https://arxiv.org/abs/2605.11818),
[360 page](https://research.360.cn/en/products/Reveal-Layer)).

**LayerDecomp** (Adobe, CVPR 2025) — image plus object mask gives a clean background and a
transparent foreground that keeps shadows and reflections. No code or weights on the project page
([CVF](https://openaccess.thecvf.com/content/CVPR2025/html/Yang_Generative_Image_Layer_Decomposition_with_Visual_Effects_CVPR_2025_paper.html),
[project](https://rayjryang.github.io/LayerDecomp)).

**PACO, Object-level Scene Deocclusion** (SIGGRAPH 2024) — SD-based, self-supervised. No release
found ([arXiv 2406.07706](https://arxiv.org/abs/2406.07706)).

**pix2gestalt** (CVPR 2024) — visible mask gives the whole object (amodal RGB plus mask). Built on
SD v2 image-conditioned. Weights on HF, demo uses 22-28 GB. Code licence not stated on the README,
data research-only ([repo](https://github.com/cvlab-columbia/pix2gestalt)).

**Open-World Amodal Appearance Completion** (CVPR 2025) — training-free. Text query plus LISA-13B,
Grounding DINO, SAM, InstaOrder (occlusion order) and SD2 inpainting give amodal RGBA objects.
Apache-2.0 ([CVF](https://openaccess.thecvf.com/content/CVPR2025/html/Ao_Open-World_Amodal_Appearance_Completion_CVPR_2025_paper.html),
[repo](https://github.com/saraao/amodal)).

## C. Peel-one-layer-at-a-time and two-layer models

**LayerD** (CyberAgent, ICCV 2025) — repeatedly matte the unoccluded top layer, inpaint beneath it,
and refine on the premise that design layers are flat in colour. Matting is BiRefNet
(`cyberagent/layerd-birefnet`). Apache-2.0, light enough for 12 GB **[estimate]**. Graphic designs
only; Qwen-Image-Layered's paper and LaDe both show its inpainting artifacts and failures on
occluded layers
([arXiv 2509.25134](https://arxiv.org/abs/2509.25134),
[repo](https://github.com/CyberAgentAILab/LayerD),
[LaDe](https://arxiv.org/pdf/2603.17965)).

**LayeringDiff** (Jan 2025) — mask-conditioned UNet LDM splits a composite into foreground and
background, applied in sequence for multi-layer output. Assumes accurate alpha, and shadows stay in
the background. No code found ([arXiv 2501.01197](https://arxiv.org/abs/2501.01197)).

**LayerDiffuse** (2024) — latent transparency for SD/SDXL generation. Code Apache-2.0, weights
CreativeML OpenRAIL-M. A generator, not a decomposer of an existing image
([repo](https://github.com/lllyasviel/LayerDiffuse),
[HF](https://huggingface.co/LayerDiffusion/layerdiffusion-v1)).

**Text2Layer** (2023) — generates background, foreground, mask and composite together. Preprint, no
release found ([arXiv 2307.09781](https://arxiv.org/abs/2307.09781)).

**MuLAn** (CVPR 2024) — a dataset of 44,860 decompositions (about 3.3 layers per image by my
division), built by a **training-free pipeline**: DetCLIPv2 boxes, SAM, ViTMatte, InstaOrderNet
occlusion/depth order, MiDaS, SD 1.5 inpainting. Measured success on 5,000 LAION images: 36%
clean, 52% including minor defects. Ships annotations only; dataset licence not stated
([arXiv HTML](https://arxiv.org/html/2404.02790), [project](https://mulan-dataset.github.io/)).
This is close to our failed attempt (3), and its 36-52% success rate is a realistic ceiling for
that family.

## D. Anime and comic evidence

**See-through** (SIGGRAPH 2026, conditional) — one anime character becomes 19 semantic body-part
layers (more after front/back splits). Each layer is inpainted (amodal), drawing order comes from a
Marigold model fine-tuned for anime, and LaMa fills gaps. SDXL base at 1024². 74 s per decomposition
plus 10 s depth on an RTX 4090. About 10 GB on 12 GB cards with group offload, 8 GB in NF4. Code
Apache-2.0, and a maintainer says the weights are Apache-2.0 too. **Background explicitly omitted**
([arXiv 2602.03749](https://arxiv.org/html/2602.03749v1),
[repo](https://github.com/lishaojiang/see-through),
[HF thread](https://huggingface.co/layerdifforg/seethroughv0.0.2_layerdiff3d/discussions/1)).
Artists noted "AI-like" textures and softened fine hatching, a warning for comic linework.

**Workflow-Aware Structured Layer Decomposition** (Mar 2026) — a Qwen-Image-Layered LoRA that
splits illustrations into lineart, flat colour, light and shadow. Documents the base model's
disordered layers on anime ([arXiv 2603.14925](https://arxiv.org/html/2603.14925v1)). Not a scene
splitter.

## E. Parallax-native and Meta options

**3D Photo Inpainting** (CVPR 2020) — RGB plus depth becomes a layered depth image (LDI). It cuts
at depth *discontinuities*, not depth bands, then inpaints colour and depth into the hidden region.
MIT, about 2-3 min per image. Co-author Johannes Kopf (Facebook at the time, **[unverified]** from
the repo) ([repo](https://github.com/vt-vl-lab/3d-photo-inpainting)). It can take DA3 depth as
input. A continuous floor stays one surface, but objects are not grouped.

**SAM 3D Objects** (Meta, Nov 2025) — mask gives the full 3D shape and texture of an occluded
object. SAM License, gated
([HF](https://huggingface.co/facebook/sam-3d-objects), [arXiv 2511.16624](https://arxiv.org/abs/2511.16624)).
Too heavy for flat cut-outs, and Meta has **no** image-to-layers model that I could find.

## Comparison

| Model | Layers out | Order | Amodal | Weights | Licence | 12 GB | Domain tested |
|---|---|---|---|---|---|---|---|
| Qwen-Image-Layered | N chosen (3-8 shown, ≤20 trained), recursive | bottom→top stack | not stated | yes | Apache-2.0 | offload only [est.] | designs, photos |
| Stable-Layers | as QIL | as QIL | — | [unverified] | [unverified] | as QIL | Crello |
| MRT / PixelART / LaDe | N | stack | — | no | — | — | designs |
| CLD | N (box-controlled) | stack | partial | LoRA yes | Apache-2.0 LoRA + FLUX.1-dev base | tight | designs |
| RefLayer | 1 per prompt | none | yes | no | academic-only | — | photos |
| RevealLayer | N per boxes | yes | yes | no (hosted) | — | — | photos |
| LayerD | iterative peel | top-down | inpainted bg | yes | Apache-2.0 | yes [est.] | designs |
| pix2gestalt / OWAAC | 1 object | OWAAC: InstaOrder | yes | yes | ? / Apache-2.0 | pix2gestalt 22-28 GB | photos |
| See-through | 19+ body parts | pseudo-depth | yes | yes | Apache-2.0 | ~10 GB offload | anime characters |
| 3D Photo Inpainting | LDI at depth edges | depth | yes (bg) | yes | MIT | likely [est.] | photos |

## Ranked shortlist for Zumi

1. **Qwen-Image-Layered (FP8 or GGUF, CPU offload, 640 px, 3-6 layers).** It is the only released,
   permissive model whose grouping was learned from human-made layers. That is exactly what
   failures (2) and (3) lacked: it can return "table and cups" as one layer because PSD authors
   group that way. Use it on the scene only: mask out characters and lettering, decompose the rest,
   then reorder layers by median DA3 depth, and split a mixed layer again recursively. First test:
   10 varied panels, measuring time and peak VRAM on the 3060 and counting usable layers per panel.
2. **3D Photo Inpainting, or its idea re-implemented on DA3 depth.** MIT and parallax-native. It
   splits at depth edges, so failure (1)'s band cuts through continuous floors go away, and it fills
   the revealed background. It does not group objects, so pair it with #1's masks or use it as the
   fallback when #1 fails on a panel.
3. **LayerD** as a cheap, Apache-2.0 baseline (BiRefNet matting plus inpainting, fits 12 GB
   [est.]). Design-trained, so expect it to fail on painted backgrounds. Worth one afternoon because
   its peel-the-top-layer loop gives an occlusion order for free.

Watch list, test when weights appear: **RevealLayer** (natural scenes, amodal), **RefLayer**
(prompted complete layers, but academic-only), **MRT** and **PixelART** (claimed far faster and
lighter than Qwen-Image-Layered).

## Risks

- **Domain gap.** Every layer model is trained on designs or photos. None is evaluated on comic
  backgrounds (screentone, speed lines, hatching), and See-through's artists already flag softened
  hatching and AI-like texture.
- **Editing layers are not depth layers.** Qwen-Image-Layered's stack order is compositing order.
  It may put a lamp and a far window together because they share an editing role. We still need
  DA3 to order layers and may need to split by depth inside a layer.
- **Count and stability.** The layer count must be preset. Expect a blank or flat layer 0, over-
  segmentation at high counts, and prompt-dependent output (each documented above). Budget for a
  reviewer pass (our LLM reviewer) to drop or merge bad layers.
- **Hidden-area fill is generative.** Inpainted backgrounds can drift from the artist's style, and
  amodal behaviour on painted scenes is unverified for Qwen-Image-Layered.
- **Compute.** 20B parameters on 12 GB means offload and minutes per panel [estimate]. Across a
  60-panel episode that is hours. Feasible offline only, and unmeasured until we run it.
- **Meta preference.** Nothing in this family comes from Meta, and SAM 3D Objects is the nearest
  Meta model. Qwen-Image-Layered is Alibaba's (Apache-2.0).
- **Licences.** CLD inherits FLUX.1-dev terms, RefLayer is academic-only, LayerDiffuse weights are
  OpenRAIL-M, and pix2gestalt's code licence is unstated.
