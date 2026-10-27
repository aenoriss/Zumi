# When does a VLM reviewer on top of SAM 3 pay off? Literature for the Zumi reviewer test — 2026-10-24

Research date: 2026-10-24. Literature only. Nothing was run.

This note does not repeat `comic-speaker-attribution-2026-10.md` or `comic-character-identity-sota-2026-10.md`. Those cover Magi v1–v3, CoMix, COO in outline, and VLM identity benchmarks.

How to read the evidence:
- Numbers are copied from the paper's abstract, HTML or PDF.
- **[unverified]** marks a claim taken from a search snippet or from memory that could not be checked against the primary page.
- **[reasoning]** marks an inference from the cited work to Zumi. No paper tests a VLM reviewer on webtoon masks.

The setup being tested: SAM 3.1 masks, then Claude Haiku 5.5 sees a set-of-mark (SoM) image and proposes drop / merge / split / enlarge / crowd / missing. SAM re-segments a crop. The same LLM confirms each change with a single-mask yes/no. Up to 3 rounds.

## Bottom line

1. **H1 (base rate) is supported, with one refinement.** Measured LLM verifiers reject a large share of correct outputs: GPT-4 rejected 95.8% of correct graph colourings. Correcting outputs that were already right costs 0–11 points even when the error location is given. So a filter on a high-precision base loses. The refinement: Zumi's confirmation step judges *changes*, so its costly error is false acceptance of a bad change, not false rejection. VLMs lean towards "yes".
2. **H2 (semantic beats spatial) is supported, but the line is "gross vs boundary", not "semantic vs geometric".**
   - In SAM 3's own data engine, an AI check of *presence and exhaustivity* added +7.2 cgF1, while an AI *mask-quality* check added +1.1.
   - Gemini 3 Flash spots merged, cut-out and wrong-object masks (F2 74–80) but almost never spots dilated or eroded boundaries (F2 0.6–4).
3. **H3 (self-correction needs external signal) is supported.** But in Zumi, SAM supplies the *action*, not a *signal of correctness*. The accept/reject decision is still the LLM grading its own proposal, which is the intrinsic case the literature finds weak.
4. **H4 (people in-distribution, lettering out) is half supported.**
   - Supported: comic sound effects are measurably hard even for supervised detectors (Hmean 67.8).
   - Not found: any published breakdown of SA-Co by "people" vs "text". SA-Co's annotation guidelines do include text masks.
   - The catch: stylised SFX are also hard for the *reviewer* to read and locate, so recall gains there have a ceiling.
5. **H5 (selective review) is plausible but has no direct evidence for VLM-over-SAM.** Cheap signals locate errors in classification and medical segmentation. SAM's own IoU head is a weak selector.

## H1. A verifier pays only when base error on judgeable types exceeds the verifier's own error

