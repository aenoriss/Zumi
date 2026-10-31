# A trained encoder for character identity and speakers: architecture decision — 2026-10-20

Research date: 2026-10-20. Three parallel web passes (datasets; architectures that fuse appearance with dialogue; components, objectives and compute). Nothing was downloaded or run, except one local experiment (body-only clustering, below).

Conventions:
- Numbers are copied from papers.
- **[unverified]** marks snippets or memory.
- Everything about webtoons is reasoning; no webtoon dataset has identity or speaker labels.

Follows `comic-character-identity-sota-2026-10.md`.

## Why train a model

Measured on our data:

| Approach | Result |
|---|---|
| Maverick, one panel at a time | Links speakers inside a panel well (pairwise P/R 0.92/0.85); loses identity across scenes (recall 0.42) |
| Body-only DINOv2-large clustering, True Beauty episodes 4/5/7 (289 crops, `segment/cluster_body.py`, deleted 2026-10-30: in the git history) | Groups by shot scale, uniform and accessories, not identity. One 28-crop cluster is close-ups of mixed characters (judged by eye; not yet labelled) |

The literature points the same way:
- Body is a weak identity cue alone: NMI 42.9 against 72.9 for face (MuHPC, TV).
- Dialogue carries identity that pixels miss. In movie identity fill-in, text alone gets 62.7–64.5, and fusing faces adds +2.2 to +4.7 (FillIn, MICap).

The model: a small **multimodal encoder** (encoder-only transformer, BERT-shaped). It reads a whole episode at once and decides which appearances are the same character and who says each line.

## What the measured winners share

1. **Joint attention over all slots matters most.** FillIn: a joint transformer over all blanks gives +8.0 class accuracy over per-blank BERT.
2. **Text carries identity; visual embeddings add a few points, and their quality decides how many.**
   - MICap: text 64.45 → + faces 67.35 → ArcFace instead of FaceNet 69.14.
   - Who's Waldo: −12.2 without text, −8.1 without visual.
3. **For unseen people, heads predict relations, not classes.** Examples: local IDs renumbered per episode (MICap), a similarity matrix with a null option (Waldo), affinity edges trained on disjoint identities (GCN face clustering). A closed-set softmax (Hu et al. 2015) cannot name a new character.
4. **Constraints are free accuracy.**
   - A cannot-link between co-occurring tracks (MuHPC).
   - Restricting candidates: +21 points in BookNLP quote attribution (0.40 → 0.61).
5. **Layout beats text for comic speakers.** Manga109Dialog reaches 75.7 Recall@#text with **no text**, against 71.5 for the same-frame rule. Text helps with names, narration and off-panel speakers.
6. **Name mentions and recency dominate text-side attribution.** Explicit quotes score 0.98. A model fed only the last 5 character mentions reaches 0.72 (PDNC).

## Data

| Source | Use | Labels | Catch |
|---|---|---|---|
| **Manga109 + Manga109Dialog** (+ v2026 text revision) | Main training set | 109 volumes, 21,142 pages; volume-wide character ids on body and face boxes; 132,692 speaker links; transcribed text | Japanese, black-and-white. **Gated Hugging Face application that wants an academic email**, "a few days to a week". Without one: Manga109-s (87 volumes, separate application). No narrator labels. |
| **PopManga Test-S/U + PopCharacters** | Second training or validation set, English | About 1,900 pages; chapter-wide character clusters; text-to-character matches; tails; names | Click-through gate. Images fetched from MangaPlus. Text must be OCR'd. |
| **COMICS** (Golden Age) | Optional self-supervised pretraining | 198k colour pages, English OCR | Self-supervision alone hurt in Soykan (P@1 49.8 vs 58.8), so it is not in v1 |
| **Our webtoon labels** | The only in-domain test | True Beauty episodes 4/5/7 (289 crops, 237 panels) plus the 38 labelled panels | Must be hand-labelled |

Magi's training data was never released. No webtoon or manhwa dataset labels identity or speakers.

## Architecture (v1)

**Tokens.** About 700–900 per episode, full attention, no causal mask.

**Appearance tokens:**
- frozen embedding of the **body crop**, plus the **head crop** when one is found;
- shot scale (box area relative to the panel), so the model can learn to discount it;
- box inside the panel as Fourier features;
- panel index and reading-order position.

**Line tokens:**
- frozen sentence embedding;
- bubble type (speech, thought, caption);
- tail direction and tip point;
- reading order and panel index;
- name-mention features from a per-series name list.

**Series-slot tokens.** Prototypes of characters known from earlier episodes, plus a learned **NEW** token.

**Attention biases:**
- reading-order distance;
- same panel;
- box distance;
- "the tail points at this appearance".

**Encoder.** 6 layers, width 384, 6 heads, FFN 1,536. About **11M trainable parameters**. The frozen encoders run offline and their vectors are cached.

**Heads and losses:**
- **Identity:** a 128-d projection and cosine pair scores. SupCon within the episode plus pairwise BCE, with same-panel pairs as hard negatives. A pointer from each appearance to the series slots or NEW, trained with cross-entropy.
- **Speaker:** a pointer from each line over the appearances plus **OFF-PANEL** and **NARRATOR** tokens, trained with cross-entropy.
- **Auxiliary:** a same-speaker head on line–line pairs.

**Inference:**
1. Identity probabilities become log-odds edge weights.
2. Speaker links add evidence: two lines with the same likely speaker raise the edge between their speakers' appearances.
3. Correlation clustering with hard cannot-links sets the number of characters itself.
4. Clusters are Hungarian-matched to series slots. A cluster becomes a **new character** when its best match falls below τ_new or the NEW token wins.
5. τ_new is calibrated on held-out series whose characters never appear in training.

