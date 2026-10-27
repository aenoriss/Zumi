# Scene layers for comic panels: what the illustration/comics field offers (2026-10)

Question: how to split the scene around already-segmented characters and lettering into a few
whole, ordered layers (object + what rests on it; floor as one piece), for parallax on Quest 3,
on an RTX 3060 12 GB. This note covers only work specific to illustration, anime, manga and
comics, plus professional practice. Searched 2026-10-24. Claims not checked against a primary
source are marked [unverified].

## 1. Short answer

- **No published model decomposes a comic or anime *scene* (not character) into ordered layers.**
  The closest anime work, See-through, explicitly omits the background. The closest general
  model, Qwen-Image-Layered, is trained on PSDs (not comics) and needs ~45 GB at bf16.
- **The best-matched idea is "Illustrator's Depth"** (CVPR 2026): predict a per-pixel *layer
  index* instead of metric depth, then assign each flat-colour region the median index of its
  pixels. That is the recipe Zumi needs, but no weights are public and it was trained on simple
  vector art.
- **Professionals split by occlusion against the characters, not by depth.** Anime background
  art is a main plate plus "Book" layers: background pieces that pass *in front of* a character.
  Typical stacks are 3-5 planes.
- **The cheap route to "whole" pieces is line art itself.** Ink lines and flat fills define
  regions that already follow object outlines. Trapped-ball fill, edge-aware watershed and
  LayerD's palette snapping all exploit this. Grouping those regions by DA3 depth plus contact
  replaces the depth bands that failed.

## 2. Layer decomposition of anime and illustrations

| Work | What it splits | Scene/background? | Exploits line art / flat colour? | Runs on 12 GB? | Licence |
|---|---|---|---|---|---|
| See-through (SIGGRAPH 2026) | Character into up to 23 body-part RGBA layers + drawing order | No | No (diffusion + depth) | ~10 GB with offload at 1280 px | Apache-2.0 |
| Qwen-Image-Layered (2025) | Any image into N RGBA layers (3-8 shown) | Yes, generic | No | 45 GB peak bf16; FP8 suggested; 12 GB not reported | Apache-2.0 |
| LayerD (ICCV 2025) | Graphic designs, top layer peeled iteratively | Yes (designs) | **Yes**, palette snapping on flat regions | Likely (BiRefNet + LaMa) [unverified] | code public |
| Illustrator's Depth (CVPR 2026) | Per-pixel layer index, then binning | Partly (weak on backgrounds) | **Yes**, colour clusters get median index | Depth Pro size, <1 s on a modern GPU | no code found |
| LayerPeeler (2025) | Vector-style images, peel top layers with VLM + diffusion | Yes (simple graphics) | Partly | Not stated | no code found |
| Workflow-aware decomposition (2026) | Anime illustration into line art / flat / shadow / highlight | No (production passes, not depth) | **Yes** | Not stated | code public |

Details:

