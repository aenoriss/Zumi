# Sharper, finer depth from DA3MONO-LARGE on webtoon panels (2026-10)

Question: how to get more precise and more granular depth out of Depth Anything 3 (DA3MONO-LARGE,
Apache 2.0) and its Apache siblings, for 700 px wide panels up to ~2400 px tall, on an RTX 3060 12 GB.
Facts about DA3 come from the vendored code (`pipeline/.vendor/Depth-Anything-3`, git HEAD
`3d835ec`, 2026-07-27), the [paper](https://arxiv.org/html/2511.10647) and the repo's issues.
Labels: **[inference]** means my reasoning, not a source; **[unverified]** means a claim I could not
confirm in a primary source. Timings marked "Zumi" are from the docstring of `pipeline/segment/depth.py`.

## Summary

1. **DA3MONO's output has an unknown shift, which bends planes when back-projected.** The paper says
   the teacher "outputs scale–shift-invariant depth" and the mono student is trained with "the same
   loss" ([§4.1, §4.3](https://arxiv.org/html/2511.10647)). With z' = s·z + t, a 3D plane (1/z linear
   in u, v) stops being planar unless t is right [inference]. DA3METRIC-LARGE has the identical
   network (same config) but is trained against metric ground truth, so its depth should carry no shift.
2. **Extra "views" give DA3MONO nothing but batching.** Its config sets `alt_start: -1`, which turns
   off the cross-view (global) attention; each image in the list is processed on its own. Flips or
   crops passed as views are plain test-time augmentation and must be aligned by hand before averaging.