**Why not the alternatives:**
- A closed-set classifier cannot add characters.
- DETR-style re-detection, as in Magi, repeats work our boxes already do.
- GCN clustering targets graphs of millions of nodes; at about 300 appearances, full attention already sees every pair.
- A generative VLM is what we have now (Maverick), and it loses identity across scenes.

## Components

**Visual encoder: chosen by a probe on our webtoon labels, never by manga scores.** No published number covers transfer from black-and-white manga to colour webtoons.

| Candidate | Evidence | Licence |
|---|---|---|
| DINOv3 ViT-L/16 | Met instance retrieval GAP 55.4 vs DINOv2 44.6 | DINOv3 licence. Gated: the user must accept its terms. |
| Magiv2 crop embedder, 85.8M (released) | PopManga P@1 0.883; Manga109 body AMI 0.620 | Research only |
| CCIP caformer_b36 | Anime same-character F1 0.941; trained on colour anime | openrail |
| DINOv2-L (cached locally) | Manga P@1 0.485; on our data it clusters by outfit and shot scale | Apache-2.0 |

Two more choices:
- Feed grayscale crops in both domains, so the frozen encoder sees one distribution. This is reasoning; no paper tests it for characters. Optionally add colour back on the webtoon side as a separate token with dropout.
- Store the summary token plus a small patch grid. A 4×4 grid over all of Manga109 is about 9 GB, so start with the summary token only. That is about 1.1 GB for body and head.

**Text encoder.** Must bridge Japanese training text and English test text.

| Candidate | Evidence | Licence |
|---|---|---|
| SONAR (Meta) | FLORES-200 xsim error 1.4% vs LaBSE 10.7% **[unverified]** | Weights probably non-commercial |
| multilingual-E5-large-instruct (fallback) | BUCC 99.0, Tatoeba 83.8 | MIT |

Also machine-translate the Manga109 lines to English with NLLB (Meta), and swap the Japanese and English embeddings at random during training.

**Domain-gap augmentation:**
- grayscale in both domains;
- cut manga pages into panels and restack them vertically, imitating a webtoon strip;
- mirror the x axis of right-to-left pages so reading always runs in one direction;
- drop page coordinates, since webtoons have no pages.

**Split by author** (94 authors), because art style leaks across an author's titles. Unnamed extras get only same-panel negatives, never positives.

**Compute** (estimates):
- Precompute embeddings: about 3 h.
- One training run: about 1 h on the 3060, under 4 GB of VRAM.
- Labelling and evaluation are the bottleneck: about 2 days.

## Plan

Each step needs approval before it starts.

0. **Unblock, the user's actions:**
   - Apply for Manga109 (or Manga109-s), PopManga test and PopCharacters.
   - Accept the DINOv3 terms.
   - Free disk: C: has about 0.6 GB. Manga109, the features and the encoders need roughly 15 GB **[estimate]**.
1. **Webtoon validation labels and the encoder probe.** No Manga109 needed, so this can start now.
   - Label identity for the 289 True Beauty crops plus their speakers; I draft, the user corrects.
   - Score DINOv2, DINOv3, the Magiv2 embedder and CCIP, on head and body crops, in grayscale and in colour, by P@1 and AMI.
2. **Manga109 data pipeline:**
   - Parse the XML into appearances, lines, panels and reading order.
   - Attach Manga109Dialog speakers.
   - Translate the lines.
   - Precompute the embeddings.
3. **Train v1.** Evaluate on the webtoon labels against Maverick (56/65 speakers, cross-scene recall 0.42) and against plain clustering.
4. **If transfer falls short:** fine-tune on high-confidence webtoon pseudo-labels plus 2–3 hand-labelled episodes.

**Fallback if data or time runs out:** the training-free episode graph. Visual similarity, Maverick's speaker links and name mentions are combined in the same correlation clustering, with no learned weights. It shares steps 1 and 3's evaluation, so no work is lost.

**Schedule risk:** about 3.5 weeks remain until 2026-11-14, and pipeline stages 4–10 are unbuilt.

## Sources

- FillIn https://ar5iv.labs.arxiv.org/html/2008.09791
- MICap https://arxiv.org/html/2405.11483v1
- Who's Waldo https://ar5iv.labs.arxiv.org/html/2108.07253
- MuHPC https://arxiv.org/html/2105.09939v1
- RAD-Net https://arxiv.org/html/2308.00588
- BookNLP+ https://arxiv.org/html/2307.03734v1
- Character embeddings https://arxiv.org/html/2406.11368v1
- Hu et al. 2015 https://ar5iv.labs.arxiv.org/html/1507.04831
- Ada-NETS https://arxiv.org/pdf/2202.03800
- Manga109 https://huggingface.co/datasets/hal-utokyo/Manga109
- Manga109Dialog https://arxiv.org/html/2306.17469v2 and https://github.com/manga109/public-annotations
- PopManga test https://huggingface.co/datasets/ragavsachdeva/popmanga_test
- PopCharacters https://huggingface.co/datasets/ragavsachdeva/popcharacters
- COMICS https://arxiv.org/abs/1611.05118
- Magiv2 https://arxiv.org/html/2408.00298 and https://huggingface.co/ragavsachdeva/magiv2-crop-embedder
- mE5 https://arxiv.org/html/2402.05672
- SeamlessM4T (SONAR numbers) https://arxiv.org/pdf/2308.11596
- DINOv3 licence https://github.com/facebookresearch/dinov3/blob/main/LICENSE.md
- Soykan et al. https://ar5iv.labs.arxiv.org/html/2308.09096
- CCIP https://huggingface.co/deepghs/ccip
