# A trained model for character identity across boxes and episodes — 2026-10-31

Research date: 2026-10-31. One web pass over primary sources (papers, dataset cards, licence files, repos). Nothing was downloaded or run.

Conventions:
- Numbers are copied from the cited source.
- **[estimate]** marks arithmetic of mine on cited numbers. **[unverified]** marks what no primary source confirmed.
- Everything about webtoons and European comics is reasoning; no labelled identity set exists for them.

Updates `character-speaker-encoder-2026-10.md` (the v1 encoder design) and builds on `comic-character-identity-sota-2026-10.md`. It does not repeat them.

## What changed since 2026-10-20

1. **No speaker head.** The rule-based association (about 95% right, confidence 0.3–0.85 per link) is now an *input*. The line pointer, OFF-PANEL and NARRATOR tokens are gone. A speaker edge enters as an attention bias, and training corrupts it on purpose.
2. **Training data is Manga109-s, not Manga109.** It is the only part cleared for commercial use. PopManga and PopCharacters stay evaluation-only at most.
3. **The Magiv2 crop embedder leaves the product path.** It is the best manga encoder measured, but its weights are non-commercial.
4. **NLLB and SONAR are out.** Both are CC-BY-NC. Translation moves to MADLAD-400 or opus-mt (Apache-2.0).
5. **Text is weaker identity evidence in comics than in films.** Name-based rules fail the break-even test (below). Text goes in as soft features; it never becomes a rule.
6. **Training crops need masks.** Manga109 has only boxes, and our cards have the background removed. SAM is run on the Manga109 body boxes once.
7. **Colour is fused late.** Manga has no colour to learn from. A colour term is added to the edge weights at inference, with its weight fitted on webtoon labels.

## 1. Manga109-s and Manga109Dialog

