# Objects, not support surfaces: clustering a single-view point cloud and returning clean 2D masks (2026-10-24)

Question: from one comic panel with characters and lettering already cut out, how do we get each OBJECT (table plus
what rests on it, vase, chair, rock) as its own RGBA layer while floor, walls, ceiling, ground and sky stay in one
back plate, with no class list, locally on an RTX 3060? Sibling notes: [scene-layers synthesis](scene-layers-synthesis-2026-10.md),
[ordering](scene-layers-ordering-2026-10.md). Claims are linked to primary sources; "reasoning" marks inference, and
timings without a link are estimates, not measurements.

## Bottom line

1. **Stop leaving image space.** The cloud is back-projected from a depth map, so every 3D point already owns a
   pixel. The 5-NN vote in (xyz, Lab) feature space is the step most likely to break the 2D result (section 0).
2. **Cluster superpixels, not points, with an LCCP-style convexity test.** Convexity separates objects from the
   surfaces they stand on by the geometry of the junction, not by plane size, which is what tore tables apart in
   the RANSAC attempt ([Stein et al., CVPR 2014](https://mlanthology.org/cvpr/2014/stein2014cvpr-object)).
3. **Decide "structure vs object" per segment afterwards** (large plane, horizontal at the bottom, vertical at the
   back, touches the frame), in the spirit of NYU support inference ([Silberman et al., ECCV 2012](https://mlanthology.org/eccv/2012/silberman2012eccv-indoor)).
4. **Snap boundaries with SAM 3.1 point prompts placed from the 3D segment**, the single-view case of
   SAMPro3D's "locate prompts in 3D" idea ([arXiv 2311.17707](https://arxiv.org/abs/2311.17707)), and resolve
   overlaps nearest-first.

## 0. Why the clusters look right in 3D but the 2D masks do not (reasoning)

- **Depth edges are smeared.** Geometry foundation models "still suffer severely from flying pixels"
  ([Xu et al. 2026](https://arxiv.org/abs/2601.05246)); L1/L2 regression blurs discontinuities
  ([survey, arXiv 2609.01172](https://arxiv.org/pdf/2609.01172)). A pixel on the outline of a vase gets a depth
  between vase and wall, so in xyz it floats in the gap. In a 3D viewer those points are sparse streaks you look
  past; in 2D they are exactly the outline, and the k-NN vote assigns them to whichever cluster is nearest in a
  feature space where they belong to neither.
- **The vote happens in the wrong space.** The unsampled 8 of every 9 pixels (stride 3) are labelled by
  distance in (xyz, Lab x 0.6), not by image adjacency or ink lines. Lab pulls a pixel toward any same-coloured
  cluster at similar depth; nothing in that space knows where the drawn contour is.
- **Density falls with depth.** Sampling every 3rd pixel spaces points proportionally to depth, so one DBSCAN eps
  over-merges near objects and fragments far ones. LCCP introduced a depth-dependent voxel grid for exactly this
  ([Stein 2014](https://mlanthology.org/cvpr/2014/stein2014cvpr-object)); HDBSCAN handles varying density
  ([scikit-learn 1.3+](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html)).
- **DBSCAN noise (-1) points** sit mostly on those same edges, so the boundary band has the fewest votes.

Cheapest fix to test first, keeping current DBSCAN clusters: write each sampled point's label at its own pixel,
drop noise and depth-edge pixels, then give every SLIC superpixel the majority label of the sampled pixels inside
it (section 2, row "superpixel vote").

## 1. Segmenting objects, not support surfaces (training-free)

| Method | In -> out | How it separates objects from floors/walls | Speed | Availability, licence | Fit to comic depth |
|---|---|---|---|---|---|
| DBSCAN / Euclidean clustering ([PCL tutorial](https://pcl.readthedocs.io/projects/tutorials/en/latest/cluster_extraction.html), [Open3D `cluster_dbscan`](https://www.open3d.org/docs/release/python_api/open3d.geometry.PointCloud.html)) | xyz(+colour) -> labels, -1 noise | It doesn't: an object touching the floor joins it unless the floor is removed first | Fast at ~100k points (estimate) | Open3D MIT, sklearn BSD | What we have; fails at contact and at density changes |
| HDBSCAN ([sklearn](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html)) | features -> labels + membership probabilities | Same as DBSCAN; only fixes varying density | Slower than DBSCAN (estimate) | sklearn >= 1.3, BSD | Drop-in for density, not for contact |
| Normal-based region growing ([PCL](https://pcl.readthedocs.io/projects/tutorials/en/latest/region_growing_segmentation.html)) | xyz + normals -> smooth regions | Grows from flattest seeds while neighbour normals stay within 3 deg (tutorial value); a floor becomes one region, an object on it stops at the crease | Fast | PCL C++ (BSD); easy to write on an image grid | Good for floor/wall extraction, over-segments rounded objects |
| Plane detection ([Open3D `segment_plane`, `detect_planar_patches`](https://www.open3d.org/docs/release/python_api/open3d.geometry.PointCloud.html)) | xyz -> planes (RANSAC) or oriented patches | By plane fit only | Fast | Open3D MIT | Our RANSAC failure: a table top is a plane too. Use only to classify segments already found, never to cut |
| VCCS supervoxels ([PCL tutorial](https://pcl.readthedocs.io/projects/tutorials/en/latest/supervoxel_clustering.html), [Papon CVPR 2013](https://pcl.readthedocs.io/projects/tutorials/en/latest/supervoxel_clustering.html)) | xyz, rgb, normals -> supervoxels + adjacency | Not by itself; it is the patch layer under LCCP/CPC. Weights: colour 0.2, spatial 0.4, normal 1.0 (tutorial defaults) | "Fast enough for online applications" (tutorial) | PCL only; Python via [pclpy](https://github.com/davidcaron/pclpy) (PCL 1.9.1, Python <= 3.7 on Windows, LCCP wrapping not stated) | On a depth map, SLIC superpixels plus image adjacency play the same role for free (reasoning) |
| **LCCP** ([Stein CVPR 2014](https://mlanthology.org/cvpr/2014/stein2014cvpr-object), [PCL class](https://pointclouds.org/documentation/classpcl_1_1_l_c_c_p_segmentation.html)) | supervoxel graph -> locally convex segments | Each patch edge labelled convex or concave; segments are convex-connected components. Object-on-floor and floor-wall junctions are concave, so they cut; a flat floor is merged by the tolerance (default 10 deg) | Graph pass is linear in edges (reasoning) | PCL C++ only; the edge test is ~20 lines ([source](https://pointclouds.org/documentation/lccp__segmentation_8hpp_source.html)), port it | Best match to "objects, not supports". Needs usable normals |
| **CPC** ([Schoeler CVPR 2015](https://openaccess.thecvf.com/content_cvpr_2015/html/Schoeler_Constrained_Planar_Cuts_2015_CVPR_paper.html), [PCL class](https://pointclouds.org/documentation/classpcl_1_1_c_p_c_segmentation.html)) | LCCP input -> planar cuts through concave regions | Adds greedy planar cuts (max 20, min score 0.16) where LCCP under-segments | Weighted RANSAC per cut, slower | PCL C++ only | Optional; splits parts, which we mostly do not want |
| Support inference ([Silberman ECCV 2012](https://mlanthology.org/eccv/2012/silberman2012eccv-indoor)) | RGB-D regions -> structure classes + "who supports whom" | Integer program over floor / structure / furniture / props and support edges | Learned features in the paper | Dataset NYUv2; idea reusable as rules | Gives us the policy: floor/walls = plate, supported items merge into their supporter |
| Min-cut ([PCL](https://pcl.readthedocs.io/projects/tutorials/en/latest/min_cut_segmentation.html)) / normalised cut on a RAG ([skimage.graph](https://scikit-image.org/docs/stable/api/skimage.graph.html) `cut_normalized`, `merge_hierarchical`) | graph -> partition | Only through the edge weights you design | Seconds on ~2k nodes (estimate) | skimage BSD | Useful as the merge engine with convexity + colour edge weights |

### 2D masks lifted into 3D (2023-2026)

All are built for multi-view posed RGB-D (ScanNet). With one view the "view consensus" part disappears, but
two pieces transfer: **superpoints from a normal-based graph segmentation** and **affinities from SAM masks**.

| Method | Core idea | Training-free? | Code, licence |
|---|---|---|---|
| SAM3D ([arXiv 2306.03908](https://arxiv.org/abs/2306.03908)) | Project SAM masks to 3D, bidirectional merge of adjacent frames, optional ensemble with Felzenszwalb over-segmentation | Yes | [Pointcept/SegmentAnything3D](https://github.com/Pointcept/SegmentAnything3D), MIT |
| SAI3D ([CVPR 2024](https://arxiv.org/abs/2312.11557)) | Superpoints by normal-based graph cut; per-view affinity = cosine of the SAM-mask-id histograms of two superpoints; region growing with thresholds 0.9 -> 0.5 ([paper](https://arxiv.org/html/2312.11557v2)) | Yes (zero-shot) | [yd-yin/SAI3D](https://github.com/yd-yin/SAI3D), licence not stated |
| SAMPro3D ([3DV 2025](https://arxiv.org/abs/2311.17707)) | Place SAM prompts in 3D and project them into each view; filter and consolidate prompts | Yes | [project page](https://mutianxu.github.io/sampro3d/) |
| MaskClustering ([arXiv 2401.07745](https://arxiv.org/abs/2401.07745)) | Mask graph, edge = how many other views' masks contain both | Yes | [project page](https://pku-epic.github.io/MaskClustering) |
| OV-SAM3D ([arXiv 2405.15580](https://arxiv.org/pdf/2405.15580v2)) | Superpoints + SAM affinity merge, open-vocabulary tags | Yes | [unverified] |
| Open3DIS ([CVPR 2024](https://arxiv.org/abs/2312.10671)) | 2D-mask-guided 3D proposals plus a 3D network's proposals | Partly; repo is built on ISBNet ([repo](https://github.com/VinAIResearch/Open3DIS), BSD-3) | |
| OpenMask3D ([NeurIPS 2023](https://arxiv.org/abs/2306.13631)) | Trained class-agnostic mask network + CLIP per mask | No, needs a mask-module checkpoint ([repo](https://github.com/OpenMask3D/openmask3d), MIT) | |
| Segment3D ([arXiv 2312.17232](https://arxiv.org/abs/2312.17232)) | Trains a 3D segmenter on foundation-model pseudo-labels | No | |

Superpoints in SAM3D and SAI3D come from ScanNet's Segmentator: Felzenszwalb-Huttenlocher on mesh normals,
`kThresh` 0.01, `segMinVerts` 20 ([ScanNet](https://github.com/ScanNet/ScanNet/tree/master/Segmentator)). The
single-view equivalent is `skimage.segmentation.felzenszwalb` or `slic` run on a normal/colour image
([skimage](https://scikit-image.org/docs/stable/api/skimage.segmentation.html)). None of these decides floor vs
object: they return every instance, the floor included, so a structure classifier is still needed.

### The convexity test (what to port)

From PCL's `connIsConvex` ([source](https://pointclouds.org/documentation/lccp__segmentation_8hpp_source.html)),
for patches s, t with centroids c and unit normals n (normals facing the camera):

- d = c_s - c_t. The edge is convex if angle(n_s, d) <= angle(n_t, d), i.e. (n_s - n_t) . d >= 0: the
  normals open away from each other, like the two faces of a box edge.
- Otherwise it is concave, but still accepted when angle(n_s, n_t) < concavity tolerance (default 10 deg), so a
  gently curved floor or a noisy flat wall stays whole.
- Smoothness check: reject if the plane-to-plane offset exceeds what the normals predict (catches depth steps
  between parallel patches, e.g. a picture frame in front of a wall).
- Sanity check: reject when the line where the two planes meet runs nearly parallel to d (threshold
  60 / (1 + exp(-0.25 (angle - 25))) deg).

Concrete: a vase standing on a table top. Table normal points up, vase side normal points at the camera, d
from table centroid to vase centroid points up and back. The normals close toward each other: concave, 90 deg
apart, above tolerance: cut. The table top meeting its own front edge is a box edge: convex: kept. That is the
behaviour RANSAC plane removal could not give.

## 2. From 3D labels back to clean 2D masks

| Method | In -> out | Handles depth-edge bleed? | Speed | Availability |
|---|---|---|---|---|
| Z-buffer rasterisation | points + labels -> label image, nearest point per pixel wins | Only occlusion; for a cloud built from our own depth map there is none, each point already has its pixel (reasoning) | ms | numpy |
| Nearest-sample fill | sparse stride-3 labels -> full res | No, a 1-3 px staircase on every edge | ms | numpy / `cv2.resize` |
| Joint bilateral upsampling ([Kopf SIGGRAPH 2007](https://www.johanneskopf.de/publications/jbu)) | low-res solution + full-res RGB guide -> full-res | Partly: weights by colour similarity, so ink lines stop it | Fast | [opencv_contrib ximgproc](https://github.com/opencv/opencv_contrib/tree/4.x/modules/ximgproc) "Joint Bilateral Filter"; run per label on one-hot maps, argmax |
| Guided filter ([He ECCV 2010](https://people.csail.mit.edu/kaiming/eccv10/index.html)) | per-label soft mask + guide -> refined soft mask | Partly; linear time regardless of radius | Fast | ximgproc "Guided Filter" |
| Fast bilateral solver ([Barron & Poole](https://arxiv.org/abs/1511.03296)) | target + confidence + guide -> edge-aware result; reported 10-1000x faster than competitors, used for semantic segmentation | Yes, via confidence: set 0 on depth-edge pixels so they are filled from the colour side | Fast | [`createFastBilateralSolverFilter`](https://docs.opencv.org/5.x/db/d50/classcv_1_1ximgproc_1_1FastBilateralSolverFilter.html) in ximgproc |
| Superpixel majority vote | labels + SLIC/Felzenszwalb regions -> one label per region | Yes if superpixels follow ink lines; boundary quality = superpixel quality | SLIC ~1 s per panel (estimate) | [skimage `slic`, `felzenszwalb`](https://scikit-image.org/docs/stable/api/skimage.segmentation.html) |
| SAM region vote | labels + SAM automatic masks ([SAM 2 generator](https://github.com/facebookresearch/sam2/blob/main/sam2/automatic_mask_generator.py): 32x32 grid, IoU 0.8, stability 0.95) | Yes, SAM follows contours | Seconds | SAM 2 Apache-2.0; [SAM 3 repo](https://github.com/facebookresearch/sam3) does not advertise an everything mode |
| **SAM point prompts from each 3D segment** (single-view [SAMPro3D](https://arxiv.org/abs/2311.17707)) | per segment: positive points inside, negatives on neighbours -> crisp mask | Yes, and it is the only option here that redraws the edge from the image | ~0.1-0.3 s per segment on a 3060 (estimate) | SAM 3.1 point predictor (already working); [SAM License](https://github.com/facebookresearch/sam3) |
| Dense CRF ([Krähenbühl & Koltun NIPS 2011](https://arxiv.org/abs/1210.5644)) | hard labels as unary + RGB bilateral pairwise -> refined labels | Yes, colour-driven | Fast | [pydensecrf](https://github.com/lucasb-eyer/pydensecrf), MIT, needs a C++ build; Windows install is "problematic" per README |

Occlusion: with masks from several segments overlapping, give the overlap to the segment whose median depth on
the overlap is nearer; this is the 2D z-buffer. The sibling note warns median depth misorders some overlapping
pairs ([ordering note](scene-layers-ordering-2026-10.md)); the side of the shared edge that jumps toward the
viewer is the better tie-break.

## 3. Recommended pipeline for Zumi (reasoning, not yet measured)

1. **Geometry at full or half resolution.** DA3 depth -> xyz per pixel with 55 deg FOV. Normals from the image
   grid: n = normalise(dX/du x dX/dv) after a 5x5 median on depth. Depth-edge mask where the neighbour disparity
   jump exceeds 0.05 normalised (Kopf 2020 value, via the [synthesis note](scene-layers-synthesis-2026-10.md)).
2. **Patches.** SLIC on Lab, characters and lettering masked out, ~1500-3000 segments, compactness ~10;
   split any superpixel the depth-edge mask crosses. Per patch: median xyz, PCA normal and plane residual, mean
   Lab, pixel count, border contact.
3. **Graph.** Patches adjacent in the image; drop edges with a depth jump along most of the shared border.
4. **LCCP merge.** Port of `connIsConvex` (tolerance 10-15 deg, smoothness on, sanity on); union-find over
   convex edges; a Lab-distance veto so a red vase on a red table does not need to be convex-separated twice.
   Segments under ~1% of the scene merge into the neighbour with the longest shared border.
5. **Structure vs object.** Gravity = image-down, refined by the normal of the largest near-horizontal planar
   segment. A segment goes to the plate if it is planar (residual small vs its extent) AND one of: horizontal and
   lowest (floor/ground), horizontal and above the camera (ceiling), vertical and backmost or touching two frame
   edges (wall); or larger than 25% of the scene; or top-border and far (sky). Everything else is an object.
6. **Support merge.** An object segment whose lowest boundary rests on the top face of another object segment
   (concave contact, small vertical gap) joins that layer: "table with what rests on it". Keep as a switch.
7. **2D snap.** Per object: 3-5 positive points at distance-transform maxima of the eroded segment, negatives at
   neighbour centroids, padded box; SAM 3.1 point predictor, keep the whole-object mask. Accept if IoU with the
   segment > 0.5, then clip to the segment dilated ~8 px so SAM cannot spill onto the floor. Overlaps nearest-first.
   Fallback when SAM disagrees: fast bilateral solver on the one-hot segment, confidence 0 on depth edges.
8. **Alpha.** 1-2 px feather; inpaint the plate behind each cut-out as already planned.

Parameters to tune, in order of expected effect: concavity tolerance; depth-edge threshold; SLIC count and
compactness; structure planarity residual and the 25% area cap; support gap; SAM acceptance IoU and clip radius;
FOV (55 deg is a guess; DA3MONO-LARGE does not output intrinsics per its
[README](https://github.com/ByteDance-Seed/Depth-Anything-3), and a wrong FOV skews the angles the
horizontal/vertical tests read).

## 4. Risks

- **Normals from stylised depth.** Convexity needs normals; comic depth is often bulged on flat-shaded regions and
  flattened on objects (reasoning). Mitigation: plane fits per patch rather than per pixel, and a tolerance high
  enough that walls survive.
- **No concavity, no cut.** A picture on a wall or a rug on the floor is coplanar with its support; only colour or
  SAM separates it. The smoothness check catches a frame that stands proud of the wall, not a painted one.
- **Tables split at the legs.** The underside meeting a leg is concave, so legs may separate from the top; the
  support/adjacency merge in step 6 has to rejoin them. CPC exists for the reverse problem, not this one.
- **SAM leaks** onto floors with the same flat colour; the clip to the dilated 3D segment is the guard.
- **Python availability.** LCCP/CPC/VCCS exist only in C++ PCL; pclpy targets PCL 1.9.1 and Python <= 3.7 on
  Windows. Plan on the numpy port, not bindings.
- **Multi-view methods do not transfer whole.** SAI3D, MaskClustering and SAMPro3D rely on many views agreeing;
  with one panel their reported gains do not apply.
