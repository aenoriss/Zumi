# Scene layers: whole-object segmentation and front-to-back ordering — 2026-10-24

Research date: 2026-10-24. Literature only. Nothing was run.

The problem: characters and lettering are already cut out. What remains (the scene) has to become 3–5 whole RGBA layers in any environment, ordered front to back, on an RTX 3060 12 GB, with Meta models preferred. Already tried and failed: depth-histogram bands; a SAM point grid (every floor tile becomes its own mask); LLM-named elements sent to SAM 3.1 as text prompts (objects resting on a table left detached; some names not found).

How to read the evidence:
- Numbers are copied from the paper, its HTML or its repo README.
- **[unverified]** means the claim could not be checked against a primary page.
- **[reasoning]** means an inference for Zumi. No paper here tests on webtoons.

## Bottom line

1. **The floor-tile problem is a granularity setting, not a model gap.** SAM returns up to 3 nested masks per point ("whole, part, and subpart", [SAM §3](https://ar5iv.labs.arxiv.org/html/2304.02643)). The automatic generator keeps all of them by default (`multimask_output=True`, [SAM 2 AMG source](https://raw.githubusercontent.com/facebookresearch/sam2/main/sam2/automatic_mask_generator.py)), so tiles survive next to the floor. **UnSAMv2** puts a continuous granularity scalar g ∈ [0.1, 1] on top of SAM 2. It works in whole-image mode and is Apache-2.0 ([paper](https://arxiv.org/html/2511.13714), [repo](https://github.com/yujunwei04/UnSAMv2)). It is the closest match to "segment at the whole-object level".
2. **Sorting by median depth fails exactly where Zumi needs it: on overlapping pairs.** Grounded SAM + Depth Anything V2 + median depth scores WHDR 10.8 on separated pairs but **39.1 on overlapping pairs**. A learned order model (InstaFormer) scores 24.7 there (lower is better; [arXiv 2510.01704](https://arxiv.org/html/2510.01704)).
3. **A VLM is a poor pairwise judge of occlusion.** Zero-shot LLaVA reaches occlusion F1 34.1 on InstaOrder pairs. Fine-tuned, it reaches 60.4. Visual expert models reach about 81 ([same paper](https://arxiv.org/html/2510.01704)).
4. **Support is old, solved-enough geometry.** On ground-truth regions, the rule "the support is the region directly below" is right 63.9% of the time. A learned energy model is right 75.9% of the time ([Silberman et al. ECCV 2012](https://cs.nyu.edu/~fergus/datasets/indoor_seg_support.pdf), Table 2). On automatic segments, the same figures drop to 22.1% and 55.1%. So segmentation quality matters more than the support rule.
5. **End-to-end layer decomposers exist but do not fit yet.** Qwen-Image-Layered (Apache-2.0) has about 20B parameters ([HF card](https://huggingface.co/Qwen/Qwen-Image-Layered)). MuLAn's modular pipeline produced a successful decomposition on only 36% of 5,000 annotated images ([arXiv 2404.02790](https://arxiv.org/html/2404.02790)).

## A. Whole objects: granularity and part-whole hierarchy

| Method | What it outputs | Weights / licence | Speed | Fit to comics / Zumi |
|---|---|---|---|---|
| **SAM / SAM 2 automatic mask generator** ([SAM](https://ar5iv.labs.arxiv.org/html/2304.02643), [AMG source](https://raw.githubusercontent.com/facebookresearch/sam2/main/sam2/automatic_mask_generator.py)) | Overlapping masks from a point grid (default 32×32). Up to 3 candidates per point; filtered by predicted IoU (0.8), stability (0.95) and box NMS (0.7) | Meta, Apache-2.0 for SAM 2 ([repo](https://github.com/facebookresearch/sam2)) | Not stated in source. A 32×32 grid is 1,024 prompts | Already in use. No notion of "whole". Its stability filter keeps crisp small masks such as tiles **[reasoning]** |
| **SAM 3 / 3.1** ([repo](https://github.com/facebookresearch/sam3)) | Every instance of a text or exemplar concept. The tracker inherits SAM 2. No automatic generator is documented | SAM License; 848M params | No timing figures given | The text route already failed on unnamed and attached things. Keep its point predictor as the mask engine |
| **UnSAMv2** ([paper](https://arxiv.org/html/2511.13714), [repo](https://github.com/yujunwei04/UnSAMv2)) | SAM 2 plus a granularity scalar g ∈ [0.1, 1]. g is a mask's normalised √area within its hierarchy. Interactive, whole-image and video modes. Whole-image evaluation uses a 64×64 grid at each of 10 g values, then NMS | Apache-2.0 code. Base SAM-2-small. Adds <0.02% params; trained on 6K unlabelled images | Not reported | **Best fit.** Fixing g high picks "the whole thing this point belongs to" instead of the tile. It builds on Meta SAM 2. Trained on photos (SA-1B-style data); comic behaviour is unknown |
| **Semantic-SAM** ([paper](https://arxiv.org/html/2307.04767), [repo](https://github.com/UX-Decoder/Semantic-SAM)) | 6 masks per click (levels 1–6). Its automatic generator takes `level=[…]`: 1–2 semantic, 3 instance, 4–6 part. 1-click mIoU on COCO is 57.0 vs SAM-L 55.7 | Swin-T and Swin-L checkpoints. The GitHub API reports no LICENSE file; UnSAM's README calls it MIT ([UnSAM](https://github.com/frank-xwang/UnSAM)) [unverified] | Not reported | Good second option: run level 3 only for instance-level wholes. Old stack (torch 1.13 / cu113), so install friction **[reasoning]** |
| **GraCo** ([arXiv 2405.00587](https://arxiv.org/abs/2405.00587)) | Interactive segmentation with an extra granularity input | Not checked | — | Interactive only. UnSAMv2 covers the same idea with a whole-image mode |
| **Entity segmentation: CropFormer / EntitySeg** ([arXiv 2211.05776](https://arxiv.org/html/2211.05776), [toolbox](https://github.com/qqlu/Entity)) | Class-agnostic, **non-overlapping** masks for things and stuff. Dataset: 33,227 images, 18.1 entities per image; domains include cartoon, clipart and comic. CropFormer reaches 41.0 APe | Swin-T/L and Hornet-L weights; **CC-BY-NC 4.0** | 1,503 ms per high-resolution image (paper's GPU) | Closest to "a partition of the scene into whole entities", and it saw comics in training. The non-commercial licence fits a hackathon only |
| **CutLER / MaskCut** ([arXiv 2301.11320](https://arxiv.org/abs/2301.11320)) | Unsupervised class-agnostic object masks. Over 2.7× AP50 on 11 benchmarks, including paintings and sketches | Meta; CC-BY-NC ([repo](https://github.com/facebookresearch/CutLER)) | — | Finds salient objects, not stuff such as floors and walls. Useful mainly as UnSAMv2's pseudo-label source |
| **U2Seg** ([arXiv 2312.17243](https://arxiv.org/abs/2312.17243)) | Unsupervised instance, semantic and panoptic segmentation from clustered self-supervised features | Apache-2.0 ([repo](https://github.com/u2seg/U2Seg)) | — | Panoptic covers stuff as well as things, but quality is far below supervised models. Low priority |
| **SOHES** ([arXiv 2404.12386](https://arxiv.org/abs/2404.12386)) | Self-supervised entity plus part hierarchy | Code not found | — | Conceptually right (part-whole tree), but nothing to run |
| **OMG-Seg** ([arXiv 2401.10229](https://arxiv.org/abs/2401.10229)) | One model for semantic, instance, panoptic, open-vocabulary and interactive segmentation | MIT ([repo](https://github.com/lxtGH/OMG-Seg)) | — | The open-vocabulary panoptic mode still needs class names, which is the failure mode already hit |
| **X-Decoder** ([arXiv 2212.11270](https://arxiv.org/abs/2212.11270)) | Masks plus language tokens; open-vocabulary and referring segmentation | Apache-2.0 ([repo](https://github.com/microsoft/X-Decoder)) | — | Same caveat as OMG-Seg |
| **PartGLEE** ([arXiv 2407.16696](https://arxiv.org/abs/2407.16696)) | Object→part hierarchy via a Q-Former; open-world detection and segmentation | No LICENSE file ([repo](https://github.com/ProvenceStar/PartGLEE)) | — | Goes the wrong way: it adds parts, while Zumi needs wholes |
| **DINOv3** ([arXiv 2508.10104](https://arxiv.org/abs/2508.10104)) | Dense self-supervised features (not masks). Gram anchoring keeps dense features sharp | Meta; DINOv3 License ([repo](https://github.com/facebookresearch/dinov3)) | — | Use it as the similarity signal for merging over-segments, not as a segmenter **[reasoning]** |

**How to get wholes rather than tiles [reasoning, from the mechanisms cited above]:**
- **Pick the coarsest candidate.** Choose the whole level at the source: UnSAMv2 with g fixed high, Semantic-SAM level 3, or SAM's largest of its 3 multimask outputs (when its IoU score is acceptable). Avoid NMS over all levels.
- **Merge adjacent regions.** Build a region-adjacency graph and merge neighbours whose shared boundary has no depth step in DA3 depth and whose DINOv3 features match. Floor tiles share a continuous surface and similar features, so they merge. A crate on that floor has a depth step along its sides, so it stays separate.
- **Raise the size floors.** Set `min_mask_region_area` and a minimum area per layer as a share of the panel, so layers stay few.

## B. Occlusion and depth order between instances

| Method | Input → output | Weights / licence | Key numbers | Fit |
|---|---|---|---|---|
| **InstaOrder dataset** ([CVPR 2022, arXiv 2111.14562](https://arxiv.org/html/2111.14562)) | 2.9M occlusion-order and depth-order labels on 101K COCO images | Annotations on Google Drive ([repo](https://github.com/POSTECH-CVLab/InstaOrder)) | Finding: occlusion order and depth order are complementary | The reference benchmark |
| **InstaOrderNet^o,d** ([same](https://arxiv.org/html/2111.14562)) | Image + **2 masks** → occlusion (none / A over B / B over A / both) and depth (nearer / farther / equal). ResNet-50 | Weights released; MIT in the newer repo ([SNU repo](https://github.com/SNU-VGILab/InstaOrder)) | Occlusion F1 80.65 (o) / 81.86 (o,d). Depth WHDR 15.99 (o,d). MiDaS-median: 20.92 overall, 36.08 on overlapping pairs | **Accepts external masks**, so it runs on Zumi's SAM regions. Trained on photos; quadratic passes, but cheap with ResNet-50 **[reasoning]** |
| **InstaFormer** ([NeurIPS 2025, arXiv 2510.01704](https://arxiv.org/html/2510.01704)) | RGB only → its own Mask2Former instances plus full occlusion and depth matrices in one pass | MIT ([repo](https://github.com/SNU-VGILab/InstaOrder)) | Occlusion F1 81.89; depth WHDR 13.30; up to 12× faster than pairwise at 20 instances; labels cover at most 10 instances per image | Generates its own (COCO-trained) instances, so it does not take Zumi's masks |
| **Depth-median baseline** (same paper) | Grounded SAM + Depth Anything V2 → sort by masked median | — | WHDR 10.8 separated / **39.1 overlapping** / 22.4 overall | This is roughly the failed band approach. It works for separated things and fails on overlapping ones |
| **PCNet-M** (self-supervised de-occlusion, scored in [InstaOrder Table 2](https://arxiv.org/html/2111.14562)) | Order from amodal-completion asymmetry | In the InstaOrder checkpoint zip | Occlusion F1 63.02 | Weaker; no labels needed |
| **Comics depth** ([Bhattacharjee et al., arXiv 2110.03575](https://arxiv.org/abs/2110.03575)) | Translates comics to natural-looking images, then estimates depth, separating text from image content | — | Beats prior methods on DCM and eBDtheque (no numbers in the abstract) | Evidence that text and inking cause depth artefacts; Zumi already masks lettering |

**Support relations.**
- **Silberman et al.** ([ECCV 2012](https://cs.nyu.edu/~fergus/datasets/indoor_seg_support.pdf)) label each region as supported from below or from behind by another region, by a hidden region, or as ground. Each region also gets a structure class: ground, furniture, prop or structure.
- **Accuracy (type-agnostic / type-aware).** On ground-truth regions: image-plane rule ("the region directly below") 63.9 / 50.7; structure-class rules 72.0 / 57.7; integer-program model 75.9 / 72.6. On automatic segments: 22.1 / 19.4 for the rule and 55.1 / 54.5 for the model. Figures come from the submission-version PDF; camera-ready numbers may differ [unverified].
- **Failure modes.** Their main one is a wrong floor (a rug taken for the floor), which cascades to everything resting on it.
- **Scene graphs.** PSG ([arXiv 2207.11247](https://arxiv.org/html/2207.11247)) grounds 56 predicates on panoptic segments, including *on, sitting on, standing on, lying on, parked on* ("resting on" is not one). Detection-level recall is low: PSGTR SGDet R@20 is 28.4. That is too noisy to drive layer grouping.

**Mechanism Zumi can use [reasoning].** A shared boundary is either an occlusion edge or a contact.
- **Occlusion edge.** Depth jumps across it, and the nearer side is the occluder. Compare depth in a thin band on each side of the shared boundary, not the regions' medians; the medians are exactly what fails on overlapping pairs.
- **Contact.** Depth is continuous along the lower edge of the upper region, and the lower region is roughly horizontal (from the DA3 depth gradient or normals). That is support from below: put both in the **same layer**. This is the "region directly below" rule, gated by depth continuity.

## C. End-to-end layer decomposers (for comparison)

- **MuLAn** ([arXiv 2404.02790](https://arxiv.org/html/2404.02790)) is the same problem built from parts.
  - Parts: detCLIPv2 boxes → SAM ViT-H → MiDaS 3.1 → InstaDepthNet^o,d for the order graphs.
  - Ordering: sort by depth-graph out-degree; swap so that occluded instances are inpainted first; break mutual occlusions by maximum depth.
  - Background: one flat layer. Inpainting: SD 1.5.
  - Result: 36% of 5,000 decompositions rated successful (52% counting minor defects). Segmentation was the top failure.
  - Lesson: the ordering logic is reusable; errors compound across stages.
- **Qwen-Image-Layered** ([arXiv 2512.15603](https://arxiv.org/html/2512.15603v1), [HF](https://huggingface.co/Qwen/Qwen-Image-Layered)) is a diffusion model that returns 3–8 RGBA layers, composited back to front.
  - Apache-2.0, about 20B params (BF16), 640 px recommended, 50 steps.
  - Trained on PSD files and evaluated on Crello graphic designs.
  - Too large for 12 GB without quantisation [unverified whether quantised builds work]. Not Meta.
- **LayerD** ([arXiv 2509.25134](https://arxiv.org/html/2509.25134), Apache-2.0, [repo](https://github.com/CyberAgentAILab/LayerD)) repeatedly peels off the unoccluded top layer of graphic designs.
  - The peel-the-front loop is a useful ordering pattern. It is built for flat designs, not scenes.
- **RevealLayer** ([arXiv 2605.11818](https://arxiv.org/abs/2605.11818)): diffusion, RGBA layers with occluded content recovered. Code release not stated.

## Recommended pipeline for Zumi [reasoning]

Inputs: panel RGB, the character and lettering masks (excluded throughout), DA3 linear depth.

1. **Whole-level candidates.**
   - Run UnSAMv2 whole-image mode at one high granularity (try g = 0.8 and 1.0) on a 32×32 grid, not 64×64 × 10 values.
   - Fallback if it misbehaves on art: the current SAM 3.1 point predictor, keeping per point the largest multimask output with IoU ≥ 0.8.
   - Drop masks under about 1% of the panel. Subtract character and lettering masks.
2. **Make a partition.** Assign each pixel to the smallest confident mask that contains it. Leftover pixels become a "rest" region.
3. **Merge over-segments.** On the region-adjacency graph, merge neighbours when (a) the depth step across the shared boundary is below τ relative to depth, and (b) mean DINOv3 patch-feature cosine similarity is above σ. This targets floors, walls and skies.
4. **Classify each shared boundary.**
   - Depth step: occlusion edge, nearer side in front.
   - Continuous depth on the upper region's lower edge, over a roughly horizontal supporter: support, so union the two into one layer.
   - A small region fully enclosed by a near-vertical one with continuous depth (a picture on a wall): support from behind, so union as well.
5. **Order.**
   - Build a directed graph from the occlusion edges; add median-depth edges only between regions that do not touch.
   - Break cycles by dropping the edge with the smallest depth margin, then sort topologically.
   - Optional check: run InstaOrderNet^o,d on each touching pair (it accepts external masks) and flag disagreements rather than trusting either.
6. **Quantise to K layers.** Cut the topological order into 3–5 layers at the largest depth gaps. The furthest layer is the backdrop. Characters slot in by their own depth.
7. **Measure before tuning.** Hand-label about 30 panels with a pairwise front/behind table and report WHDR separately for touching and separated pairs, the split that exposed the median-depth failure.

## Risks

- **Domain gap.**
  - InstaOrder, Silberman and SA-1B are all photographs.
  - EntitySeg is the only source found with comic images in training, and it is non-commercial.
  - Flat shading, screentone and speed lines may give DA3 depth steps along ink lines rather than along object edges; [Bhattacharjee et al.](https://arxiv.org/abs/2110.03575) note text and style artefacts in comic depth.
- **No-object backgrounds.** Gradients, effect backgrounds and abstract panels have no wholes to find. The pipeline must degrade to a single backdrop layer rather than invent a split.
- **Support rule errors cascade.** In Silberman's experiments a wrong floor broke everything resting on it ([ECCV 2012](https://cs.nyu.edu/~fergus/datasets/indoor_seg_support.pdf)). Zumi's version is merging the floor with a rug or a table.
- **Granularity is image-relative.** UnSAMv2's g is normalised within each mask hierarchy ([paper](https://arxiv.org/html/2511.13714)), so the same g can mean "room" in one panel and "table" in another.
- **Licences.**
  - CutLER, UnSAM v1 and CropFormer are CC-BY-NC. SAM 3 uses the SAM License and DINOv3 the DINOv3 License.
  - UnSAMv2, U2Seg, X-Decoder, LayerD and Qwen-Image-Layered repos are Apache-2.0. OMG-Seg and InstaFormer are MIT.
  - Semantic-SAM and PartGLEE have no LICENSE file.
- **Holes behind layers.** Splitting the scene exposes occluded background. MuLAn found inpainting the second most common failure ([arXiv 2404.02790](https://arxiv.org/html/2404.02790)); parallax depth should stay small enough that holes stay hidden.
- **Speed is unmeasured.** No source gives the 3060 runtime of UnSAMv2 or SAM 2 automatic mask generation. Budget a test run before committing.
