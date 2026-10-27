# What to show behind a card when the head moves: shadow fill, band inpaint or erase — 2026-10-27

Research date: 2026-10-27. Method: primary papers read in full text (Kopf 2019 and 2020, Shih 2020, Telea 2004, Criminisi 2004, Barnes 2009, Luft 2006, Cavanagh 2005); abstracts for Kersten 1997 and Mamassian 1998; patents, vendor docs and source code (OpenCV, Material Components). I also ran one small local experiment, on a Pepper & Carrot 39 box and its 29 boxes' masks, with OpenCV 4.10 in `pipeline/segment/.venv` (§6). Nothing was run in a headset. **[inference]** = my reasoning or arithmetic; **[measured]** = my run, on one machine and one episode; **[unverified]** = abstract only, or not confirmed.

Symbols: d is the reading distance. Depths z are in units of d (window 1.0, cards 1.005-1.2, backdrop 1.20-1.38). t is the head move. f = 600 / tan 27.5° = **1152.6 px** for a box whose long side is 1200 px. *Band* means the strip of backdrop that a head move uncovers along a card's outline.

## Answer

1. **The band is 20-60 px for a normal lean, and up to 95 px at most.** Stereo alone uncovers up to 10 px per eye **[inference, §1]**.
   - The bands are thin, but comic figures are thinner. On the 29 boxes of P&C 39 the cards cover a median 36 % of the box. A 60 px band covers **33 %**, so it is 92 % of everything the cards cover. A 25 px band covers **21 %** **[measured, §6]**.
   - So a "reveal band" erase only shrinks the hole when the band is ≤ ~25 px. That takes the head-motion damping from the earlier note (k ≈ 0.3-0.4) or a shallower backdrop on crowded frames.
2. **Nobody in the 3D-photo line uses a shadow fill.**
   - Facebook and Shih et al. inpaint a band of 40-50 px behind each depth edge. Facebook shipped plain diffusion (a smooth blur) to more than 10 M photos.
   - Facebook also limits the viewing angle and fades the photo out past it. Google Cinematic photos choose a camera path that keeps the stretch artefacts out of view.
   - Hand-made 2.5D (Live2D, the Disney multiplane) paints the hidden area by hand.
   - The one shadow precedent is Disney's 1936 patent. It casts a "relatively faint but distinct shadow" of a translucent-painted cel onto a 3D set.
3. **A dark strip reads as a shadow only if it is darker but not opaque.**
   - Shadows "must be darker than their immediate surroundings", yet "cannot look opaque and still appear as shadows". Their colour and direction can be wrong without anyone noticing (Cavanagh 2005).
   - Viewers read shadow motion under a stationary light (Kersten 1997). A shadow fixed on the backdrop, with the card sliding over it, fits that rule.
   - "Depth darkening", which darkens only the background next to an occluder, was the separation its authors liked best. That is the authors' opinion; they ran no user study (Luft 2006).
   - My run agrees: a flat dark silhouette reads as a black doppelgänger of the figure, not as a shadow **[measured, visual, §6]**.
4. **What I would try first: Telea on the band, multiplied by a shadow ramp that darkens toward the card, baked into the backdrop texture.**
   - It costs 0.25 s per box, runs locally, gives the same result every run, never invents objects, and leaves the rest view identical to the original art.
   - Use it where FLUX Erase fails (cards cover > 50 % of the box). Keep the FLUX full erase where it works: on my test box it looked best of all the fills.
   - The FLUX reveal band is the second thing to try on crowded frames, and only together with damping.
5. **How to judge it.** Use a desktop render with the eye offset, then the headset at ±10 and ±25 cm leans. Count the boxes where the strip reads as a *hole*, a *ghost* or a *smear* rather than a shadow or nothing. Check that the rest view differs from the art by 0 px (§9).

