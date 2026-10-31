# Filling what a head move uncovers: what the established methods do — 2026-10-27

Research date: 2026-10-27. This builds on [disocclusion-shadow-fill-2026-10.md](disocclusion-shadow-fill-2026-10.md) (the band widths, the 3D-photo systems, Telea, the shadow perception rules). It does not repeat them.

**Method.**
- **Sources.** Full text: the reference renderers' source code (HTM-16.2 renderer, a VSRS mirror), the DIBR and view-interpolation papers (Müller 2008, Mori 2009, Oh 2009, Zitnick 2004, Shade 1998, Didyk 2010, Stefanoski 2013), the conversion patents (In-Three, Conversion Works/Legend3D) and StereoBrush, Pérez 2003, Bertalmio 2003, Barnes' thesis, the AO papers (Alchemy, HBAO) and the Unity HDRP source. Abstract only: Fehn 2004, Zhang & Tam 2005, Tam 2004, Daribo 2010, Gautier 2011, Bosc 2011, Ndjiki-Nya 2011 and Stelmach 2000.
- **Run.** One local run on boxes 9, 20 and 24 of Pepper & Carrot 39 (§6). Nothing was run in a headset.
- **Labels.** **[inference]** = my reasoning or arithmetic. **[measured]** = my run (one machine, one episode, a 2D lean simulation). **[unverified]** = abstract only, secondary, or not confirmed.

**Symbols** as in the earlier note: d is the reading distance, f = 1152.6 px for a 1200 px box, and one box px ≈ 1.15 Quest 3 px ≈ 2.8′. The *band* is the strip behind a card's outline that a head move uncovers. The *lean* in §6 is t/d = 0.2 (30 cm at 1.5 m), which gives card shifts of 7-54 px on these boxes.

## Answer

