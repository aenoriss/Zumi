# Speaker attribution and character identity in comics: what the literature says — 2026-10-19

Research date: 2026-10-19, about 12 minutes of reading. Method: arXiv/CVF HTML papers read directly (Magi 2401.10224, Magiv2 2408.00298, Magiv3 2503.23344, Manga109Dialog 2306.17469, zero-shot speaker prediction 2404.13993, CoMix 2407.03550, Re:Cognize 2609.34032, animated-movie characters 2509.12204); licences and last push from the GitHub API on the research date; DINOv3 and SAM 3 licence files read raw; model cards on Hugging Face. Items known only from search snippets, abstracts without numbers, or pages that refused the fetch are marked **[unverified]**. Nothing was downloaded or run. Every "this will/won't work for webtoons" statement is reasoning, not measurement, and says so.

Zumi context: SAM 3.1 already segments bubbles, captions and SFX per panel; Llama 4 Maverick attributes speakers at 86 % on 65 labelled lines (Muse Spark 1.3: 89 %). The literature numbers below are on **black-and-white manga or Golden Age comics, scored per page**, so they are not directly comparable to a per-line score on colour webtoon panels.

## Executive summary

1. **The detect → embed → bank → geometry → LLM shape is what the best published systems converge on**, just split differently. Magiv2 = per-crop embedding + per-page must-link/cannot-link edges + one exemplar per named character + an "other" slot, solved as a MILP; speaker = learned text–character and text–tail heads. The zero-shot LLM paper (Li et al. 2024) = LLM proposes speakers, image classifier propagates names, repeat. Nobody has published exactly "geometry candidates → LLM picks", but every ingredient has a number behind it.
2. **Raw DINOv2 is a weak manga character encoder.** On PopManga Test-S ground-truth crops, DINOv2 gets P@1 0.485 and AMI 0.070; CLIP 0.584 / 0.105; Magi's trained crop encoder 0.842 / 0.489 (Magi, Table 3). On western comics the picture flips: CoMix reports DINOv2 AMI 0.29, above Magi, because Magi does not leave the manga domain. Colour webtoons are probably closer to the second case (reasoning, untested). Plan a cheap adaptation: the VGG animated-movie paper fine-tunes only a linear head on DINOv2 ViT-g with 8 exemplars per character and goes from 75.3 to 81.8 name AP.
3. **One good reference crop per character is nearly enough; the bank's maintenance is the hard part.** Re:Cognize (NeurIPS 2026): one seed per identity recovers almost the full closed-set ceiling; letting the bank grow from its own matches puts the wrong character on 62–89 % of additions and both right and wrong matches score cosine > 0.7. Magiv2: swapping an arbitrary exemplar for a good one lifts chapter naming from 0.727 to 0.874.
4. **Constraints beat clustering.** Magiv2 chapter naming: K-means 0.380 → constraint optimisation with predicted per-page edges 0.727 → with true edges 0.799 (Test-S). The cheapest constraint: two crops in the same panel are different characters.
5. **Geometry is a strong prior but caps out exactly where Zumi fails.** Closest character: R@#text 0.776 vs Magi 0.845 (PopManga). Manga109Dialog: frame-distance rule 71.5 %, scene-graph model 75.7 %, but only **30.7 %** when the speaker is not in the text's frame. Magiv2 says errors concentrate on **tailless** text; text-to-tail association itself is AP 0.98–0.99.
6. **Text-only LLMs and small open VLMs are poor at identity.** GPT-4 from dialogue alone: 43.6 % speaker accuracy on Manga109; with image fusion 51.8 %. Magiv2 notes text-only LLMs struggle with three or more candidate speakers. Re:Cognize cites ≤ 1.1 % character identification for Qwen2.5-VL-3B / InternVL3-14B / Ovis2-8B on chapter-length manga. Zumi's 86 % with a large VLM per panel is well above these, which argues for keeping the LLM as the chooser, not the identity store.
7. **Every strong comic-specific model is non-commercial or unlicensed** (Magi v1/v2/v3, Manga109Dialog code, CoMix, COO code, Re:Cognize code). Permissive building blocks: DINOv2 (Apache-2.0), DINOv3 and SAM 3 (Meta custom licences, royalty-free, no commercial bar, ITAR/military excluded), DASS detector code (Apache-2.0; weights licence unstated). Manga109Dialog and COO **annotations** are CC BY 4.0, but the Manga109 images are research-only (Manga109-s: 87 volumes cleared commercially by application).
8. **No webtoon-specific speaker or character-identity work, and no SFX-ownership work, was found.** SFX research covers detection and recognition only (COO, ECCV 2022). Magiv2 classifies text as dialogue vs non-dialogue (AP 0.99) but does not assign SFX to a source.
9. **No published evaluation of SAM 3 on comic characters was found.** Zumi already runs SAM 3.1, so a 20-panel check of "person"/"face"/"character" prompts is the fastest way to find out.

