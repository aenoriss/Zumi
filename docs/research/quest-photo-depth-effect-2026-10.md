# The Quest Gallery "3D photo" effect, and what Zumi's flat layers lack — 2026-10-26

Research date: 2026-10-26. Method: Meta blog posts, help pages and a Meta patent; the Facebook 3D Photos papers (PDFs read in full); Apple developer docs and newsroom; Google blog and help pages. Nothing was run in a headset. **[unverified]** = secondary source or not confirmed; **[inference]** = my reasoning. Every pixel figure is computed by me, not measured. It assumes a 63 mm IPD, a 1.5 m viewing distance (the one `cards.py` assumes) and Quest 3's 25 px/degree, so 1 px ≈ 2.4 arcmin.

## Answer

1. **What the effect is.** Since 2026 the Horizon OS Gallery opens photos and videos "in 3D" by default, "to add lifelike depth" ([Meta blog, 2026-08-25](https://www.meta.com/blog/explore-the-latest-meta-quest-updates/)). You can also upload phone photos from the Horizon app to view them in 3D (same post). A PTC build added "View in 3D" for images in the Quest Browser ([UploadVR, 2026-05](https://www.uploadvr.com/quests-latest-ptc-update-turns-web-photos-into-3d/), **[unverified]**). It follows the 2025 Instagram-on-Quest test, which used "AI view synthesis algorithms" to transform photos "pixel by pixel" ([Meta blog, 2025-05-22](https://www.meta.com/blog/instagram-3d-photos-spatial-medianavigator-meta-quest-test/)).
2. **How Meta makes it: not published.** I found no paper, developer doc or release note that describes the current pipeline. The best evidence is Meta's own lineage:
   - [One Shot 3D Photography](https://arxiv.org/abs/2008.12298) (Kopf et al., Facebook, SIGGRAPH 2020): monocular depth, a layered depth image (LDI), inpainting, then a mesh.
   - A 2021-2024 Meta patent on viewing those photos in VR as framed windows ([US20220383602A1](https://patents.google.com/patent/US20220383602A1/en), granted as US 11,961,201 B2). It names Kopf and Quigley as inventors.
   - "Pixel by pixel" suggests per-pixel depth or view synthesis, not cut-out layers **[inference]**.
   - Horizon-app uploads are processed by Meta and then appear in the headset, which points to the cloud for that path **[inference]**.
3. **What makes these effects convincing.** All five points come from Meta and Apple primary sources:
   1. **Stereo and head-motion parallax together**, with head motion mapped 1:1 in 6DoF (Kopf 2020, §5).
   2. **A window frame that clips the scene**, with the scene seen through it. Apple puts the nearest object "just behind the front of the window".
   3. **Holes filled before viewing.** The background is extended up to 50 px behind every depth edge and then inpainted.
   4. **Head motion kept inside a quality zone.** Viewing angles are constrained and the photo fades out (2020). In the patent, the photo pivots to follow the viewer, with a dead zone, hysteresis and clamping.
   5. **Depth normalised per image**, so every scene gives the same on-screen parallax whatever its real scale (Practical 3D Photography, 2019).
4. **What Zumi lacks.** On the user's observation (2026-10-26) that "it looks 3d due to the frame but its still 2d": the numbers predict exactly that **[inference]**.
   - One Zumi step (1.5 cm at 1.5 m) gives 1.5 arcmin of stereo disparity, which is **0.6 px** on Quest 3. The full four-step stack gives **2.5 px**.
   - The panel's frame against a room wall 3 m away gives **30 px**. So the frame is the only strong stereo cue, and the art inside is near the threshold.
   - Zumi also has the window backwards. The frame sits at the backdrop, the farthest plane, so cards in front of it are clipped by an edge behind them: a stereo window violation.
   - The fix the sources point to: a larger depth budget **behind** a window plane, with head-motion parallax damped separately from stereo.

## 1. What the Meta effect does visually

| Question | What primary sources say | Status |
|---|---|---|
| Stereo or head parallax | The current Gallery feature: no Meta description beyond "lifelike depth" ([blog](https://www.meta.com/blog/explore-the-latest-meta-quest-updates/)). Meta's own prior system did **both**: "adding stereo viewing to head-motion induced parallax", 1:1 in 6-DOF headsets, and in 3-DOF it fakes translation from neck rotation ([Kopf 2020](https://arxiv.org/abs/2008.12298), §1, §5.2). The patent: "separate images for each eye … (stereopsis)" plus "real-time positional and rotational head tracking" ([patent](https://patents.google.com/patent/US20220383602A1/en)) | Current feature **[unverified]**; lineage confirmed |
| How strong the depth is | Not stated anywhere for Quest. Facebook normalised the depth range "so each scene induces the same amount of screen-space parallax, independent of its real-life scale" ([Practical 3D Photography](https://johanneskopf.de/publications/photo3d_practical/Practical_3D_Photography.pdf), §2). UploadVR: the browser result "floats beyond the frame with convincing depth" | Secondary for Quest |
| Edges and holes | Kopf 2020: depth is sharpened into step edges (5×5 weighted median, merging components under 20 px), then background geometry grows behind every discontinuity for **50 iterations** (1 px per iteration). It is then inpainted by a PartialConv network running *on the LDI*. Screen-space inpainting was rejected because it "leads to strong blur artifacts along the edges" and differs between views (§4.2-4.3) | Confirmed for the 2020 system |
| Framing | "We create a frame around the model to hide the outer boundary of the photo. The result appears like a 3D model viewed through a 2D frame … we constrain the viewing angles and fade the model out if there is too much head motion" (Kopf 2020, §5). Patent: each frame "may act like a window", each photo "clipped at its frame" with shader clipping planes. Photos "only look good from a narrow region around their capture point", so the photo is rotated, translated and **non-uniformly scaled** so that its optimal viewpoint follows the viewer: a dead zone for small motion, hysteresis (a spring) and a clamping region. No numeric thresholds are given | Confirmed (patent claims 1, 6-9) |

## 2. How Meta generates it

- **Current Quest Gallery, browser and Instagram: nothing published.**
  - Meta says only "AI view synthesis algorithms … pixel by pixel" ([2025 blog](https://www.meta.com/blog/instagram-3d-photos-spatial-medianavigator-meta-quest-test/)).
  - The release notes page is JS-rendered and could not be read. Search snippets put "Gallery media adds lifelike depth automatically" in Horizon OS 2.5, week of 2026-06-22 **[unverified]**.
  - Searches of arXiv and Google Patents found no 2024-2026 Meta paper or patent on single-image stereo conversion.
  - Where it runs is not stated for Gallery or the browser. The browser takes "a few seconds" ([UploadVR](https://www.uploadvr.com/quests-latest-ptc-update-turns-web-photos-into-3d/), **[unverified]**).
- **The 2020 system Meta shipped**, used "over 100 million times" in the Facebook app (Kopf 2020, §6.1). On an iPhone 11 Pro it took **1,098 ms** for a 1152×1536 image:

  | Stage | What it does | Time |
  |---|---|---|
  | Depth | Mobile network, estimated at 288×384 | 230 ms |
  | Depth filtering, components, occluded geometry | Prepares the LDI | 94 ms |
  | Colour inpainting | Fills the hidden layers | 540 ms |
  | Texture charts | Atlas for the mesh | 234 ms |
  | Meshing | Simplified triangles in the atlas domain, lifted along each pixel's ray | 11 ms |

  - Rendering was three.js with WebVR, one view per eye (§5.2).
  - The 2018 dual-camera version took 1.8 s on an iPhone X and used diffusion inpainting ([Practical 3D Photography](https://johanneskopf.de/publications/photo3d_practical/Practical_3D_Photography.pdf)).
  - The research sibling, [3D Photo Inpainting](https://arxiv.org/abs/2004.04727) (Shih, Su, Kopf, Huang, CVPR 2020), does the same LDI inpainting with context-aware networks.
- **Best inference for 2026.** A server-side depth plus view-synthesis model (DIBR or a learned novel-view model), rendered on the headset with stereo and some head parallax **[inference]**. Mesh or Gaussian splats? Nothing distinguishes them. Meta has no published single-image splat model (see [feedforward-splat-2026-10.md](feedforward-splat-2026-10.md)).

## 3. Comparable features

| Feature | Representation | Viewing | Where it runs | Source |
|---|---|---|---|---|
| **Apple spatial scenes** (visionOS 26, iOS 26) | "generate textured 3D geometry from either a spatial photo or a regular 2D image". Unlike a *spatial photo*, which "presents two separate 2D images, one to each eye" | Window mode (`spatial3D`) or immersive (`spatial3DImmersive`). Users "lean in and look around" | `generate()` takes "several seconds"; not in the Simulator. Newsroom: "a new generative AI algorithm and computational depth" | [Presenting images in RealityKit](https://developer.apple.com/documentation/realitykit/presenting-images-in-realitykit), [ImagePresentationComponent](https://developer.apple.com/documentation/realitykit/imagepresentationcomponent), [newsroom 2025-06](https://www.apple.com/newsroom/2025/06/visionos-26-introduces-powerful-new-spatial-experiences-for-apple-vision-pro/) |
| **Apple spatial photos: comfort rule** | A stereo pair plus a disparity adjustment as a fraction of image width | **+2%** of width puts "the nearest object … just behind the front of the window, while still keeping an effective illusion of depth" | — | [Writing spatial photos](https://developer.apple.com/documentation/imageio/writing-spatial-photos) |
| Apple SHARP (ICLR 2026) | One image to ~1.2 M Gaussians, metric scale, "for nearby views" | — | <1 s on a GPU | [arXiv 2512.10685](https://arxiv.org/abs/2512.10685). Whether it powers spatial scenes is **[unverified]** |
| **Google Photos on Android XR** | Converts 2D photos and videos to 3D | Quality "may vary" | Video conversion "happens in the cloud"; photos "take just a few seconds" | [Google Photos help](https://support.google.com/photos/answer/16667814?hl=en) |
| **Android XR auto-spatialization** (Galaxy XR, 2026-04) | Turns "almost any app, game, website, image or video" into 3D. Experimental, in Labs | Focused window only, Home Space, ≤1080p30 | Uses "slightly more battery", so on-device **[inference]** | [Google blog](https://blog.google/products-and-platforms/platforms/android/android-xr-immersive-features-update-april-2026/), [help](https://support.google.com/android-xr/answer/17004031?hl=en) |
| Google Cinematic photos (2020) | Depth mesh extruded from the photo; segmentation pulls people forward | A **virtual camera path optimised per photo** to hide "stretchiness" | Cloud | [Google Research blog](https://research.google/blog/the-technology-behind-cinematic-photos/) |
| **Facebook 3D Photos** (2018-2020) | LDI, then an inpainted textured mesh | Stereo plus head parallax, a frame, constrained angles, fade-out | On the phone, 1.1-1.8 s | Kopf 2019/2020 above |

## 4. Why Zumi reads as "3D frame, 2D picture"

Every figure in this section is computed by me **[inference]**.

| Pair | Stereo disparity | Head-motion parallax, 5 cm lean |
|---|---|---|
| Card one step (1.5 cm) in front of the backdrop, at 1.5 m | 1.5′ = **0.6 px** | 0.5 px |
| Card four steps (6 cm) in front | 6.0′ = **2.5 px** | 2.0 px |
| Panel frame at 1.5 m against a room wall at 3 m (passthrough) | 72′ = **30 px** | — |
| Earlier tries the user rejected, if 4 steps were used: 0.03 → card at 1.32 m | — | 6.5 px ("moved too much") |
| Same, 0.08 → card at 1.02 m | — | 22 px |
| Proposed: backdrop 30 cm **behind** a window at 1.5 m | 24′ = **10 px** | 8 px undamped |

Four things follow:

- **Stereo inside the panel is 12-50× weaker than the frame's own depth cue.** The brain places the panel as an object in the room and reads the art as printed on it, which is what the user saw.
- **The step size was tuned against head-motion parallax.** Today stereo and head parallax are the same geometry, so lowering one lowered the other. Meta's patent separates them: full stereo, damped motion (pivot, dead zone, clamping).
- **The window is on the wrong side.**
  - The stencil clips cards at their frame, and that edge lies in the backdrop plane, 1.5-6 cm *behind* the cards. A near object cut by a farther edge is a window violation.
  - Apple and Facebook both put the scene behind the window ("just behind the front of the window"; "viewed through a 2D frame").
  - Bubbles are the exception, and they already behave correctly: they are on the glass and are not clipped.
- **Flat cards with no relief.** At small depths this does not show. At larger depths, flat cards sliding over each other read as cardboard. Kopf's meshes carry depth inside each region, with "interior vertices to represent depth variation" (Fig. 10) **[inference on the cardboard effect]**.

What Zumi already has, compared with Meta's system: a hole fill before viewing, done better than Kopf's 50-px LDI fill (FLUX Erase under each card). Clean step edges, from SAM masks with an ink fringe and an 0.8 px feather (Kopf has to sharpen his depth to get these). And per-frame windows via the stencil.

## 5. Plan for Zumi

Ordered by value per hour. Costs are my estimates.

| # | Change | Cost | Test |
|---|---|---|---|
| 0 | **Judge depth in stereo, not on a flat screen.** Add three.js `VRButton` and WebXR to `parallax_viewer/index.html` and open it in the Quest Browser. Today's viewer has no stereo, so sway is its only depth cue and it overweights head parallax | 1-2 h | Same box, same settings: look once on the desktop and once in the Quest. Note whether the cards separate in depth with the head held still |
| 1 | **Move the window forward.** Put each frame's stencil quad (plus an optional thin border) at the window plane, `z_w`, with the nearest card at or 0-1 cm behind it. Cards spread back from there; the backdrop is deepest. Bubbles go on or just in front of the glass, unclipped (as today). The stencil should mark the window quad, not the backdrop's alpha | 2-3 h (`cards.py` z assignment, viewer and Unity stencil) | Look for a card cut at the frame edge in stereo (the violation should be gone). A/B against today on 5 boxes |
| 2 | **Set the depth budget as disparity at the viewing distance**, not as 1% of backdrop depth. Backdrop 10-50 cm behind the window at 1.5 m gives 4-15 px. Space the cards between them by DA3MONO order, still in steps. Use the format's per-panel `depthScale` so the XR app can tune it (decisions.md §3). Normalise per panel, as Facebook did | 1 h plus tuning | Sweep the backdrop at +10, +20, +30, +50 cm (3.8, 7.1, 10, 15 px). The user rates "depth inside the art" and comfort at each. Pass: depth visible inside the panel with the head still, and no strain after 2 min. The comfort bounds in diopters are in [Shibata et al. 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3369815), not checked here **[unverified]**; the proposed range is ≤0.17 D from the window |
| 3 | **Damp head-motion parallax separately from stereo** (Meta's pivot). In Unity, keep the window world-locked. Translate the content group by `(1-k)·(head − rest)`, clamped to a radius, with a dead zone and a spring. Both eyes still see the full stereo depth, while lateral parallax is cut to `k`. Start with k = 0.3, a 2 cm dead zone and a 10 cm clamp **[inference: no numbers in the patent]** | 0.5-1 day | At backdrop +30 cm: undamped, a 5 cm lean gives 8 px. At k = 0.3 it is 2.4 px, about what the user accepted at 0.01. Check that it does not "swim" with the backdrop sliding against the frame. Compare k = 1, 0.5, 0.3 |
| 4 | **Give the cards relief.** Bend each card: fit DA3MONO inside its mask to a plane or a quadratic, clamped to ±1-2 cm, or inflate it from the mask's distance transform (a "pillow"). Use a 16×16-32×32 grid mesh per card instead of a quad | 0.5-1 day | At ±10 cm head offsets, does a character still read as a cut-out? Watch the silhouettes for edge tears where the bent card leaves the plate |
| 5 | **Check the hole budget after #2-3.** Only the erased plate under the cards hides the gaps. At +30 cm the backdrop shifts about 6 mm per eye (stereo) and 2 cm for a 10 cm lean, so ~6-20 px on a 700 px panel 0.7 m wide **[inference: panel size assumed]**. The erase covers the whole card footprint, so this should hold, but a card *refused* by the erase shows its doubled outline at a 10× larger offset | 1 h (measure) | Render at ±10 cm on the 6 boxes from the splat test plan. Count boxes with visible doubled outlines |
| 6 | **Fade or limit outside the zone** (Kopf §5). Fade the cards toward the plain backdrop, or freeze the pivot, when the head leaves the clamp radius | 2 h | Lean 30 cm sideways: there should be no tears and no plate edges |
| 7 | **Subtle motion: last, and only if 0-4 leave the panel dead.** In the headset, stereo and real head motion carry the depth; Kopf's "without motion, a 3D photo is just a 2D photo" was about 2D screens. Options: a slow per-panel push-in (a 1-2% scale over the panel's duration), or a ≤3 mm idle drift of near cards. Avoid a camera-style sway in XR | 2-4 h | A/B on the user, with vs without |

Leave out: MPI or splat rewrites (see the splat note) and fake depth for the frame border. The frame already works; the job is to put real depth *behind* it.
