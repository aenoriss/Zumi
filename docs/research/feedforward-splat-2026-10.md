# Feed-forward single-image Gaussian splatting for webtoon panels — 2026-10-25

Research date: 2026-10-25. Method: arXiv papers, GitHub READMEs and source, HF model cards, GitHub API (licence, last push). Nothing was downloaded or run, so **no claim below is a measurement on our panels**. **[unverified]** = secondary source or not confirmed; **[inference]** = my reasoning.

Zumi context: a panel is 700 px wide and up to ~2000 px tall, cel-shaded, and is viewed on Quest 3 with 2-20 cm of head motion. Today it becomes an LDI mesh (`pipeline/segment/ldi_mesh.py`): DA3 depth, FLUX-Erase hidden layers behind objects, textured from the full-resolution art.

## Answer

1. **YoNoSplat does not fit.** It is a multi-view model (ETH Zurich / Microsoft, ICLR 2026, [arXiv 2511.07321](https://arxiv.org/abs/2511.07321)): any number of unposed, uncalibrated images, but it was "trained with 2 to 32 views" and every benchmark uses 6+ views. Single-image input is never evaluated. The only released weights are 224×224 ([repo](https://github.com/cvg/yonosplat), [HF](https://huggingface.co/botaoye/YoNoSplat)), and the high-resolution model is still a TODO (issue #3, 2026-03). MIT code and weights is its one strength. Its authors' earlier NoPoSplat says outright that single-image input "may not perform optimally" because training relies only on photometric loss between views ([issue #4](https://github.com/cvg/NoPoSplat/issues/4)).
2. **Best pick: Apple SHARP**, the only mature model built for exactly our case: one image, a headbox of "posture shifts" (it targets ~0.5 m of motion), about 1 s per image. Its weights are **research-only**.
3. **Runner-up: InfiniSplat v1** (ZJU, SIGGRAPH Asia 2026). It beats SHARP on the authors' own benchmark (PSNR 20.39 vs 18.48, LPIPS 0.277 vs 0.299), and its Gaussian count is a config value. But it is three months old, and it is built on Depth Pro, whose weights are also research-only.
4. **No source tests any of these on comics, anime or line art.** All training and evaluation data are photographs or photoreal renders. The main risk is **frontal fidelity**, not holes: SHARP stores 768×768×2 Gaussians, so on a 2000 px tall panel each one covers ~2.6 source pixels vertically, and 1-2 px ink lines will soften **[inference]**. Our mesh is textured at full resolution, so its frontal view matches the art exactly.
5. **There is no Meta model for this.** Meta's SAM 3D Objects does output Gaussian `.ply` files from one image, but per masked object: it needs 32 GB VRAM and Linux ([setup.md](https://github.com/facebookresearch/sam-3d-objects/blob/main/doc/setup.md)). It is under the SAM License, which permits commercial use.

## Comparison

| Model | Input | Poses / intrinsics | Quality evidence | Licence: code / weights | Hardware, time | Output, Gaussian count | Released / last push |
|---|---|---|---|---|---|---|---|
| **SHARP** (Apple, ICLR 2026) [arXiv 2512.10685](https://arxiv.org/abs/2512.10685), [repo](https://github.com/apple-aiml-research/ml-sharp) | **1 image**, resized (non-uniformly) to 1536×1536 | None. Focal comes from EXIF and **defaults to 30 mm** without EXIF (`utils/io.py`) | Zero-shot LPIPS 0.154-0.554 vs Flash3D 0.345-0.683 on 6 datasets; best ≤ 0.5 m, "best or second best up to 3 m" (App. D.6). Failure cases are depth errors (macro, night sky, reflections) | Apple permissive sample-code licence / **Apple ML Research Model License: "does not include … use in any commercial product"** | 0.91 s on A100; 702 M params. Prediction runs on CPU, CUDA and MPS; rendering needs CUDA gsplat. VRAM not published. Runs on a T4 16 GB on Replicate. 12 GB fit is **[unverified]** | `.ply` 3DGS, **2×768×768 ≈ 1.18 M** Gaussians, no SH (RGB only) | 2025-12 / 2026-09-11; 9.0 k stars |
| **InfiniSplat v1** (ZJU, SIGGRAPH Asia 2026) [arXiv 2608.02437](https://arxiv.org/abs/2608.02437), [repo](https://github.com/zju3dv/InfiniSplat) | **1 image**, optionally plus a depth prompt (≤1500 samples, scale-free OK) | Focal via `--focal-px`, `--focal-mm`, an intrinsics file or EXIF | Avg of 4 datasets, PSNR/SSIM/LPIPS: **20.39 / 0.806 / 0.277** vs SHARP 18.48 / 0.758 / 0.299 vs Flash3D 17.34 / 0.738 / 0.328. Baselines span 0 to >2 m and are not broken out by range | "Project Registration License": free; organisations register once, commercial use included / checkpoint on [HF](https://huggingface.co/PLUS-WAVE/InfiniSplat). Its RGB mode builds on **Depth Pro (`apple-amlr`)**, and depth-prompt mode uses InfiniDepth (non-commercial, see depth-precision doc) | 0.60 s at the 1.5 M default (GPU not stated). DINOv3 ViT-L/16 + Depth Pro; needs xformers; Windows **[unverified]** | `.ply` always (gsplat optional); count = `sample_point_num`, default **1.5 M, configurable**; floater filter | 2026-08 / 2026-10-19; 557 stars |
| **Flash3D** (Oxford VGG, 3DV 2025) [arXiv 2406.04343](https://arxiv.org/abs/2406.04343), [repo](https://github.com/eldar/flash3d) | 1 image at **256×384** | None (UniDepth metric depth) | RE10K: 28.46 / 0.899 / 0.100 at +5 frames, 24.93 / 0.833 / 0.160 at ±30 frames. Loses to SHARP and InfiniSplat on every dataset above | **No LICENSE file** (all rights reserved by default) / depends on UniDepth, **CC BY-NC 4.0** | ~10 fps; trained on 1 A6000 | 2 Gaussians per pixel (~197 k at 256×384); `.ply` not documented | 2024-06 / 2025-06 |
| **YoNoSplat** (ICLR 2026) | **2-32 views** | Optional (pose-free and intrinsics-free modes) | DL3DV, 6 views, pose-free: 24.53 / 0.804 / 0.142. RE10K, 6 views: 24.57 / 0.823 / 0.144. Nothing for 1 view | MIT / MIT (HF tag) | 100 views at 280×518 in 2.69 s on GH200 | 1 Gaussian per pixel per view; only **224×224** weights released | 2025-11 / 2026-02-25 |
| **NoPoSplat** (ICLR 2025) [arXiv 2410.24207](https://arxiv.org/abs/2410.24207) | 2 views (256×256 **[unverified]**) | Pose-free; intrinsics used **[unverified]** | Multi-view only; authors discourage 1-view use (issue #4) | MIT | — | per pixel per view | 2024-10 / 2026-02 |
| **AnySplat** [arXiv 2505.23716](https://arxiv.org/abs/2505.23716), [repo](https://github.com/InternRobotics/AnySplat) | K views at 448×448, trained ≤ 24 | Pose-free | Multi-view. Single-view Gaussians extracted from it render "heavily mixed with the background colour" ([issue #45](https://github.com/InternRobotics/AnySplat/issues/45)) | MIT / MIT (HF tag); VGGT-distilled **[unverified]** | — | voxelised | 2025-06 / 2025-12 |
| **Splatter Image** (CVPR 2024) [arXiv 2312.13150](https://arxiv.org/abs/2312.13150) | 1 image, **objects** (ShapeNet, CO3D, Objaverse) | — | Object-centric; not trained on scenes | BSD-3 / not stated | very fast; 1 Gaussian per pixel | 128² class models **[unverified]** | 2023-12 / 2024-08 |
| **LGM, LaRa** [2402.05054](https://arxiv.org/abs/2402.05054), [2407.04699](https://arxiv.org/abs/2407.04699) | 4 views of an **object** (LGM gets them from a multi-view diffusion model) | — | 360° objects; regenerates the art, so frontal fidelity is lost **[inference]** | MIT | — | ~65 k Gaussians (LGM) **[unverified]** | 2024 / 2024-08 |
| **SAM 3D Objects** (Meta) [repo](https://github.com/facebookresearch/sam-3d-objects) | 1 image + an object mask | — | Real-world photo objects | SAM License (commercial OK) | **≥ 32 GB VRAM, Linux** | Gaussian `.ply` per object | 2025-11 / active |
| UniSHARP [2606.07514](https://arxiv.org/abs/2606.07514), PhGS [2609.20623](https://arxiv.org/abs/2609.20623) | 1 image | — | UniSHARP extends SHARP to fisheye and panoramas; PhGS prunes single-view feed-forward splats. Neither gives numbers in its abstract | No code found | — | — | 2026 |

Other options:

- **Hosted SHARP.** [Replicate `kfarr/sharp-ml`](https://replicate.com/kfarr/sharp-ml) costs ~$0.0039 per run on a T4, ~18 s including cold load. That is $0.20 for 50 panels. The weight licence still applies.
- **Modal.** On our existing `pipeline/modal`, an A10G costs about $1.1/h, so 1-2 s per panel is fractions of a cent **[unverified price]**.
- **Quest 3 budget.** The only concrete number I found is ~400 k Gaussians at a stable 72 fps, from an unmaintained Unity fork ([ninjamode](https://github.com/ninjamode/Unity-VR-Gaussian-Splatting)). So one SHARP panel (1.18 M) needs about 3× pruning, and several panels in view need more **[inference]**.

## Recommendation

- **Prototype with SHARP, and run InfiniSplat on the same panels.** Both take <1 s, so the comparison costs minutes. The licence caveat is the same one already accepted for Magiv3 (hackathon, research use). A shipped product would need a permissive replacement, and none exists yet at this quality.
- **Use YoNoSplat, NoPoSplat and AnySplat only if Zumi ever has several views of one scene.** That would mean consecutive panels of the same room, which could be used as unposed multi-view input **[inference]**. It would be a different experiment from this one.
- **Expect splats to win on holes and lose on line art** **[inference]**:
  - SHARP's second layer fills disocclusions with regression blur, not drawn content. FLUX Erase does better there.
  - The likeliest good result is a hybrid: keep the full-resolution mesh for the frontal surface and use splats only where the mesh tears.
  - The alternative hybrid is to turn our own LDI samples into Gaussians, which needs no model. It is worth trying if the models soften the art.

## Minimal test plan

**Inputs: 6 panels.**
1. A close-up face with heavy ink lines.
2. Two characters overlapping, with a large disocclusion.
3. An interior with floor and furniture.
4. A flat-colour sky or gradient background.
5. A tall 700×2000 establishing shot.
6. A panel with an SFX or speech bubble.

**Variants per model:**
- SHARP: native (stretched to 1536²); padded to square; 700×700 tiles.
- InfiniSplat: `--focal-mm 30`, 50 and 85. Optionally DA3 depth as the prompt.

**Measure against the current LDI mesh, rendered from the same virtual camera at 0, ±5, ±10 and ±20 cm lateral offsets:**

| What | How |
|---|---|
| Frontal fidelity | At 0 cm: PSNR and LPIPS against the original panel, plus edge-F1 on Canny maps (ink-line survival) |
| Holes | % of pixels with accumulated alpha < 0.5 (splat) or no triangle coverage (mesh), at each offset |
| Edge halos | Mean colour error in a 4 px band around character silhouettes (SAM masks we already have), at ±10 and ±20 cm |
| Depth sanity | Median relative depth vs DA3 inside each character mask; checks the 30 mm focal default on art without EXIF |
| Budget | Gaussian count after opacity pruning at < 0.05, and `.ply` size |
| Cost | Wall time and peak VRAM on the RTX 3060 (`torch.cuda.max_memory_allocated`) |

**Pass bar:**
- Frontal LPIPS within 0.02 of the mesh.
- Fewer hole pixels at ±20 cm.
- ≤ 400 k Gaussians after pruning, with no visible line softening at 0 cm.
- If frontal fails but holes pass, test the hybrid (mesh in front, splats only where the mesh tears).