---

## 1. Speaker attribution in comics and manga

| Work | What it does | Inputs | Reported result (dataset, metric) | Code / weights licence | Relevance |
|---|---|---|---|---|---|
| **Magi** (Sachdeva & Zisserman, CVPR 2024) | One DETR-style model (ResNet-50) detects panels, text, characters; MLP heads score char–char (same identity, τ = 0.65) and text–char pairs; argmax speaker; < 0.4 confidence printed as ⟨?⟩ | Whole B&W page; character crops re-encoded by a 224 px MAE-initialised ViT | Speaker R@#text **0.845 / 0.831** (PopManga Test-S/U) vs closest-character **0.776 / 0.766**. Clustering AMI 0.657 (Test-S) | README: "academic research purposes only"; GitHub reports no SPDX licence | Geometry baseline gap (+7 pts) is the size of what a learned association adds. Lists sound effects and characterless panels as its low-confidence cases |
| **Magiv2** (ACCV 2024, "Tails Tell Tales") | Adds tail detection, text–tail head, dialogue/non-dialogue text classifier, and chapter-wide naming: crops embedded (12-layer ViT, SupCon loss), per-page edges become must-link/cannot-link, one exemplar per principal character plus an "other" slot at fixed cost η = 0.75, solved as MILP (CBC) | Pages + a character bank (one image per character) | Text–char AP **0.750** (Test-S) vs Magi 0.525. Text–tail AP **0.984**. Naming accuracy Test-S/U: K-means 0.380/0.422, iForest+K-means 0.510/0.494, constraints (predicted) **0.727/0.753**, constraints (true) 0.799/0.853, with "optimal" exemplars 0.874/0.877 | HF card: "personal, research, non-commercial, not-for-profit"; else contact author | Closest published analogue of the proposed design. Copy: the "other" slot with fixed cost, cannot-link within a page/panel, identity-level scoring (max-pool scores over boxes of the same identity) |
| **Magiv3** (ICCV 2025, "From Panels to Prose") | Florence-2 (DaViT, 768 px) fine-tuned for detection, OCR, association, and grounding caption phrases to character boxes | Image + task prompt | Char–char AMI 0.688/0.693/0.678 (PM-S/PM-U/M109) vs v2 0.675/0.665/0.646; text–char AP **0.724/0.733**, *below* v2; text–tail 0.991/0.986. Grounding F1 0.69 (PopCaptions) vs Florence-2 0.28 | Same non-commercial terms | A bigger multimodal model did not improve speaker association; grounding drops "significantly" in crowded panels |
| **Manga109Dialog** (Li, Aizawa, Matsui, ICME 2024) | 132,692 speaker-box↔text pairs on Manga109; scene-graph-generation model (MOTIFS etc.) plus frame (panel) features | Page, GT boxes (PredCls) or detected (SGDet) | R@#text total: short distance 63.4, frame distance 71.5, proposed **75.7**. **Easy** (speaker in same frame) 84.8; **Hard** 30.7. SGDet: 60.5. On eBDtheque the frame rule (80.3) beats the model (77.5) | Annotations **CC BY 4.0** (in `manga109/public-annotations`); code repo has no licence; images under Manga109 terms | The Easy/Hard split is the protocol to copy. Hard ≈ Zumi's off-panel and floating-line errors |
| **Zero-shot character id + speaker prediction** (Li, Hinami, Aizawa, Matsui, arXiv 2404.13993 v4) | GPT-4 predicts speaker names from dialogue (with LLM-made summaries and profiles, confidence 1–5); a per-comic ResNet-50 is fine-tuned on those pseudo-labels; scene-graph scores propagate; LLM re-asked with candidates; iterate | Dialogue text, GT body/text boxes, name list | Manga109 23-volume test: speaker 33.1 (K-means+distance) → 43.6 (LLM only) → **51.8** (iteration 2); character id 44.0. With true relations: 63.8 / 56.6. Fully end-to-end: 38.7 / 35.0 | Code licence not stated | Direct evidence that LLM + image identity beat either alone (+8 pts). Also: more iterations did not help (51.6 at iteration 3); labels leak to non-speaking characters in the panel |
| **CoMix** (Vivoli, Bertini, Karatzas, NeurIPS 2024 D&B) | Multi-task benchmark incl. speaker identification and re-id across 4 sources | Pages | Speaker R@#text (supp. Table 9): closest character avg **38.4**; Magi **27.9** (13.2 DCM, 13.1 eBD, 15.0 Comics, 57.2 PopManga). Re-id: DINOv2 AMI 0.29 | Repo licence NOASSERTION; eBDtheque non-commercial | Domain shift is brutal: Magi falls from 57 to 13–15 off manga. Main and supplementary tables disagree (0.68 vs 38.4) for the heuristic; treat with care |
| Emotion-aware speech for comics (Qian, Liang, Zhang, arXiv 2509.15253) | LLM attributes dialogue using detected characters and plot context, then TTS | Detections + text | No attribution accuracy on the abstract page; search snippet says it underperforms the Manga109 deep baseline on hard cases **[unverified]** | No code | Same pipeline idea as Zumi, no usable numbers |
| IEICE tech. report, March 2026 **[unverified]** (page refused fetch) | Feeds images, dialogue order and bounding boxes differently so an MLLM actually uses visual cues for manga speaker prediction | — | Snippet: existing MLLM methods "do not effectively exploit visual information" | — | Supports giving the LLM explicit numbered boxes rather than a bare image |
| DramaSR-LRM (Li et al., ICML 2026, arXiv 2607.02504) | TV dramas, not comics: a reasoning LLM gathers audio/text/visual evidence via tool calls | Video | Abstract: "significantly outperforms" baselines, biggest gain on short utterances; no numbers on abstract page | Code "will be" released, no licence | Pattern for "LLM chooses with tools", out of domain |

