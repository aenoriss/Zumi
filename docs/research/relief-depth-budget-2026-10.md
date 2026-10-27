# How much depth a layered panel should have at 1-1.5 m on Quest 3 — 2026-10-26

Research date: 2026-10-26. Method: vision-science papers (Shibata 2011 and McKee & Taylor 2010 read in full text on PMC; the others from abstracts), Meta, Apple and Microsoft developer pages, and Zumi's `cards.py` and desktop viewer. Nothing was run in a headset. **[unverified]** = secondary source, abstract only, or not confirmed; **[inference]** = my reasoning. Every centimetre, arcmin and pixel figure is my own arithmetic, not a measurement.

Assumptions: 63 mm IPD (I). Quest 3 has 25 px/degree ([Meta compare page](https://forwork.meta.com/meta-horizon-managed-solutions/compare-vr-headsets/)), so 1 px = 2.4′ = 6.98·10⁻⁴ rad. *d* is the reading distance. Two conversions recur:

- **Disparity to depth.** A relative disparity η (in radians) at distance d corresponds to a depth of `Δ = η·d² / (I − η·d)` behind and `Δ = η·d² / (I + η·d)` in front. For small η, both are ≈ `η·d²/I`.
- **Depth to disparity.** A point at a share s of d behind a plane at d has a disparity of `η = (I/d)·s/(1+s)` relative to that plane. Here I/d is 0.063 rad at 1 m and 0.042 rad at 1.5 m.

## Answer

1. **Comfort is not what limits Zumi today: visibility is.** At 1-1.5 m, the comfort limits allow 20-70 cm of depth. Zumi uses 6-10 cm.
   - The 1° disparity rule allows **38 cm behind / 22 cm in front** of a panel at 1 m, and **107 cm / 44 cm** at 1.5 m.
   - Shibata's zone of comfort is wider still for a 1.5-2 m focal plane.
   - Meanwhile, Zumi's level steps are **0.4-1.2 px** of disparity at 1.5 m. One Quest 3 pixel is **2.5 cm of depth at 1.5 m and 1.1 cm at 1 m**.
2. **The flat-screen tuning measured tolerable motion, not depth** **[inference]**.
   - The desktop viewer's auto-sway moves the camera **±9.4 % of the viewing distance** (±14 cm at 1.5 m, at the default speed of 0.5). That is not the user's own head.
   - On a monitor, disparity and vergence say "flat", so parallax reads as layers sliding, not as depth ([Kim, Angelaki & DeAngelis 2016](https://pmc.ncbi.nlm.nih.gov/articles/PMC4901450/)).
   - The 3 % step the user rejected on the desktop gives **4.5′ = 1.9 px** of stereo in the headset at 1.5 m: barely a visible step.
3. **Shape should scale with the drawn subject; scene depth cannot, so compress it.**
   - Readers notice flattened *objects* (cardboarding) once depth falls below about 30 % of correct ([Chapiro et al. 2014](https://la.disneyresearch.com/?p=13736)). Devernay & Beardsley put the floor at a roundness factor of 0.2 ([2015](https://arxiv.org/abs/1506.06001)).
   - So a card's relief should be proportional to its drawn size. A fixed 3 % makes a small figure puffy and a face close-up flat.
   - Scene depth at panel scale would be metres for a close-up. It must be compressed per panel, as Facebook did ([Kopf 2020](https://arxiv.org/abs/2008.12298)).
4. **Recommended defaults.** All depths are measured *behind* the window (the panel's frame at d). Shares are of d, so shapes stay the same at 1 m and 1.5 m.

   | | Share of d | at 1 m | at 1.5 m | Disparity, 1 m / 1.5 m |
   |---|---|---|---|---|
   | (a) Backdrop behind window | **20 %** (cap 25 %) | 20 cm | 30 cm | 36′ (15 px) / 24′ (10 px) |
   | (b) Card level step | **4 %**, ≤ 4 levels (12 % span); nearest relief peak 0.5 % behind the window | 4 cm | 6 cm | 6.9′ (2.9 px) / 4.6′ (1.9 px) |
   | (c) Card relief | **A = 0.25 × card's short side**, clamped to **2-10 %** | 2-10 cm | 3-15 cm | up to 19.5′ / 13′ |
   | (d) Backdrop relief | **4 %**, tilt kept, ≥ 1 % behind any card that covers it | 4 cm | 6 cm | 6.2′ / 4.1′ |

   Today's numbers, for comparison: backdrop 7.5 %, steps 2 % then 0.7 %, relief 3 % fixed, backdrop relief 1.5 %. The new total range (20 % of d, 36′ at 1 m) stays inside Percival's zone (0.67°) and the 1° rule.
   - If head motion then feels like too much movement, **damp the head-motion parallax** (the content-follow factor *k* in [quest-photo-depth-effect-2026-10.md](quest-photo-depth-effect-2026-10.md) §5 #3). Do not shrink the stereo depth.

## 1. Stereo limits at 1-1.5 m, converted

| Limit | Source value | At 1 m: in front / behind | At 1.5 m: in front / behind | Source |
|---|---|---|---|---|
| Stereoacuity, real objects | 4-14″ (naive observers, 1.12 m); 10″ used | 0.8 mm (0.08 %) | 1.7 mm (0.12 %) | [McKee & Taylor 2010](https://pmc.ncbi.nlm.nih.gov/articles/PMC2951307/): "6 to 14 arcsec in the austere setting, and 4–8 arcsec in the enriched setting" |
| Stereoacuity, Randot clinical test | 28″ mean in adults | 2.2 mm | 4.8 mm | [Yonsei HMD stereotest](https://ir.ymlib.yonsei.ac.kr/handle/22282913/189459) **[unverified: abstract via search]** |
| Stereoacuity measured *in* an HMD | 160″ mean, Gear VR (phone-based, low resolution) | 12 mm (1.2 %) | 28 mm (1.8 %) | same **[unverified]** |
| One Quest 3 pixel of disparity | 2.4′ | 11 mm (1.1 %) | 25 mm (1.7 %) | arithmetic. Sub-pixel disparities do render through filtering, so the true threshold is somewhat below 1 px **[inference]** |
| Percival's zone | "0.67 to 1 degree" | 16 cm / 23 cm (16 % / 23 %) | 33 cm / 58 cm (22 % / 39 %) | [Devernay & Beardsley](https://arxiv.org/abs/1506.06001) §2.5 |
| "One-degree" rule | ≤ 1° disparity relative to the screen | 22 cm / 38 cm (22 % / 38 %) | 44 cm / 107 cm (29 % / 71 %) | [Lambooij et al. 2009](https://library.imaging.org/jist/articles/53/3/art00001) **[abstract]**; Devernay §2.5: "disparities beyond one degree" cause discomfort, and "70 arcmin disparity is too much" (Pastoor) |
| Shibata zone of comfort, focal plane 1.5 m | near limit 0.80 m, far 5.0 m | 20 cm / 4.0 m | 70 cm / 3.5 m | [Shibata et al. 2011](https://pmc.ncbi.nlm.nih.gov/articles/PMC3369815/) |
| Shibata zone, focal plane 2.0 m | 0.92 m, 19.5 m | 8 cm / 18.5 m | 58 cm / 18 m | same |
| Shibata zone, focal plane 1.3 m | 0.74 m, 3.45 m | 26 cm / 2.45 m | 76 cm / 1.95 m | same |
| Percentage rule (TV and cinema) | near 2.5 %, far 1.5 % of screen width (averages of the rule's ranges) | 29 cm / 33 cm | 57 cm / 89 cm | Shibata 2011, Fig. 24. Assumes a panel 1.04·d wide, the 55° box of `cards.py` **[inference]** |

How the Shibata rows were computed. The fit is `D_focal = m·D_vergence + T`, in dioptres. The paper gives "m_near = 1.0352, T_near = −0.6257, m_far = 1.1286, and T_far = 0.4420" and calls the estimate "arguable".
- Focal plane at 1.5 m (0.667 D): near boundary (0.667 + 0.626)/1.035 = 1.25 D, i.e. 0.80 m. Far boundary (0.667 − 0.442)/1.129 = 0.20 D, i.e. 5.0 m.
- Sign: conflicts behind the screen hurt more at far distances, and conflicts in front hurt more at near ones (Shibata, Exp. 2).

**Quest 3's focal distance is not published.**
- Meta says only that current headsets have "a fixed focus, typically at 5 to 6.5 feet (1.5 to 2 meters)" ([Tech at Meta, 2022](https://tech.facebook.com/reality-labs/2022/06/passing-the-visual-turing-test-the-inside-story-of-our-quest-for-visual-realism-in-vr/)).
- Microsoft gives 1.25-2.5 m for immersive headsets ([Microsoft comfort guide](https://learn.microsoft.com/en-us/windows/mixed-reality/design/comfort)).
- A 2024 paper puts Quest 2 at 1.3 m **[unverified: search snippet of arXiv 2405.07335]**.
- With any focal plane from 1.3 to 2 m, everything Zumi puts *behind* a window at 1-1.5 m is deep inside the comfort zone. The only binding side is in front: at 1 m with a 2 m focal plane, only 8 cm is left. That is one more reason to keep everything behind the window **[inference]**.

**Platform guidance has no depth-range numbers for pictures.**
- Meta: content users fixate on "should be rendered at least 0.5 meters away", and "1 meter is a comfortable distance for menus and GUIs" ([Meta display guide](https://developers.meta.com/vr/design/display/)).
- Apple, for spatial photos in a window: choose a disparity shift "that pushes the closest objects just behind the front of the window … while maintaining a sense of depth". "+2 percent typically provides a good default" ([Creating spatial photos](https://developer.apple.com/documentation/imageio/creating-spatial-photos-and-videos-with-spatial-metadata), [Writing spatial photos](https://developer.apple.com/documentation/imageio/writing-spatial-photos)). This is a convergence shift, not a depth range.
- Microsoft: an optimal zone of 1.25-5 m. Objects moving in depth cause more discomfort than static ones ([comfort guide](https://learn.microsoft.com/en-us/windows/mixed-reality/design/comfort)). Zumi's layers are static, so this does not apply.
- The depth range of Apple spatial scenes, Meta Gallery 3D and Facebook 3D Photos is not published. Facebook normalised depth per image so that each induces the same screen parallax, but gave no number (see the earlier note).

## 2. What makes depth look right, not just comfortable

- **Roundness.** "The roundness factor is the ratio between its apparent depth and its apparent width". Below 1, a sphere looks like a disc. A rule of thumb says it "should never be below 0.2" (Devernay & Beardsley §1.3, §3.2).
  - Cardboarding is when depth is perceived, "but too little for the object's image size" (§2.4).
  - Chapiro et al. 2014 measured it: compressing depth "to 80% or above is likely to be acceptable", while "sensitivity to the cardboarding artifact below 30% is very high".
- **Orthostereo means homothetic, which here means proportional to the drawn size.** Faithful depth needs depth, size and baseline magnified by the same factor (Devernay Eq. 9). A comic has no camera, but a figure drawn at magnification m (drawn size / real size) keeps its true shape only if its relief is m × its real relief **[inference]**. Two examples at 1.5 m:
  - A full figure drawn 90 cm tall (m ≈ 0.5). Visible body relief is about 0.25-0.3 of shoulder width, i.e. ~12 cm real **[unverified: rough anthropometry]**. That gives **~6 cm**. Today's 3 % gives 4.3 cm, a roundness of ~0.7: fine.
  - A face close-up, face drawn 50 cm wide (m ≈ 3.3). Nose tip to ear plane is about 0.65 of face width, ~10 cm real **[unverified]**. That gives **~33 cm**. Today's 4.3 cm is a roundness of **0.13**, below both thresholds above. This is probably the "needs more relief" the user sees **[inference]**.
  - Hence relief ∝ the card's drawn size. With A = 0.25 × short side, clamped at 10 % of d, the close-up gets 10-15 cm: roundness ≈ 0.35-0.45, above the 0.3 cliff. The figure gets ≈ 1-1.2.
- **Scene depth cannot be orthoscopic.** At panel scale, a close-up's background would sit metres behind the window, and even a full shot's wall would be ~1 m back. So compress the backdrop distance per panel, and spend the budget on object roundness, which is what reads as cardboard. Chapiro's and Devernay's thresholds concern object shape **[inference]**.
- **Puppet theatre.**
  - Yamanoue, Okui & Okano (IEEE TCSVT 16(6), 2006) derive both distortions geometrically. Parallel-camera stereo avoids the puppet-theatre effect, and both camera setups can produce cardboarding **[unverified: abstract via search]**.
  - A headset renders parallel off-axis stereo, so Zumi has no geometric puppet-theatre source **[inference]**.
  - Whatever is done, figures will read at their drawn size at the panel's distance, like a diorama. Apple names the same split: window presentation versus immersive "at real-world scale" ([Apple](https://developer.apple.com/documentation/imageio/creating-spatial-photos-and-videos-with-spatial-metadata)).
- **Distance scaling.** Stereo shape is about veridical near 1 m. Objects look expanded in depth at 0.5 m and compressed at 2 m (Johnston 1991, Vision Research 31:1351) **[unverified: secondary descriptions]**. Adding motion cues removes the distortion ([Johnston, Cumming & Landy 1994](https://www.cns.nyu.edu/~msl/papers/johnstonetal94.pdf), abstract). So at 1.5 m the same share of depth will look a little flatter than at 1 m: use about ×1.2 there if the 1.5 m test reads flat **[inference]**.

## 3. Head-motion parallax vs stereo

- **Same geometry, different baseline.** A head translation t gives the parallax that stereo gives with baseline I, scaled by t/I **[inference]**.
  - Stereo is always on, at 6.3 cm.
  - A seated reader's head drifts by much less than that, except when leaning on purpose **[inference: no source found for seated reading]**.
  - So for a reader at 1-1.5 m, stereo carries the depth with the head still.
- **Precision.** At 1.12 m, binocular thresholds beat monocular ones "by as much as a factor of 18", and still by "roughly a factor of 10" with textures. Lateral head moves of 8-10 cm "produced little improvement" (McKee & Taylor 2010). Kim et al. 2016: depth from disparity "generally outperforms" motion parallax.
- **But parallax helps, and the two cues add.** Motion parallax is "a relatively strong depth cue", and with it present disparity can take "aggressive disparity compression" ([Kellnhofer et al. 2016](https://history.siggraph.org/?p=210583)). Combined thresholds show sub-threshold summation ([Bradshaw & Rogers 1996](https://pubmed.ncbi.nlm.nih.gov/8977012) **[abstract; authorship inferred from title and year]**).
- **Why the desktop said "too much".** Three mechanisms, all **[inference]** from the sources cited:
  1. **Cue conflict.** On a monitor, disparity, vergence and focus all report a flat surface. When disparity and parallax conflict, subjects "perceive rotation of the stimulus relative to the scene" (Kim et al. 2016). So the layers looked like they moved, not like depth.
  2. **The motion was not the viewer's.** The auto-sway (`index.html` tick: `0.18·amp·sin(t/900)` box widths) and WASD move the camera, not the head. Without extra-retinal signals, the depth sign of parallax "can be ambiguous" (Kim et al. 2016), so the shift is attributed to the layers.
  3. **The amplitude was large.**
     - The pinhole sits 0.96 box widths from the backdrop, so the sway at amp 0.5 is ±9.4 % of d: ±14 cm at 1.5 m, 28 cm peak to peak, 4.4× the IPD.
     - A 3 % step under that sway shifts 0.094 × 0.03/0.97 = 2.9 mrad (10′) peak, 20′ peak to peak.
     - In stereo at 1.5 m the same step is 0.042 × 0.0309 = 1.3 mrad (**4.5′, 1.9 px**). At 1 m it is 6.7′ (2.8 px).
  - So the desktop measured how much *sliding* is tolerable. In the headset that maps onto the head-parallax gain, not onto stereo depth.

## 4. Recommendation for Zumi

**Re-anchor at the window.** Today the backdrop is fixed at 1.0 and the window falls wherever the nearest point is (0.93-0.95). So the window-to-backdrop distance varies per frame: 5-7.5 % of d, or 7.5-11 cm at 1.5 m.
- Put the window at d, the reading distance where the XR app places the panel, and lay everything behind it.
- The format's `depthScale` default (0.6 m "of parallax spread between depth 0 and 1", `zumi.schema.json`) is 40 % of d at 1.5 m. Reconcile it with (a) below.

Everything below is a share of d behind the window.

**(a) Backdrop: 20 % (20 cm at 1 m, 30 cm at 1.5 m), cap 25 %.**
- Disparity relative to the window: 0.063 × 0.2/1.2 = 10.5 mrad = **36′ (15 px)** at 1 m, and **24′ (10 px)** at 1.5 m.
- At 1 m that is under Percival's 40′ and the 1° rule; at 1.5 m it is far under. A 25 % cap gives 43′ at 1 m.
- It is 3-4× today's 7.5 %, and one third of the frame against a room wall (30 px, earlier note).
- With a 5 cm lean, the backdrop moves 19′ (8 px) against the frame at 1.5 m, and 29′ (12 px) at 1 m.
- Margin check: an eye offset t needs t·B/d of backdrop past the frame. For a 15 cm lean at 1.5 m that is 2 % of d, against today's MARGIN of 4 % of the long side ≈ 5 % of d. It holds up to about a 35 cm lean.
- If the stack below does not fit, use B = max(20 %, farthest card plane + 3 %), up to the cap. Beyond the cap, compress the steps.

**(b) Card levels: a 4 % step (4 cm at 1 m, 6 cm at 1.5 m), at most 4 levels (12 % span), steps no smaller than 2.5 %.**
- The nearest card's relief peak sits 0.5 % behind the window: Apple's "just behind the front of the window".
- Each level's plane is its peak + A behind.
- One step is **6.9′ (2.9 px) at 1 m and 4.6′ (1.9 px) at 1.5 m**: 2-3 px, a clearly visible step. Today's 0.7 % is 0.4-0.7 px, at or under one pixel.
- Larger steps make a wrong DA3MONO order more visible. Watch for it in the test.

**(c) Card relief: A = c × the card's short side, with c = 0.25, clamped to 2-10 %.**
- Measure the short side in units of d at the card's depth: `short_px · z / f`, with `f = long_px / (2·tan 27.5°)`.
- Today's 3 % equals this rule at a short side of 12 % of d (~115 px on a 1000 px box).
- Examples at 1.5 m:

  | Card | Short side | A | Roundness |
  |---|---|---|---|
  | Background figure | 8 % | 2 % (3 cm) | ~0.9 |
  | Full figure | 20 % | 5 % (7.5 cm) | ~1.2 |
  | Face close-up | 40 % | 10 % (15 cm, clamped) | ~0.4 |

- Disparity of a 10 % relief: 19.5′ (8 px) at 1 m, 13′ (5.4 px) at 1.5 m. That is comfortable.
- Risks that grow with A **[inference]**: DA3MONO errors inside a figure get amplified (a hand, hair), and the texture stretches on the RELIEF_EDGE ramp at the silhouette when viewed off-axis. Keep the edge at the card plane, as now.

**(d) Backdrop relief: 4 % (4 cm at 1 m, 6 cm at 1.5 m), tilt kept.**
- Wherever a card covers the backdrop, keep the backdrop at least 1 % of d behind that card's plane. Otherwise occlusion and disparity disagree.
- Where no card covers it, a floor may come forward toward the figures' feet, so they stand on it rather than float **[inference]**.
- Disparity at the backdrop: 6.2′ (2.6 px) at 1 m, 4.1′ (1.7 px) at 1.5 m.

**Head motion separately.** If the headset shows the right depth with the head still but leaning feels like too much movement, damp the head-motion parallax with the factor k from the earlier note (start at 0.5). Leave the stereo depth alone.

## 5. Test plan (in the headset, at 1.0 m and 1.5 m)

Use 10 boxes: 3 face close-ups, 3 medium shots, 2 full or wide shots, and 2 with 3 or more characters. Show them in random order, and do not tell the user which setting is on.

| # | Sweep (others at default) | What to record | Pass |
|---|---|---|---|
| 1 | Head still (chin on hand): today vs the defaults | "Depth inside the art?" yes/no per box. Then close one eye: does the depth disappear? (That would mean stereo is what carries it.) | Defaults give yes on ≥ 8 of 10 boxes; today's settings fewer |
| 2 | Backdrop B = 10, 20, 30 % | Depth rating 1-5; comfort after reading all 10 boxes (~3 min); any double image | Pick the smallest B where depth ≥ 4, with no strain and no double images |
| 3 | Level step S = 2.5, 4, 6 % | Do characters separate? Does any order look wrong? | Separated without "stacked cardboard"; count wrong-order boxes |
| 4 | Relief c = 0.12, 0.25, 0.4, per shot type | "Flat / right / puffy" per card | Close-ups and full figures both "right" at one c. If not, split c by shot type |
| 5 | Lean ±10 cm and ±25 cm at the chosen settings | Tears at silhouettes, the plate edge showing, the frame cutting a card | None at ±10 cm; a fade is acceptable at ±25 cm |
| 6 | Only if leaning feels "too much motion": k = 1, 0.5, 0.3 | Motion comfort while keeping the stereo depth of #2 | Lowest k that removes the complaint without the backdrop "swimming" |

Repeat #2 and #4 at 1.5 m. If 1.5 m reads flatter at the same shares (the Johnston scaling), try ×1.2 there.
