# Motion inside the panels: keep, drop, or narrow? — 2026-11-10

Research date: 2026-11-10. Two readings of the public sources (the evidence on motion in comics; a catalogue of techniques with prices read that day), plus the repo's own state. No paid calls. Context: step 9, Motion, as designed on 2026-11-07 (`docs/architecture/decisions.md` section 4 step 9; `CONTEXT.md`: Track, Beat, Hold, Motion); nothing of it is built.

Conventions: **[docs]** read in the cited primary source. **[est]** inference or arithmetic. **[unverified]** not confirmed in a primary source. **[local]** read in this repo.

## Recommendation

**Do not drop animation; drop the Motion step as designed, and build a narrower one that costs nothing per episode.**

The designed step asks an agent, per box, for two things: ambient motion that "keeps the panel alive" and acted beats where a character cuts to a new position (about 1 to 1.5 USD an episode). The evidence supports neither half as designed, and supports something smaller that the design did not single out.

1. **Ambient loops on cards: drop.** No study shows decorative motion helps. The two literatures that measured motion over still pictures both expect decoration to add nothing or to interfere (Takacs & Bus 2016; Höffler & Leutner 2007) **[docs]**. In the headset the panel already answers the head with parallax, which never starts on its own and so never pulls the eye off the speaker **[est]**.
2. **Acted beats that move a character: drop.** Three reasons. The erase now paints only a band as wide as a 30 cm head move behind each card, on a flat prefill (`pipeline/segment/layers.py` lines 29-39) **[local]**, so a card cut to a new place uncovers a plain patch; the 2026-11-07 design assumed the whole area was painted. A figure drawn mid-gesture that changes place reads as a paper cut-out **[est]**. And it is the one kind that needs a paid judgement per box.
3. **Motion tied to the spoken line: keep, as rules, with no model call.** This is the only kind with evidence behind it: under narration, motion that showed what the narrator said raised attention to the right detail (0.80 vs 0.70 of the time) and recall (12.7 vs 11.4 content words), n = 39 children **[docs]**; representational animation d = 0.40 across 26 studies **[docs]**. The pipeline already knows, per balloon, who speaks, when, and how (speech, shout, thought, sound effect, a delivery note) **[local]**. So: a small accent on the speaking card at its balloon's start (a scale of a few percent, a short settle), a shake on a shout or an impact sound, nothing on a thought. The onset of motion is what captures attention (Abrams & Christ 2003) **[docs]**; placed on the speaker at the first syllable, that capture points where the reader should look, which parallax cannot do. All of it stays inside the painted band. It is the visual-novel convention, minus the lip flaps.
4. **Motion in the room: keep, from data already there.** The place's light, its props and the view behind the walls can move without touching the drawing: a slow candle flicker, weather in the walls' view, sparse particles. No model call. Meta's limits apply: no purposely flickering content, no large moving field, nothing rushing at the reader **[docs]**.
5. **Timing: already built, and it is the largest part.** When each balloon, frame and panel appears, and the held wordless frame, are the animation the comics makers themselves endorse (Infinite Comics, Thrillbent) **[docs]**. The clock does it today **[local]**.
6. **Everything generative or rigged: drop for now.** Image-to-video costs 0.45 to 21 USD an episode at one clip per panel and has no measured record on hand-drawn line art; automatic rigging succeeds on 23 to 39 % of full, front-facing figures and names cropped and overlapping figures (most comic panels) as failures; neural talking heads need an upright front-facing bust and about 30 GPU-hours per character **[docs]**. Runtime on Quest 3 is also the worst here (6 to 30 MB of texture per animated card) **[est]**.

**Is the narrow version impactful?** Unknown, and that is the honest state: nobody has measured motion in comics for adult readers, nor whether a still image under a voice reads as dead. What can be said: it is the kind the evidence favours, it cannot damage the drawing, and it costs no call. So the decision can be made by looking: build the speaker accents and the room motion for one episode in the three.js preview and compare it against the same episode still. That test costs no money.

**What this changes in the plan**

| Planned (2026-11-07) | Proposed |
|---|---|
| `motion.py`: one Sonnet call per box, a Haiku review, 1 to 1.5 USD an episode | No model call. Rules in the export from the clock, the speakers and the balloon kinds |
| Ambient tracks on every box | None on the cards; ambient life comes from the room and from head parallax |
| Beats: a character cuts to a new place | None. A card never leaves its painted band |
| Holds of 2 to 8 s on wordless boxes | Keep (a timing rule; it needs no motion designer) |
| `step` easing added to the schema | Not needed |
| Track player in the reader: translate, rotate, scale, opacity, sway, shake | A smaller player: scale and shake on a card, timed to a balloon |

**Open questions the research could not settle**

- Whether head parallax already gives the sense of life that ambient motion was meant to add: no study; my inference.
- Whether an accent on every line becomes a tic. Visual novels use it sparingly; there is no measurement. A rule such as "only on a change of speaker, on a shout, or after a silence" is a design choice to try in the preview.
- A possible later step, if the still cards feel dead in the headset: sway of a part that the drawing itself shows moving (a flame, a flag), cut by SAM 3.1 on request and bent in a vertex shader. It needs an erase under the part (0.034 USD each) and a reviewer; amplitude of 1 to 2 % of the card hides the stretch **[est]**.

**What is weak in this note**

- The best evidence is children with picture books and learning tasks, not adult comic readers and enjoyment.
- Several key texts were not read in the primary source (Tversky 2002, McCloud, Balak, anything from the Korean platforms); they are marked below.
- No primary source measures how current video models treat hand-drawn lines; the stated failures are expectation.

---

# Part A. The evidence


Tags: **[docs]** = read in the cited page this session. **[est]** = my inference. **[unverified]** = seen only in a search summary or secondary write-up; the primary text was not read.

### Summary (150 words)

No study compares animated and static comics for adult readers; that gap is itself the main finding. The nearest controlled evidence is narrated picture books: with 39 children, motion that showed what the narrator was saying raised attention to the right detail (+9 points of fixation time) and story recall (12.7 vs 11.4 content words). The learning literature agrees: animation helps when it depicts the content (d = 0.40) and its authors expect decorative motion to add nothing or interfere. Creators' objections (Waid, Quesada, Balak) are about motion taking the clock away from the reader, which a voiced, timed episode has already done. The market dropped autoplayed motion comics as a way to read, but kept voiced stills and triggered one-off effects. In a headset, small world-locked motion is not a comfort risk; large moving fields are. So: motion tied to the spoken line can help; ambient decoration is unsupported and can distract.

### 1. Research on motion comics and animated digital comics