**Graph / scene-graph approaches**: Manga109Dialog and the zero-shot paper both use scene-graph generation for text–character edges; Magi/Magiv2 treat the page as a graph of pairwise edges with transitive char–char edges evaluated as clusters. No GNN-specific comic speaker paper with better numbers was found in this pass.

**Webtoon-specific**: none found (searched arXiv/web for webtoon + speaker/character/dataset).

## 2. Character re-identification and clustering

| Work | What it does | Reported result | Licence | Relevance |
|---|---|---|---|---|
| **General encoders on manga crops** (Magi Table 3, GT crops, per-page clustering) | DINOv2, CLIP, ZACI, AMFR vs Magi crop encoder | PopManga Test-S **P@1**: DINOv2 0.485, CLIP 0.584, AMFR 0.609, Magi crop-only 0.842, Magi full 0.888. **AMI**: 0.070 / 0.105 / 0.155 / 0.489 / 0.657. Manga109 face P@1: DINOv2 0.592, CLIP 0.626, Magi 0.856 | DINOv2 Apache-2.0 | Off-the-shelf DINOv2 is the weakest baseline on B&W manga. Caveat in the paper: baselines got a per-test-set tuned threshold, Magi a fixed one |
| **General encoders on western comics** (CoMix) | DINOv2 vs Magi for re-id | DINOv2 AMI 0.29, NMI 0.51, above Magi; CLIP benchmarked, numbers not in main table | — | Style matters more than model size; colour/western art favours general encoders |
| **DINOv2 + linear head, animated films** (VGG, arXiv 2509.12204) | Bank of top-10 cast × 8 exemplars from IMDb/Fandom, extended by web crawl filtered with DINOv2 similarity; DINOv2 ViT-g/14 with registers; only final linear layer fine-tuned per movie, InfoNCE τ = 0.07; top-3 cosine vote over 5 frames | CMD-AM name AP: InsightFace 45.3; DINOv2 no adaptation **75.3**; adapted **81.8**. Says raw DINOv2 "often struggle[s] to distinguish between visually similar characters" | Code via project page, licence not stated; method uses only DINOv2/OWLv2/SAM 2 | The closest recipe to Zumi's bank: few exemplars, colour stylised art, full-body crops (faces fail on non-human designs), a cheap per-title head |
| **Re:Cognize** (Baranwal et al., NeurIPS 2026, arXiv 2609.34032) | Open-set, sequential re-id benchmark: 4 protocols (closed-set, few-shot fixed gallery, online clustering, pre-seeded online growth) on PopCharacters, Manga109, Re:Verse (Re:Zero, 12 characters, 1,825 instances, 308 pages); ReCast = one running mean per character, accept a crop only if another crop in its page group is already committed to that character | Closed-set POPCharacters mAP / R-1: MagiV2 51.2 / 57.2, MagiV3 41.3 / 48.7, CLIP-based ReID5o 38.7 / 44.8, TransReID 37.4 / 40.6 (chance 33.1 mAP). One seed per identity ≈ ceiling. Naive self-growth: 62–89 % of additions wrong, R-1 −4. Page-group rule: additions 86.9 % correct, +3.3 to +6.5 R-1 (5 random seeds), +12.5 to +16.9 with first-appearance seeds | Code at `eternal-f1ame/Re-Cognize`, licence not stated; POPCharacters research-only | The most direct evidence for a per-series bank, and for gating its growth. DINOv2/SigLIP not among the 5 backbones |
| **Identity-aware SSL for comic re-id** (Soykan, Yuret, Sezgin, arXiv 2308.09096) | Face+body contrastive (SimCLR-style) embeddings | Abstract: beats face-only and body-only; no numbers on abstract page | No code found | Supports embedding face and body together. Datasets: 1M+ character instances; 3,000+ four-panel identity sequences |
| **CCIP** (deepghs) | Contrastive anime character similarity on single-character crops | Same/different F1 **0.941** (threshold 0.213); clustering score 0.895 (DBSCAN) / 0.957 (OPTICS) on its own test set | Model "openrail", library `imgutils` MIT; trained on Danbooru-derived `deepghs/character_index` (provenance not checked) | Strong anime baseline to compare DINOv2 against; not Meta, so a benchmark rather than the default |
| **DAF:re** (Rios et al. 2021) | Anime face recognition dataset | ~500k images, 3,000+ classes **[numbers from search snippet]** | Crowd-sourced from Danbooru **[unverified licence]** | Pretraining/eval data for faces only |