**Volumes.** "87 of the 109 volumes have been newly approved for commercial use", released as Manga109-s ([manga109.org](http://www.manga109.org/en/)). Which 22 are excluded is not public: neither the site nor the Hugging Face card lists them **[unverified]**. The list arrives inside the archive (3.3 GB, `Manga109s_released_2026_05_21.zip`, [HF API](https://huggingface.co/api/datasets/hal-utokyo/Manga109-s)).

**Who may use it.** The Hugging Face card's table: universities doing academic work get Manga109; universities doing non-academic work, and companies doing anything, get Manga109-s ([card](https://huggingface.co/datasets/hal-utokyo/Manga109-s)). Access is a form: name, address, affiliation, purpose. It takes "2–3 days or a week". No academic email is needed, unlike full Manga109.

**Terms** ([manga109.org licence section](http://www.manga109.org/en/)):
- Permitted: machine-learning experiments, and "using results, or portions of results ... for commercial use".
- Published results, "including pre-trained models", must state that Manga109-s was used. So a trained model may ship, with attribution.
- Forbidden:
  - redistributing the dataset;
  - selling manga images together with results;
  - treating copies or modifications of the images as products;
  - publishing more than 20% of the whole pages of any volume.
- Credit "courtesy of [Author's Name]" when showing parts.
- Hackathons and competitions are not mentioned. A demo that ships the model and shows no Manga109 pages fits "results for commercial use". That is my reading, not legal advice **[unverified]**.

**Manga109Dialog covers every volume.** The public repo has 109 files, one per volume ([public-annotations](https://github.com/manga109/public-annotations), counted via the GitHub API). So the Manga109-s volumes are covered. Each link is `<speaker_to_text text_id speaker_id>`. Both ids point at elements of the main Manga109 XML. Body and face elements carry a volume-wide `@character` id, and characters have names ([manga109api](https://github.com/manga109/manga109api)). Whether `speaker_id` points at a body or a face box is not documented **[unverified]**; both carry the character id. Licence: CC BY 4.0.

**Join against the old annotations, not v2026.**
- The 2026 release says "Manga109Dialog is not included in this release" and points to the v2023 repos. A `hal-utokyo/Manga109-s-v2023` exists and contains `annotations_Manga109Dialog/` ([card](https://huggingface.co/datasets/hal-utokyo/Manga109-s-v2023)).
- v2026 split about 14,900 under-segmented balloons and about 50 oversized boxes, and added about 800 missing texts ([2605.21182](https://arxiv.org/html/2605.21182)). Text ids may therefore not match the dialogue links. The v2026 zip also ships `annotations.v2021.12.30/`; join against that.

**Sizes.**
- Manga109: 157,152 bodies, 118,715 faces, 147,918 texts, 2,979 character names ([2005.04425](https://ar5iv.labs.arxiv.org/html/2005.04425)).
- Per volume that is about 1,440 bodies and 27 characters **[estimate]**.
- Manga109Dialog: 132,692 links. If they spread evenly, Manga109-s gets about 106k **[estimate]**.
- Narration and unknown speakers are not linked ([2306.17469](https://arxiv.org/html/2306.17469v2)).

**Gaps for us:**
- No line-kind labels: speech, thought and caption are not distinguished.
- No masks.
- Character ids are per volume. Five series have two volumes (Love Hina 1/14, Salad Days 1/18, and others), and their names allow cross-volume ids by string match. Whether those volumes are in Manga109-s is unknown.

## 2. State of the art: who clusters comic characters, and with what

| Work | Inputs to identity | Scope | Numbers | Text for identity? |
|---|---|---|---|---|
| Magiv2 ([2408.00298](https://arxiv.org/html/2408.00298)) | Crop embeddings (12-layer, 768-d transformer, SupCon); per-page edges; MILP with must/cannot-links to a character bank | Page edges, chapter naming | Page clustering AMI: PopManga-S 0.6745, -U 0.6650, Manga109 body 0.6456. Chapter naming 0.727 / 0.753 (predicted constraints), 0.799 / 0.853 (gold) | No |
| Magiv3 ([2503.23344](https://arxiv.org/html/2503.23344v1)) | MLP over detector tokens (Florence-2 init) | Page | AMI 0.6884 / 0.6928 / 0.6782 | No |
| Re:Cognize ([2609.34032](https://arxiv.org/html/2609.34032)) | Ground-truth crops streamed in reading order; galleries | Volume, open set | Online clustering, MagiV2 features: NMI 34.1, ARI 24.0, purity 69.6. Closed-set mAP: MagiV2 50.8, MagiV3 40.7, ReID5o 37.8, TransReID 37.1 (POPCharacters); MagiV2 65.3 vs TransReID 28.4 (Manga109). Gallery-growth gains: Vouch +3.3 to +6.5 Rank-1; first-appearance binding +12.5 to +16.9 | Tested name rules; they fail (below) |
| Zero-shot ID + speaker ([2404.13993](https://arxiv.org/html/2404.13993v4)) | GPT-4 speaker guesses become pseudo-labels for a per-comic ResNet-50; iterated | Volume, names given | Character ID: K-means image-only 36.8 → fused 44.0. With gold speaker relations, 55.5 | **Yes**: speaker links are the identity signal |
| CoMix ([2407.03550](https://arxiv.org/html/2407.03550)) | Single-page clustering; 59% colour pages | Page | Best baseline DINOv2: AMI 0.29, NMI 0.51. Magi scored lower on Western comics | No |

What this says:
- **Page-level numbers flatter.** About 0.68 AMI within a page falls to NMI 34.1 when the same features stream across a volume. Our task is the cross-box one.
- **Speaker links do carry identity.** They lift character ID by +7.2 points (36.8 → 44.0). Link quality matters as much again: gold links give a further +11.5 (55.5).
- **Name mentions are weak.** Re:Cognize tested 385 bubbles that contain a name, scored against a break-even of 40.9%:
  - the named person is the bubble's speaker: 16.6% right;
  - the named person is the **addressee**, another character on the page: **29.1%**;
  - the named person is the character nearest the speaker: 15.8%.
- **Vocatives are uneven across series.** The addressee rule clears break-even only on Bakuman (30/36) and Kagurabachi (21/37). It reaches 15.3% on Nisekoi, which supplies 40% of the firings. So vocatives belong as a learned, down-weighted feature.
- **No 2025–26 paper trains a set-level identity model that takes dialogue as input** (searched arXiv, CVF and citers). This design has no direct precedent.

## 3. Architecture: how to cluster a set of 100–1,000 items

| Option | Evidence | Verdict |
|---|---|---|
| **Transformer over the set + pairwise head + correlation clustering** | Every comic system above predicts pairwise edges (Magi v1–v3). The face-clustering Transformer reaches pairwise F 91.12 on MS-Celeb-1M with relation encoding plus linkage prediction ([2104.11502](https://arxiv.org/pdf/2104.11502)). "Attention-based clustering" learns a kernel from context the same way ([2010.01040](https://arxiv.org/pdf/2010.01040)) | **Use** |
| DETR-like slots / attractors | Slots cap the cluster count at what training saw. EEND-EDA, trained on 1–4 speakers, gets DER 9.26 at 4 speakers, 23.11 at 5 and 34.97 at 6. Adding clustering brings that to 12.44 and 17.98 ([2107.01545](https://ar5iv.labs.arxiv.org/html/2107.01545)). Set Transformer seeds fix k in advance (2010.01040) | Reject: episodes hold 5–40 characters plus extras |
| GNN edge classification (GCN-V/E, Hi-LANDER) | Built for kNN graphs of millions of nodes | Reject: at ≤1,000 tokens, full attention already sees every pair |
| Incremental / streaming assignment | Coreference formulations differ by ≤0.2 F1 on CoNLL: pairwise 83.6, incremental 83.5, start-to-end 83.4. Incremental wins long documents: LitBank 78.3 vs 77.6 ([2407.21489](https://arxiv.org/html/2407.21489)) | Use only for **cross-episode** memory |

The formulation matters little: coreference shows it, and Magiv2's naming moves 0.727 → 0.799 just from better constraints. **Edge quality and constraints decide the result.** So: batch clustering inside an episode, and incremental matching across episodes.

**Text in film identity (already covered):** MICap text-only 64.45 → with faces 69.14; FillIn 64.4 → 65.9. Both use anonymised local ids per video set and no names ([2405.11483](https://arxiv.org/html/2405.11483v1)).

**Name mentions in film:** a second-person mention ("Hi, X") implies X is present; a third-person mention implies X is absent ([1809.08761](https://arxiv.org/pdf/1809.08761), 2018). That is the addressee cue Re:Cognize measured at 29.1% in manga.

## 4. Frozen visual encoder

| Encoder | Evidence | Licence |
|---|---|---|
| **DINOv3 ViT-L/16** (0.3B) | Met instance GAP 7B 55.4 vs DINOv2 44.6. IN-R linear probe ViT-L 88.1 (prior note). Trained with `RandomGrayscale(p=0.2)` ([augmentations.py](https://github.com/facebookresearch/dinov3/blob/main/dinov3/data/augmentations.py)), so grayscale views are trained to agree with colour views | DINOv3 License. Section 1 grants use and derivatives with no non-commercial clause ([LICENSE](https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md)); gated, manual approval |
| DINOv2-L | Same grayscale augmentation ([augmentations.py](https://github.com/facebookresearch/dinov2/blob/main/dinov2/data/augmentations.py)). CoMix page AMI 0.29; on True Beauty it clustered by outfit and shot scale | Apache-2.0; cached locally |
| Magiv2 crop embedder | Best manga encoder measured: Re:Cognize mAP 50.8 / 65.3 | "Personal, research, non-commercial" ([model card](https://huggingface.co/ragavsachdeva/magiv2)). **Research baseline only** |
| CCIP (anime) | Colour-anime same-character F1 0.941 (prior note) | openrail |
| SigLIP 2 / CLIP | Met GAP 13.9; weak at instance identity | Apache-2.0 |

**Pick: DINOv3 ViT-L/16, frozen, on grayscale masked crops in both domains**, storing the CLS token plus a mask-weighted mean of the patch tokens. No paper measures B&W→colour character transfer; the grayscale choice rests on the augmentation above plus reasoning. The 2026-10-20 probe (DINOv2 vs DINOv3 vs CCIP vs Magiv2, P@1 and AMI on our crops) still decides; DINOv3 is the default only if it ties.

## 5. Frozen multilingual text encoder

MMTEB bitext mining, the closest public proxy for "a Japanese line and its English translation land together" ([EmbeddingGemma, 2509.20354](https://arxiv.org/html/2509.20354); [Qwen3-Embedding, 2506.05176](https://arxiv.org/html/2506.05176)):

| Model | Params | Bitext | Licence ([HF API](https://huggingface.co/api/models/intfloat/multilingual-e5-large-instruct)) |
|---|---|---|---|
| **multilingual-e5-large-instruct** | 560M | **80.13** | MIT |
| BGE-M3 | 568M | 79.11 | MIT |
| Qwen3-Embedding-0.6B | 595M | 72.22 | Apache-2.0 |
| GTE multilingual base | 305M | 71.79 | Apache-2.0 |
| jina-embeddings-v3 | 572M | 65.25 | CC-BY-NC |
| EmbeddingGemma | 308M | 64.40 | Gemma terms, gated |
| SONAR | — | not on MMTEB | **CC-BY-NC-4.0** |
| LaBSE | 471M | not in these tables | Apache-2.0 |

**Pick: mE5-large-instruct, with BGE-M3 as the swap-in.**

**Train mostly on English.** Machine-translate every Manga109-s line to English, so training text looks like test text:
- MADLAD-400-3B ([card](https://huggingface.co/google/madlad400-3b-mt), Apache-2.0) fits the 3060 in bf16 **[estimate]**;
- opus-mt-ja-en (Apache-2.0) is the light option;
- NLLB is CC-BY-NC, so it is out.

Feed English 70% of the time and the Japanese original 30%.

Reasoning, untested: Japanese marks speaker identity through first-person pronouns and sentence endings. Translation flattens both. A model trained on Japanese alone would lean on cues that English test text lacks.

## 6. Recommended v1

**Set.** An episode at test time.

In training, a window of 16–32 consecutive Manga109-s pages:
- about 120–240 appearances and a similar number of lines **[estimate]**;
- frames restacked vertically like a webtoon strip;
- right-to-left reading order mirrored so it runs one way;
- page coordinates dropped.

**Tokens** (about 250–500 per set; full attention):
- **Appearance token**, one per card:
  - DINOv3 CLS and masked-mean (2×1024 → 384);
  - an optional head-crop embedding: the face box in training, a detector at test, dropped 30% of the time;
  - box geometry inside the frame as Fourier features;
  - shot scale;
  - frame index and reading-order index.
- **Line token**, one per bubble:
  - mE5 embedding (1024 → 384);
  - kind (speech, thought, caption, unknown). Manga109 has no kinds, so training uses "unknown" plus a heuristic "unlinked" flag, and test kinds are dropped 30% of the time;
  - reading order;
  - name features from a per-series name list: contains a name; vocative shape ("X," / "…, X!").
- **Memory tokens**, cross-episode:
  - one prototype per known character from earlier episodes (mean of its embeddings);
  - one learned NEW token.

**Attention biases** (learned scalar per head):
- same frame;
- reading-order distance bucket;
- **speaker edge** between a line and its linked appearance, scaled by the link's confidence;
- line-to-line "same linked speaker".

**Encoder.** 6 layers, width 384, 6 heads, FFN 1,536: about 10.6M. With projections and heads, about **12M trainable** **[estimate]**.

**Heads:**
1. A 128-d identity embedding on appearance tokens.
2. A pair head: an MLP over `[h_i, h_j, h_i⊙h_j, |h_i−h_j|, same-frame, order gap]` giving a same-character logit.
3. An appearance→memory head, with NEW as an option.

**Losses:**
- SupCon on the embeddings within the set;
- pair BCE on all appearance pairs (about 30k at N=250, cheap). Same-frame pairs are hard negatives, weighted ×2;
- cross-entropy on the memory head.

Unnamed extras get negatives only, never positives (as in the prior note). Before training, measure how often one character appears twice in one frame in Manga109. If it is rare, keep cannot-link as a hard rule at inference.

**Noise in speaker links.** Training links are gold; test links are about 95% right. So in training:
- drop each link with p=0.2;
- move 5–10% of the links to another card in the same frame;
- sample a fake confidence from the test distribution, lower on corrupted links.

Zero 15% of line embeddings. Precompute 3 augmented views per crop. This mirrors the 44.0 vs 55.5 gap in Li et al.: the model must not trust links blindly.

**Inference:**
1. Edge weight w_ij = logit(p_ij). Same-frame pairs get −∞.
2. Optionally add a colour term: hue-histogram similarity on the mask, with its weight fitted on webtoon labels.
3. Correlation clustering: greedy additive edge contraction, then Kernighan–Lin moves. The cluster count falls out.
4. Hungarian-match clusters to memory prototypes. A cluster with match probability below τ_new, or one where NEW wins, becomes a new character.
5. Update a prototype only from high-confidence clusters, the Re:Cognize "Vouch" idea (+3.3 to +6.5 Rank-1).

**Training recipe:**
- AdamW, learning rate 3e-4, cosine schedule, about 40 epochs over the windows.
- One run takes about 1 h and under 4 GB of VRAM **[estimate]**.
- Split Manga109-s **by author**: about 70 volumes train, 8 validation, 9 test.
- Memory training: cut a volume into windows A and B, and build prototypes from A. Characters absent from A train NEW.

**Precompute** (offline, frozen):
1. SAM masks on Manga109-s body boxes.
2. DINOv3 features on grayscale masked crops: about 126k bodies × 3 views × 4 KB, about 1.5 GB **[estimate]**.
3. Translation, then mE5 on JA and EN: about 0.5 GB.

## 7. Evaluation plan, and the labels we must make

**Metrics:**
- pairwise precision, recall and F1, overall and split into same-scene vs cross-scene;
- B-cubed F1;
- AMI;
- error in the number of characters;
- cross-episode: Rank-1 against memory, and new-character precision and recall.

**Sets:**
1. Manga109-s held-out authors: the main learning signal. Ablations:
   - visual only;
   - plus text;
   - plus speaker edges;
   - link corruption at 0 / 5 / 15%;
   - training on EN vs JA.
2. **True Beauty episodes 4/5/7** (289 cards): colour webtoon, in-domain.
3. **Pepper&Carrot**, 2–3 episodes: colour European comic, evaluation only, never trained on.

**Baselines on the same splits:**
- DINOv3 cosine with the same correlation clustering and no training;
- Maverick (cross-scene recall 0.42);
- Opus 5.5 (0.99 / 0.98 at 3.1 ¢/box) as the ceiling.

**Labels to make** (I draft, the user corrects):
- (a) a character id for every card in sets 2 and 3, consistent across episodes, about 500 cards;
- (b) per-series name lists;
- (c) an audit of about 100 rule-based speaker links in those episodes, to measure the real test-time link noise and set the corruption rates;
- (d) a scene id per box, for the same-scene vs cross-scene split.

With about 500 cards, a difference under about 5 F1 points is noise **[estimate]**. Report bootstrap intervals.

## 8. Rejected

| Alternative | Reason |
|---|---|
| Magiv2 / Magiv3 as the product encoder | Non-commercial weights |
| Training on full Manga109, PopManga or PopCharacters | Academic or research-only terms |
| SONAR, NLLB, jina-v3 | CC-BY-NC |
| Slots or attractors | Cluster count capped by training (EEND-EDA 9.26 → 34.97 DER from 4 to 6 speakers) |
| GNN on a kNN graph | Built for a scale we do not have |
| A hard name or vocative rule | 16.6–29.1% against a 40.9% break-even (Re:Cognize) |
| An LLM pseudo-label loop (Li et al.) | 44.0% character ID with GPT-4; VLMs name ≤1.1% (Re:Cognize) |
| A closed-set classifier per series | Cannot add characters. Per-series fine-tuning (+6.5 AP in the VGG work) stays a later option |

## Sources

- Manga109 site and licence: http://www.manga109.org/en/ · Manga109-s card: https://huggingface.co/datasets/hal-utokyo/Manga109-s · v2023: https://huggingface.co/datasets/hal-utokyo/Manga109-s-v2023 · Manga109 card: https://huggingface.co/datasets/hal-utokyo/Manga109
- Manga109 statistics: https://ar5iv.labs.arxiv.org/html/2005.04425 · v2026: https://arxiv.org/html/2605.21182
- Manga109Dialog: https://arxiv.org/html/2306.17469v2 · https://github.com/manga109/public-annotations · https://github.com/liyingxuan1012/Manga109Dialog
- Magiv2: https://arxiv.org/html/2408.00298 · Magiv3: https://arxiv.org/html/2503.23344v1 · Magi licence: https://huggingface.co/ragavsachdeva/magiv2
- Re:Cognize: https://arxiv.org/html/2609.34032 · Zero-shot ID: https://arxiv.org/html/2404.13993v4 · CoMix: https://arxiv.org/html/2407.03550
- Face Transformer: https://arxiv.org/pdf/2104.11502 · Attention-based clustering: https://arxiv.org/pdf/2010.01040 · EEND unlimited speakers: https://ar5iv.labs.arxiv.org/html/2107.01545 · Maverick coref: https://arxiv.org/html/2407.21489
- MICap: https://arxiv.org/html/2405.11483v1 · Speaker naming in movies: https://arxiv.org/pdf/1809.08761
- DINOv3 licence: https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md · EmbeddingGemma: https://arxiv.org/html/2509.20354 · Qwen3-Embedding: https://arxiv.org/html/2506.05176 · Licences: Hugging Face API model cards (mE5, BGE-M3, SONAR, NLLB, MADLAD-400, opus-mt, jina-v3)
