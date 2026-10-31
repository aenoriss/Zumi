# Character identification across a whole comic: state of the art and alternatives — 2026-10-20

Research date: 2026-10-20. Three parallel web passes of about 4 minutes each: comic-specific work, adjacent domains with encoder choice, and vision-language model (VLM) approaches. Nothing was downloaded or run.

This note extends `comic-speaker-attribution-2026-10.md` and does not repeat what that note covers: Magi v1–v3, Magiv2 constraint naming, Re:Cognize, CoMix, Manga109Dialog, CCIP, DASS, and the VGG animated-film bank.

How to read the evidence:
- Numbers are copied from papers (abstract or HTML).
- **[unverified]** marks an item taken only from a search snippet or from an abstract without numbers.
- Every statement about webtoons is reasoning, not measurement. No webtoon identity dataset or paper exists.

Zumi baseline, measured on 38 boxes and 65 lines (`compare_understand.py`, deleted 2026-10-30 and in the git history; `experiments/score_understand.py`). Same-speaker pairs, precision / recall:

| Pairs | Maverick, one box at a time with a text cast | Opus 5.5 (3.1 ¢/box) |
|---|---|---|
| Within a box | 0.92 / 0.85 | — |
| Other box, same scene | 0.84 / 0.62 | — |
| Other scene | 0.69 / 0.42 | 0.99 / 0.98 |

Magiv3 superframe identities: pairwise precision 0.64–0.71.

## Bottom line

1. **No VLM keeps identity reliably over a page, let alone an episode.**
   - Matching characters on one comic page of about 13 panels: Gemini 2.5 Pro 83%, GPT-5-mini 66%, GPT-4o 49%, Qwen2.5-VL-7B 49% (AI4VA-FG; 4-way choice, chance 25).
   - Counting a character's appearances on a page: at most 27%.
   - Episodes are about 100 panels.
2. **Prompt tricks show small or no measured gains; specialised identity components show large ones.**
   - Reference images in the prompt: 0.63–0.69 matching (MM-ID). No same-model with-versus-without delta exists for a cast sheet.
   - Face-crop visual prompts did not help and often hurt (VLM2-Bench).
   - An identity bank feeding a VLM tripled naming: 10.0 → 30.1 (VGG animated films).
   - Identity training: +20 to +40 points (IIR-VLM 52.6 → 90.4; ComicsPAP 54 → 93; RARL 49 → 71).
3. **No comic, manga or webtoon re-identification method with numbers has appeared in 2025–26 beyond the covered list.** Semantic Scholar citers of Magi (23), Magiv2 (15), CoMix (23) and Soykan (8) were checked. Re:Cognize has no citers yet.
4. **The choice of encoder matters more than the bank design.** Character identity is an instance task. On Met instance retrieval (GAP), CLIP-style encoders are weak at it (measured):

   | Encoder | Met GAP |
   |---|---|
   | DINOv3-7B | 55.4 |
   | DINOv2 | 44.6 |
   | SigLIP 2 | 13.9 |
   | PE-Core G | 10.6 |

5. **Key the series bank on the face or head; add the body only within a scene.**
   - In comics, aligned face+body fusion reaches top-1 97.3 against 22.4 unaligned, and MAP 78.7 against 70.4 for a ResNet-50 baseline (Soykan).
   - Clothes-changing re-id stays at 40–70% Rank-1 even at SOTA (CCAF on PRCC and LTCC), so outfit features break across episodes. This is measured on photos; applying it to webtoons is reasoning.
6. **Measure the choice step on gold identities.** Given ground-truth identities, an LLM speaker step reached only 63.6%, against 75.7% for a supervised speaker model (2509.15253: black-and-white manga, LLM unnamed). Zumi's within-box 0.92 / 0.85 suggests a stronger chooser here, but this has not been measured on gold identities.

**Verdict (reasoning from the above):** run identity as a separate local pass. Let it give episode-wide clusters and series-wide names. Keep Maverick for what it measurably does well: reading text and linking lines to characters inside one box. The designs that work in adjacent domains (AutoAD-Zero, StoryTeller, the VGG animated-film work) all use this split.

## 1. VLMs on identity: measured