1. **The established recipe is background-side extension, not a shadow.** I found no source that darkens disocclusions on purpose. Every source fills the band from the background side only and avoids smearing foreground colour into it:
   - the MPEG reference renderers (HTM's default is "line wise background extension"; VSRS uses OpenCV inpainting);
   - the DIBR papers (Oh 2009: "fill up the holes using the background pixels rather than the foreground ones");
   - 2D-to-3D conversion ("repeating pixels from the edge of the background object", which "often goes unnoticeable" if the gap is small).

   Before filling, every reference pipeline first **widens the hole 3-7 px into the background**. The edge pixels mix foreground and background colour and would otherwise show as a ghost contour.
2. **That widening step is missing in Zumi, and it shows** **[measured]**.
   - **Ghost contour.** With the hole exactly the card's mask, the outline's anti-aliased fringe stays in the backdrop. At a lean it appears as a dotted ghost outline. The mirrored texture of `blended_shadow` also reflects it into echo contours (P&C 39 p24, hair).
   - **Rest-view leak.** The card's 0.8 px feather lets the filled backdrop show through the card's own edge **at rest**. With `blended_shadow`, the rest view differs from the art by up to 79-109 levels, on 2,883-4,868 px per box (> 8 levels), as a dark rim.
   - **The fix.** Grow each card's opaque region by 2 px and feather outside it. This is Zitnick's boundary layer, and it moves the mixed pixels with the card. Then fill under the grown footprint. With that, the rest view is **pixel-identical** (max diff 0 on all three boxes).
3. **Ship a plain, subtle fill:**
   - **(a)** The 2 px boundary grow.
   - **(b)** A background-only fill of the band, PatchMatch completion from the same frame. Its cheap fallback is the membrane (diffusion) alone, *without* the mirrored texture.
   - **(c)** Instead of the offset cast shadow, at most a faint contact occlusion. That is a physically shaped ambient-occlusion term (strength 0.3), which darkens the revealed strip by **6-10 %** **[measured]**.

   On the three test boxes, the strip's mean colour moves from **ΔE 22-55** away from the surrounding ring (today) to **ΔE 2.4-11** (PatchMatch) or 2.5-19 (PatchMatch + AO). Its luminance moves from **19-44 % darker** than the ring to between 12 % darker and 7 % brighter (PatchMatch) or 1-21 % darker (with AO) **[measured, §6]**.
4. **Do not use the rubber sheet** (letting the backdrop near a card follow the card's parallax: Fehn-style depth smoothing). It is the established *small-gap* trick and leaves no hole. But in the run it bent the straight window mullions in p24. In stereo it would turn the backdrop around every figure into a tent. The user already rejected bending backdrops (`cards.py`, BACK_DETAIL / MAX_BREAKS notes). Conversion vendors call stretching a distortion to be "kept small".
5. **No published px or arcmin threshold for a "visible" stretched or blurred gap exists** that I could find. The closest are qualitative ("not extensively large", "kept small"), and one production figure: Titanic's 50-80 px shifts needed repainting. One-eye blur is tolerated (Stelmach 2000), so the ≤ 10 px strip that stereo alone shows can be smooth.

| Option | Established where | Seen on P&C 39 at a 30 cm lean | Cost per 1200×500 box | Failure modes on painted comics |
|---|---|---|---|---|
| **2 px boundary grow, alpha 1 inside** | Zitnick 2004 (4 px matting band), VSRS (7×7 disc dilation), HTM (6 px margin), Mori 2009 | No ghost contour; rest view identical (0 diff) | ~0 | A 2 px rim of the old background travels with the card where the ring is not ink (light halo on dark fills) **[inference]** |
| **Background-only PatchMatch band fill** | Barnes 2009 (Photoshop CS5 Content-Aware Fill), search-and-vote completion (Wexler et al. 2007, not read **[unverified]**), Criminisi/Daribo/Gautier "background side" | Best texture: wall, sky and wood continue; strip ΔE 2.4-11 to the ring | 78-158 s in numpy **[measured]**; ~1-5 s in C++ or on GPU **[inference]** | Copies the wrong structure (wood where a window was, p24); cannot continue straight lines; smoother than the ring (voting average) |
| **Membrane only (diffusion)** | Facebook 3D Photos (shipped to > 10 M photos), Pérez 2003's "membrane interpolant" | Clean, slightly soft; no echoes | 0.6-1.4 s **[measured]** | Blurs texture (Pérez: "unsatisfactory, blurred"); a stroke crossing the outline smears (a speed line in p9) |
| Membrane + mirrored high-pass (today's base) | Structure + texture idea of Bertalmio 2003, but with mirroring instead of synthesis | Echo contours of hair and outline (p24), doubled speed lines (p9) | 0.6 s | Mirrors whatever lies near the outline, ink included |
| **Planar contact AO, strength 0.3** | AO / obscurance (SSAO, Alchemy, HBAO); Luft 2006 depth darkening | Barely visible; strip 6-10 % darker | 0.5-0.9 s (FFT per card) | Wrong on glowing objects and bubbles: set 0 there (earlier note §7) |
| Offset cast shadow in art colours (today) | No precedent found in DIBR or conversion; Disney 1936 patent only | Strip 19-44 % darker, ΔE 22-55; a dark wedge on p24 | ~0.8 s | Reads as a second dark figure; leaks at rest through the feather |
| Rubber sheet (backdrop follows the card, linear over R = 3·shift) | Fehn 2004 / Zhang & Tam 2005 depth smoothing; In-Three "pixel repeat"; Disney IDW / StereoBrush | No hole, but the window mullions kink (p24) | Runtime mesh or shader | Bends straight lines; a stereo "tent" around figures **[inference]**; the user rejected bending backdrops |
| FLUX Erase plate (where cover < 50 %) | Generative inpainting | Keeps architecture best (p24 window); a darker blob in p9 | API call | Flat fields above ~60 % cover (user); can invent objects |

## 1. DIBR and view synthesis: what the reference systems do

| Source | Hole handling | Edge (mixed-pixel) handling | Numbers |
|---|---|---|---|
| **HTM-16.2 renderer** (3D-HEVC reference, H.265.2) | `HoleFillingMode` default 1: "line wise background extension". `xFillPlaneHoles` copies the first non-hole pixel on the background side across each run, row by row | `xRemBoundaryNoisePlane` overwrites up to `BlendHoleMargin` px next to each hole. `xCreateAlphaMapPlane` blends over a linear ramp of the same width | `BlendHoleMargin` = 6 px; `BlendZThresPerc` = 30; pre-filter off by default ([TRenTop.cpp, mirror](https://github.com/deepansh-ai/HEVC/blob/main/HTM-16.2/source/Lib/TLibRenderer/TRenTop.cpp)) |
| **VSRS** (MPEG FTV) | Default: `cvInpaint(..., 5, CV_INPAINT_NS)`. A compile-time NICT path first copies the farthest (background) pixel along the row, then runs Telea with radius 3 to smooth | The background-side boundary of each hole is dilated with a 7×7 disc (radius ≈ 3 px); a 3×3 median on the warped depth | [ViewSynthesis.cpp, unofficial mirror](https://github.com/keifergu/vsrs/blob/master/ViewSynLibStatic/src/ViewSynthesis.cpp) **[mirror, not the MPEG repo]** |
| **Mori et al. 2009** (basis of VSRS) | "The remaining blank area was filled with inpainting [Telea]" | Boundary matting "actually expands the border of the occlusion… It erases the mixture of foreground and background colors" | σd = 20, σr = 5, threshold 5 depth levels ([PDF](https://fukushima.web.nitech.ac.jp/paper/2009_spic_mori.pdf) §3.2-3.3) |
| **Müller et al. 2008** | "larger holes are currently filled linewise with neighboring available background information… This simple constant-color extrapolation of the background pixel leads to better results, than an unconstrained linear interpolation" | A "7-sample-wide area" along depth edges is marked unreliable and split into foreground and background boundary layers. A "three-tap low-pass filter" at depth edges | 7 px; 3 taps ([EURASIP JIVP 438148](https://jivp-eurasipjournals.springeropen.com/counter/pdf/10.1155/2008/438148.pdf) §4.1, §4.3) |
| **Oh, Yea, Ho 2009** | Telea, but "it makes more sense to fill up the holes using the background pixels rather than the foreground ones as the disoccluded area usually belongs to the background by definition". The foreground-side boundary is replaced by background so that the hole's "neighborhood only come[s] from background" | "we extend the holes boundaries by using image dilation" (width not given) | +0.02 to +0.7 dB PSNR ([MERL TR2009-025](https://shadow.merl.com/publications/docs/TR2009-025.pdf) §2-3) |
| **Zitnick et al. 2004** | No hole filling (two input views) | "If we use the original mixed pixel colors during image-based rendering, visible artifacts will result". Matting is computed "within a neighborhood of four pixels from all depth discontinuities". The boundary layer is rendered separately and is "about 1/64 the amount of data as the main layer" | 4 px band; discontinuity threshold 4 px of disparity ([PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/ZitnickSig04.pdf) §5, §7) |
| **Layered depth images** (Shade et al. 1998) | "The farther depth pixels, which are occluded from the LDI center, will act to fill in the disocclusions" | — | Zumi's backdrop under a card *is* the LDI's second layer ([PDF](https://grail.cs.washington.edu/projects/ldi/ldi.pdf)) |
| **Depth pre-smoothing** (Fehn 2004; Zhang & Tam 2005; Tam et al. 2004) | Smoothing depth across edges "reduces or completely removes newly exposed (disocclusion) areas". The asymmetric filter "reduces the amount of geometric distortion". In a 23-viewer test, quality ratings "improved with increasing levels of smoothing" with no loss of rated depth | — | Filter sizes not verified ([Zhang & Tam, DOI](https://doi.org/10.1109/TBC.2005.846190); [Tam 2004, DOI](https://doi.org/10.1117/12.583105); [Fehn, DOI](https://doi.org/10.1117/12.524762)) **[abstract only]** |
| **Depth-aided exemplar** (Daribo & Pesquet-Popescu 2010; Gautier et al. 2011) | Small disocclusions by depth pre-processing; larger ones by a Criminisi variant that "take[s] into account the depth information by distinguishing foreground and background parts". Gautier: "The depth is used to drive the filling order" | — | Gautier zeroes the priority on the foreground side of the hole (per [Buyssens et al. 2015](https://tschumperle.users.greyc.fr/publications/tschumperle_siggraphasia15.pdf) §2.3) ([Daribo DOI](https://doi.org/10.1109/mmsp.2010.5662013), [Gautier DOI](https://doi.org/10.1109/3dtv.2011.5877193)) **[abstract only]** |

**What they recommend by hole size** **[inference from the table]**:

- **A few px** (rounding cracks, the stereo-only strip): a median, a 3-tap low-pass, or plain background repeat. Mori: "one pixel wide blank region… can be filled by median filter".
- **Up to tens of px**: background-side extension or inpainting. HTM, VSRS, Müller and Oh all use a local method, not synthesis, with the background-side hole always widened by 3-7 px first.
- **Larger**: depth-aware exemplar synthesis (Daribo, Gautier, Ndjiki-Nya's background sprite).

Zumi's 30-55 px bands sit at the border between the second and third groups.

**Subjective quality.** Bosc et al. 2011 built the IRCCyN/IVC DIBR set: 7 hole-filling methods (Fehn, Telea, VSRS, Müller, Ndjiki-Nya, Köppel, unfilled), viewer ratings. They found that "usual metrics seem to be unable to express the degree of annoyance perceived" around disocclusions. I could not verify which method viewers ranked best ([DOI](https://doi.org/10.1109/jstsp.2011.2166245)) **[abstract only]**.

## 2. 2D-to-3D conversion practice

- **Small gaps are filled by repeating or stretching the background.**
  - In-Three: "the missing gap of pixels can be filled by repeating pixels from the edge of the background object that the object is moving away from". "As long as the pixel repeat gap is not extensively large … simply 'pixel repeating' background pixels across the gap often goes unnoticeable" ([US 7,116,323](https://patents.google.com/patent/US7116323B2/en), Background).
  - The patent's own method fills larger gaps from hidden pixels in other frames: a clean plate.
- **Stretching is a distortion to keep small.** Conversion Works (later Legend3D) on stretching the background: "the stretching operations cause distortion of the object being stretched … The amount of stretching also corresponds to the disparity … Thus, the relative distances of interacting objects must be kept small" ([US 8,274,530](https://patents.google.com/patent/US8274530B2/en)).
- **Disney's answer is to hide the stretch where nobody looks.**
  - StereoBrush "undetectably stretch[es] background regions into disocclusions", using "visual saliency information to smooth out deformations, hiding artifacts in less salient image regions" ([Wang et al. 2011](https://la.disneyresearch.com/wp-content/uploads/StereoBrush-Interactive-2D-to-3D-Conversion-Using-Discontinuous-Warps-Paper.pdf) §2).
  - Image-domain warping: "disoccluded regions are implicitly inpainted by stretching unsalient texture from the neighborhood". It works for virtual cameras from −0.5 to 1.5 times the baseline. Beyond that, "artifacts due to incorrect texture in disoccluded areas start to become observable" ([Stefanoski et al. 2013](https://studios.disneyresearch.com/wp-content/uploads/2019/03/Automatic-View-Synthesis-by-Image-Domain-Warping.pdf)).
  - Didyk 2010 stretches grid quads over disocclusions: "the artifacts become less visible, but they can be perceived in certain configurations" ([PDF](https://resources.mpi-inf.mpg.de/AdaptiveStereoViewSynthesis/AdaptiveStereoViewSynthesis.pdf)).
- **Production scale.** These figures come from fxguide, a secondary source built on interviews ([fxguide 2012](https://www.fxguide.com/fxfeatured/art-of-stereo-conversion-2d-to-3d-2012)) **[secondary]**.
  - Stereo D on Titanic: "about a 50-60 pixel average shift in most shots. And in some shots as high as 80 pixel shift. This means a lot of image needed to be replaced or painted back in". Probably at 4K **[inference]**.
  - Cinesite on John Carter: an automatic edge-pixel inpaint first, "worked extremely well even on larger seams", then manual paint where needed.
- **Compositing tools.**
  - Nuke's EdgeExtend corrects "unpremultiplied foreground color at the edge of soft mattes by eroding or dilating the sample region". That is edge decontamination, the mixed-pixel problem of §1 ([Foundry](https://learn.foundry.com/nuke/content/reference_guide/filter_nodes/edgeextend.html)).
  - Nuke's Inpaint "uses surrounding pixels to fill an area", with "Stretch controls" to bias it in one direction ([Foundry](https://learn.foundry.com/nuke/content/reference_guide/filter_nodes/inpaint.html)).
- **Threshold:** none published (§4).

## 3. Texture synthesis and compositing standards

- **Membrane = the blurry baseline.** Pérez et al. 2003: "The simplest interpolant f of f* over Ω is the membrane interpolant… this simple method produces an unsatisfactory, blurred interpolant". Their seamless cloning adds "a membrane interpolant of the mismatch (f* − g) between the source and the destination along the boundary" to a source image g ([Poisson Image Editing](https://www.cs.jhu.edu/~misha/Fall07/Papers/Perez03.pdf) §2). Zumi's `membrane()` is exactly that baseline.
- **Mean-value cloning** gives the same seamless result without a solve: each interior pixel is "a weighted combination of values along the boundary", "enabling real-time cloning of large regions" ([Farbman et al. 2009](https://history.siggraph.org/?p=108825), abstract). It is useful only if a source texture g exists to clone.
- **Structure + texture.** Bertalmio, Vese, Sapiro & Osher 2003 split the image: the structure part "is inpainted following the work by Bertalmio-Sapiro-Caselles-Ballester", and the texture part "is filled-in with a texture synthesis algorithm following the work by Efros and Leung" ([IEEE TIP 12(8)](https://www.math.ucla.edu/~lvese/PAPERS/01217265.pdf)).
  - Today's `blended_shadow` base has this shape: membrane plus high-pass. But its texture step *mirrors* the ring instead of synthesising it.
  - A mirror reflects every edge near the outline back into the band, including the card's own ink fringe. That is the echo contour seen in §6 **[inference, measured visually]**.
- **Exemplar synthesis.**
  - [Efros & Leung 1999](https://people.eecs.berkeley.edu/~efros/research/NPS/efros-iccv99.pdf) grows a texture pixel by pixel. [Efros & Freeman 2001](https://people.eecs.berkeley.edu/~efros/research/quilting/quilting.pdf) quilts patches.
  - PatchMatch makes the nearest-patch search interactive. It "has been included in Adobe Photoshop CS5 as a new feature 'content aware fill'" ([Barnes thesis, Princeton TR-896-11](https://www.cs.princeton.edu/techreports/2011/896.pdf)). The fill runs coarse to fine, alternating search and a vote of overlapping patches. My prototype follows that scheme.
  - Criminisi's priority order (earlier note §5) is the depth-aware variant of §1.
- **Soft edges.** The established soft edge is a matte a few px wide at the depth edge, with the mixed pixels assigned to the foreground layer (Zitnick, 4 px) and decontaminated (EdgeExtend). Feathering more is not it: a wider feather lets more of the backdrop show at rest, which is the leak measured in §6.
  - Zumi already feathers 0.8 px (`cards.py` FEATHER) and claims the ink fringe (claim_fringe).
  - The missing piece is alpha = 1 over the mask plus the 2 px grow, so the feather lies *outside* over unchanged art.

## 4. Perceptual tolerances

- **No study gives a px or arcmin width at which a stretched or blurred disocclusion becomes visible.** All of the above are qualitative: In-Three "not extensively large", Legend3D "kept small", Didyk "perceived in certain configurations". Bosc 2011 shows that metrics fail there, not where viewers draw the line.
- **One-eye blur is tolerated.**
  - Stelmach et al. 2000 low-pass filtered one eye's view down to ¼ resolution horizontally and vertically: "the overall sensation of depth was unaffected by low-pass filtering, while ratings of quality and of sharpness were strongly weighted towards the eye with the greater spatial resolution". Temporal filtering was "unacceptable" ([IEEE TCSVT 10(2)](https://compression.ru/download/video_quality_measure.html) **[abstract only]**).
  - For Zumi, the ≤ 10 px strip that stereo alone shows (earlier note §1) is seen by one eye only, so a smooth fill there is masked by the other eye's sharp view. It must stay stable over time **[inference]**: no per-frame re-synthesis.
- **Sizes.** A 2 px boundary grow is 2.3 Quest px, about 5.5′ **[inference]**. The 33-54 px bands of §6 are 38-62 Quest px, 1.5-2.6° **[inference]**. That is far above any acuity limit, so the band's content will be seen: it has to look like background, not merely be small.

## 5. Ambient occlusion and contact shadows: established parameters

| Source | Parameters | Defaults |
|---|---|---|
| Crytek SSAO ([Mittring 2007](https://www.advances.realtimerendering.com/s2007/Mittring-Finding_NextGen_CryEngine2(Siggraph07).pdf)) | Samples "scaled with distance", "far samples with less influence"; "Smart blurring (depth buffer)" | None given |
| Alchemy AO ([McGuire et al. 2011](https://research.nvidia.com/sites/default/files/pubs/2011-08_The-Alchemy-Screen-space/paper.pdf)) | "world-space radius and bias, and aesthetic intensity and contrast" | r = 0.5 m, σ = 1, k = 1, β = 10⁻⁴ m; "art directors for our games prefer to overdarken" |
| NVIDIA HBAO ([Bavoil & Sainz 2008](https://developer.download.nvidia.com/SDK/10.5/direct3d/Source/ScreenSpaceAO/doc/ScreenSpaceAO.pdf)) | Falloff "W(x) = 1 – x²" of distance over radius | None given |
| Unity HDRP SSAO ([source](https://github.com/Unity-Technologies/Graphics), `ScreenSpaceAmbientOcclusion.cs`) | intensity 0-4, radius 0.25-5, maximumRadiusInPixels 16-256 | intensity 0 (off); radius 2.0; max 40 px |
| Unity HDRP Contact Shadows (`ContactShadows.cs`) | length (m), opacity | length 0.15, opacity 1.0 |
| Unreal AO ([Python API](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/PostProcessSettings?application_version=5.4)) | Intensity "0=off … 1=strong", affects only "the non direct lighting" | Defaults not verified |

- **AO is standard, but it is a full-screen lighting term.** No source prescribes an opacity for a composited contact shadow at a cut-out's edge. The AO terms are lighting, not paint. Their scale is the physical gap: the radius in metres, falling off with distance.
- **A physically shaped version for Zumi** **[inference]**. A card is a plane hovering h = (z_b − z_c)·f/z_b px in front of its backdrop. That is ~150 px for p9 (z 1.04 over 1.20).
  - Under uniform ambient light, the share of the sky it blocks at a backdrop point is the card mask convolved with the parallel-plane form factor h² / (π (ρ² + h²)²).
  - For a disc of radius r straight above, that integrates to r² / (r² + h²): the textbook configuration factor ([Howell catalog B-12](https://www.thermalradiation.net/sectionb/B-12.html)).
  - So a 100 px-radius card at h = 150 px blocks 31 % of the ambient light at its centre, and less at its edge. With an ambient share of 0.3 that is ≈ 9 % darker: faint, soft, with no direction to contradict the art's lighting.
  - This is Luft's depth darkening with a kernel from geometry instead of a chosen 2-5 % of the diagonal.

## 6. Local run: boxes 9, 20, 24 of P&C 39 **[measured]**

**Setup.**
- 2D lean simulation (`experiments/shadow_fill.py` `lean`, deleted 2026-10-30: in the git history) at t/d = 0.2, both directions. Card shifts were 33-40 px (p9), 7-45 px (p20) and 24-54 px (p24).
- The cards cover 67-74 % of each box, including bubbles: all three are "crowded" boxes.
- Scripts are in a temp folder, not in the repo: `C:/Users/Usuario/AppData/Local/Temp/zumi-disocc/` (`proto.py`, `crop.py`, `metrics.py`, `membrane_only.py`).

**Methods compared.**
- The FLUX plate (dilated 2 px, as the existing script).
- Today's `blended_shadow` on the cards as shipped.
- And, all on cards grown 2 px with alpha 1 inside:
  - membrane + mirrored texture + planar AO;
  - membrane only + planar AO;
  - PatchMatch band + planar AO, and without the AO;
  - the rubber sheet over PatchMatch.

**PatchMatch details.**
- Hole: the band = footprint ∩ distance ≤ max shift + 6 px.
- Sources: 7×7 patches fully outside all cards, inside the same frame (window alpha eroded 3 px), > 4 px from the white page, ≤ 90 px from the hole.
- Schedule: 3 pyramid levels, initialised with the membrane; 2-3 search-and-vote rounds per level, 3 PatchMatch iterations each; votes weighted by patch distance.

**Rest view** (cards at rest over each backdrop vs the original art):

| Box | Today (`blended_shadow`, cards as shipped) | Grown cards, any fill |
|---|---|---|
| p9 | max 109 levels, 2,883 px > 8, mean 0.12 | max 0 |
| p20 | max 93, 4,868 px > 8, mean 0.17 | max 0 |
| p24 | max 79, 4,714 px > 8, mean 0.24 | max 0 |

The leak comes from the 0.8 px feather inside the mask, through which the dark fill shows. Every shipped box with the shadow fill has it, assuming the viewer composites the card's PNG alpha over the backdrop **[inference]**.

**The revealed strip vs a 15 px ring just outside the cards:**

| Box, lean | FLUX | Today | Membrane+tex+AO | PatchMatch | PatchMatch+AO |
|---|---|---|---|---|---|
| p9 → | 1.04 / 4.8 | **0.67 / 40.6** | 0.92 / 9.6 | 1.03 / 4.0 | 0.96 / 5.0 |
| p9 ← | 1.02 / 2.4 | 0.81 / 22.6 | 0.94 / 7.6 | 1.07 / 8.1 | 0.99 / 2.5 |
| p20 → | 0.97 / 3.7 | 0.64 / 33.2 | 0.88 / 11.2 | 0.98 / 2.4 | 0.89 / 10.6 |
| p20 ← | 0.96 / 4.4 | 0.71 / 26.5 | 0.82 / 16.6 | 0.88 / 11.2 | 0.79 / 18.8 |
| p24 → | 0.97 / 7.5 | 0.56 / 55.1 | 1.02 / 4.9 | 1.01 / 3.5 | 0.95 / 6.7 |
| p24 ← | 0.99 / 3.5 | 0.76 / 29.9 | 0.98 / 4.0 | 1.02 / 6.0 | 0.96 / 6.6 |

Each cell is the luminance ratio, then the mean-colour ΔE (Lab). The strips are 53-70k px. The gradient ratio, my texture proxy, is 0.06-0.62 for every method. The ring contains ink and bubble edges, so that proxy did not separate the methods, and I do not use it.

**What I saw** (crops at 1-1.6×):
- **Today:** a dark offset wedge beside every figure, plus echo contours of the hair (p24 girl) and doubled speed lines (p9). This is the least subtle of all.
- **Membrane + mirrored texture:** the same echo contours, without the shadow.
- **Membrane only:** clean and soft. One speed line smeared into a white streak (p9).
- **PatchMatch:** the most "nothing happened" look on flat painted walls and skies (p9, p20, the p24 girl).
  - It copies the wrong thing where the background is structured: wood replaced part of a window in p24.
  - My first run had black blobs. That was a 0/0 in the vote weights, a bug in my code, fixed.
- **Planar AO at 0.3:** hard to see at all in the crops. It is a 6-10 % luminance drop (PatchMatch vs PatchMatch+AO: 1.03→0.96, 1.07→0.99, 0.98→0.89, 0.88→0.79, 1.01→0.95, 1.02→0.96).
- **Rubber sheet:** smooth, no hole, but the arched window's mullions kink beside the cloak (p24 left). It also pulls the white gutter into the frame unless clamped to the frame.
- **FLUX:** the best on architecture (p24 window); a darker brown blob beside the p9 girl.
- **Cards cut by the frame edge** (p9 man, p24 cloak): no background exists on the outer side. Every method, FLUX included, shows a vertical smear strip there.

**Comparison images** (left to right, top to bottom: source at rest, FLUX, today, membrane+tex+AO, membrane only+AO, PatchMatch, PatchMatch+AO, rubber sheet):
- `C:/Users/Usuario/AppData/Local/Temp/zumi-disocc/out4/crop-p009-R-girl.png`
- `C:/Users/Usuario/AppData/Local/Temp/zumi-disocc/out4/crop-p009-L-man.png`
- `C:/Users/Usuario/AppData/Local/Temp/zumi-disocc/out4/crop-p020-R-bull.png`
- `C:/Users/Usuario/AppData/Local/Temp/zumi-disocc/out4/crop-p020-L-girl.png`
- `C:/Users/Usuario/AppData/Local/Temp/zumi-disocc/out4/crop-p024-L-girl.png`
- `C:/Users/Usuario/AppData/Local/Temp/zumi-disocc/out4/crop-p024-L-left.png`
- Whole boxes: `out4/p0NN-leanR.png` and `-leanL.png`. Backdrops: `out4/p0NN-backdrop-*.png`.

## 7. Recommendation for Zumi, ranked

1. **Boundary layer: grow each card 2 px, alpha 1 inside, feather outside.**
   - *What:* `m = dilate(mask, 2)`, then `alpha = max(gauss(m, 0.8), m)`. The card carries the art's own pixels over m. The backdrop is filled under m (`cards.py` FEATHER, claim_fringe).
   - *Why:* this is the step every reference pipeline has (Zitnick 4 px, VSRS r ≈ 3, HTM 6, Müller 7). It removes the ghost contour and the rest-view leak (§6).
   - *Cost:* ~0.
   - *Failure:* where the 2 px ring is not ink but a different background, a thin rim of that background travels with the card. If it shows, decontaminate the ring the EdgeExtend way, pulling colour from 2-3 px inside the mask, before growing **[inference]**.
2. **Fill the band from the background only, with PatchMatch completion.** This replaces the mirrored texture.
   - *Parameters:* band = footprint ∩ dist ≤ S + 6, with S = the card's largest shift at the head-move clamp. 7×7 patches; sources from the same frame, outside every card, ≤ 90 px away, not gutter; 3 levels.
   - *Beyond the band:* the membrane, since it is never seen inside the clamp.
   - *Cost:* 78-158 s per box in my numpy code. A compiled PatchMatch, or the GPU torch already in the venv, should be 1-5 s **[inference: not run]**. It is a bake-time cost only.
   - *Failure:* structured backgrounds (windows, furniture, perspective lines) get the wrong structure. Thin strokes near the outline (speed lines) can be copied in.
   - *Policy:* where FLUX works (cover < 50 %, no flat-field failure), compare it with PatchMatch per box. FLUX won on architecture, PatchMatch on painted walls and skies.
   - **Cheap fallback, shippable today: membrane only**, the diffusion Facebook shipped. Simply drop the mirrored high-pass term from `blended_shadow`. 0.6-1.4 s.
3. **Replace the offset cast shadow with planar contact AO, or with nothing.**
   - *Parameters:* strength 0.3; h = (z_b − z_c)·f/z_b; kernel radius 3.5 h; ramp-in over 6 px from the outline; characters and objects only, 0 for lettering and glowing objects. Keep it under the footprint only, so the rest view stays identical.
   - *Effect:* 6-10 % darker strips **[measured]**, inside Cavanagh's "darker, not opaque", with no direction to contradict the art.
   - *Cost:* 0.5-0.9 s (an FFT per card; it could run at ½ resolution).
   - *Failure:* nearly invisible at 0.3. If the user wants the figure to "detach" more, try 0.5 before going back to a directional shadow.
4. **Keep the band small (orthogonal): head-motion damping or clamp, then Kopf's fade past it** (earlier notes). The DIBR depth-smoothing evidence (Tam 2004: better quality, no depth loss) supports shrinking the parallax rather than painting more.
5. **Not recommended:**
   - the rubber sheet (kinked mullions; a stereo tent **[inference]**; bending already rejected by the user);
   - the mirrored texture (echo contours);
   - the offset cast shadow (19-44 % darker, ΔE 22-55: the least subtle measured).
6. **Frame-edge cards:** where a card touches the frame, no fill has a background on the outer side.
   - Let the window clip there: in the headset the window frame is nearer and may hide most of the strip **[inference: the 2D simulation ignores the window]**.
   - Or clamp that card's lean toward the edge.

**How to judge it:** use the earlier note's §9 protocol (blind labels *nothing / shadow / smear / ghost / hole* at ±10 and ±25 cm). Compare today's fill against items 1+2 (fallback) and 1+2 (PatchMatch), each with and without item 3. Add a rest-view check: the max difference must be 0.

## 8. Not verified

- The full text of Fehn 2004, Zhang & Tam 2005, Daribo 2010, Gautier 2011, Bosc 2011 and Ndjiki-Nya 2011: filter sizes, priority terms and subjective rankings.
- The official MPEG VSRS repository (only a mirror was read).
- Any Stereo D or Prime Focus technical text. Unreal's AO defaults. Adobe's own statement that Content-Aware Fill is PatchMatch (only Barnes' thesis says so). Hasinoff 2006.
- Any perceptual threshold in px or arcmin for stretched or blurred disocclusions (none found).
- The prototype:
  - 2D only: no relief, no stereo, no window parallax, no headset;
  - one episode, three boxes, one lean;
  - judged by me from crops, not blind;
  - PatchMatch timing is unoptimised numpy;
  - the AO strength and the 2 px grow were not swept.