3. **Our input is far outside DA3's training range.** Training: base 504×504, sizes up to 896×504,
   metric model aspect 1:1 to 1:1.8 ([§3.4, §4.4](https://arxiv.org/html/2511.10647)). That is at
   most 64×36 = 2,304 patch tokens. A 700×2394 panel is 50×171 = 8,550 tokens at aspect 1:3.4.
4. **The boundary spikes and the dot pattern are known DA3 behaviour**, not Zumi bugs: spiky
   artefacts along silhouettes with DA3MONO-LARGE ([#279](https://github.com/ByteDance-Seed/Depth-Anything-3/issues/279),
   open, no maintainer answer) and 14×14-patch patterns ([#125](https://github.com/ByteDance-Seed/Depth-Anything-3/issues/125)).
5. **Cheapest big wins are post-processing, not new models:** drop edge ("flying") pixels before
   clustering, replace the 5 px median with an RGB-guided weighted median, and add a half-patch
   shift + flip TTA. All are Apache/MIT, cost well under a second, and need no new weights.
6. **Best licence-clean model alternative: MoGe-2 / MoGe-3 (MIT weights)**, which output point maps,
   normals and an edge mask directly. Depth Pro, Illustrator's Depth, BoostingMonocularDepth,
   DepthAnything-AC and DA3-LARGE/GIANT are all non-commercial.

## 1. What DA3 itself offers

| Fact | Source |
|---|---|
| DA3MONO-LARGE = DINOv2 ViT-L + DPT head, `output_dim: 1`, `alt_start: -1` (no cross-view attention). DA3METRIC-LARGE's config is byte-identical. | [da3mono-large.yaml](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/configs/da3mono-large.yaml), [da3metric-large.yaml](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/configs/da3metric-large.yaml) |
| `output_dim == 1` means no confidence channel; depth = `exp(logit)` (always positive). A confidence map (`depth_conf`, activation `exp+1`) exists only when `output_dim > 1`. | [dpt.py](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/model/dpt.py) |
| DA3-BASE (0.12B) and DA3-SMALL (0.08B), both Apache, use a DualDPT head with `output_dim: 2` (depth + confidence) and cross-view attention from layer 4. | [da3-base.yaml](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/configs/da3-base.yaml), [README model table](https://github.com/ByteDance-Seed/Depth-Anything-3) |
| Mono "directly predicts depth", unlike DA2 which predicts disparity. | [README](https://github.com/ByteDance-Seed/Depth-Anything-3) |
| Teacher and mono student: scale–shift-invariant depth, exponential depth "enhancing discrimination at small distances", losses: MoGe global–local + depth-gradient ("preserves sharp edges while ensuring smoothness in planar regions") + distance-weighted normal loss. | [paper §3.1, §4.1, §4.3](https://arxiv.org/html/2511.10647) |
| Metric: canonical focal 300; `metric_depth = focal * net_output / 300`. | [README](https://github.com/ByteDance-Seed/Depth-Anything-3), [paper §4.4](https://arxiv.org/html/2511.10647) |
| Patch size 14. `*_resize` rounds each side to the nearest multiple of 14; `*_crop` floors by centre crop. Output depth is at the processed size, not the input size. | [input_processor.py](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/utils/io/input_processor.py), [#43](https://github.com/ByteDance-Seed/Depth-Anything-3/issues/43) |
| The backbone runs under bf16 autocast (on an RTX 3060, which supports bf16); the depth head runs with autocast disabled (fp32). | [api.py](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/api.py), [da3.py](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/model/da3.py) |
| Mono and Metric have a sky head. Pixels with sky score ≥ 0.3 get their depth overwritten with the 99th percentile of non-sky depth; `pred.sky` exposes the mask (≥ 0.5). | [da3.py `_process_mono_sky_estimation`](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/model/da3.py), [output_processor.py](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/src/depth_anything_3/utils/io/output_processor.py) |
| Default `process_res=504`, `upper_bound_resize`; the docs give no other recommended settings for high-resolution input. | [docs/API.md](https://github.com/ByteDance-Seed/Depth-Anything-3/blob/main/docs/API.md) |

What follows for Zumi:

- **Resolution.** Zumi measured 1.0 s / 3.8 GB at 700 px and 5.4 s at 1008 px, "barely sharper".
  Going higher on the whole panel is unlikely to pay. Tiling the tall panel into windows near the
  training aspect is the untested lever (§2).
- **Sky head on comics.** White or flat-pale backgrounds may be classified as sky and flattened to
  one far plane [inference]. Check `pred.sky.mean()` on a few panels. If it fires on art, the sky
  overwrite is a 3-line patch to skip (`_process_mono_sky_estimation`).
- **Multi-view with crops.** Asked in [#34](https://github.com/ByteDance-Seed/Depth-Anything-3/issues/34),
  no answer. With DA3MONO it does nothing (no cross-view attention). With DA3-BASE, overlapping crops
  of one flat image carry no parallax, so cross-view attention has nothing to triangulate [inference];
  the only gain would be the confidence map, from a 3× smaller model.
- **Batch size.** [#133](https://github.com/ByteDance-Seed/Depth-Anything-3/issues/133) reports
  worse depth at batch ≥ 10 on the Nested model, and one commenter says the same of Mono [unverified].
  Keep TTA batches at 2–4 views.
- **Mono vs Metric.** Same cost, same API. I found no head-to-head relative-depth comparison of the
  two in the paper [unverified]. The mono student beats DA2 on all five sets (e.g. ETH3D 98.8 vs 86.5, SINTEL
  82.3 vs 77.2 δ1; [Table 10](https://arxiv.org/html/2511.10647)). Metric's real-photo training may
  transfer worse to line art [unverified]. It is worth one A/B on planarity (rank 3).

## 2. Test-time techniques for any monocular depth model

Costs on the 3060 are estimates scaled from Zumi's 1.0 s / 3.8 GB pass unless a source is given.

| Technique | Expected gain | Cost on RTX 3060 | Licence | Source |
|---|---|---|---|---|
| **Drop edge pixels before clustering**: mark pixel pairs whose depth ratio exceeds 1 + t and exclude them from the point cloud | Removes the spikes of #279 and the "flying pixels" between figure and ground, which otherwise bridge clusters | ms, CPU | MIT (MoGe's `utils3d`) or 10 lines | Depth Pro defines contours as d(j)/d(i) > 1 + t/100, t = 5..25 ([paper](https://arxiv.org/html/2410.02073)); MoGe's CLI removes edges with `--threshold 0.01` ([README](https://github.com/microsoft/MoGe)); PPD is built around flying-pixel-free point clouds, Chamfer 0.08 vs 0.18 for DA2 on Hypersim ([arXiv 2510.07316](https://arxiv.org/html/2510.07316)) |
| **RGB-guided weighted median** in place of the plain 5 px median | Same noise removal on flat areas, but steps snap to colour edges instead of rounding off | tens of ms [unverified] | Apache (opencv-contrib) | `cv2.ximgproc.weightedMedianFilter(joint, src, dst, r, sigma, WMF_EXP)` ([header](https://github.com/opencv/opencv_contrib/blob/4.x/modules/ximgproc/include/opencv2/ximgproc/weighted_median_filter.hpp)) |
| **Guided / joint-bilateral filter / fast bilateral solver** with the RGB as guide | Smooths flat areas, keeps edges that coincide with ink lines. The solver takes a per-pixel confidence: set it low on depth edges and screentone | 10 ms – 1 s [unverified] | Apache (opencv-contrib) | `guidedFilter` (He et al.), `jointBilateralFilter`, `fastBilateralSolverFilter` (Barron & Poole 2016), `fastGlobalSmootherFilter`, `l0Smooth` ([edge_filter.hpp](https://github.com/opencv/opencv_contrib/blob/4.x/modules/ximgproc/include/opencv2/ximgproc/edge_filter.hpp)) |
| **Flip TTA**: average the prediction with the flipped prediction of the flipped image | Lower variance; standard practice | ×2 time (one batched call) | — | ZoeDepth's `infer` does flip + reflect-pad averaging by default ([depth_model.py](https://github.com/isl-org/ZoeDepth/blob/main/zoedepth/models/depth_model.py)) |
| **Half-patch shift TTA**: reflect-pad 7 px top/left, predict, crop back, average with the unshifted pass | Targets the 14×14 grid artefacts; a flip keeps the patch grid aligned when the width is a multiple of 14, so it cannot cancel them [inference] | ×2 time | — | Grid artefacts: [#125](https://github.com/ByteDance-Seed/Depth-Anything-3/issues/125). Pad augmentation precedent: ZoeDepth above |
| **Tiling + fusion without training** (Boosting-style): global pass for structure, tall panel cut into overlapping 700×~1050 windows (aspect 1:1.5, 3,750 tokens), each window scale+shift fitted to the global pass, feather-blended | Closer to training conditions per window; detail from windows, layout from the global pass | ~3 windows ≈ +1.5–3 s [inference] | own code | Structure-vs-detail trade-off with resolution and double estimation: Miangoleh et al. CVPR 2021 ([arXiv 2105.14021](https://arxiv.org/abs/2105.14021)); code is academic-only ([LICENSE](https://github.com/compphoto/BoostingMonocularDepth/blob/main/LICENSE)), so reimplement the idea |
| **Low/high frequency merge**: low-pass of a coarse pass + high-pass of a fine pass, after affine alignment | Cheapest version of the above, one extra pass | +0.5 s | own code | Same idea as above [inference] |
| PatchFusion / PatchRefiner | −17.3% RMSE vs ZoeDepth on UnrealStereo4K ([2312.02284](https://arxiv.org/abs/2312.02284)); −18.1% ([2406.06679](https://arxiv.org/abs/2406.06679)) | 84 s per image on V100 ([Depth Pro Table 5](https://arxiv.org/html/2410.02073)) | MIT code; fusion nets trained for DA1/ZoeDepth only ([README](https://github.com/zhyever/PatchFusion)) | Built for 4K photos; our panels are 1.7 MP, and it would need retraining for DA3 |
| Depth Pro | Best boundary scores in its paper: Sintel F1 0.409 vs 0.228 for DA2 | 0.34 s on V100 at 1536² | **Weights `apple-amlr`, research only** ([HF](https://huggingface.co/apple/DepthPro)) | [arXiv 2410.02073](https://arxiv.org/abs/2410.02073) |
| **MoGe-2 (ViT-L, ViT-B, ViT-S)** | Affine/metric point maps, normals and a mask in one pass; "sharp details" from cleaned real data | `num_tokens` 1,200–2,500 suggested; output at input size [unverified VRAM] | **MIT code and weights** ([HF](https://huggingface.co/Ruicheng/moge-2-vitl-normal)) | [arXiv 2507.02546](https://arxiv.org/abs/2507.02546), [README](https://github.com/microsoft/MoGe) |
| **MoGe-3 (ViT-L 370M, ViT-G 1.25B)** | Refines the point map on a sparse voxel shell so features stop mixing across depth discontinuities, aimed at thin structures | Unknown; needs FlexGEMM (Triton sparse GEMM) [unverified on Windows] | **MIT** ([HF](https://huggingface.co/Ruicheng/moge-3-vitl)) | [arXiv 2607.17967](https://arxiv.org/abs/2607.17967) |
| Pixel-Perfect Depth (pixel-space diffusion) | Flying-pixel-free edges; 0.08 Chamfer vs 0.14 Depth Pro | 0.14 s at 512² on RTX 4090, 4 steps; trained at 1024×768 | Apache weights; use the **MoGe-2 semantics** variant (the DA2 one loads DA2-Large, CC BY-NC) ([README](https://github.com/gangweix/pixel-perfect-depth)) | [arXiv 2510.07316](https://arxiv.org/html/2510.07316) |
| Marigold (v1.1 / LCM) | Fine detail, but low boundary F1 in Depth Pro's tests (Sintel 0.068) | 4.4–5.2 s on V100 | v1.1 OpenRAIL++, LCM v1.0 Apache ([HF](https://huggingface.co/prs-eth/marigold-depth-lcm-v1-0)) | [README](https://github.com/prs-eth/Marigold) |
| Marigold-DC as a refiner (DA3 samples as sparse guidance) | Keeps DA3's layout, adds diffusion detail | 10.7 s / 50 steps on A100 (bf16), much more on a 3060 | Apache | [README](https://github.com/prs-eth/Marigold-DC) |
| BetterDepth, SharpDepth | Diffusion refiners for detail | — | No code found | [NeurIPS 2024](https://proceedings.neurips.cc/paper_files/paper/2024/hash/c4b652b7e228b18e1c65478da3a4a2cf-Abstract.html), [CVPR 2025](https://arxiv.org/abs/2411.18229) |
| InfiniDepth (implicit field, any resolution) | Largest gains in fine-detail regions | — | Registration licence; free use only for research/personal ([LICENSE](https://github.com/zju3dv/InfiniDepth/blob/main/LICENSE)) | [arXiv 2601.03252](https://arxiv.org/abs/2601.03252) |
| Depth Anything at Any Condition | Robustness to weather and low light, "clearer semantic boundaries" | — | Weights CC BY-NC ([HF](https://huggingface.co/ghost233lism/DepthAnything-AC)) | [arXiv 2507.01634](https://arxiv.org/abs/2507.01634); off-target for comics |

**Aligning to segmentation.** Zumi already has flat-colour regions and SAM masks. Two uses
[inference]: (a) per region, fit a plane to the back-projected points with RANSAC and replace depth
with the plane where the residual is small (flat walls, floors and sky stop being noisy); (b) on a
region boundary, assign each edge pixel the depth of the side it belongs to. This is what the DA3
gradient loss tries to learn and what Illustrator's Depth does with per-region medians (see
[scene-layers-comics](scene-layers-comics-2026-10.md)).

## 3. Anime and illustration

- No open, commercially usable anime depth checkpoint exists. ComicsDepth (WACV 2022) and Toon3D are
  covered in [scene-layers-comics](scene-layers-comics-2026-10.md); two searches in 2026-10 found
  nothing newer.
- **Update to that doc:** Illustrator's Depth released code and weights in 2026-05
  ([repo](https://github.com/nissmar/illustrators_depth)), but under the Adobe Research Licence,
  "noncommercial research purposes … only", on top of Depth Pro. Usable as a reference to compare
  against, not to ship.
- Comic-specific traits that matter for the filters above [inference]: ink outlines sit exactly on
  occlusion edges, so RGB-guided filters work well there; screentone and hatching are
  high-frequency guide edges with no depth meaning, so smooth the guide first (`l0Smooth` or the
  flat-colour map) before guided filtering, or give tone areas low confidence in the bilateral solver.

## 4. Ranked list: what Zumi should try first

Measure each step on the same 10 panels with two numbers: plane RANSAC residual on a labelled floor
or wall (planarity), and the share of pixels flagged as depth edges (flying pixels).

1. **Edge-pixel removal before back-projection.** Flag a pixel if max over its 4-neighbours of
   d_max/d_min > 1.03 (Depth Pro's t = 3–5%; MoGe uses 0.01 in its own units). Drop it from the
   cloud and refill from the nearer side only if a mesh is needed. Cost: ms. Directly attacks #279.
2. **Replace `medianBlur(5)` with `weightedMedianFilter(guide, d, r=3, sigma=25.5, WMF_EXP)`**,
   guide = the panel after `l0Smooth(lambda=0.02)` so screentone is flattened. Then optionally
   `fastBilateralSolverFilter(guide, d, conf)` with conf = 0.1 on edge pixels from step 1, 1.0
   elsewhere, defaults `sigma_spatial=8, sigma_luma=8, lambda=128`.
3. **Fix the shift for planarity.** Run DA3METRIC-LARGE once at the same resolution (same API,
   +1.0 s, +0 GB if run sequentially). Least-squares fit Mono = s·Metric + t on non-edge pixels,
   then back-project s⁻¹(Mono − t) with one fixed focal for all panels (e.g. 60° FOV). Keeps Mono's
   detail, takes Metric's shift. If Metric alone gives flatter planes, use it outright.
4. **TTA, 4 views in one call:** identity, h-flip, 7 px shift, h-flip + 7 px shift; scale+shift
   align each to the identity view, then take the per-pixel median (not mean, so one bad view does
   not drag edges). ~2–3 s, VRAM roughly ×2–3 of a single view [unverified; split into 2 calls if
   it exceeds 12 GB].
5. **Tile tall panels** taller than 1.8× their width: windows 700×1050 with 350 px overlap, each
   aligned by scale+shift to a whole-panel pass, linear feathering in the overlap. Compare against
   the full 700×2394 pass on the same metrics; keep only if planarity improves.
6. **Region planes** from Zumi's flat-colour regions (RANSAC, inlier threshold ~1% of depth range),
   replacing depth only where ≥ 80% of a region's pixels are inliers.
7. **A/B MoGe-2 ViT-L normal** (MIT) on the same panels: its point map removes the focal/shift
   guesswork and its normals help planar clustering. Try MoGe-3 ViT-L only if FlexGEMM installs on
   Windows. Pixel-Perfect Depth (MoGe-2 variant) is the boundary-quality reference if 1–6 fall short.

Not worth trying: higher process_res on the whole panel (Zumi: 1008 px, 5.4 s, barely sharper),
DA3MONO multi-view input (no cross-view attention), PatchFusion (84 s, retraining needed), and every
non-commercial option (Depth Pro, Illustrator's Depth, Boosting, InfiniDepth, DA-AC, DA3-LARGE/GIANT).