## 3. Character detection with permissive licences

| Model | Detects | Reported | Licence | Notes |
|---|---|---|---|---|
| **SAM 3 / 3.1** (Meta) | Any noun-phrase concept, masks + boxes | SA-Co benchmark; **no comic or manga evaluation found** | SAM License: royalty-free, no commercial bar; redistribute under same terms; ITAR/military excluded | Already in Zumi's pipeline. Test "person", "face", "character", "head" on ~20 panels and score recall by hand |
| **DASS** (Topal et al., IJCAI 2023) | Faces and bodies in drawings (YOLOX-based, self-supervised domain adaptation) | Manga109 body AP 87.98, face 87.88; DCM772 body 87.24, face 85.77; Comic2k body 76.00; Magiv2 Table 1: DASS Manga109 body 0.925 vs Magiv2 0.905 | Code **Apache-2.0** (pushed 2026-10-03); weights on Google Drive, **licence not stated**; trained partly on Manga109/iCartoonFace (research-only data) | Best permissive-code fallback; weights' commercial status needs an email |
| Magi / Magiv2 / Magiv3 | Characters, text, panels, tails | Magiv3 character F1 0.85/0.87 (PM-S/U) vs v2 0.81/0.83 | Non-commercial | Use only as an offline oracle for building eval labels |

## 4. Datasets with speaker or identity labels