| Work | Task | Result | Takeaway |
|---|---|---|---|
| AI4VA-FG / RARL ([2511.06490](https://arxiv.org/html/2511.06490v1)) | "Same character across panels?" on a full page, plus counting | Char-ID: Gemini-2.5-pro 83.09, 2.5-flash 68.38, GPT-5-mini 66.18, InternVL3-9B 59.56, GPT-4o 49.22, Qwen2.5-VL-7B 49.26. Counting: best 27.03. Region-aware RL: Qwen 7B char-ID 49.26 → 71.32, but counting 8.11 → 2.70 | The closest benchmark to our task; even one page is hard |
| ComicsPAP ([2503.08561](https://arxiv.org/html/2503.08561)) | Character coherence: which character says the text (2-way, chance 50) | Zero-shot Qwen2.5-VL 7B 54.55, 72B 53.84. LoRA 3B and 7B both 93.01 | Binding text to speaker is cheap to learn and near chance zero-shot. Code and LoRA weights public |
| VLM2-Bench ([2502.12084](https://arxiv.org/html/2502.12084)) | Cross-image "same person?" grouping (chance 25, human 91.17) | Qwen2.5-VL-7B 69.0, Claude-3.7 60.0, GPT-4o 47.0, Gemini-2.0-flash 21.0 | Face-crop prompting and chain of thought did not help |
| MM-ID / IDA-VLM ([2407.07577](https://arxiv.org/html/2407.07577v1)) | Named reference images in the prompt (≤ 8 images, includes animation) | Matching: Gemini-pro 0.687, GPT-4V 0.627, IDA-VLM 0.716. Locating a named character: IDA-VLM 0.821 vs GPT-4V 0.244 | The closest test of a cast sheet: modest, and no baseline without references |
| IIR-VLM ([2601.14188](https://arxiv.org/html/2601.14188)) | In-context instance recognition with a re-id expert encoder | Person: Gemini 2.5 Pro 75.4, Qwen2.5-VL-7B 73.6, IIR-VLM 92.6. The expert encoder adds only +1.8; training adds most of the gain (3B: 52.6 → 90.4) | Training, not prompting, closes the gap |
| arXiv [2603.01950](https://arxiv.org/html/2603.01950v1) | Hallucination audit of comic page descriptions | Wrong-character rate 29–100%; Qwen2.5-VL 45.16%; dialogue misattributed 25.81% | The failure mode |
| "Do Video-LLMs Actually Watch?" ([2607.11078](https://arxiv.org/abs/2607.11078)) | Swaps a character's name in the question | Answers change only 4–31% of the time **[unverified]** | VLMs fake identity tracking using cues such as gender |
| Re:Verse ([2508.08508](https://arxiv.org/abs/2508.08508)), Re:Cognize | Manga reading and naming | VLMs "struggle with character consistency"; < 1.2% naming on Re:Zero **[unverified]** | Same direction |

## 2. Hybrids: a specialised identity component feeding a language model

| Work | Design | Result | Transfer to Zumi |
|---|---|---|---|
| VGG animated films ([2509.12204](https://arxiv.org/html/2509.12204v1)) | Per-film DINOv2 bank (8 exemplars per character; OWLv2+SAM 2 tracks), with a linear head, feeding Qwen2-VL | Name AP: InsightFace 45.3 → DINOv2 bank 75.3 → adapted 81.8. Naming in audio description (CRITIC): no labels 10.0 → InsightFace 18.9 → bank 30.1 | The best analogue: drawn characters, where face models fail |
| AutoAD-Zero ([2407.15850](https://arxiv.org/abs/2407.15850)) | Cast bank of name + face feature, matched by cosine above a threshold; colour-coded circles drawn on the frame, names given in the text, the VLM describes | No naming figure retrieved **[unverified]**. Training-free | Set-of-mark template: Maverick picks a mark, not a name |
| StoryTeller ([2411.07076](https://arxiv.org/html/2411.07076v3)) | Global ids from audio diarisation; a 7B MLLM names them from cast photos; votes combined across the whole video | ID accuracy 0.791 (without video 0.430; without global decoding 0.759) | Global voting per cluster: +3.2 points |
| Comics speech ([2509.15253](https://arxiv.org/html/2509.15253v1)) | ResNet-50 per comic (about 40 crops per main character) plus an LLM with plot summaries | Character top-1 62.9%. Speaker 64.8% (predicted ids), 63.6% (gold ids); supervised 75.7%; hard cases 20.5% | Ceiling for a weak per-series classifier; the choice step was the bottleneck |
| RAP, CVPR 2025 ([2410.13360](https://arxiv.org/abs/2410.13360)) | Key-value concept database, multimodal retriever, MLLM trained to choose among retrieved candidates | No comic numbers | The same shape as "bank → LLM chooses", with a model trained for it. Code, data and models public |
| PAGE ([2610.13840](https://arxiv.org/abs/2610.13840)) | Opus 5.5 codes each character once from a crop sheet | Gender agreement 95.5%; **no identity metric** | Uses crop sheets, but identity is assumed, not measured |
| M3-Agent ([2508.09736](https://arxiv.org/abs/2508.09736)), MM-Narrator ([2311.17435](https://arxiv.org/abs/2311.17435)) | Entity memory built from face and voice ids, or a re-id memory bank | No isolated identity figure **[unverified]** | Memory pattern only |

## 3. Encoders for drawn characters

| Encoder | Measured evidence | Licence | Fits 12 GB? (reasoning) |
|---|---|---|---|
| **DINOv3** ([2508.10104](https://arxiv.org/abs/2508.10104)) | 7B: Met GAP 55.4 (DINOv2 44.6). Linear probe IN-R 91.1, Sketch 71.3 (DINOv2-g 81.1 / 65.4). Distilled IN-R: ViT-L 88.1, ViT-H+ 90.0. Third party ([Toronto visual-abstraction probe](https://www.cs.toronto.edu/~ary/visual-abstraction/)): ViT-B instance R@1 59.8 at the line-drawing end (MAE 0.4) | Meta custom; gated on Hugging Face | ViT-L (0.3B) and ViT-H+ (0.8B) yes; 7B no |
| **CCIP** caformer_b36 ([HF](https://huggingface.co/deepghs/ccip_onnx)) | Colour anime same-character F1 0.941 (threshold 0.213); OPTICS cluster score 0.957 | openrail | Yes (ONNX) |
| **PE-Core** ([2504.13181](https://arxiv.org/abs/2504.13181)) | Zero-shot IN-Sketch: L 73.4, G 76.5; IN-R 95.2 / 96.5. Met GAP 10.6 from the final layer | Apache-2.0 | G (1.9B) yes |
| SigLIP 2 | IN-Sketch: L 75.5, g 77.4; Met 13.9 | Apache-2.0 | Yes |
| MetaCLIP 2 | No evidence on stylised art; licence CC-BY-NC **[unverified]** | — | H yes |
| WD EVA02-L tagger v3 | Closed vocabulary of Danbooru character names (characters with at least 600 images). Macro-F1 0.477 over all tags | Not checked | Yes. Only a prior for famous casts such as Tower of God |

Identity metrics from story-visualisation work:
- ViStoryBench CIDS ([2505.24862](https://arxiv.org/abs/2505.24862)) uses Grounding DINO crops, ArcFace for realistic characters and CLIP for stylised ones. Agreement with humans: Spearman 0.676, Kendall 0.498.
- DreamBench++ ([2406.16855](https://arxiv.org/abs/2406.16855)) uses GPT-4o as an identity judge: 79.6% human agreement, +54% over DINO and CLIP.
- StoryWeaver ([2412.07375](https://arxiv.org/abs/2412.07375)) says, without numbers, that CLIP-I cannot separate look-alike characters.

The reasoning from these: automatic identity scores are good for shortlisting candidates, not for making the decision.

## 4. Comic-specific work found in this pass

None of the following measures cross-page identity with numbers:
- AI4VA ([GitHub](https://github.com/IVRL/AI4VA)) is a dataset of two colour Franco-Belgian series with character-identification labels. Whether the labels persist across pages is **[unverified]**. It is a possible held-out colour test.
- Hierarchical knowledge graphs for visual narratives ([2506.10008](https://arxiv.org/abs/2506.10008)) maps character appearances on a hand-annotated subset of Manga109, with no numbers. It is a possible format for a story-level character graph.
- DiffSensei / MangaZero ([2412.07589](https://arxiv.org/abs/2412.07589)) has Magi ids that are consistent only within a page; the authors call them "relatively inaccurate".
- OregairuChar ([2511.05263](https://arxiv.org/abs/2511.05263)) trains a closed-set detector per character on anime episodes, with no metrics in the abstract.
- OAM-ReID, an occlusion-aware manga re-id method known only from the survey [2409.09502](https://arxiv.org/abs/2409.09502), and an IEEE MultiMedia 2025 comic speaker paper are paywalled and not verified.
- Checked, with no identity contribution: Manga2Animate, ManGo, ComicScene154, and Manga109-v2026 (which revises text annotations only).

## 5. What this means for Zumi (reasoning)

Proposed pass, each step drawn from the work above:

1. **Detect** characters with Magiv3 boxes (already run and free). Fall back to a SAM 3.1 "person" prompt. Crop the **head** and the **body** separately.
2. **Embed** with three candidates and test them against each other on our crops: DINOv3 ViT-L, CCIP, and PE-Core with a sweep over its intermediate layers. Add a linear head per series on top of the winner, as the VGG work does (+6.5 AP there).
3. **Cluster each episode transductively**:
   - Two characters in the same box cannot be the same person (cannot-link).
   - Merge with high precision first.
   - Use head and body similarity within a scene, head only across scenes.
4. **Match clusters to a series bank**:
   - The bank is keyed on heads and seeded once per character.
   - It grows only through Re:Cognize's page-group gate.
   - Outfit exemplars stay per episode and are never merged into the series bank.
5. **Show the clusters to Maverick as marks** (AutoAD-Zero):
   - Numbered, colour-coded boxes on the panel.
   - A text line such as "#3 = C7, also in boxes 2, 9, 14".
   - Maverick links lines to marks and proposes names. Each cluster's name is then decided by a vote across the episode (StoryTeller).

Test plan, cheapest first:
1. Label the Magiv3 character crops in the 38 boxes, about 60–80 crops (local, free).
2. Score the encoders on P@1, AMI, and naming accuracy with one exemplar per character plus an "other" slot. Repeat with 3 different exemplar choices; Magiv2's spread across exemplar choices was 0.727 → 0.874 (local, free).
3. Run Maverick with **gold** cluster marks, then with **predicted** marks: about 4 ¢ per run of 38 boxes. This isolates the choice step (the 2509.15253 warning).

Risks:
- Chibi and comedy deformation, frequent in True Beauty, will probably break every encoder (unmeasured).
- Unnamed extras share the "other" slot.
- Bank drift over a series: Re:Cognize names identity maintenance as the main bottleneck **[unverified snippet]**.

Practical:
- DINOv3 is gated on Hugging Face, so it needs an access request like SAM 3.
- ViT-L is about 1.2 GB in fp32, and the disk had about 1.2 GB free. Deleting the 1.6 GB SAM 3 mirror would cover it.

## Sources

Listed inline. The main ones: [2511.06490](https://arxiv.org/html/2511.06490v1) · [2503.08561](https://arxiv.org/html/2503.08561) · [2502.12084](https://arxiv.org/html/2502.12084) · [2407.07577](https://arxiv.org/html/2407.07577v1) · [2601.14188](https://arxiv.org/html/2601.14188) · [2509.12204](https://arxiv.org/html/2509.12204v1) · [2407.15850](https://arxiv.org/abs/2407.15850) · [2411.07076](https://arxiv.org/html/2411.07076v3) · [2509.15253](https://arxiv.org/html/2509.15253v1) · [2410.13360](https://arxiv.org/abs/2410.13360) · [2508.10104](https://arxiv.org/abs/2508.10104) · [2504.13181](https://arxiv.org/abs/2504.13181) · [2308.09096](https://ar5iv.labs.arxiv.org/html/2308.09096) · [2406.09198](https://arxiv.org/abs/2406.09198) · [2505.24862](https://arxiv.org/abs/2505.24862) · [deepghs/ccip](https://huggingface.co/deepghs/ccip_onnx)