- **See-through** turns one anime illustration into inpainted semantic RGBA body-part layers and
  per-part pseudo-depth for ordering, trained on commercial Live2D models
  ([arXiv 2602.03749](https://arxiv.org/html/2602.03749v1)). Pipeline: SDXL with a LayerDiffusion
  transparency decoder, Marigold fine-tuned to predict per-part depth, LaMa for newly exposed
  regions; ~74 s per 1024 px image plus ~10 s depth on an RTX 4090. The paper states: "We omit
  background reconstruction, since production pipelines typically replace it with a new scene"
  ([same](https://arxiv.org/html/2602.03749v1)). Repo: Apache-2.0, bf16 ~12-16 GB at 1280 px,
  `--group_offload` ~10 GB, NF4 ~8 GB ([GitHub](https://github.com/shitagaki-lab/see-through)).
  Useful for Zumi later (a character's arm in front of its torso), not for scenes.
- **Qwen-Image-Layered** decomposes an RGB image into a variable number of RGBA layers with an
  RGBA-VAE and a diffusion transformer, trained on layers extracted from PSD files
  ([arXiv 2512.15603](https://arxiv.org/html/2512.15603v1),
  [GitHub](https://github.com/QwenLM/Qwen-Image-Layered), Apache-2.0, 640 px recommended).
  ComfyUI Wiki reports 45 GB peak and 120 s at 1024 px on a 96 GB card, near-full VRAM on a
  4090, and recommends FP8 for less VRAM
  ([ComfyUI Wiki](https://comfyui-wiki.com/en/tutorial/advanced/image/qwen/qwen-image-layered)).
  It is generative: it repaints pixels, and layer count is a prompt-time choice, not derived
  from the scene. Not a Meta model.
- **LayerD** extracts all unoccluded top layers with BiRefNet, fills the hole with LaMa, and
  repeats (max 3 iterations). Its refinement is the line-art trick: where gradients are near
  zero, completed pixels snap to a ≤2-colour palette, and flat connected regions matching the
  palette are merged into the foreground mask. The authors chose LaMa over FLUX.1 Fill because
  FLUX "often inserted unwanted objects"
  ([arXiv 2509.25134](https://arxiv.org/html/2509.25134v1),
  [code](https://github.com/CyberAgentAILab/LayerD)). Trained on Crello designs, not comics.
- **Illustrator's Depth** predicts, per pixel, the index of the layer an artist would have
  drawn it on. Built on Depth Pro (DINOv2 encoder), trained on ~100K layered SVGs. On 100 test
  images, pixel-pair order accuracy 0.987 vs 0.791 for Depth Anything v2 and 0.636 for Depth
  Pro. For decomposition, colours are clustered, each cluster gets its median predicted index,
  similar clusters merge, then layers are sorted and inpainted
  ([arXiv 2511.17454](https://arxiv.org/html/2511.17454v1),
  [CVPR 2026 poster](https://cvpr.thecvf.com/virtual/2026/poster/38824)). Stated limits:
  trained on "single objects over white backgrounds", so background elements such as stripes
  can be ignored; textures read as foreground. No repository or weights found.
- **LayerPeeler** removes the topmost unoccluded layers one at a time, with a VLM building the
  occlusion graph and a fine-tuned diffusion model doing the removal
  ([arXiv 2505.23740](https://arxiv.org/abs/2505.23740v1)).
- **Workflow-aware layer decomposition** splits anime illustrations into production passes
  (line art, flat colour, shadow, highlight)
  ([arXiv 2603.14925](https://arxiv.org/abs/2603.14925v2),
  [code](https://github.com/zty0304/Anime-layer-decomposition)). Not depth layers, but a flat
  pass would make region extraction on shaded webtoon art much easier [inference].

## 3. Regions from line art and flat colour (the cheap route)

- **Trapped-ball segmentation** (Zhang et al., TVCG 2009): a ball of fixed diameter flood-fills
  without crossing ink, so gaps narrower than the ball do not leak
  ([paper](https://cg.cs.tsinghua.edu.cn/papers/TVCG_2009_cartoon.pdf); mechanism as described in
  [arXiv 1706.06918](https://arxiv.org/pdf/1706.06918)). Known to over-segment near boundaries;
  small regions are merged afterwards.
- **Measured on manga line art** (Li et al., CVPR 2026): closed-contour filling "fail[s] to
  produce meaningful segmentation" because hand-drawn line art has few closed contours;
  TrappedBall over-segments; SAM "often merges semantic parts, such as the face, with the
  background" and lacks fine boundaries without colour or shading cues. Their own pipeline
  merges patches by learned similarity, runs an edge-aware watershed on a Sobel map of the
  strokes, then merges small fragments by contact length and edge strength
  ([arXiv 2509.09501](https://arxiv.org/html/2509.09501),
  [code](https://github.com/liyingxuan1012/r2r-lineart-correspondence)).
  The SAM finding matches Zumi's own point-grid failure.
- **Delaunay Painting** closes contour gaps by triangulating the strokes and has an automatic
  mode for segmenting contour images
  ([CGF 2022](https://diglib.eg.org:443/handle/10.1111/cgf14517)).
- **Screentone** is the obstacle in B/W manga: its dots and lines resemble contours. Liu et al.
  estimate screentone regions from texture features and refine with graph cut
  ([CVM 2017](https://link.springer.com/article/10.1007/s41095-016-0069-x)); ScreenVAE maps
  screentone to a smooth intermediate domain
  ([project](https://www.cse.cuhk.edu.hk/~ttwong/papers/screenstyle/screenstyle.html)).
- **Flatting** (filling each closed region with one flat colour) is the step professional comic
  colourists automate; FlatMagic is an AI flatting tool for Photoshop that cut professionals'
  measured effort in a CHI 2022 study ([project](https://cragl.cs.gmu.edu/flatmagic/)).
  A flatting output is exactly a region map.

## 4. Depth for comics

- **ComicsDepth** (WACV 2022): translate comics to photo style, then run an attention-guided
  depth model; a text/art separation module reduces artefacts; releases a comics depth
  evaluation set ([CVF](https://openaccess.thecvf.com/content/WACV2022/html/Bhattacharjee_Estimating_Image_Depth_in_the_Comics_Domain_WACV_2022_paper.html),
  [arXiv 2110.03575](https://ar5iv.labs.arxiv.org/html/2110.03575)). Predates DA-class models;
  of interest mainly for its eval set. A CVPRW 2023 follow-up extends it to multitask dense
  prediction ([arXiv 2307.08071](https://arxiv.org/abs/2307.08071)).
- **Toon3D** builds 3D from a few inconsistent cartoon views via depth, point-cloud warping and
  Gaussian refinement ([GitHub](https://github.com/ethanweber/toon3d)). Multi-view, needs a
  labelling step; not a single-panel tool.
- A 2024 comics survey names missing ground truth as the main obstacle for comics depth
  ([arXiv 2409.09502](https://arxiv.org/pdf/2409.09502)). I found no anime-specific open depth
  checkpoint; See-through's anime Marigold is trained for per-part character depth only.

## 5. Datasets

| Dataset | Content | Scene layers? | Licence |
|---|---|---|---|
| Manga109 | 109 volumes; boxes for frame, text, face, body | No | academic, non-profit ([arXiv 2005.04425](https://arxiv.org/pdf/2005.04425)) |
| MangaSeg (CVPR 2025) | Manga109 masks: frame, text, onomatopoeia, body, face, balloon | No | annotations credited to authors; images under Manga109 ([CVF](https://openaccess.thecvf.com/content/CVPR2025/html/Xie_Advancing_Manga_Analysis_Comprehensive_Segmentation_Annotations_for_the_Manga109_Dataset_CVPR_2025_paper.html), [HF](https://huggingface.co/datasets/MS92/MangaSegmentation)) |
| COO | 10,602 images of Japanese onomatopoeia, with links between truncated fragments | No | ([ECCV 2022](https://www.ecva.net/papers/eccv_2022/papers_ECCV/html/1946_ECCV_2022_paper.php), [GitHub](https://github.com/ku21fan/COO-Comic-Onomatopoeia)) |
| CoMix / PopManga | Detection, speaker ID, re-ID, reading order; PopManga test 1,136 + 789 pages | No | ([arXiv 2407.03550](https://arxiv.org/pdf/2407.03550)) |
| Anime instance seg. (2023) | >100K cartoon images with character instance masks; demo of 3D Ken Burns | Characters only | weights MIT ([arXiv 2312.01943](https://arxiv.org/pdf/2312.01943), [HF](https://huggingface.co/dreMaz/AnimeInstanceSegmentation)) |
| skytnt anime-segmentation | Foreground/background split images | fg/bg only | CC0 ([HF](https://huggingface.co/datasets/skytnt/anime-segmentation/blob/adefd25c170fbfc15ea5b395c4d2918fef1a7959/README.md)) |

No dataset labels scene layers or support relations in comics. Evaluation will have to be Zumi's
own hand-labelled panels.

## 6. Commercial and production practice

- **Anime "Book" layers.** Background elements not painted onto the main plate, used when an
  object must sit in front of an animated character (e.g. doors a character walks behind), and
  to get parallax in camera moves; numbered from the camera, Book.A nearest
  ([Wolf Children art book review](https://halcyonrealms.com/film/wolf-children-art-book-review-part-ii-layout-cg-more/);
  single source, practitioner blog).
- **Multiplane.** Disney's camera shot through up to five planes: two for animation, two for
  backgrounds, one fixed for sky ([Toon Boom docs](https://docs.toonboom.com/help/harmony-12-2/premium/basics/multiplane.html));
  layers are transparent except where art is ([Wikipedia](https://en.wikipedia.org/wiki/Multiplane_camera)).
- **Live2D material separation.** Finer division gives better models; parts that move a lot,
  and parts revealed when others move, are drawn first, i.e. hidden areas are painted in
  ([Live2D manual](https://docs.live2d.com/en/cubism-editor-manual/divide-the-material/)).
  Rule: split by what moves or gets revealed, not by semantics.
- **Motion comics.** Artists rarely get layered art; they cut flat art into layers in
  Photoshop, and the planned animation decides the layering
  ([Adobe Community](https://community.adobe.com/t5/after-effects-discussions/how-to-create-motion-comic-effect-in-after-effects-premiere/m-p/14857154), forum).
  In the DancingBoard study's expert workflow, each visual element is its own layer and
  backgrounds are often just blurred for depth ([arXiv 2503.09061](https://arxiv.org/html/2503.09061v1)).
  "Not every panel needs ten layers" comes from a vendor blog
  ([LlamaGen](https://llamagen.ai/blogs/motion-comic-vs-animatic)) [unverified as practice].
- **Webtoon effects.** Naver's Webtoon Editor lets artists add scroll-driven motion; the demo
  had a rising moon and distant buildings growing as the reader scrolls
  ([Korea JoongAng Daily](https://www.koreajoongangdaily.com/lifestyle/webtoon-artists-get-special-effects-help-from-naver/10463021)).
  Layers there are drawn by the artist.
- **Immersity AI (Leia).** 4.0 separates foreground and background into layers and fills
  occluded detail ([press release](https://www.presshook.com/brands/leia-inc/press-releases/leia-inc-unveils-immersity-40-revealing-hidden-details-in-any-digital-image));
  method undisclosed, and nothing comic-specific.
- **Wallpaper Engine** offers two modes: per-layer parallax depth on hand-cut layers
  ([docs](https://docs.wallpaperengine.io/en/scene/parallax/introduction.html)) and a
  depth-map shader on one image ([docs](https://docs.wallpaperengine.io/en/scene/parallax/depthparallax.html)).
  One anime wallpaper fixed "depth inconsistencies" by moving particles into separate layers
  ([changelog](https://steamcommunity.com/sharedfiles/filedetails/changelog/1503318128?l=spanish)).
- **ComiXR** (KAIST, ACM DIS 2026, Meta Quest Pro, open source): in a 15-person study,
  immersion rose when characters sat at a different depth from the background and when
  speech bubbles were on separate layers ([KAIST](https://ee.kaist.ac.kr/en/research-achieve/prof-ian-oakleys-team-develops-comixr-an-extended-reality-xr-platform-for-reading-and-creating-comics/),
  [GitHub](https://github.com/ammarjamal/ComiXR)). How their layers were made is not stated.

## 7. What Zumi should adopt

1. **Define the target the professional way.** Per panel: sky/far plate, main background plate,
   0-2 "Book" pieces (scene parts that overlap a character in front), characters, lettering.
   A scene piece goes in front only if it occludes a character or another piece; everything
   else stays on the plate. This caps the count at 3-5 layers and makes "floor as one piece"
   the default, because the floor never occludes anything above it. ComiXR's result says the
   character/background/bubble split delivers most of the effect.
2. **Build regions from ink and flat colour, not from SAM grids or depth bands.** On flat-coloured
   panels: colour quantisation + connected components, with LayerD-style palette snapping.
   Where ink has gaps: trapped-ball or Sobel-edge watershed, then merge small fragments by
   contact length and edge strength (the CVPR 2026 recipe). Regions then follow outlines.
3. **Order regions the Illustrator's Depth way, using DA3 in place of its model.** Give each
   region the median DA3 depth of its pixels, merge adjacent regions with similar depth into
   pieces, and attach a region to whatever it rests on when they touch along a lower edge
   [inference, untested]. Then only Book candidates (pieces whose depth is clearly nearer than
   an overlapping character) get their own layer.
4. **Fill holes with LaMa**, as See-through and LayerD both do; LayerD found FLUX Fill inserts
   objects. For B/W screentone, MangaInpainting (SIGGRAPH 2021; licence allows commercial use)
   ([project](https://www.cse.cuhk.edu.hk/~ttwong/papers/mangainpaint/mangainpaint.html)).
5. **Benchmark, do not adopt, Qwen-Image-Layered** on 10 panels via FP8 or offload, as an upper
   bound for "whole pieces". Watch Illustrator's Depth for a weight release; a layer-index model
   is the right long-term ordering signal.
6. **Keep See-through for later**, for character self-occlusion, not for scenes.

## 8. Risks

- **Painterly webtoon backgrounds** (Tower of God style) have gradients, not flat fills, so
  colour regions fragment. Mitigation: a flat pass first (§2 workflow-aware decomposition) or
  merging by DA3 depth plus DINO features [unverified that DINO helps here].
- **Screentone, speed lines and hatching** look like contours and over-segment; Illustrator's
  Depth also reads textures as foreground. They need a texture mask before region extraction.
- **Line gaps** leak flood fills; trapped-ball trades leaks for over-segmentation.
- **No ground truth** for comic scene layers anywhere (§5); evaluation must be hand-labelled.
- **12 GB VRAM**: Qwen-Image-Layered 12 GB fit is unreported; generative models repaint the
  artist's pixels, which may be unacceptable for a reader.
- **Licences**: Manga109 images are academic-only; MangaSeg annotations depend on them.
- **Meta preference**: none of the comics-specific work above uses Meta models except via
  DINOv2 inside Depth Pro (Illustrator's Depth) and SAM inside See-through and Toon3D.