| Dataset | Content | Size | Licence |
|---|---|---|---|
| Manga109 | 109 Japanese volumes; body/face boxes carry a per-volume character id and name | 10,602 double-page images (Manga109Dialog count) | Images research-only; Manga109-s: 87 volumes cleared for commercial use by application |
| Manga109Dialog | Speaker box ↔ text links, Easy/Hard | 132,692 pairs (111,959 Easy, 20,733 Hard), 9,904 annotated images | Annotations CC BY 4.0 |
| PopManga / PopManga-X | Test-S/U (seen/unseen series) pages; X adds tails, text–tail links, names, dialogue vs non-dialogue (13k / 7k texts) | ~2,000 test pages | Magi repo, no SPDX licence; research use |
| PopCharacters | Character bank: 11K+ characters, 76 series, 16K+ web thumbnails | 11.5K exemplars | "Research use only" (Re:Cognize appendix) |
| CoMix | Speaker links + identity clusters across DCM, eBDtheque, Comics, PopManga | 3.8k images, ~100 books, 30k text–character links, 33k clusters; val 466 images public, test via server | NOASSERTION; eBDtheque non-commercial |
| COMICS / Comics Text+ | Golden Age panels + OCR / text detection gold standard | 1.2M panels, 3,948 books | COMICS code MIT; Comics Text+ licence not found |
| Comic Character Instances / Comic Sequence Identity (Soykan) | Character instances; identity across 4-panel sequences | 1M+ instances; 3,000+ sequences | Not found |
| Re:Verse | Re:Zero manga identity benchmark | 12 characters, 1,825 instances, 308 pages | Not stated |
| COO | Manga onomatopoeia polygons, transcriptions, fragment links | Manga109-based | Annotations CC BY 4.0 |
| Webtoon speaker/identity dataset | — | **None found** | — |

## 5. Sound effects

- **COO** (Baek, Matsui, Aizawa, ECCV 2022): detection, recognition, and linking of split SFX fragments on Manga109. No ownership label.
- **Magiv2** dialogue vs non-dialogue text classifier, AP 0.990 (Test-S). Useful as a gate (SFX should rarely get a speaker), not as ownership.
- **Magi** lists sound effects among its low-confidence speaker cases.
- Manga109 text-detection mask dataset (Del Gobbo & Matuk Herrera 2020) treats SFX as a separate, harder class.
- **No work found that assigns an SFX to a character vs the environment.** Zumi will need its own labels; the cheapest rule set from the literature's geometry is: an SFX overlapping or touching one character's mask, or a vocal SFX (gasps, laughs) near a face, goes to that character; otherwise environment (reasoning, untested).

---

## Conclusions

### (i) Does the literature support detect → embed → bank → geometry → LLM?

Yes, with two corrections.

- **Supported.** One reference per character is close to the ceiling (Re:Cognize); constraint-based assignment with an "other" slot beats clustering by ~35 points of naming accuracy (Magiv2: 0.380 → 0.727); geometry gives ~72–78 % on its own (closest character, frame distance); LLM + image identity beats either alone (43.6 → 51.8). The LLM-as-chooser over numbered candidates is unpublished as such but consistent with the IEICE 2026 finding that MLLMs need explicit boxes to use visual evidence **[unverified]**.
- **Correction 1: don't use raw DINOv2 cosine as the identity decision.** On B&W manga it is the weakest encoder tested (P@1 0.485). On colour art, a linear head trained on the bank's exemplars took DINOv2 from 75.3 to 81.8 AP. Budget that step; compare against CCIP as a yardstick.
- **Correction 2: the bank must not grow from its own matches without a page-level check.** Re:Cognize measured 62–89 % wrong additions under naive growth.

### (ii) Permissive building blocks to try first

1. **SAM 3.1** "person"/"face" prompts for character masks (already licensed and running; comic performance unknown).
2. **DINOv2 ViT-L/14 or ViT-g/14 with registers** (Apache-2.0) on full-body crops, plus a per-series linear head trained with InfoNCE on bank exemplars. Try **DINOv3** next (custom Meta licence: royalty-free, no commercial bar, ITAR/military excluded, must ship the licence text).
3. **Assignment as constrained optimisation**: Hungarian or a small MILP (scipy / OR-Tools) with cannot-link within a panel and an "other" slot at a fixed cost, as in Magiv2.
4. **DASS** (Apache-2.0 code) as a detector fallback if SAM 3 misses characters; ask the author about weights.
5. **CCIP** (openrail) only as a non-Meta comparison baseline. **Magi v2/v3** only as an offline oracle for drafting labels, never shipped.