| Evidence | Numbers | What it shows |
|---|---|---|
| Stechly, Valmeekam, Kambhampati, [arXiv 2402.08115](https://arxiv.org/abs/2402.08115) (GPT-4 as verifier, Table 2) | False-negative rate (correct solutions rejected): Game of 24 20.7%, Graph Colouring 95.8%, Blocksworld 15.5%, Mystery BW 97.1%. False-positive rate 0.5–18.6% | LLM verifiers can be badly asymmetric. Accuracy alone (72–87%) hides it |
| Same paper, Table A1 | Accuracy, standard / LLM self-verify / sound verifier: Game of 24 5 / 3 / 38; Graph Colouring 16 / 2 / 37; Blocksworld 40 / 55 / 87 | A self-verify loop lost to the base in 3 of 4 domains. A sound external verifier won in all 4 |
| Tyen et al., ACL Findings 2024, [arXiv 2311.08516](https://arxiv.org/abs/2311.08516) | GPT-4 finds the mistake step 39.8–52.9% of the time. Backtracking with the *oracle* location: originally-correct traces −0 to −11.4 points; originally-wrong traces +18 to +44 | Finding errors is the bottleneck. Corrections applied to correct outputs do real harm, so the net depends on the base error rate |
| Stroebl, Kapoor, Narayanan, ICLR 2026, [arXiv 2411.17501](https://arxiv.org/abs/2411.17501) | With imperfect verifiers, false positives cap accuracy. The best number of samples is often < 10 once false positives cost more than abstaining | Repeated attempts plus a leaky check plateau, then decline |
| MQ-RAVSBench, [arXiv 2602.03892](https://arxiv.org/html/2602.03892v1) (MLLM judging masks, image setting, Seen split) | Gemini-3-Flash labels *perfect* masks as perfect with F2 only 20.6. Qwen2.5-Omni-7B 88.3, but it "tends to accept most candidate masks" | The same MLLM is either a harsh judge (rejects good masks) or a lenient one (accepts bad ones). Neither is neutral |
| POPE, EMNLP 2023, [arXiv 2305.10355](https://arxiv.org/html/2305.10355v3) | Share of "yes" answers to object-presence questions: LLaVA 95–99%; MiniGPT-4 / InstructBLIP 55–69% | Yes/no visual checks carry model-specific yes-bias. Claude Haiku 5.5's bias is unmeasured |

**Worked arithmetic [reasoning].** Take 100 lettering masks at base precision 0.95, so 5 are wrong.
- Say the reviewer catches 60% of the wrong ones (3) and wrongly drops 5% of the correct ones (4.75).
- Net: −1.75 masks.
- The same reviewer on a base at precision 0.75 removes 15 wrong masks and 3.75 correct ones, a net gain.

The breakeven is: base error × reviewer recall on errors > (1 − base error) × reviewer false-action rate. This must hold *per action type*, because each action has its own error profile (see H2).

**Refinement for Zumi [reasoning].** Each change passes two LLM gates: the proposal, then the confirmation.
- A *harmful proposal* survives when the confirmation says yes to a bad change: a false acceptance, which yes-bias makes likely.
- A *helpful proposal* is lost when the confirmation says no.
- So measure the confirmation step's accept rate separately on helpful and harmful changes. If the two rates are close, the confirmation adds cost and no protection.

## H2. VLMs: reliable at "what is it", weak at "where exactly"

| Evidence | Numbers | What it shows |
|---|---|---|
| SAM 3 paper, [arXiv 2511.16719](https://arxiv.org/html/2511.16719), Table 8d (SA-Co/Gold) | SAM 3 54.0 cgF1 → + exhaustivity/presence AI verifier 61.2 → + mask-quality AI verifier 62.3; human 72.8. The verifiers are fine-tuned Llama 3.2. MV transferred zero-shot to new domains; EV needed some in-domain labels | The closest analogue to Zumi's reviewer. Most of the gain came from the *is the concept here, are all instances found* judgement. Little came from judging mask quality. Both verifiers were trained on human accept/reject labels, not prompted |
| MQ-RAVSBench, [arXiv 2602.03892](https://arxiv.org/html/2602.03892v1) (Gemini-3-Flash, F2 by error type) | Wrong object (Full_neg) 80.4, Merge 74.0, Cutout 77.8–79.0; Dilate 0.6–3.1, Erode 3.4–4.0. IoU estimate RMSE 0.33 | MLLMs catch *gross* mask errors (wrong object, two objects fused, a missing chunk). They are blind to boundary over- and under-segmentation. This maps onto Zumi's drop/merge (judgeable) vs enlarge (not judgeable) |
| "VLMs are blind", [arXiv 2407.06581](https://arxiv.org/abs/2407.06581) | 4 VLMs average 58.07% on 7 trivial geometry tasks (best: Claude 3.5 Sonnet 77.84%; human ≈ 100%). Failures concentrate where shapes overlap or sit close. Linear probes show the encoder has the information | Overlapping, adjacent marks (crowds, bubbles touching characters) are exactly where judgements fail |
| BLINK, ECCV 2024, [arXiv 2404.12390](https://arxiv.org/abs/2404.12390) | Humans 95.70%, GPT-4V 51.26%, Gemini 45.72%; random ≈ 38% | Perception tasks (correspondence, relative depth, multi-view) sit near chance for frontier VLMs |
| Set-of-Mark, [arXiv 2310.11441](https://arxiv.org/html/2310.11441) | GPT-4V + SoM: RefCOCOg REC 86.4 (plain GPT-4V 25.7). Gains depend on the proposals: GT masks add +14.5 mIoU. Reported limits: marks clash in dense scenes, the person query returned the backpack's mark, numbers confuse on number-heavy images, 100-image subsets | SoM turns localisation into *choosing a label*, which VLMs do well. Mark-to-region confusion in dense layouts is a known failure. Numeric marks next to lettering are a predictable confusion source [reasoning] |
| MangaVQA / MangaLMM, [arXiv 2505.20298](https://arxiv.org/html/2505.20298v2) | End-to-end manga OCR (box + text) Hmean: GPT-4o 0.0, Gemini 2.5 Flash 0.0, Claude Sonnet 4.5 0.0, Qwen2.5-VL-7B 0.9; fine-tuned MangaLMM 71.5. Its misses "are mostly onomatopoeia" | Generalist VLMs cannot *localise* manga text in coordinates. The fine-tuned model's residual errors are SFX. Reading inside a given crop is a different, easier task; no number for it was found |
| SAM 3 Agent, [arXiv 2511.16719](https://arxiv.org/html/2511.16719) | ReasonSeg val gIoU: agent + Qwen2.5-VL-7B 62.2, + Llama 4 Maverick 68.5, + Qwen2.5-VL-72B 74.6, + Gemini 2.5 Pro 77.0; prior SOTA 65.0. SAM 3 alone "is not designed for long referring expressions" | An MLLM over SAM 3 helps where the gap is *semantic* (which concept to ask for). Benefit scales with the MLLM: a 15-point spread across backbones. No ablation of its mask-checking step was found **[unverified: Appendix G not read]** |
| MLLM-as-a-Judge, ICML 2024, [arXiv 2402.04788](https://arxiv.org/abs/2402.04788) | Pairwise comparison agrees with humans; absolute scoring and batch ranking diverge notably | A "before vs after" pair is a more reliable confirmation format than a lone yes/no on one mask |

**Refinement [reasoning].** The split that matters for Zumi's actions:
- **Judgeable (gross):** "this mask is not lettering / not a character" (drop), "these are two things fused" (split, if visually obvious), "this is missing a large piece" (enlarge, gross case), "there is an uncovered SFX/caption here" (missing), "this is a crowd".
- **Not judgeable (boundary/correspondence):** a few-pixel enlarge or shrink, which numbered mask covers which overlapping figure, part-whole in overlaps (a hand that belongs to someone else).

## H3. Self-correction without an external signal degrades; external feedback fixes it

| Evidence | Numbers | What it shows |
|---|---|---|
| Huang et al., ICLR 2024, [arXiv 2310.01798](https://arxiv.org/html/2310.01798v2) (GPT-3.5, Table 3) | Standard → self-correct round 1 → round 2: GSM8K 75.9 → 75.1 → 74.7; CommonSenseQA 75.8 → 38.1 → 41.8; HotpotQA 26.0 → 25.0 → 25.0. Earlier gains "vanish when oracle labels are not available" | Intrinsic self-correction is flat to sharply negative. On CommonSenseQA it halved accuracy. Changed answers go correct → wrong more often than wrong → correct |
| Kamoi et al., TACL 2024, [arXiv 2406.01297](https://arxiv.org/abs/2406.01297) | Survey finding: no reviewed work shows success with prompted self-feedback, except in exceptionally suited tasks. It works with *reliable external feedback* or *large-scale fine-tuning* | The two conditions under which a reviewer works |
| Liao et al., CVPR 2025, [arXiv 2404.06510](https://arxiv.org/abs/2404.06510) | VLM semantic grounding: noise-free binary feedback gives > +15 accuracy, iteratively. Out of the box VLMs "struggle to self-correct". With an *automated* binary verifier, up to +5 | The VLM version of Huang/Kamoi. The gap between +15 (oracle) and +5 (automatic verifier) is the price of an imperfect checker |
| CRITIC, ICLR 2024, [arXiv 2305.11738](https://arxiv.org/abs/2305.11738) | Tool-interactive critique improves QA, maths and toxicity. Authors conclude external feedback is essential | Tools give the signal. The no-tool ablation numbers were not read **[unverified]** |
| Stechly et al. (above) | Self-verify loop lost to the base in 3 of 4 domains; sound verifier won in all 4 | Same pattern with planning |

**Mapping to Zumi [reasoning].**
- SAM re-segmentation and the written segmentation rules are external, but only partly a *signal*. SAM executes the change; it does not say whether the change was right.
- The confirmation is the same LLM grading its own proposal. That is intrinsic verification, describe-then-decide notwithstanding. Chain-of-thought did lower one verifier's false-negative rate (Game of 24: 20.7% → 4.3%, Stechly Table A2), but did not close the gap to a sound verifier.
- Signals that *are* external and cheap: SAM's score on the new mask, area change, overlap with other masks, whether a rule is violated (bubble mask crossing a character), and agreement between SAM runs.
- Expect rounds 2–3 to add little and to show some oscillation: a change in round 2 undone in round 3, as Huang's answer flips.

## H4. SAM 3's distribution: people near the centre, comic lettering far out

| Evidence | Numbers | What it shows |
|---|---|---|
| SAM 3 paper, [arXiv 2511.16719](https://arxiv.org/html/2511.16719) | SA-Co/HQ: 5.2M images, 4M noun phrases, 52M masks. SA-Co/SYN: 38M phrases, 1.4B masks. 15 external datasets (EXT). 12 media domains, "from web-scraped data to... art, food, or driving". SA-Co/Gold cgF1: Crowded 60.3, Sports Equip. 63.0, Food 56.1, SA-1B 53.8, MetaCLIP 46.9, Wiki-Common 42.9. Out-of-scope RF100-VL: 15.2 AP, below gDino-T 15.7 | No per-category (people vs text) count is published. "Crowded" scenes (mostly people [reasoning]) score *above* average. Long-tail concepts score lowest |
| SAM 3 annotation guidelines (Table 20, same paper) | Mask verifiers have an "Accept as text" rating for masks covering text | Text *is* a SAM 3 concept. Comics, manga or drawn onomatopoeia are not named among the sources **[unverified: Table 25 of mining datasets not read]** |
| COO, ECCV 2022, [arXiv 2207.04675](https://arxiv.org/abs/2207.04675) (Table 2) | 61,465 SFX polygons in 10,602 Manga109 pages; 2,261 split-SFX links. *Supervised* detection: MTS v3 P/R/H 69.8 / 65.9 / 67.8; ABCNet v2 67.7 / 64.5 / 66.0. The same detectors reach about 83–85 on MSRA-TD500. Failures: small SFX (25×28 px on 1654×1170) and text-like art detected as SFX. Manga109 has 5.8 SFX per page | SFX is hard even with in-domain training. Both misses (small, curved, split) and false positives (text-like strokes) are documented |
| MangaVQA (above) | 61K of 209K Manga109 text instances are onomatopoeia (29%). The fine-tuned model's misses are mostly SFX | Same conclusion, and it applies to the VLM side too |
| Manga109 text AP ([arXiv 2005.04425](https://arxiv.org/pdf/2005.04425)) | SSD512 text AP 0.918 **[unverified: from search snippet]** | Dialogue text in balloons is comparatively easy |

**Refinement [reasoning].** H4 predicts a high *base error* on SFX. But H2 and MangaVQA predict the *reviewer* is also weak on stylised SFX, which it must notice, read and locate. Review pays off where base error is high **and** the reviewer can judge. That makes three regimes for lettering:
- **Bubbles and captions:** low base error. Expect review ≈ 0 or negative.
- **Big, legible SFX that SAM missed:** high base error, judgeable. Expect review positive.
- **Small, faint or decorative SFX, and text-like strokes:** high base error, not judgeable. Expect review to add false positives.

People sit near the centre of photo data. Webtoon characters are drawn, so SAM's base error on *non-human or chibi* characters is unknown. Search found no SAM evaluation on comics or illustrations.

## H5. Selective review: cheap signals vs recall of fixes

| Evidence | Numbers | What it shows |
|---|---|---|
| Geifman and El-Yaniv, NeurIPS 2017, [arXiv 1705.08500](https://arxiv.org/abs/1705.08500) | Top-5 ImageNet error of 2% guaranteed (p = 0.999) at about 60% coverage, using the model's own confidence | A cheap confidence signal ranks errors well enough to trade coverage for risk in-distribution |
| Mozannar and Sontag, ICML 2020, [arXiv 2006.01862](https://arxiv.org/abs/2006.01862) | Joint classifier plus rejector trained from expert decisions, with a consistent surrogate loss | The right gate depends on where the *expert* (here, the reviewer) is right, not only where the base is unsure. That needs labelled reviewer outcomes, which the Zumi test will produce |
| FrugalGPT, [arXiv 2305.05176](https://arxiv.org/abs/2305.05176) | Cascade matches GPT-4 with up to 98% cost reduction, or +4% accuracy at equal cost | Escalating only uncertain items can keep most of the benefit at a fraction of the calls |
| Zenk et al., Medical Image Analysis 2024, [arXiv 2406.03323](https://arxiv.org/abs/2406.03323v2) | Failure-detection benchmark over 5 datasets: pairwise Dice between ensemble predictions is a strong, simple baseline. Evaluated with risk-coverage | *Disagreement* between runs is a good cheap failure signal for masks. SAM analogue: different prompts or crops giving different masks [reasoning] |
| SAMRefiner, [arXiv 2502.06756](https://arxiv.org/pdf/2502.06756) | Choosing among SAM masks by SAM's predicted IoU falls well short of choosing by true IoU (DAVIS-585) **[unverified: from search snippet]** | SAM's own score is a weak gate on its own |
| RUAC, [arXiv 2605.10603](https://www.alphaxiv.org/abs/2605.10603) | SAM uncertainty stops tracking error under domain shift **[unverified: preprint, snippet only]** | Gates calibrated on photos may misfire on webtoons |

**Refinement [reasoning].** Gate on signals the test shows are correlated with *accepted-and-correct* fixes. Candidates:
- low SAM score
- prompt or crop disagreement
- extreme area
- rule violations (lettering mask overlapping a character mask)
- a lettering-detector region with no SAM mask

Expect a gate to keep most lettering "missing" fixes at a fraction of the cost. For characters the gate should rarely fire, and skipping review there should lose little.

## Predictions for the Zumi test

Each prediction is falsifiable on held-out panels with per-action labels (helpful / harmful / neutral, judged against ground truth masks). Magnitudes are guesses from the evidence above, not measurements. **[reasoning]**

**Confirmation check (both tasks)**
- **P1.** The confirmation step accepts most proposals (> 80%). Its accept rate on harmful changes is within 15 points of its accept rate on helpful ones, so its AUROC for separating them is < 0.7. Basis: POPE yes-bias; MQ-RAVSBench lenient models.
- **P2.** Rejected proposals that were actually helpful are rarer than accepted proposals that were harmful. False acceptance is the dominant confirmation error. If instead the check rejects many good changes (the Gemini-like harsh mode), H1's false-rejection arithmetic applies directly.

**Lettering**
- **P3.** Most of the net benefit comes from "missing" on large, legible SFX and captions that SAM skipped. Lettering recall rises. Precision rises less, or not at all.
- **P4.** "missing" also introduces a new false-positive class: text-like art strokes, background signage, small or faint SFX boxes that SAM then segments badly. This mirrors COO's documented confusions. Expect harmful "missing" proposals mainly where the SFX is small (< ~2% of panel area) or decorative.
- **P5.** "drop" on speech bubbles and captions is net ≤ 0, because base precision there is already high. Any benefit comes from dropping non-lettering masks (art mistaken for text), not bubbles.
- **P6.** "enlarge" on lettering gives median ΔIoU ≈ 0 (|Δ| < 0.02), with both signs. The VLM cannot see boundary errors (MQ-RAVSBench dilate/erode F2 < 5), so the change is driven by SAM's re-segmentation, not by the reviewer's judgement.
- **P7.** "merge" of split SFX fragments helps when the fragments are legible as one word, and is near chance otherwise. Basis: COO link prediction needs reading.
- **P8.** Net lettering benefit is positive and concentrated in recall. If the test shows a net lettering gain driven by precision fixes instead, H2 is refuted for this setup.

**Characters**
- **P9.** Net benefit is near zero: within ±1 matched character per 10 panels, or the F1 change within its noise band. SAM's base error is low on human figures, and the reviewer's errors concentrate where characters overlap.
- **P10.** "split" and "merge" on overlapping or touching characters are harmful at least as often as helpful. These are part-whole and which-mask-is-which judgements, the "VLMs are blind" and SoM dense-scene failure.
- **P11.** "crowd" is the most reliable character action (a semantic judgement). It helps rule conformity, crowds as one mask, more than raw IoU.
- **P12.** Useful character "missing" proposals, if any, are non-human, chibi or partly visible characters. Missed ordinary human figures should be rare in the base output.

**Rounds and cost**
- **P13.** Round 1 holds ≥ 80% of the net benefit. Rounds 2–3 are net ≈ 0 and show reversals: a mask changed and then changed back, or a merge followed by a split of the same pair. Basis: Huang flat or negative later rounds; Stroebl's plateau.
- **P14.** Per useful change, lettering costs less than characters, because characters yield fewer useful changes for similar call counts. A gate on the cheap signals listed under H5 keeps most lettering fixes and skips most character calls.

**What would refute the hypotheses**
- Characters gain as much as lettering: refutes H4 as stated.
- Enlarge actions improve boundary IoU consistently: refutes H2's boundary claim for Haiku 5.5.
- Rounds 2–3 keep adding net gains: weakens H3, and suggests SAM plus the rules act as a stronger external signal than assumed.