- **No controlled study of motion comics vs static comics with adult readers was found** (comprehension, immersion or eye movements). Searches of the motion-comics, webtoon and eye-tracking literature returned none. **[est]** from absence.
- Craig Smith's work is definitional, not empirical. His 2012 article on motion comics and authenticity says audience reception is outside its scope. **[unverified]** ([repository record](https://repository.canterbury.ac.uk/item/8751q/motion-comics-modes-of-adaptation-and-the-issue-of-authenticity), [2015 article](https://repository.canterbury.ac.uk/item/87685/motion-comics-the-emergence-of-a-hybrid-medium)).
- Closest experiment: Takacs & Bus 2016, narrated storybooks, within-subject, **n = 39** children aged 4 to 6 (35 with usable eye data). Animated vs static illustrations: share of time on the illustration 0.84 vs 0.79; time on the detail that moved 0.80 vs 0.70; content words recalled 12.74 vs 11.40 (ηp² = 0.14); pages correctly summarised 67.6% vs 61.2%. Vocabulary: no difference. The motion tested always matched the narration. The authors state decorative animation "might even interfere with learning" and call that an untested hypothesis. **[docs]** ([Frontiers in Psychology](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2016.01591/full)).
- The same group's meta-analysis of technology-enhanced storybooks found animation, music and sound effects helped comprehension and word learning, while interactive hotspots and games distracted. **[docs]** for the direction (thesis abstract, [Leiden repository](https://scholarlypublications.universiteitleiden.nl/access/item%3A2872127/view)); effect sizes not read.
- Webtoons: a 2017 Korean analysis (no participants) found that scroll-triggered animation and sound go out of sync with the reader, because scroll speed sets the animation speed, and that the mismatch breaks concentration. **[docs]** (abstract, [Kim 2017](https://koreascience.kr/article/JAKO201714563184149.page?lang=ko)). Note the cause: the reader, not a clock, drives time.
- A 16-reader interview study reports webtoon readers valuing sound and visual effects for immersion, with no static comparison. **[unverified]** ([USF record](https://digitalcommons.usf.edu/si_facpub/647)).
- These are children, picture books and qualitative work. Transfer to adult comic readers is an inference. **[est]**

### 2. Comics theory: why motion can break the form

- **Mark Waid**: "I believe that the reader has to stay in control of the experience... It needs to be up to you, the reader, to decide at what pace you go through the story." Once the creator adds "music, voices, animation, or anything that imposes moving time on the experience", it "becomes a more passive, and certainly a different, experience". **[docs]** ([IEEE Spectrum](https://spectrum.ieee.org/comic-books-go-digital)). He does not say worse; he says different.
- **Joe Quesada, Marvel Infinite Comics (2012)**: the format is "essentially an animatic, but what makes it a comic is that the reader controls the timing"; motion comics have become "a hybrid between comics and animation". **[docs]** ([CBR](https://www.cbr.com/marvel-sxsw-quesada-opens-the-all-digital-infinite-comics/)).
- **Balak, "About Digital Comics" (2009)**: the reader advances by click; changes are "simple cuts from one image to another", no animation needed. **[docs]** for the commentary ([Timeframing](https://scalar.usc.edu/works/timeframing/excerpt-from-about-digital-comics)). His own wording against sound, voice and movement "gimmicks" was not read. **[unverified]** ([original](https://www.deviantart.com/balak01/art/about-DIGITAL-COMICS-111966969)).
- **McCloud**: comics as a "temporal map" where space stands for time; in Reinventing Comics he asks whether, if partial sound and motion aid immersion, full sound and motion would not do it better. **[unverified]**, via secondary sources ([Timeframing](https://scalar.usc.edu/works/timeframing/the-slippery-slope-of-time)); page numbers not checked.
- All three practitioner rules rest on one premise: the reader owns time. A product that plays on a voice clock has already left that premise, so these rules say it is not "a comic" by their definition; they do not predict that added motion makes it worse. **[est]**
- A related craft claim: literal animation can "short circuit the implied motion" already drawn into comic art. **[unverified]**, critic's opinion from a search summary ([Full Stop](https://www.full-stop.net/?p=12635)).

### 3. What the market did

- **Watchmen: The Complete Motion Comic (2009)**: reviews praised fidelity and attacked the single male narrator voicing every role; one reviewer did not see the point of the format. **[unverified]** (review summaries: [PopMatters](https://popmatters.com/71818-watchmen-the-complete-motion-comic-2496042805.html), [DVD Talk](https://www.dvdtalk.com/reviews/review/36564)). The complaints named are about voice, not motion.
- **Madefire Motion Books**: entered insolvency on 7 April 2021 after raising at least 16.4 M USD. The trade press verdict: motion-comic technology "just never became a popular way to read comics"; readers "prefer free comics, print comics and Amazon". **[docs]** ([The Beat](https://www.comicsbeat.com/madefire-shuts-down/)). The company published no engagement numbers that I found. It shipped on Oculus Rift and Magic Leap (12 titles at launch, described as the tablet app moved into AR). **[unverified]** ([Reality News](https://magic-leap.reality.news/news/magic-leap-finally-releases-madefire-comic-book-app-for-interactive-reading-comic-creation-0193337/)).
- **comiXology Guided View**: the motion that shipped at scale was the transition between still panels, not motion inside them; some readers called even that "nauseating". **[unverified]**.
- **Japanese vomics**: voiced manga panels with occasional motion graphics; Shueisha ran them from at least 2013, moved them to its YouTube channel in 2020, and used one to promote Kagurabachi in 2024. **[unverified]** ([Kanzenshuu](https://www.kanzenshuu.com/2014/02/08/jaco-galactic-patrolman-first-vomic-installment-online/), [Sportskeeda](https://www.sportskeeda.com/anime/news-kagurabachi-becomes-first-major-shonen-series-receive-manga-animation-english)). Voice over near-still panels survived, as promotion. No view counts found.
- **Korean webtoons**: "Bongcheon-Dong Ghost" (Naver, 2011) used two sudden triggered animations and went viral internationally. **[unverified]**, via [Wikipedia](https://en.wikipedia.org/wiki/Bongcheon-Dong_Ghost) and its cited press. Nothing was found in primary sources on Naver "effect toons", WEBTOON FX episodes or Kakao, and no platform engagement numbers. **No data found.**
- Pattern: products built on continuous autoplayed motion were dropped as a reading format; rare, timed, story-bearing effects (a jump scare) and voiced stills persisted. **[est]** The failures are confounded by price, distribution and voice quality; none isolates motion.

### 4. Voiced visual novels and gacha story scenes

- **No player study, postmortem or conference talk was found that measures which small motions matter.** Thin evidence.
- One telemetry study of visual-novel reader preferences (about 555 players) covers text and interface settings only; nothing on sprite motion. **[docs]** ([itch.io devlog](https://trinitite-team.itch.io/the-sekimeiya-spun-glass/devlog/294020/vn-reader-preferences-an-empirical-analysis)).
- Developer intent, not measurement: the Emberstoria team says it used Live2D to hold players who would otherwise skip the story, and upgraded lip sync late because volume-driven mouths looked clipped. **[unverified]** ([Automaton](https://automaton-media.com/en/interviews/square-enixs-emberstoria-switched-to-elaborate-lip-syncing-technology-only-6-months-before-launch-achieving-a-level-of-realism-rarely-seen-in-mobile-games/)).
- Anecdote: indie developers have removed or halved Live2D for cost, and their players accepted it while saying it made the game feel "more alive". **[unverified]** ([itch.io](https://itch.io/blog/784676/announcement-removing-animations)).
- Whether idle breathing is "expected" has no measured answer. Static-sprite visual novels still ship and sell; commercial gacha games mostly animate. **[est]**

### 5. Adjacent fields

**(a) Attention capture.** Abrams & Christ 2003 (three experiments): "motion per se does not automatically attract attention"; "the onset of motion does indeed attract attention". **[docs]** (abstract, [WUSTL record](https://profiles.wustl.edu/en/publications/motion-onset-captures-attention/)). Bartram et al. 2001 found moving icons are detected well in the periphery and that some motion types are far more distracting and irritating than others. **[unverified]** ([paper](https://www.interruptions.net/literature/Bartram-Interact01.pdf), PDF could not be parsed). Reading: each start of a motion pulls the eye once; steady motion pulls less. A motion that starts on something other than the speaker competes with the line being spoken. **[est]**

**(b) Animation vs static graphics.**
- Höffler & Leutner 2007: 26 studies, 76 comparisons, overall d = 0.37 (95% CI 0.25 to 0.49) for animation; d = 0.40 "when the animation is representational rather than decorational"; d = 1.06 for procedural-motor content. **[docs]** (abstract, [IPN](https://www.leibniz-ipn.de/en/research/publications/instructional-animation-versus-static-pictures-a-meta-analysis)). No separate figure for decorative animation in the abstract.
- Tversky, Morrison & Bétrancourt 2002: animations often fail because they are too fast or complex to be perceived (the apprehension principle), and many apparent wins came from animations carrying more information than the static version. **[unverified]** this session ([PDF](https://hci.stanford.edu/courses/cs448b/papers/Tversky_AnimationFacilitate_IJHCS02.pdf), not parseable).
- Berney & Bétrancourt 2016 found a smaller overall effect, g = 0.226. **[unverified]** ([Springer discussion](https://link.springer.com/article/10.1007/s11251-021-09541-w)).
- These measure learning, not enjoyment.

**(c) Cinemagraphs.** Only small conference eye-tracking studies and vendor numbers exist. A tool maker's "5 to 6 times the click-through rate" is a **marketing claim**. **[unverified]**. No solid evidence either way.

### 6. Mixed and virtual reality

- Meta's guidance: "Vection (illusory self-movement) can arise when a user is stationary but content is moving and impact user comfort"; "Approaching or looming content can lead to reactive behavior such as dodging quickly or backing up into a physical object"; depth is harder to judge "when content occupies most of the FoV". **[docs]** ([MR health](https://developers.meta.com/horizon/design/mr-health-general/), [vision](https://developers.meta.com/horizon/resources/bp-vision/)). The pages read say nothing on head-locked vs world-locked content.
- Implication: a small card moving inside a panel with passthrough around it is a small moving object, not a moving field. A wall-sized painted view that moves is the vection case, and anything that rushes at the viewer is the looming case. **[est]**; Meta gives no size threshold.
- VR/MR comics research is new and does not test motion. ComiXR (KAIST, ACM DIS 2026, **n = 15**, built for Quest Pro): participants strongly preferred layouts that use real depth, characters at different depths from the background, over flat pages. **[unverified]** (news write-up, [KAIST](https://ee.kaist.ac.kr/en/research-achieve/prof-ian-oakleys-team-develops-comixr-an-extended-reality-xr-platform-for-reading-and-creating-comics/)). Goodbrey & Tree 2026 is practice-based, no participants, about panel placement in depth. **[docs]** (abstract, [IJFMA](https://revistas.ulusofona.pt/index.php/ijfma/article/view/10074)).
- **Does head-tracked parallax already supply the "life" that animation adds on flat screens? No study found tests this.** Parallax is self-caused motion: it answers the viewer's head, never starts on its own, and so should not trigger onset capture; that also means it cannot point at the speaker. **[est]**
- Nothing found on Quill-made stories or Magnetique that reports measured reactions to motion. **No data found.**

### 7. Voice changes the question

- Audio alone engages. Richardson et al. 2020 (Scientific Reports): the same scenes as audiobook or video; viewers rated video as more engaging, but heart rate, skin conductance and temperature were higher for audio. **[unverified]** this session (sample about 100; [PMC](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7347852/) blocked). A voice does not need moving pictures to hold a listener. **[est]**
- Documentary practice on stills under a voice. Ken Burns: "any movement, however dazzling or frenetic, if it doesn't have meaning, it doesn't have a place", and "there are times when you absolutely have to stop and look and drink it in". Editors in the same piece: motion "tells the viewer where to look"; "If it's a powerful image, I wouldn't mess around with it". **[docs]** ([Poynter](https://www.poynter.org/news/meaning-motion-ken-burns-and-his-effect)). Expert statement, not measurement.
- **No study was found on whether a still image under a voice reads as "dead", or on the minimal motion that fixes it** (animatics, illustrated audio drama). The picture-book result in section 1 is the nearest: under narration, motion that depicts the spoken content helps. **[est]** for the transfer.

### Table: kind of motion × evidence

| Kind of motion | Evidence it helps | Evidence it hurts | Confidence |
|---|---|---|---|
| Motion that depicts the line being spoken (speaker acts, object named moves) | Picture books n = 39: more attention to the detail, better recall; representational animation d = 0.40 | None found | Medium (children, learning tasks) |
| Ambient or decorative loops (sway, idle breathing) | Only developer belief ("more alive") | Authors of both literatures expect none or interference, untested; onset capture if it starts mid-line | Low: no direct test |
| One-off timed accent (shake, flash, sudden cut) | Market: the 2011 scroll-triggered horror webtoon; common in gacha story scenes | Onset pulls gaze from the speaker if mistimed (inference) | Low to medium |
| Slow pan or zoom over a still | Documentary practice: directs the eye | Burns: movement without meaning has no place; hold still on strong images | Low (expert opinion) |
| Continuous autoplayed motion-comic animation | None found | Market dropped the format; creators say it stops being comics (confounded) | Medium that it failed commercially; low on why |
| Reader-triggered animation | Viral single cases | Kim 2017: timing desyncs with reader speed | Low; not this case (clock-driven) |
| Large moving field (wall view) or looming content in a headset | None | Meta: vection and reactive dodging | High (platform guidance) |
| Head-tracked parallax alone, no animation | ComiXR n = 15: depth strongly preferred | None found | Low: never compared with animation |
| Lip flaps, blinking | None measured | None measured | No evidence |

---

# Part B. The techniques


Read on 2026-11-10. Every price below was read that day unless marked. Tags: **[docs]** read in the cited primary source; **[est]** my inference or arithmetic, shown; **[unverified]** not confirmed in a primary source.

Local facts used (read in the repo): the track vocabulary is translate, rotate, scale, opacity, sway, shake, spriteCycle, with easings linear, inOut, out, in (`packages/format/schema/zumi.schema.json`, lines 388-392; `step` is in the glossary and the design but not yet in the schema enum). The planned Motion step is one Sonnet call per box plus a Haiku review, about 1-1.5 USD for 31 boxes (`docs/architecture/decisions.md`, section 4 step 9).

One local conflict matters for everything that moves a card. `decisions.md` step 9 says "the erase paints everything behind a card, so a card may go anywhere in its frame". `pipeline/segment/episode.py` (step 3) says the card interiors are prefilled with the frame's plain background colour and only "a band as wide as a head move uncovers" is painted. If the second is the current state, a card moved further than that band shows a flat-colour patch, not painted art. **[docs, local]**

### Ranked table

Ranked by how safely the technique can ship with today's assets. "Episode" = 30 panels, 4 s of motion each (120 s).

| # | Technique | Needs | Automatic? | Cost per episode | Quest 3 runtime | Risk to the drawing | Precedent |
|---|---|---|---|---|---|---|---|
| 1 | Timing only (reveal order, holds, cuts) | Already have (clock, reading order, voices) | Yes | 0 | Low: no extra rendering | None | Thrillbent, Marvel Infinite Comics, Naver Webtoon Editor |
| 2 | Motion in the room (light, props, walls' view, spatial audio) | Already have (light record, props, place mesh) | Yes, from the setting's attributes | 0 to about 0.13 USD (one small call per frame) | Low to medium: relit proxy surfaces are alpha blended | None on the panel; flashing is a health limit | Meta Passthrough Relighting sample |
| 3 | Effect layers over the panel (particles, flicker, glow) | One model call for weather and light position | With a reviewer | About 0.13 USD | Medium: overlapping transparent quads cost fill rate | Low: an effect can cover a face or a balloon | Naver Webtoon Editor, visual novels |
| 4 | Rigid card transforms (cut, pop, slide, shake, fade) | Already have; a designer call decides | With a reviewer | 1-1.5 USD (the planned step) | Low: transforms on existing cards | Low to high: a far move may expose the prefill | Limited animation, motion comics, visual novels |
| 5 | Clock-driven camera and relief (push-in, drift) | Already have | Yes | 0 | Low | None to the art; comfort risk if layers shift without head motion | Ken Burns, motion comics |
| 6 | Procedural sway of a part (hair, cape, flame) | One SAM call per part plus a pin edge | With a reviewer | 0 paid (local SAM) | Low: a few hundred vertices per part | Low to medium: stretch at the pin, the part tears from its outline | Live2D physics, Naver motion effects |
| 7 | Blink and mouth flap (minimal talking head) | New research: eye and mouth parts, plus painted closed states | No (not shown automatic on comic art) | Unknown | Low (sprite swap) | High: a redrawn eye or mouth on a face | Limited animation (Syncro-Vox, anime mouth flaps) |
| 8 | Single-still motion fields (Generative Image Dynamics, Eulerian fields) | New research: no official code; trained on real video | No | Unknown | Low if baked to a displacement map | Medium: warps thin lines | Papers only, on photos |
| 9 | Generative video per card (image-to-video, matte, sprite sheet) | One paid call per card plus matting | With a reviewer; failures are common | 0.60 to 21 USD by model, plus about 0.77 USD matting | High: 6-30 MB of texture per animated card, or video decode | High: boiling lines, off-model faces, matte fringe, loop pop | ToonCrafter (cartoon interpolation) |
| 10 | Puppet rig of a figure (Animated Drawings, Live2D-style layers) | New research for partial figures | No | Unknown | Medium (mesh skinning) | High: wrong joints, torn limbs | Animated Drawings (full figures only) |
| 11 | Neural talking head (Talking Head Anime, LivePortrait) | Front-facing 512 px bust per character; 30 GPU-hours per character for real time | No | Above budget | High: needs an Nvidia GPU, so bake only | High: face redrawn; landmarks fail on stylised faces | VTuber avatars |

### 1. Camera and relief

What it looks like: the virtual camera inside the panel pushes in or drifts, and the depth layers shift against each other on the clock rather than with the head.

- Meta's comfort page says "Motion sickness can occur when there is a mismatch between what the user sees and how they move" and asks developers to avoid "unnatural camera movements". It also says showing the real room at the edges "provides stable visual references and helps ground the user". **[docs]** [Meta, Comfort](https://developers.meta.com/horizon/design/comfort/)
- The page does not address motion inside a world-locked panel. **[docs]** (absence checked on that page)
- Inference: a slow push-in inside a panel that fills a small part of the view, with passthrough around it, resembles watching a screen and is low risk. Clock-driven parallax is different: the reader already gets parallax from the head, so layers that shift while the head is still contradict the depth cue they just learned. Scale and opacity of the whole frame are safer than lateral layer shifts. Never move the panel itself in the room. **[est]**
- Cost: zero paid, zero new assets. Failure: a push-in crops balloons or reaches the plate's edge; both are checkable by geometry. **[est]**

### 2. Rigid card transforms

What it looks like: a character card cuts to a new place, an object slides, the frame shakes on an impact, a card scales in.

- Precedent: limited animation reuses frames and holds still characters; anime shows "mouth movement with occasional eye blinks"; smear frames show fast motion as a blur. **[docs]** [Wikipedia, Limited animation](https://en.wikipedia.org/wiki/Limited_animation) (secondary source)
- Precedent on comics: the Naver Webtoon Editor (2015) gave artists parallax, vibration ("a rifle shot or a phone buzzing"), flickering dialogue and scroll-timed motion. Those were authored by the artist, not automatic. **[docs]** [Korea JoongAng Daily, 2015-06-22](https://www.koreajoongangdaily.com/lifestyle/webtoon-artists-get-special-effects-help-from-naver/10463021)
- Cost: the planned designer and reviewer calls, 1-1.5 USD an episode. **[docs, local]** Runtime: transforms on cards that are already drawn; no new draw calls. **[est]**
- Typical failure on drawn art: a figure drawn mid-gesture slides like a cut-out, which reads as cheap; a far move exposes the flat prefill (see the local conflict above); a shake moves a card whose mask has a fringe and the fringe becomes visible. **[est]** Cheap check: compare each card's swept area with the painted band; reject tracks that leave it. **[est]**

### 3. Deforming a card

**Procedural sway of a part.** A part mask (SAM 3.1, prompted "hair", "cape", "flame") is cut to a sub-card with a pin edge; a vertex shader bends it with a sine weighted by distance from the pin.

- Runtime: a 16 x 16 grid is 289 vertices per part **[est: 17 x 17]**. Meta's conservative target is "50,000 static triangles per-eye per-view" **[docs]** [Meta, Unity mobile performance](https://developers.meta.com/vr/documentation/unity/unity-mobile-performance-intro). The part is one more alpha-blended quad over the card. **[est]**
- Needs beyond the mask: the pin edge (where the part meets the body) and what is behind the part. The erase works behind whole cards, not behind parts of a card, so a swaying part uncovers a hole in its own card unless the card is inpainted under the part (one more erase call, 0.034 USD at the pipeline's current price **[docs, local]**). **[est]**
- Failure: black outlines stretch, hair detaches from the head at the pin. Amplitudes of 1-2% of the card height hide it. **[est]**

**Puppet and auto-rig.**

- Animated Drawings assumes "a single human figure", counts a box that cuts off an arm or foot as a failure, fails when "limbs are drawn touching at points other than the joints", and says figures "not drawn facing forward ... also result in failure". On 571 test drawings all three stages succeeded for 23.3% (Mask R-CNN) or 39.4% (image processing). **[docs]** [Smith et al. 2023](https://ar5iv.labs.arxiv.org/html/2303.12741)
- The repository was archived on 2025-09-03; code and weights are MIT. **[docs]** [AnimatedDrawings](https://github.com/facebookresearch/AnimatedDrawings)
- Comic panels mostly hold busts, cropped bodies and overlapping figures, which are the stated failure cases. **[est]**
- See-through decomposes one anime illustration into "up to 23 layers" (hair, face, eyes, clothing) as a PSD with depth, at 12-16 GB VRAM at 1280 px, about 10 GB with group offload. It "only decomposes"; rigging "is not covered in this project". **[docs]** [see-through](https://github.com/mitmul/see-through). It was trained on Live2D models; behaviour on non-anime comic styles is **[unverified]**.
- Textoon generates Live2D characters from text, not from an existing drawing. **[docs]** [arXiv 2501.10020](https://arxiv.org/abs/2501.10020). CharacterGen builds a 3D character from one image, trained on anime characters. **[docs]** [arXiv 2402.17214](https://arxiv.org/abs/2402.17214). Neither animates a given panel.

**Talking head.**

- Talking Head Anime 3 and 4 need a 512 x 512 image with alpha, "only one humanoid character", "standing upright and facing forward", hands "below and far from the head". **[docs]** [THA4 demo](https://github.com/pkhungurn/talking-head-anime-4-demo), [THA3 demo](https://github.com/pkhungurn/talking-head-anime-3-demo)
- The full model is "too slow to run in real-time". The distilled student reaches 30 FPS or more on a desktop GPU, but training it took "about 30 hours on a computer with an Nvidia RTX A6000 GPU" per character. Models are CC BY-NC 4.0. **[docs]** [THA4 demo](https://github.com/pkhungurn/talking-head-anime-4-demo), [project page](https://pkhungurn.github.io/talking-head-anime-4/)
- Neither source says anything about non-anime styles, three-quarter views or occluded faces. **[docs]** (absence). Quality there is **[unverified]**.
- LivePortrait describes itself as for "humans, cats and dogs" and warns of "visual artifacts". **[docs]** [LivePortrait](https://github.com/KwaiVGI/LivePortrait). Reports that stylised faces often fail at landmark detection come from a third-party project, not read in full. **[unverified]** [WarpTuber](https://huggingface.co/AIWarper/WarpTuber)
- Lip-sync risk: a voice already plays per balloon, so a mouth that moves off the syllables is seen at once; a face redrawn off-model is the most visible failure in a comic. A two-state mouth flap avoids sync claims but needs a painted closed mouth per face. **[est]**

### 4. Generative video on a card or frame

Prices, read 2026-11-10 on [fal's price page](https://fal.ai/pricing) **[docs]**: PixVerse V6 0.005 USD/s; Grok Imagine Video 1.5 0.01; MiniMax H3 Max Turbo 0.025; H3 Max 0.05; Kling 2.5 Turbo Pro and 2.6 Pro 0.07; FLUX 3 Max 0.085; Kling v3 and O3 0.14. The page states no resolutions. On [Runway's API price page](https://docs.dev.runwayml.com/guides/pricing/) **[docs]**, at 0.01 USD a credit: gen4_turbo 0.05 USD/s; gen4.5 0.12; wan3 0.05 (480p) to 0.20 (1080p); veo3.1_fast 0.10 without audio; veo3.1 0.20 without audio; hailuo3 0.10 (768p). I could not read Veo's price on Google's own page (the fetch was truncated), nor Luma's or Kling's own pages. **[unverified]**

Cost for 30 panels **[est: 30 x 3-5 s = 90-150 s]**: PixVerse V6 0.45-0.75 USD; Grok 1.5 0.90-1.50; H3 Max Turbo 2.25-3.75; Kling 2.6 6.30-10.50; Kling v3 12.60-21.00; Veo 3.1 Fast (Runway) 9-15. That is one clip per panel. One clip per card, with retries, multiplies it. Only the two cheapest fit a budget of about 1.5 USD an episode.

Open models and 12 GB:
- Wan 2.2 TI2V-5B: 720p at 24 fps, "at least 24GB VRAM", Apache 2.0. **[docs]** [Wan2.2](https://github.com/Wan-Video/Wan2.2). Quantised builds on 12 GB are **[unverified]**. Hosted: 0.15 USD a video up to 5 s, so 4.50 USD for 30 **[est]**; the endpoint is removed 2027-01-04. **[docs]** [fal](https://fal.ai/models/fal-ai/wan/v2.2-5b/image-to-video)
- LTX-2: image-to-video and keyframe interpolation, a download of "roughly 66 GiB", fp8 quantisation and offload flags, no stated minimum VRAM; weights under a community licence. **[docs]** [LTX-2](https://github.com/Lightricks/LTX-2)
- ToonCrafter: interpolates two cartoon frames, "up to 16 frames with a resolution of 512x320", 24-27 GB, lowered by the community "to ~10GB"; "the success rate is not guaranteed". **[docs]** [ToonCrafter](https://github.com/Doubiiu/ToonCrafter). It needs an end frame, which a single panel does not have.

Alpha:
- TransPixar generates RGBA video; released weights are text-to-video on CogVideoX-5B, about 24 GB. **[docs]** [TransPixar](https://github.com/wileewang/TransPixar)
- Wan-Alpha is text-to-video; its image-to-video weights were still a to-do item in the model card as reported by search. **[unverified]** [Wan-Alpha](https://huggingface.co/htdong/Wan-Alpha)
- So the practical route is: composite the card on a flat colour, run image-to-video, then matte. Hosted matting costs 0.008 USD per 30 frames **[docs]** [fal](https://fal.ai/pricing): 96 frames a clip is about 0.026 USD, 0.77 USD an episode **[est: 4 s x 24 fps / 30 x 0.008 x 30]**. MatAnyone is "human video matting" and needs a first-frame mask. **[docs]** [MatAnyone](https://github.com/pq-yang/MatAnyone)

Loops: first-and-last-frame models take a start and an end image (0.20 USD at 480p on fal **[docs]** [wan-flf2v](https://fal.ai/models/fal-ai/wan-flf2v)); giving the same still as both ends should close the loop, at the risk of an almost static clip. **[est]**

Line art: I found no primary source that measures how these models keep hand-drawn lines. Expected failures: lines shimmer frame to frame (boiling), flat colours gain shading, a face drifts off-model within seconds, hatching turns to texture. **[unverified]** Cheap checks **[est]**: similarity of every frame to the source outside the moving region; the identity encoders the pipeline already has, run on each frame's face; first-versus-last-frame difference for the loop; alpha coverage for holes.

Runtime:
- Unity supports per-pixel alpha in two codecs, ProRes 4444 and WebM VP8. On Android "you must enable transcoding during the import process and enable Keep Alpha". **[docs]** [Unity manual 6000.3](https://docs.unity.com/en-us/engine/6000.3/manual/video/sources/transparency/codecs). Import-time transcoding does not suit files loaded from an episode package at run time. **[est]** How many videos Quest 3 decodes at once is **[unverified]**.
- Sprite sheet: 48 frames (4 s at 12 fps) of a 512 x 512 card is 50 MB uncompressed **[est: 512 x 512 x 4 bytes x 48]**, or 5.6 MB in ASTC 6x6, 7.5 MB with mipmaps **[est: 128 bits per 36 pixels = 3.56 bits per pixel]**. At 1024 x 1024 it is four times that, about 30 MB a card. Meta recommends ASTC. **[docs]** [Meta, Unity mobile performance](https://developers.meta.com/vr/documentation/unity/unity-mobile-performance-intro)

### 5. Motion from a single still without a prompt

- Generative Image Dynamics predicts a spectral volume (16 frequencies) that converts to "a sequence of time-varying 2D displacement maps", supports seamless loops by a guidance term, and was trained on 3,015 real videos of "trees, flowers, candles, and clothes". It degrades with "thin moving objects or objects with large displacements". **[docs]** [paper](https://arxiv.org/html/2309.07906v3), [project page](https://generative-dynamics.github.io)
- The project page links no code. **[docs]** An official release is **[unverified]**; I found none.
- The output form suits a shader: 16 sinusoids per pixel from a small coefficient texture. **[est]** But the paper renders with a learned feature-splatting network, not a plain warp; a plain warp of line art leaves stretched lines. **[est]**
- Eulerian Motion Fields: one static flow field for "flowing water and billowing smoke", looping by blending forward and backward flows; the page links no code. **[docs]** [project page](https://eulerian.cs.washington.edu/)
- 3D Cinemagraphy: code released (Apache 2.0); masks and motion hints are drawn by hand for the controllable mode; the README describes photos only. **[docs]** [repo](https://github.com/xingyi-li/3d-cinemagraphy)
- Text2Cinemagraph: code released (MIT); it generates the image from text and covers water; it handles painted styles only because it generates a realistic twin of its own image. **[docs]** [repo](https://github.com/text2cinemagraph/text2cinemagraph). It does not take an existing drawing as designed. **[est]**
- None of these is shown on comic art. **[docs]** (absence in the sources above)

### 6. Effect layers that touch no drawing

What it looks like: rain or dust between the depth layers, a glow that breathes on a candle, embers.

- Inputs: weather and time of day are attributes of the setting **[docs, local]**; a light position per frame is one more vision call, about 0.13 USD an episode at the pipeline's existing 0.0043 USD per box **[est: 30 x 0.0043]**.
- Meta: "Avoid overlapping alpha-blended geometry (e.g., dense particle effects) and full-screen post processing effects"; "Keep alpha blended transparency to a minimum"; "don't use grabpass in a shader". **[docs]** [Meta, Unity mobile performance](https://developers.meta.com/vr/documentation/unity/unity-mobile-performance-intro)
- Consequences **[est]**: sparse particles confined to the panel are fine; fog as stacked full-panel quads is the expensive case; heat haze needs a screen grab and is the one effect Meta's list rules out; bloom and vignette should be an additive quad or part of the panel shader, not a post effect.
- VFX Graph on Quest 3: Unity's requirements page was not read in full. **[unverified]** [VFX Graph requirements](https://docs.unity3d.com/Packages/com.unity.visualeffectgraph@17.0/manual/System-Requirements.html). The built-in particle system avoids the question. **[est]**
- Failure: rain over an indoor frame, a glow on the wrong object, particles over a face or a balloon. A reviewer call on a rendered frame can catch placement. **[est]**
- Flicker has a health limit: "Do not create purposely flickering content. High-contrast, flashing, or rapidly alternating stimuli can trigger photosensitive seizures". **[docs]** [Meta, Rendering best practices](https://developers.meta.com/vr/resources/bp-rendering). A candle flicker must be slow and low in contrast; a lightning flash needs a cap on rate and brightness. **[est]**

### 7. Motion outside the panel, in the room

- Meta's Passthrough Relighting sample shows a point light "projecting highlights onto the scene planes and volumes" and virtual shadows on real surfaces, through an MRUK shader with a URP single-pass version. **[docs]** [Meta, Passthrough Relighting](https://developers.meta.com/vr/documentation/unity/unity-passthrough-relighting)
- The assets exist: a light record per place, a hero light on a prop, a relit proxy of the real surface, a graded passthrough, a painted view behind the walls **[docs, local]**. A flicker, a storm flash, weather particles in the walls' view and spatial audio events add no model call. **[est]**
- Whether a moving room with a still panel gives a sense of life: I found no study or guidance on this. **[unverified]** Meta's comfort page does note that some objects emit light that "shines onto the floor and ceiling, highlighting its position in the room". **[docs]** [Meta, Comfort](https://developers.meta.com/horizon/design/comfort/)
- Risks: the same flicker rule as above, larger here because the room fills the periphery, where "people are more sensitive to flicker" **[docs]** [Meta, Rendering best practices](https://developers.meta.com/vr/resources/bp-rendering); and motion at the edge of vision pulls the eye off the panel. **[est]**

### 8. Timing only

- Mark Waid on Thrillbent: the swipe lets creators "more tightly control what the reader sees and when they see it"; motion comics and voice-over "take away my ability as a reader to absorb the story at the pace I'm absorbing it". **[docs]** [CBR](https://www.cbr.com/sdcc-mark-waids-thrillbent-tutorial/)
- That Marvel's Infinite Comics and Thrillbent took the reveal technique from Balak's turbomedia comes from a search summary of a USC text I did not open. **[unverified]** [Timeframing](https://scalar.usc.edu/works/timeframing/stepwise-time-in-born-digital-comics)
- The pipeline already has this: the clock sets when each panel, frame and balloon appears; the reader reveals each balloon at its start time; a wordless box may be held 2-8 s. **[docs, local]**
- Waid's objection applies in part: here the clock and the voices set the pace, not the reader. **[est]**
- Cost and runtime: none. Failure: a reveal order that follows a wrong reading order (84 of 86 right according to the project's session notes, not re-measured here). **[unverified]**

### What could not be verified

- Current Veo, Kling, Luma and Hailuo prices on the vendors' own pages (only fal's and Runway's reseller prices were read). The Wan 2.5 price of 0.05 USD/s came from a search summary only.
- Any measurement of how current image-to-video models preserve hand-drawn line art.
- Talking Head Anime and LivePortrait on non-anime comic faces.
- Official code for Generative Image Dynamics and Eulerian Motion Fields (none found).
- Image-to-video RGBA weights (TransPixar, Wan-Alpha) as of today.
- Wan 2.2 or LTX on a 12 GB GPU.
- How many videos Quest 3 can decode at once, and the layout of Unity's transcoded alpha video.
- VFX Graph support on Quest 3.
- Any guidance or study on animating the surroundings while a panel stays still, or on scripted motion inside a world-locked panel.
- Which of the two local statements about the erase (whole card painted, or a band only) is current.

---

# Part C. Cheap tricks on a rigid card

Added 2026-11-10, after the owner asked for more rule-based animations than the speaker accent. Playable examples of the designed set: `pipeline/.data/out/motion_demo/index.html` (not in the repo).


Researched 2026-11-10. Pixel values assume a 1200 px wide panel. "Band" is the 10 to 20 px of paint behind each card.

Marks: **[docs]** the number was read in the source. **[est]** my number, reasoned from the sources. **[unverified]** I could not read the primary source.

### Three geometric rules that decide most rows

These are my reasoning, not from a source.

1. **Scaling a card up never uncovers the band.** The card only covers more. The risks of a scale-up are overlap with a neighbour or a balloon, and clipping at the frame window.
2. **Shifting, shrinking, squashing and rotating do uncover it.** A squash of 3% on a 400 px tall card pivoted at its base drops the top by 12 px. A 1° tilt about the base moves the top 7 px sideways. Budget: at most 5 to 6 px of exposed band, about half the narrowest band.
3. **A card that touches its frame edge is cut there.** Pivot it on that edge. Never shift it away from the edge and never let it break the frame: the cut would show.

### Table of tricks

| # | Trick | What moves | Recipe | Signals | Risk under the hard limits | Source |
|---|---|---|---|---|---|---|
| 1 | Pop on line start | Speaker card | Scale 1.00 → 1.04 → 1.00 in 250 ms, ease-out, pivot at base (or at the touched edge). Ship engines go far bigger: TyranoScript `talk_anim=zoom` uses rate 1.2 | "This one speaks now" | Safe for the band. 20% would cover neighbours, so 3 to 5% | [est] from [Tyrano](https://tyrano.jp/tag/) [docs] 1.2 |
| 2 | Hop | Speaker card | Up 5 px and back, 200 ms total, ease-out up, ease-in down. Tyrano offers `talk_anim=up/down` | Energy, a start of speech | Uncovers 5 px at the base. Not for edge-touching cards | [est]; trick [docs] [Tyrano](https://tyrano.jp/tag/) |
| 3 | Held step forward | Speaker card | Scale 1.03 (2D) or a few mm toward the viewer (headset), in over 225 ms, out over 195 ms, held for the line | Who holds the floor | In a headset the nearer card shows more parallax, so the band is uncovered sideways when the head moves. Keep small. Slow, so not "rushing" | [est]; timings [docs] [Material 1](https://m1.material.io/motion/duration-easing.html) |
| 4 | Dim the listeners | Other cards | Brightness to 60% over 200 to 300 ms, back when they speak. Alternative: blur 2 | Same as 3, with no geometry at all | None for the band. One slow luminance change is not a flash | [docs] [Tyrano](https://tyrano.jp/tag/) `brightness_value` 60, `blur_value` 2 |
| 5 | Overshoot and settle (follow-through) | Any pop | Use a "back" ease: overshoot about 10% of the travel, then settle. Ren'Py ships `easein_back`, `elastic`, `bounce` warpers | Weight; the card is not a UI tile | Elastic or bounce repeats read as nervous. One overshoot only | [docs] warpers exist: [Ren'Py](https://www.renpy.org/doc/html/transforms.html); amount [est] |
| 6 | Stretch (no squash) | Speaker card | Height +3%, width −1.5% for 80 ms at the top of the pop, then back | Elasticity | Width loss uncovers about 2 px per side on a 250 px card. A squash phase would uncover the top: skip it. Art visibly deforms above about 4% | [est] from the volume rule, [12 principles](https://en.wikipedia.org/wiki/Twelve_basic_principles_of_animation) |
| 7 | Anticipation dip | Speaker card | Start 100 ms before the balloon: scale 0.99, then the pop | Prepares the eye for the pop | A shrink: 1% of 400 px = 4 px at the top. Never more | [est]; principle from same |
| 8 | Lean | Speaker card | Rotate at most 1° about the base toward the listener, 250 ms, hold, return | Address, intimacy, threat | 7 px at the top of a 400 px card. Forbidden for edge-touching cards | [est] |
| 9 | Jolt | Speaker card | Jump 4 px, hold 2 frames (about 33 ms at 60 fps), jump back. No easing | Surprise, a start | Within the band. Fine in a headset: small object, no glide | [est] |
| 10 | Shake on a shout | Speaker card | 3 swings of ±4 px, about 275 ms in all, each swing weaker. Ren'Py `hpunch` is ±15 px, `vpunch` ±10 px, 0.10 s per swing, 0.275 s total, on the whole screen | Loudness | Ren'Py's 10 to 15 px is for a full screen with nothing behind it. On a card, more than 5 px shows the band | [docs] [Ren'Py source](https://raw.githubusercontent.com/renpy/renpy/master/renpy/common/00definitions.rpy); card amount [est] |
| 11 | Decaying shake | Card or frame content | Amplitude = trauma², trauma falls from 1 to 0. Bevy's example decays 0.5 per second | Shake that dies off like a real knock | Same as 10. Stop within 300 ms | Bevy, after Eiserloh's GDC 2016 talk [unverified in the talk itself](https://bevy.org/examples/camera/2d-screen-shake/) |
| 12 | Kick away from the source | Frame content, or listeners | 4 px displaced away from the shouter, then eased back in 200 ms | Force with a direction | Band, on the listeners' far side | Nijman: shake "slightly in the opposite direction of the player's gunfire" [docs via](https://www.gamedeveloper.com/design/vlambeer-co-founder-shares-advice-on-building-better-action-games); px [est] |
| 13 | Flinch | Other cards | 4 px away from the shouter, 80 ms after the shout begins, back over 300 ms | Reaction; overlapping action | Uncovers the band on the shouter's side | [est] |
| 14 | Hit-stop | Everything in the frame | On an impact sound effect, hold all motion for 100 to 130 ms, then shake. Street Fighter 6's guide example is 8 frames (133 ms); SF2 about 10 frames | The blow landed | None. The voice keeps playing, so only pictures freeze | [docs via search] [Capcom](https://game.capcom.com/cfn/sfv/column/131545?lang=en), [critpoints](https://critpoints.net/2017/05/17/hitstophitfreezehitlaghitpausehitshit/) |
| 15 | Frame shake on impact | Content inside one frame | Tyrano `[quake]`: time 300 ms, count 5, vmax 10 px. Naninovel `@shake`: 3 shakes, 0.15 s, vertical. Use ±5 px, inside a fixed window | Impact | Cards move together, so no band shows. Headset: keep the frame border and the room still | [docs] [Tyrano](https://tyrano.jp/tag/), [Naninovel](https://naninovel.com/guide/special-effects) |
| 16 | Punch-in on a shout | Content inside one frame | Scale 1.00 → 1.03 in 150 ms, back in 300 ms, around the speaker | Sudden emphasis | Scaling up inside a fixed window uncovers nothing. Above about 3% it starts to rush at the viewer | [est] |
| 17 | Slow push-in | Content inside one frame | Scale 1.00 → 1.03 across the whole line, linear | Growing tension, a held beat | The safest camera move. One frame at a time only | [est]; "zooms, pans, limited animation" are the motion-comic staples ([reviews](https://scalar.usc.edu/works/timeframing/watchmen-motion-comic)) |
| 18 | Active frame highlight | Other frames | Dim to 60% over 300 ms | Reading order | None | [est], value borrowed from row 4 |
| 19 | Frames enter in sequence | Frames | Fade 225 ms each, in place. No travel | Reading order, timing | Apple advises a fade over a visible move | [docs] [Apple HIG](https://developer.apple.com/design/human-interface-guidelines/motion), [Material 1](https://m1.material.io/motion/duration-easing.html) |
| 20 | Balloon entrance by kind | Balloon | Speech: cut or 100 ms fade. Shout: scale 0.9 → 1.05 → 1.0 in 200 ms. Thought: dissolve 500 ms (Ren'Py's `dissolve` default) | Tone of voice | A uniform scale of the whole balloon also scales the lettering for 200 ms. If limit 4 forbids even that, fade only | [docs] 0.5 s [Ren'Py](https://www.renpy.org/doc/html/transitions.html); rest [est] |
| 21 | Sound-effect lettering entrance | The lettering as one rigid object | Scale in from 0.9 with one overshoot, 150 ms, then share the frame shake | Loudness | Same note on limit 4 | [est] |
| 22 | Card entrance | A card | Fade and scale 0.97 → 1.0 in 225 ms | Arrival | **Breaks limit 2**: before it enters, the plain patch shows. Only possible if the whole frame enters with it | [est] |
| 23 | Breaking the frame | Speaker card | Lift the clip while the card is forward | Importance; comics' own device | Only for cards that do not touch the frame edge (rule 3) | Device named in [MediaSmarts](https://mediasmarts.ca/digital-media-literacy/general-information/visual-media/comics/expression-and-storytelling-comics) |
| 24 | Beat hold | Everything | Nothing moves for a silent beat. No idle loop | A pause; weight | None | McCloud's silent panel, [unverified, read secondhand] |
| 25 | Postcard freeze | The frame | At the end of a strong beat: hold, and shift the colour grade (warmer, softer) over 400 ms | "This moment matters" | The original repaints the drawing. A grade is the only no-drawing version | Dezaki's "postcard memories" [docs] [Wikipedia](https://en.wikipedia.org/wiki/Osamu_Dezaki); grade [est] |
| 26 | Layer parallax (2D preview) | Backdrop against cards | Backdrop drifts 3 to 4 px against the cards over the line | Depth | A card moving against its backdrop uncovers the band: cap at 5 px. In the headset the head already does this | Naver's parallax [docs] [JoongAng](https://www.koreajoongangdaily.com/lifestyle/webtoon-artists-get-special-effects-help-from-naver/10463021); px [est] |
| 27 | Stagger | All of the above | One thing starts at a time, 40 to 80 ms apart: card, then balloon, then listeners | Order; avoids a "everything twitched" look | None | [est] |

### Sources and the numbers I relied on

**Game feel.** Nijman's talk is reported as "30 minor tweaks", including shake "slightly in the opposite direction of the player's gunfire". A fan recreation lists camera lerp, screenshake, knockback, hit pause and recoil. I found no primary numbers for his hit pause or kick. *Juice it or lose it*: the demo's own settings file has a 0.7 s tween-in, shake power 0.5 and a freeze (hit-pause) setting, all off by default ([Settings.as](https://raw.githubusercontent.com/grapefrukt/juicy-breakout/master/src/com/grapefrukt/games/juicy/Settings.as)). Hit-stop: Capcom's example is 8 frames; critpoints says it "gives the eyes a few frames to confirm" the hit. Warning from practitioners: "Too much, and you'll shake the zen right out of the player", and offer a shake slider ([dev.to](https://dev.to/selfish_dev/the-art-of-screen-shake-33bi)). Swink's *Game Feel* was not readable.

**Visual novel engines.** Ren'Py source: `vpunch = Move((0, 10), (0, -10), .10, bounce=True, repeat=True, delay=.275)`, `hpunch` with 15 px, `dissolve = Dissolve(0.5)`, `fade = Fade(.5, 0, .5)`, move and ease families 0.5 s, `zoomin` 0.5 s from 0.01. Ren'Py has no built-in speaker highlight; a community pack adds "a small zoom and darkening of the sprite" ([pack](https://wattson.itch.io/renpy-auto-highlight)). TyranoScript builds it in: `talk_focus` = brightness or blur, listeners at brightness 60, blur 2; `talk_anim` = up, down or zoom, zoom rate 1.2. Naninovel: speaker highlight "usually by tinting or scaling"; `@shake` count 3, duration 0.15, amplitude 0.5, vertical. So dimming listeners is a standard, shipped convention, at about 60%.

**Limited animation and anime.** Limited animation lists "cycled animations" and still characters ([Wikipedia](https://en.wikipedia.org/wiki/Limited_animation)). Dezaki: "split screen, stark lighting", Dutch angles, and pastel freeze frames he called "postcard memories". Impact frames are "usually monochromatic … drawings hidden within sequences" ([Sakuga Blog](https://blog.sakugabooru.com/glossary/)): they need new drawing and they flash, so they are out twice. Needing no new drawing: camera shake, pan or slide over a held drawing, slow zoom, freeze, split screen.

**Motion comics.** The form "is manipulated with zooms, pans, limited animation, and special effects". Critics' complaints: "limited and stiff", art that is "ALWAYS in motion", "too frenetic to follow", and "the viewer has little control beyond pausing the playback" ([Scalar](https://scalar.usc.edu/works/timeframing/undermining-comics-with-time), [Gizmodo](https://gizmodo.com/5032273/why-motion-isnt-the-future-of-comics)). Lesson: motion at events only, stillness between.

**Twelve principles.** Usable on a rigid card: anticipation (row 7), slow in and out (all easing), follow-through as one overshoot (row 5), overlapping action as delay between cards (rows 13, 27), secondary action (the balloon after the card), timing, staging (rows 4, 18), exaggeration (row 23). Squash and stretch only half: "an object's volume does not change", so any stretch costs width.

**Webtoon effects.** Naver's 2015 editor: vibration ("when a villainous character shoots a rifle"), flicker for emphasised dialogue, parallax (up to 12 layers in one scene), scroll-driven growth. Flicker breaks limit 5.

**UI motion.** Material 1: 300 ms typical on mobile, 225 ms entering, 195 ms leaving, "transitions that exceed 400ms may feel too slow"; motion is "more natural … when acceleration and deceleration occur asymmetrically". NN/g: 100 to 500 ms; ease-out for most; "far more common for animations to be too long than too short"; frequent animations should be shorter and subtler ([NN/g](https://www.nngroup.com/articles/animation-duration/)).

**Comfort.** Apple, visionOS: "Avoid showing objects that oscillate in a sustained way", especially "around 0.2 Hz"; "avoid displaying motion at the edges of a person's field of view"; "consider giving people a stationary frame of reference"; for large objects lower the contrast; "consider using fades when you need to relocate an object"; "make motion optional". Meta: "avoid using depth on text components as it can make them harder to read" ([Meta](https://developers.meta.com/horizon/design/comfort/)). WCAG: no more than three flashes in any one second ([W3C](https://www.w3.org/WAI/WCAG21/Understanding/three-flashes-or-below-threshold.html)).

### Tricks that were not on the first list

- Dim or blur the listeners (row 4). The cheapest and safest speaker cue.
- Hop instead of scale (row 2).
- Hit-stop before a shake (row 14).
- Decaying shake and directional kick (rows 11, 12).
- Slow push-in across a line (row 17).
- Beat hold and postcard freeze (rows 24, 25).
- Sound-effect lettering entering as one rigid object (row 21).
- Layer parallax drift for the 2D preview (row 26).
- Stagger, and entering slower than leaving (rows 27, 3).
- A motion level setting, including off (Apple, and the shake-slider advice).

### Items on the first list that sources warn against or that break a limit

- **Card popping in (entrance)** breaks limit 2. The plain patch shows until the card arrives.
- **"Others slightly back"** in the step forward is a shrink. It uncovers the band on every listener. Dim them instead.
- **Squash** uncovers the top band and deforms the art. Keep the stretch half only.
- **Anticipation dip** is a shrink: 1% at most.
- **Lean and flinch** uncover the band on one side: 1° or 4 px at most, never on edge-touching cards.
- **Breaking the frame** is wrong for any card that touches its frame edge.
- **Balloon pop with overshoot** scales the lettering for a moment. Decide whether limit 4 allows a uniform scale.
- **Frame shake and punch-in** in the headset: move the content inside a still border, never the panel or the room. Punch-in at most 3%.
- **Any idle "breathing" loop** (common in motion comics, period 3 to 5 s) sits at 0.2 to 0.33 Hz, the band Apple names as the most sensitive. Do not loop. Use one-shot motions.
- **Shake length**: nothing sustained. Engines ship 275 to 300 ms.
- **Constant motion** is the main complaint about motion comics. Most of each line should be still.

---

# Part D. The animation budget, as a committee decided it

2026-11-10. The owner asked for a budget of animation, spent on the catalogue of Part C, decided by an adversarial committee. Four seats argued two rounds from the same brief and the same measurements of one episode (pepper-carrot-39: 90 balloons in 7 min 12 s; 52 speech, 15 shout, 20 sound effect, 3 thought): a comics editor, a game-feel and visual-novel director, a perception and headset-comfort scientist, and a pipeline and runtime engineer. The chair's own draft (loudness points; a step forward on every change of speaker) was rejected by all four in the first round. What follows is what they converged on, with each dissent. None of it is measured on readers; every seat said so.

## The budget

- **Unit: one motion per line, on one target.** A motion's start is what pulls the eye, once, however small the motion (all four). Nothing is priced by loudness.
- **Size.** At most one motion at a line's start. At least 8 s between two motions of a frame's content (majority). No motion is held: everything ends within about half a second (three seats; the director wanted a held step capped at 4 s).
- **Density is the one open quantity.** The majority rules move 34 of 90 lines (20 pops, 7 cuts, 7 impacts); with one more condition (a pause of at least 1 s before a spoken line) they move 24 (10 pops). Five voiced lines of this episode have no recording and so get nothing; counting them as if recorded gives 39 and 26. The editor and the scientist want at most 30; the director wants no cap; the engineer wants a rule, not a quota. So both versions are built, to be compared by eye and then in the headset.

## How it is spent

| Balloon | What fires | Conditions | Seats |
|---|---|---|---|
| Thought | Nothing | | all |
| Speech | `pop` on the speaking card (103 %, back in 450 ms) | The speaker differs from the previous line's; the frame holds two or more characters; the card covers at most 25 % of the panel. Sparse version: also a pause of at least 1 s before the line | Trigger: all. `pop` over `step`: three (director dissents). The pause: the scientist; the editor leans to it |
| Shout | A scale-only cut (103 % for 90 ms, no glide) on the first shout of a run; later shouts of the run nothing; a run re-arms after 8 s | Card at most 25 % of the panel | First only: three (the director wants later shouts to keep a cue). The cut: majority; the editor preferred `pop` |
| Sound effect | One `impact` shake of the frame's content (peak 4 px, 350 ms); effects at the same instant are one | At least 8 s since the last one | All on merging; majority on 8 s; the scientist alone wanted it off on frames over 40 % of the panel |
| Any balloon with no speaker, no frame or no audio | Nothing | | majority |

Free, in both versions: the balloon appears first and the motion starts 60 ms later; balloons fade in (120 ms, a thought 600 ms) and are never scaled. A frame fading in at its start was approved by three seats and is held back until the case the engineer found is fixed (the clock's active frame can differ from the frame the speaker's card sits in).

**Out.** By all four: `stretch`, `hop`, `lean`, `flinch`, `activeframe`, the shout balloon pop. By majority: `step`, `shake`, `dim`, `pushin`, `punch`, `breakframe`, `jolt` with its 4 px lift.

## Why, in the seats' own arguments

- **Why the chair's draft fell.** 58 of 70 spoken lines change speaker, so a cue on every change moves two lines in three, and with 0.6 s between lines one card would sink as the next rose (editor). Its 10 s cap never bound on quiet motions (editor) and could not be checked by a script (engineer). It priced a slow push-in as loud although it has no perceptible start, and a step as quiet although it holds for up to 15 s (director).
- **Why `pop` and not `step`.** A step is the only cue that holds: on the 1 line in 40 with the wrong speaker it keeps the wrong card forward for the whole line, where a pop is over in 450 ms (engineer). Capping the hold only moves the problem: the release becomes a second motion in the middle of the line (editor; the scientist conceded). In the headset a card that really comes forward uncovers the band sideways under head motion (scientist).
- **Why only where a frame holds two or more characters.** In a frame with one character (29 of 66) the cue says nothing and trains the reader to ignore it (scientist; all conceded).
- **Why nothing acts on the other characters.** A wrong speaker inverts the meaning: dimming the listeners darkens the character who is talking (engineer; the director conceded).
- **Why large cards do not move.** 18 of 70 speaking cards cover over a quarter of their panel; moving one moves the picture, and half strength reads as a fault rather than a gesture (director, scientist).
- **Why the sound effect is the safest spend.** It is the one motion that depicts what is heard, the kind the evidence favours, and it has no speaker to get wrong (scientist).

## What would change the decision

Each seat named the same test: one episode in the headset in several versions (still, sparse, majority, and the director's fuller version), asking who said each line (including lines whose speaker the pipeline got wrong), how many accents the reader noticed, and a discomfort rating before and after. Two cheaper checks come first: both versions side by side in the 2D preview, and the uncovered band of a card moved in depth, computed from the geometry.

## What the format lacks for this (the engineer's reading)

Balloon kinds in the schema have no sound effect; a track's `loop` defaults to true; a track targets a layer, not a frame's content; the export writes no animations yet. The two motions on cards need only `scale`; the impact needs a way to address a frame's content.