### (iii) Evaluation protocols worth copying

- Per-line speaker accuracy split **Easy/Hard** (speaker in the same panel or not; Manga109Dialog) and **tail/tailless** (Magiv2). Zumi's 65 lines should report all four cells; overall 86 % hides where the errors live.
- **Identity-level** speaker scoring: count a hit if the chosen box belongs to the right identity (Magiv2 max-pools over boxes of one identity).
- Identity: per-episode **AMI/NMI** for clustering plus **P@1 / MAP@R** for retrieval (Magi), and **naming accuracy with one fixed exemplar per character + "other"** (Magiv2). Re-run with 3 different exemplar choices; Magiv2's spread was 0.727 → 0.874.
- Re:Cognize **P2** (few-shot fixed gallery) and **P4** (pre-seeded growth) to test the bank across episodes 2…n.
- Score with ground-truth detections and end-to-end separately (Li et al.), so detector misses and attribution errors don't hide each other.

### (iv) Pitfalls the papers report

- **Look-alikes merged**: Magi's two brothers in similar checked clothing; Ice Age's two mammoths; clustering baselines group "similar looking, but distinct" characters (Magiv2).
- **Exemplar choice** swings naming by ~15 points; thumbnails from anime/live-action adaptations do not match the drawn style.
- **Off-panel speakers**: Hard split 30.7 % vs Easy 84.8 %; image-only methods fail when the speaker is not the nearest character or not in the panel.
- **Tailless text** carries most speaker errors; alternating dialogue with no visual cue is hard even for humans.
- **Unnamed characters**: Magiv2 cannot tell "unnamed 1" from "unnamed 2"; they share the "other" slot.
- **Appearance change** (costume, age, transformation) is untested in all of them.
- **Confidence is not calibrated**: right and wrong matches both score cosine > 0.7 (Re:Cognize).
- **LLM loops**: more iterations did not help and spread labels to non-speaking characters (Li et al.); text-only LLMs falter at ≥ 3 candidates (Magiv2).
- **Domain shift**: Magi speaker R@#text 57 % on manga, 13–15 % on western comics (CoMix). Nothing has been measured on webtoons.

## Sources

- Magi: https://arxiv.org/html/2401.10224v3 · https://github.com/ragavsachdeva/magi
- Magiv2: https://arxiv.org/html/2408.00298v1 · https://huggingface.co/ragavsachdeva/magiv2
- Magiv3: https://arxiv.org/html/2503.23344 · https://huggingface.co/ragavsachdeva/magiv3
- Manga109Dialog: https://arxiv.org/html/2306.17469v2 · https://github.com/manga109/public-annotations
- Zero-shot speaker prediction: https://arxiv.org/html/2404.13993v4
- CoMix: https://arxiv.org/html/2407.03550v2 · https://github.com/emanuelevivoli/CoMix
- Re:Cognize: https://arxiv.org/html/2609.34032v1 · https://neurips.cc/virtual/2026/poster/138878
- Animated-movie characters: https://arxiv.org/html/2509.12204
- Identity-aware comic re-id: https://arxiv.org/abs/2308.09096
- Emotion-aware comic speech: https://arxiv.org/abs/2509.15253
- DramaSR: https://arxiv.org/abs/2607.02504
- VLM comic hallucination benchmark (no speaker task found): https://arxiv.org/abs/2603.01950
- COO: https://arxiv.org/pdf/2207.04675 · https://github.com/ku21fan/COO-Comic-Onomatopoeia
- DASS: https://github.com/barisbatuhan/DASS_Det_Inference
- CCIP: https://huggingface.co/deepghs/ccip
- DINOv2 licence: https://github.com/facebookresearch/dinov2 (Apache-2.0) · DINOv3: https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md · SAM 3: https://github.com/facebookresearch/sam3/blob/main/LICENSE
- IEICE report (refused fetch): https://ken.ieice.org/ken/paper/20260318ScSZ/eng/