| Option | Quality on painted art (P&C 39 test, 60 px shift) | Cost per box | Failure modes |
|---|---|---|---|
| Original art left in the band (do nothing) | Ghost: a doubled horn or head beside every figure | 0 | Unacceptable at any shift above ~5 px |
| **FLUX Erase, full footprint (today)** | **Best** where it works: the sofa and wall continue | 1 API call, network, paid | Above ~60 % cover: flat brown or grey fields, blanks. It also erases drawn cast shadows |
| FLUX Erase, reveal band only | Not tested. Should equal the full erase where the band ≈ the footprint **[inference]** | 1 API call | Saves area only at ≤ 25 px (§6). With the interior art visible as context, it may regrow the figure **[inference]**; LayerD saw FLUX Fill insert objects |
| Telea / NS on the band, outside-only context | Plausible colours, a smooth smear, streaks on long edges | 0.25-0.32 s, local **[measured]** | Blurs anything thicker than 10-15 px (Telea's own limit); smears line art, screentone and speed lines |
| **Telea band + shadow ramp (recommended first)** | Reads as soft contact shadow / AO; the darkening masks the smear | ~0.3 s, local | Wrong on glowing objects, bubbles and white "no-background" panels (§8) |
| Colour average + shadow ramp | Brown blobs shaped like the figure | ~0 | Opaque look; the silhouette shape shows |
| Flat dark silhouette (opaque) | Black doppelgängers | ~0 | Fails Cavanagh's "not opaque" rule; reads as a hole or a second figure |
| Shift-map (exemplar, opencv_contrib) | Sharper, but copies wrong texture (table wood into the wall) | 22.6 s **[measured]** | Copies objects; slow |
| FSR fast (opencv_contrib) | Green blocks | 6.9 s **[measured]** | Colour artefacts on this art |
| Criminisi / PatchMatch | Not run. Exemplar, so the same class as shift-map | s-min (paper hardware) | Copies characters' patches; "not designed to handle curved structures" |
| LaMa (local GPU) | Not run here. See [scene-layers-comics-2026-10.md](scene-layers-comics-2026-10.md) | Local GPU; not measured | Smoother than FLUX; LayerD chose it over FLUX Fill |
| Damping k / fade past a clamp (orthogonal) | Shrinks every band by k | 0 | Too much damping makes the backdrop "swim" (earlier note) |

## 1. How wide the uncovered band is **[inference]**

Shift of a card against the backdrop, in box pixels: `s = f · (t/d) · (1/z_card − 1/z_backdrop)`. One box pixel is ~1.15 Quest 3 pixels (55° × 25 px/° = 1375 px across a 1200 px box).

| Pair (z_card / z_backdrop) | 1/z_c − 1/z_b | t/d = 0.133 (20 cm at 1.5 m) | 0.2 (20 cm at 1 m, 30 cm at 1.5 m) | 0.3 (30 cm at 1 m) | Stereo, one eye (3.15 cm at 1 m) |
|---|---|---|---|---|---|
| Nearest card 1.005 / deepest backdrop 1.38 | 0.2704 | **41.6 px** | **62.3 px** | **93.5 px** | 9.8 px |
| Nearest card 1.005 / backdrop 1.20 | 0.1617 | 24.8 | 37.3 | 55.9 | 5.9 |
| Mid card 1.10 / backdrop 1.29 | 0.1339 | 20.6 | 30.9 | 46.3 | 4.9 |
| Farthest card 1.17 / backdrop 1.20 | 0.0214 | 3.3 | 4.9 | 7.4 | 0.8 |
| Bubble on the glass 1.0 / backdrop 1.38 | 0.2754 | 42.3 | 63.5 | 95.2 | 10.0 |

Example: 1152.6 × 0.2 × 0.2704 = 62.3 px.

- A card over another card four levels back (1.005 over 1.165) gives 1/1.005 − 1/1.165 = 0.137: the same as the mid row.
- **The band appears on one side only:** the side the head moves toward, while the lean lasts. Over a session, every side of a card gets seen.
- **With damping k** (the content-follow factor, [quest-photo-depth-effect-2026-10.md](quest-photo-depth-effect-2026-10.md) §5 #3), every band scales by k. At k = 0.3 the 93.5 px worst case becomes 28 px.
- **Depth is also a lever.** Moving a close-up's backdrop from 1.38 to 1.20 cuts its band from 62 to 37 px at t/d = 0.2.
- For a box with a longer long side, f grows in proportion (1600 px gives f = 1537 px), and so does s in box pixels.
- **Stereo shows a strip even with the head still.** Each eye sees up to 10 px of band on its own side, so whatever is in the outer ~10 px of the band is visible at rest in stereo. Regions seen by one eye only, beside an occluding edge, are themselves a depth cue ([Nakayama & Shimojo 1990, "Da Vinci stereopsis: depth and subjective occluding contours from unpaired image points"](https://doi.org/10.1016/0042-6989(90)90161-D) **[unverified: title and abstract only]**). That strip must therefore look like background, not like a dark rim.

## 2. What 3D-photo systems do at disocclusions

| System | What fills the uncovered area | Shadow-like or darkened? | What they found | Source |
|---|---|---|---|---|
| Facebook 3D Photos 2018 (dual camera) | Geometry is extended behind every back-side discontinuity. Then "Iterative isotropic diffusion inpaints colors into the occluded regions … very fast and produces predictable, albeit smooth, results". Color inpainting took 500 ms of 1.8 s on an iPhone X. Viewing: "we create a frame around the model and constrain the viewing angles" | No: a blur | Shipped; "more than 10 million 3D photos" | [Kopf et al. 2019, Practical 3D Photography](https://johanneskopf.de/publications/photo3d_practical/Practical_3D_Photography.pdf) §3-4 |
| Facebook One Shot 3D 2020 | The background is grown behind each discontinuity "for 50 iterations" (1 px each), then inpainted on the LDI with a PartialConv network. Screen-space inpainting was rejected: it "would be continuous on both foreground and background sides … thus leading to strong blur artifacts along the edges". Viewing: "constrain the viewing angles and fade the model out if there is too much head motion" | No. Fade past a limit | "used over 100 million times" | [Kopf et al. 2020](https://arxiv.org/abs/2008.12298) §4.2-4.3, §5, §6.1 |
| Shih et al. 2020 | A synthesis region grown "for 40 iterations" behind each depth edge (a 40 px band), from a context region of 100 iterations, with edge, color and depth networks. Naive warping "either produce[s] gaps … or stretched content". Diffusion "produces overly smooth results and is unable to extrapolate texture and structures" | No | Prefers learned band fill over blur | [arXiv 2004.04727](https://arxiv.org/abs/2004.04727) §1, §3.2, Fig. 1 |
| Google Cinematic photos | A depth mesh with no hole fill. Stretched polygons appear where depth jumps. A per-photo camera path is optimised with a loss that "triggers more heavily in areas with a greater number of connected artifact pixels" and prefers "artifacts in the background regions" | No: stretch, hidden by the path | Mask people and pull them forward, because quality is "particularly sensitive to the depth map's accuracy at person boundaries" | [Google Research blog](https://research.google/blog/the-technology-behind-cinematic-photos/) |
| Apple spatial scenes | "a new generative AI algorithm and computational depth"; nothing on the fill | Not published | — | Earlier note: [quest-photo-depth-effect-2026-10.md](quest-photo-depth-effect-2026-10.md) §3 |
| Quest Gallery "3D" | Not published | Not published | — | Same note, §2 |

Two lessons for Zumi **[inference]**:

- **Everyone fills a band, not the whole occluded area.** The bands are 40-50 px on 1152×1536 images, the same size as Zumi's from §1. The "reveal band" idea is the standard design.
- **Fill from the background side only.** Kopf's blur argument applies directly to Telea. If the band is inpainted with the figure's interior as known pixels, the figure's colours bleed into it. So inpaint the whole footprint with only outside pixels as context, then keep the result in the band.

## 3. What hand-made 2.5D does

- **Live2D:** "Add the parts of the illustration that are visible when the illustration is moved" ([Production flow](https://docs.live2d.com/en/cubism-editor-manual/workflow/)). Also "the parts that will be visible when other parts move should be drawn earlier in the process" ([Material separation](https://docs.live2d.com/en/cubism-editor-manual/divide-the-material)). The answer there is hand painting, not a fill.
- **Disney multiplane camera** ([US 2,198,006](https://patents.google.com/patent/US2198006A/en), Garity, 1940):
  - Planes are "spaced distances ranging from 6 inches to 24 inches apart", and "each of the planes … may be provided with suitable illuminating devices".
  - The housing is designed to "preclude light from the source" spilling onto neighbouring cels. Each level is lit on its own, so no plane shadows another; the background is a full painting **[inference from the patent text]**.
- **Disney "Art of animation"** ([US 2,201,689](https://patents.google.com/patent/US2201689A/en), filed 1936):
  - A character on glass is lit so as to "throw a shadow of such character upon the stage" (a modelled 3D set). The character may be painted "with a translucent paint so that a relatively faint but distinct shadow" appears.
  - This is the closest precedent for a cutout's own silhouette shadow on the set behind it, and it is deliberately faint.
- **Photoshop/After Effects parallax:** tutorials fill the background layer under each cutout with Content-Aware Fill before animating ([Toolfarm](https://www.toolfarm.com/?p=25340) **[unverified: secondary tutorial, no Adobe doc found]**).
- I found no primary source for pop-up books, toy theatres or Spine on this question.

## 4. Perception: when does a dark strip read as a shadow?

- **Darker, not opaque.** Shadows "must be darker than their immediate surroundings", a rule "confirmed by perceptual experiments". Also, "although shadows can lie in the wrong direction and have the wrong shape, they cannot look opaque and still appear as shadows", and "as long as they are darker, [they] do not have to be the right colour" ([Cavanagh 2005, Nature 434:301](https://homepage.villanova.edu/diego.fernandezduque/Teaching/CognitivePsychology/Lectures_and_Labs/s2objectRecognition/sReading/CavanaghBrainArt.pdf), text and Figs. 2-3). In Zumi terms, a shadow should **multiply** the backdrop (its texture shows through) and should not paint over it **[inference]**.
- **Moving shadows carry depth, under a stationary light.**
  - "the information provided by the motion of an object's shadow overrides other strong sources of information". "the natural constraint of shadow darkness plays a role in the interpretation of a moving image patch as a shadow". The visual system assumes "a stationary light-source constraint" ([Kersten, Mamassian & Knill 1997, abstract](https://pubmed.ncbi.nlm.nih.gov/9274752/)).
  - Cast shadows are "perceptually most relevant for the recovery of spatial arrangement", especially when they move ([Mamassian, Knill & Kersten 1998, abstract](https://experts.umn.edu/en/publications/the-perception-of-cast-shadows/)).
  - The Kersten lab demos add two points. Reversing a dark shadow to a light one weakens the effect. And when stereo disagrees, shadows work at first but "disparity seems to win out" over time ([demos](https://kerstenlab.psych.umn.edu/demos/shadows)).
  - For Zumi: a shadow baked into the backdrop stays fixed on the backdrop while the card slides over it. That is exactly what a stationary light gives, and stereo agrees, because the shadow lies at the backdrop's depth **[inference]**.
- **A dark halo is accepted when it follows depth.**
  - Luft, Colditz & Deussen darken "only the background along spatially important edges … similar to a cast shadow", using a Gaussian of "2% to 5%" of the image diagonal. They call it "a very natural depth cue that, in our view, provides the best object separation", and say it works for "a white object in front of a white background" ([Luft et al. 2006](https://pub-085d059a8619439494873b401c0986ce.r2.dev/Luft2006ImageEnhancementUnsharp/Luft2006ImageEnhancementUnsharp.pdf) §3).
  - The same paper calls the halos of local tone mapping "unwanted ringing artifacts", useful only "in combination with depth information". So a halo reads as an artefact when it is unrelated to depth, and as depth when it sits on the far side of a real occluding edge.
  - There is no user study in the paper. For a 1200×600 box, 2-5 % of the diagonal is 27-67 px, the same range as the bands of §1 **[inference]**.
- **How dark is "a shadow" in UI practice.** Material's elevation shadows have opacities of 0.20 (umbra), 0.14 (penumbra) and 0.12 (ambient). Their penumbra offset equals the elevation, and the blur is ≈ 1.5× the elevation (e.g. level 16: `0px 16px 24px 2px`) ([MDC source](https://github.com/material-components/material-components-web/blob/master/packages/mdc-elevation/_elevation-theme.scss)). Stacked, the darkest point is 1 − 0.8·0.86·0.88 = **39 %** darker **[inference]**.

## 5. Classical local inpainting

| Method | What it does | Speed | Where it breaks on comic art |
|---|---|---|---|
| **Telea** (FMM), `cv2.INPAINT_TELEA` | Fills pixels in order of distance from the hole's edge. Each pixel is a weighted average of known pixels within radius ε, weighted by direction, distance and level-set distance | "under three seconds on a 800 MHz PC" for 800×600 (paper). **0.25 s** for a 1200×434 box with 33 % masked; 31-124 ms on synthetic bands of 10-95 px, 159 ms for the whole synthetic footprint **[measured]**. Linear in the hole size | "the blurring produced when inpainting regions thicker than 10–15 pixels, especially visible when sharp isophotes intersect the region's boundary almost tangentially" ([Telea 2004](https://webspace.science.uu.nl/~telea001/uploads/PAPERS/JGT04/paper.pdf) §4). Zumi's bands are 20-95 px, so expect smears. Flat cel colour fills well; ink lines, screentone and speed lines smear to grey **[inference]** |
| **Navier-Stokes**, `cv2.INPAINT_NS` | [Bertalmio, Bertozzi & Sapiro 2001](https://doi.org/10.1109/CVPR.2001.990497) carries isophotes in as a fluid-flow PDE. OpenCV implements it as a single fast-marching pass with NS-style weights (`icvNSInpaintFMM` in [inpaint.cpp](https://github.com/opencv/opencv/blob/4.x/modules/photo/src/inpaint.cpp)) | 0.32 s on the same box **[measured]** | Same blur class as Telea; visually near-identical in my run |
| **Criminisi** exemplar | Copies 9×9 patches in a priority order (confidence × isophote strength), so linear structures propagate first | 2 s for a 200×200 image on 2004 hardware ([Criminisi et al. 2004](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/criminisi_tip2004.pdf) §IV) | "the synthesis of regions for which similar patches do not exist does not produce reasonable results … not designed to handle curved structures … does not handle depth ambiguities". In a crowded panel the nearest similar patch is often another character **[inference]** |
| **PatchMatch** | Randomised nearest-neighbour field search, which makes patch-based completion interactive | 20-100× faster than prior work; ~0.7 s for a 0.1 MP field (2009 hardware, Table 1) ([Barnes et al. 2009](https://pixl.cs.princeton.edu/gfx/pubs/Barnes_2009_PAR/patchmatch.pdf)) | Greedy or wrong copies on large holes with complex structure; no ready OpenCV binding |
| Shift-map / FSR (`cv2.xphoto.inpaint`) | Shift-map is an exemplar method based on dominant patch offsets. FSR is a frequency-domain reconstruction ([inpainting.hpp](https://github.com/opencv/opencv_contrib/blob/4.x/modules/xphoto/include/opencv2/xphoto/inpainting.hpp)) | 22.6 s / 6.9 s on the box **[measured]** | Shift-map copied table wood into the wall. FSR made green blocks **[measured, visual]** |

**Thin vs large:**

- Telea's sweet spot is ≤ 10-15 px: the stereo-only strip and damped bands. At 40-95 px it is a smear. That is acceptable under a shadow and noticeable without one **[inference from §6]**.
- Exemplar methods do better on texture in wide holes, but they copy wrong content, and painted comics have little repeated texture next to a character.

## 6. One local run (P&C 39) **[measured]**

What I ran:
- Box `pepper-carrot-39-p007` (1200×434), with its four character masks merged into one card (33 % of the box).
- Every fill was computed from outside pixels only, over the footprint dilated by 2 px. The result was composited into the band, the card was moved 25, 40, 60 and 90 px, and I looked at the renders.
- Scripts in a temp dir; not committed.

What I saw:
- **Original art in the band:** a duplicate horn, head and back beside each figure at 40 px.
- **FLUX full erase** (the existing `plate-all.png`): the most coherent background (sofa, wall).
- **Telea:** plausible colour, soft wavy smears, visible as "blurry patches" at 60-90 px.
- **Telea + ramp:** reads as soft darkness next to the figure. The smear is less noticeable.
  - An early version that was darkest *at the outline* made a dark rim that appeared first.
  - The ramp has to be darkest *next to the card* and fade to 0 at the outline.
- **Flat dark (35 % of the local mean) and colour average + ramp:** figure-shaped dark or brown silhouettes. These are the "opaque" failure.

**Band share across all 29 boxes of the episode** (characters and objects merged):

| | Median share of box | Boxes > 50 % covered (n = 3), median |
|---|---|---|
| Card footprint | 0.36 | 0.56 |
| Band ≤ 25 px inside the outline | 0.21 | 0.27 |
| Band ≤ 60 px | 0.33 | 0.47 |
| Band ≤ 95 px | 0.36 | 0.56 |

So at 60-95 px the band is nearly the whole footprint: limbs, horns and small figures are thinner than the band. At 25 px it is 58 % of the footprint. On the crowded boxes, a 25 px band drops the hole from 56 % (where FLUX fails) to 27 % (where FLUX works) **[inference from the user's 50 % / 60 % thresholds]**.

## 7. Recipe for the shadow fill **[inference unless cited]**

Per card c, with z_b the depth of whatever lies behind it (the backdrop, or a farther card):

1. **Band width.** `S = k · f · 0.2 · (1/z_c − 1/z_b) + 3 px`.
   - 0.2 is t/d for 30 cm at 1.5 m or 20 cm at 1 m. k is the damping factor (1 if there is none).
   - The 3 px cover the 0.8 px feather (`FEATHER`) and the ink fringe.
   - Band B = footprint − erode(footprint, disc of radius S).
2. **Base colour.** Run Telea (radius 5) on the union of all card footprints dilated by 2 px, with only non-card pixels as context, and keep the result inside B.
   - This is Kopf's background-side-only rule. Inside the footprint but outside B, keep the original art. It is never seen inside the clamp, and past the clamp, fade (step 6).
3. **Shadow.**
   - Multiply B by `1 − a · r`, where `r = clamp(dist / (0.8 S), 0, 1)^1.5` and dist is the distance inward from the card's outline.
   - So the darkness is 0 at the outline and full next to the card's interior. This is the contact-shadow / AO shape, in the style of Luft's depth darkening.
   - With a = 0.35 and S = 60: 3 % darker 10 px in (the stereo-visible strip stays clean), 17 % at 30 px, 35 % from 48 px. That is inside Material's 39 % maximum.
   - **Colour:** a multiply keeps the backdrop's hue. Cavanagh says the colour need not be right, so do not tint.
   - **Blur:** the ramp is already smooth; at most a Gaussian of σ ≈ S/8 on r, clipped to B.
   - **Offset:** none by default (centred, like AO), because the reveal can happen on any side. If the art has a drawn cast shadow, the ramp's centre may shift ≤ S/3 toward that shadow. Cavanagh: inconsistent direction "is not readily noticed".
4. **Strength by background.**
   - Mid and dark backdrops (local L* < 70): a = 0.35.
   - Light backdrops (L* > 80, paper white): a = 0.15-0.2. Luft found that darkening separates white-on-white well, but a deep grey on a blank manga panel adds a surface the art did not draw.
   - Glowing, emissive or translucent cards (fire, magic, lamps, sky bodies, smoke, glass, SFX): a = 0, Telea only.
5. **Where it lives.**
   - **Baked into the texture of the layer behind the card**, normally the backdrop. It then sits at the backdrop's depth and parallax, as a stationary-light shadow should (Kersten), and stereo agrees with it.
   - Not on the card: it would move with the card and never be uncovered. Not its own layer: no gain, extra overdraw.
   - Card over card: the near card's band falls on the far card. Grow the far card's alpha by S over the near card's footprint, and fill that from the far card's own pixels (Telea), then the ramp. Otherwise the gap shows the backdrop through the far figure.
6. **Past the clamp.** If the damping clamp is ever exceeded, the original art beyond S shows as a ghost. Fade the cards toward the backdrop there, as Kopf does ("fade the model out if there is too much head motion"), or keep the clamp hard.
7. **Rest view unchanged.** Every change lies under the card, so with the head at rest the frame is pixel-identical to the original art. Only stereo shows the outer ≤ 10 px of the band, and that part is near-clean (step 3).

## 8. Failure cases **[inference]**

- **Characters filling the frame (> 60 %).** Telea has little background to draw from and smears a few colours over a wide area. The ramp turns this into a dark surround, which is acceptable as a vignette but not as scenery. First cut the band: damping k, plus a shallower backdrop for close-ups (37 px instead of 62, §1). Then compare with the FLUX reveal band, which at ≤ 25 px puts the hole under 50 % (§6).
- **Speech bubbles.** They sit on the glass, so their band is the largest (up to 95 px). The backdrop under a bubble is already the lettering erase. Use no shadow (a = 0), or at most a faint one: a balloon is not a physical object in the scene. Bubbles usually sit on flat colour or gutters, where Telea is clean.
- **Light or white backgrounds.** Use a = 0.15-0.2 (step 4). If the panel is white because it has no background, try a = 0 and Telea only (white inpaints perfectly).
- **Characters with a drawn cast shadow.** The backdrop keeps the original art outside the cards, so the drawn shadow stays (`cards.py` docstring: the erase "also removes cast shadows"). The synthetic ramp lies under the card and does not double it at rest. At a lean, the two may merge into one darker region, which is consistent. Only directional offsets that contradict the drawn shadow are a risk (step 3).
- **Objects that should not cast** (light sources, effects, sky, smoke, glass, lettering): a = 0.
- **Line art and screentone in the band.** Telea smears hatching and dots into grey. Under a 35 % ramp the band reads as a shadow on a soft patch. Without the ramp it reads as a smudge. Shift-map/Criminisi copy texture but also copy the wrong objects.
- **Thin parts (horns, fingers, weapons).** Their whole width is band (§6), so the ramp covers them entirely. A horn's "shadow" is then a horn-shaped grey streak at a full lean, which is fine at 35 % and doppelgänger-like at 70 %+ (as in the flat-dark render).

## 9. What I would try first, and how to judge it

**Order:**
1. Telea + ramp (§7) on every card. It is free, so produce it for all boxes.
2. Per box, the backdrop band source:
   - FLUX full erase where FLUX succeeds (cover < 50 % and no flat-field failure).
   - Telea + ramp everywhere else.
   - A mild ramp (a ≈ 0.2) on top of the FLUX fill too, as a test: Luft's depth darkening may help separation even when the fill is good.
3. Only if crowded boxes still look wrong: the FLUX reveal band at the damped width, with the interior pre-filled by Telea so FLUX does not see the figure.

**Judge (desktop first, then headset):**

| # | Check | Measure | Pass |
|---|---|---|---|
| 1 | Rest view | Max pixel difference between the rest render and the original art | 0 (bubbles excepted) |
| 2 | Lean renders at t/d = 0.067, 0.133, 0.2 on 12 boxes (4 with > 50 % cover, 2 white-background, 2 with drawn shadows, 2 close-ups, 2 with bubbles over art) | The user labels each revealed strip *nothing / shadow / smear / ghost / hole*, blind to the method, for FLUX full vs Telea vs Telea + ramp vs FLUX band | Telea + ramp is *nothing* or *shadow* on ≥ 10 of 12 boxes, and never *ghost* or *hole* |
| 3 | Smear proxy | Mean gradient magnitude in the revealed strip divided by that in a ring of the same width outside the outline | Note it, don't gate on it: < 0.3 = smeared. Under a ramp, a low ratio is acceptable if #2 says *shadow* |
| 4 | Darkness | Mean luminance of the strip divided by the ring's | 0.6-0.95 with the ramp; > 0.95 = invisible; < 0.6 risks *opaque* |
| 5 | Headset, ±10 and ±25 cm leans at 1.0 and 1.5 m | Same labels, plus "does the figure look more detached from the background?" with ramp vs without | Ramp ≥ no ramp on detachment, no new *ghost* labels |
| 6 | Cost | Seconds per box locally | ≤ 1 s (Telea measured 0.25 s) |

The decisive test is #2. The rest only explain why a box failed.
