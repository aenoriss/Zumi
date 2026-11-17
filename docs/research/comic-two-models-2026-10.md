# Two trained models: who says each line (A) and who each card is (B) — 2026-10-31

Research date: 2026-10-31. One web pass over primary sources (papers, dataset cards, licence pages); two paper PDFs were read in full (SSIC, MangaSeg). Nothing else was downloaded or run.

Conventions:
- Numbers are copied from the cited source.
- **[estimate]** marks my arithmetic. **[unverified]** marks what no primary source confirmed.
- Statements about webtoons and European comics are reasoning. No labelled set exists for them.

Builds on `character-identity-model-2026-10.md` (Manga109-s licence, Manga109Dialog coverage, encoders, identity SOTA, the B v1), `character-speaker-encoder-2026-10.md` and `comic-speaker-attribution-2026-10.md`. It does not repeat them.

## What is new since this morning's note

1. **Manga109 now has pixel masks.** MangaSeg (CVPR 2025) gives instance masks for all 109 volumes: 157,152 bodies, 118,715 faces, 103,900 frames and **130,180 balloons**, a class Manga109 never had. Its licence allows commercial use with credit. SAM on Manga109 bodies is no longer needed.
2. **The "no speaker" classes can be built from three sources.** COO polygons give the sound effects. Manga109Dialog leaves narration and off-page speakers unlinked. MangaSeg balloons tell a caption from a balloon.
3. **Text-only reasoning beats region matching on hard books.** SSIC (EMNLP 2026) uses ordered dialogue and layout with no character boxes. It reaches 74.62% against 67.60% for the best region-based fusion. On Hard books the gap is 78.13 vs 66.61. Dialogue context is real evidence for both models.
4. **Recommendation: two separate trainable models on one shared data and feature stack.** B reads A's calibrated probabilities. See §5.

## 1. Data: what the Manga109 family gives each model

| Source | What | Count | Licence | Use |
|---|---|---|---|---|
| Manga109-s images + `annotations.v2021.12.30` | frame, text, face, body boxes; character id per body/face; text transcripts | 87 volumes (see identity note) | Manga109-s terms: commercial results allowed, with attribution | A, B |
| Manga109Dialog | text → speaker box links; a text with several speakers links to all of them | 132,692 links; Easy 111,959, Hard 20,733 | CC BY 4.0 | A labels; B identity of lines |
| COO | onomatopoeia polygons, transcripts, links between split fragments | 61,465 polygons, 2,261 links | annotations CC BY 4.0, code MIT ([repo](https://github.com/ku21fan/COO-Comic-Onomatopoeia)) | A: the SFX class |
| MangaSeg | instance masks: frame, text, onomatopoeia, body, face, balloon; COCO JSON, RLE | 130,180 balloons; other counts equal Manga109's | "customized license ... same spirit as CC BY 4.0"; the JSON's licence field is CC BY 4.0; the HF card permits "academic and commercial usages" with the credit "Copyrighted by Minshan Xie" | A, B: card and balloon masks |
| PopManga-X (tails, text–tail links) | tails and dialogue/non-dialogue labels | ~2,000 test pages | research only | Not usable |

**Gaps that matter.**
- **Manga109 has no text kinds.** It has one text class; the paper says text holds "a character's speech, a monologue, or narration" ([2005.04425](https://ar5iv.labs.arxiv.org/html/2005.04425)). It has no tail attribute.
- **Onomatopoeia are not in Manga109's text boxes.** They come only from COO. Manga109-v2026 removed about 4,300 text/onomatopoeia overlaps from dialogue boxes ([2605.21182](https://arxiv.org/html/2605.21182v2)).
- **Manga109Dialog leaves out:** narration, unknown speakers, titles, and speakers not on the page (phone calls, letters). "Others" are linked only when a box can be drawn ([2306.17469](https://arxiv.org/html/2306.17469v2)). So "unlinked" mixes narration, off-page speech and unknowns. At least 15,195 texts (10.3%) are unlinked **[estimate: 147,887 texts − 132,692 links; links to several speakers only raise it]**.
- **MangaSeg licence text.** The `license.txt` itself sits behind the HF gate (HTTP 401), so its exact wording is **[unverified]**. Read it at access time.
- **MangaSeg mask quality.** Masks were made by models and then corrected by hand in rounds. Balloons follow the *inner* boundary ([MangaSeg paper and supplement](https://openaccess.thecvf.com/content/CVPR2025/papers/Xie_Advancing_Manga_Analysis_Comprehensive_Segmentation_Annotations_for_the_Manga109_Dataset_CVPR_2025_paper.pdf)).
- **MangaSeg ids.** Whether its annotations carry the Manga109 element ids is not stated **[unverified]**. Join by box IoU: the per-class counts match Manga109's exactly.

**Weak labels for the null classes on Manga109-s** (heuristic, to be checked by hand on ~200 texts **[unverified quality]**):

| Text on the page | Label |
|---|---|
| linked in Manga109Dialog | speaker card(s) |
| a COO polygon | SFX |
| unlinked, outside every MangaSeg balloon | NARRATOR (caption) |
| unlinked, inside a balloon | OFF_PANEL / unknown |
| linked, but the speaker's body removed by augmentation (§3.3) | OFF_PANEL, with a clean label |

The last row is the useful one: it manufactures clean off-panel examples from clean links.

**Tails.** No Manga109-family set annotates them. PopManga-X does, but it is research-only. Plan:
1. Run our production `speakers.tail_parts` (morphological opening) on MangaSeg balloon masks.
2. Check 50 balloons first. MangaSeg's figures suggest the tail stays inside the inner-boundary mask, but no sentence says so **[unverified]**.
3. If tails are cut off, fall back to SAM 3 point prompts on the balloon, with the text box as the prompt.

## 2. Model A: state of the art (2023–2026)

| Work | Inputs | Text content used? | Result |
|---|---|---|---|
| Manga109Dialog SGG ([2306.17469](https://arxiv.org/html/2306.17469v2)) | Faster R-CNN box features, union-box features, frame boxes and reading order | **No**: "only with visual information" | R@#text (PredCls), Easy / Hard / Total: short distance 71.43 / 22.72 / 63.41; frame distance 81.55 / 22.06 / 71.53; union feature 83.20 / 28.50 / 73.99; with frame **84.77 / 30.65 / 75.69**. With detection (SGDet): 60.54. eBDtheque: frame distance 80.27 beats the model's 77.45 |
| Magi v1 (CVPR 2024) | DETR tokens of the page | No | R@#text 0.845 / 0.831 vs closest character 0.776 / 0.766 (PopManga S/U; prior note) |
| Magiv2 ([2408.00298](https://arxiv.org/html/2408.00298)) | Pairwise 3-layer MLP on text and character tokens; tails have their own head | Not as input | Text–char AP **0.7499 / 0.7512** (v1 0.5248 / 0.5632); text–tail 0.9838 / 0.9830. Errors sit on tailless text. Text–tail is many-to-many: several tails = several speakers |
| Magiv3 ([2503.23344](https://arxiv.org/html/2503.23344v1)) | Florence-2 multitask | OCR is a task, not an input to association | Text–char AP 0.7241 / 0.7331, **below v2**, while character AMI rose to 0.6884 / 0.6928 / 0.6782 |
| Iterative multimodal fusion, IMF ([2404.13993](https://arxiv.org/html/2404.13993v4)) | GPT-4 on dialogue + per-book ResNet + SGG relations | Yes | Speaker accuracy: LLM only 43.6; iteration 1 51.1; iteration 2 51.8; iteration 3 51.6 (Hard 51.3 → 49.8). Gold relations: 63.8. Fully automatic: 38.7 |
| SSIC ([EMNLP 2026](https://aclanthology.org/2026.emnlp-main.2632.pdf)) | Ordered text + text-box positions + reading order; **no character boxes**; GPT-5.4 | Yes, the main signal | Character-level accuracy (Hungarian-matched), 23 books: IMF (same LLM) 67.60, LLM direct 66.12, **SSIC 74.62**; Hard 78.13 vs 66.61. No speaker seeds: 70.10; no layout: 72.43. With OCR'd input: 56.72 vs 54.42 |
| Zhang & Hotta, IEEE MultiMedia 32(3) 2025 | visual relations + NLP tasks | Yes | Cited by SSIC; numbers not found **[unverified]** |

**What this says for A:**
- **No published model links each line to a box using geometry, tails and text together.** Box-level systems ignore the words; text-level systems ignore the boxes. A would combine them. That is new, and no number predicts its gain.
- **Tails carry the box-level result.** Magiv2 credits tails for its jump from 0.52 to 0.75 AP, and puts its errors on tailless text. Our tail rule is right on 209 of 212 lines with an aimed card (`speakers.py`). Our remaining errors are the tailless and ambiguous lines.
- **Dialogue order resolves what geometry cannot.** On Hard books, SSIC's dialogue-only registry (78.13) beats region fusion (66.61). This is the "Shhh, Pepper!" case: the conversation decides it.
- **Bigger joint models did not help association.** Magiv3 lost 2.6 AP on text–char against v2 while gaining on clustering.
- **Our own baselines** (P&C, `speakers.py` docstring):
  - rules 116/121 (95.9%) on P&C 36; 263/278 (94.6%) on four episodes;
  - a logistic regression over the same features, leave-one-episode-out: 255/278 (91.7%);
  - VLM fallback on P&C 36: Haiku 105/121, Sonnet 99/121.
  - So **a learner fed only the rule features lost to the rules on 278 lines.** A must bring new evidence (text, context, appearance, 100k+ training lines), not relearn the cascade.

## 3. Model A: design

### 3.1 Output structure

| Option | Fit | Verdict |
|---|---|---|
| **Pointer per line over candidates ∪ {NARRATOR, SFX, OFF_PANEL}, plus a chorus head** | Many lines may point at one card; nulls compete with cards in one softmax, like a coreference "dummy antecedent" | **Use** |
| Set transformer + cross-attention, DETR-style queries | Re-detects what our masks already give | Reject |
| Pairwise classifier + assignment | Hungarian forces one line per card, but one character says many lines. Without set context it cannot do turn-taking; our LR version scored 91.7% < 95.9% | Reject as the head; keep pairwise *features* |
| Optimal transport with a dustbin (SuperGlue, [1911.11763](https://arxiv.org/abs/1911.11763)) | Built for one-to-one matching | Reject |

**Chorus.** Manga109Dialog links a text to all its speakers, so multi-speaker labels exist. How many there are is not reported: count them at load time. Head:
- a count softmax over {1, 2, 3+}, read only when the top answer is a card;
- a per-card sigmoid that picks which extra cards join;
- input features: the number of tails, and whether a second tail aims at the card (Magiv2: several tails mean several speakers).

### 3.2 How the rules enter, so A starts from their strengths

The rule cascade is the same code at train and test: `speakers.features` and `_assign`, run on MangaSeg masks.
- **As pair features φ_ij:**
  - same frame;
  - distance / box long side;
  - tip distance / box long side;
  - tail aim cosine, and aim > 0.85;
  - has tail; number of tails;
  - card area share; frame-order gap;
  - speaking-group membership.
- **As attention biases.** A per-head scalar from a small MLP over φ_ij, added to line↔card attention logits (the Graphormer pattern of learned spatial biases, [2106.05234](https://arxiv.org/abs/2106.05234)). Line↔line biases use the reading-order gap and same frame.
- **As a residual prior.** z_ij = MLP(h_i, h_j, φ_ij) + β·r_ij. Here r_ij is the log-odds of the rule's confidence when the rule picked card j, else 0 (nulls likewise), and β starts at 1. Before training, A therefore equals the rules. Training learns where to depart from them.
- **As a safety gate at inference.** The model overrides the rule pick only when its calibrated margin exceeds m, with m fitted on a dev set (not P&C).

### 3.3 Context and names

- **Window.** Lines of 3 consecutive boxes (the box, the one before, the one after) attend to each other. Each line's candidates are the cards of its own box plus the nulls; context cards are visible but are not candidates.
- **Turn-taking** is learned from line↔line attention with reading-order biases. SSIC's ablation: seed induction from ordered text without layout lost only 2.19 points, so order carries most of it.
- **Identity, pass 2 (optional).** Add B's anonymous cluster id to each card token (randomly renumbered per window, dropped 50% in training). Then "the speaker of the last line" can point at a card two frames on. Stop after one feedback round: IMF gained +0.7 at iteration 2, and its Hard books lost 1.5 at iteration 3.
- **Names.** A feature only, never a rule. Re:Cognize's best vocative rule ("the named one is the addressee") hit 29.1% against a 40.9% break-even (identity note). Per line: "mentions a name" and "vocative shape". Per pair: "the line names card j's character". Gold in training; at test from B's named bank. Dropped 50% in training.

### 3.4 A v1

**Tokens** (≤ ~190 per window **[estimate: 3 boxes × (≤40 lines + ≤20 cards) + 3 nulls]**):
- **Card token:**
  - DINOv3 CLS + masked mean of the grayscale masked crop (2048 → 384), shared cache with B;
  - mask box as Fourier features, area share;
  - relative frame and box index;
  - optional B cluster slot.
- **Line token:**
  - mE5 of the line text (1024 → 384);
  - kind (speech / thought / shout / caption / sfx / unknown), dropped 30%;
  - box geometry; tail tip and direction (sin, cos); number of tails;
  - reading order;
  - name flags.
- **Null tokens:** NARRATOR, SFX, OFF_PANEL, each a learned embedding.

**Encoder.** 6 layers, width 384, 6 heads, FFN 1,536, full attention with the biases above: 10.6M. With projections and heads, about **12.6M trainable** **[estimate]**.

**Heads.** The pointer logits z_ij and z_i,null; the chorus count and per-card sigmoid; an auxiliary line–line "same speaker" logit (B reuses its output).

**Losses:**
- multi-positive softmax CE over candidates ∪ nulls: −log Σ_pos e^z + log Σ_all e^z;
- per-card BCE for chorus membership;
- count CE;
- line–line BCE at weight 0.3;
- label smoothing 0.05.

**Data per epoch** (Manga109-s, about 70 training volumes):
- about 85k linked lines **[estimate: ~106k × 70/87]**;
- unlinked texts as nulls;
- COO polygons as SFX, about 49k **[estimate: 61,465 × 87/109]**.

**Augmentation:**
- grayscale;
- restack frames into webtoon-like boxes (§6);
- mirror right-to-left pages;
- text: English (MADLAD-400 translation) 70% / Japanese 30%; zero 15% of text embeddings (OCR failure);
- **drop the gold speaker's card with p = 0.15**, which turns the label into OFF_PANEL, but only when no other card of that character is in the box;
- jitter the masks (dilate or erode 1–3 px), which changes tail detection the way our SAM masks do;
- drop the tail feature 10%.

**Training.** AdamW 3e-4, cosine, about 30 epochs, batch 32 windows. Under 4 GB VRAM and about 1 h per run **[estimate, same scale as the identity note]**.

**Inference:**
1. argmax over candidates ∪ nulls;
2. if count ≥ 2, add the cards whose sigmoid exceeds τ_c;
3. the safety gate against the rules;
4. output temperature-scaled probabilities, which B consumes.

**Baselines A must beat:**

| Set | Baseline | Number |
|---|---|---|
| P&C 36 (121 lines) | rules | 116 (95.9%) |
| P&C 36–39 (all labelled) | rules / LR on rule features | 263/278 (94.6%) / 255/278 (91.7%) |
| Manga109-s held-out authors | our rules on MangaSeg masks; frame distance; SGG | measure; on full Manga109: 71.53 / 75.69 R@#text, Hard 22.06 / 30.65 |
| Fresh English colour set (§6) | rules | measure |

**Power.** On P&C 36 the rules make 5 errors. If A fixed 3 and broke none, the exact McNemar p would be 0.25 **[estimate]**. Two more problems: the rules were tuned on all four P&C episodes (the tune/test split "was spent"), so P&C favours them, and it cannot prove a gain. A significant win needs about 10 fixed against 1 broken on the pooled sets (p ≈ 0.012) **[estimate]**.

## 4. Model B: what changes from the v1 in the identity note

1. **Speaker edges come from A, not from the rules.** Each line carries A's distribution over its box's cards and the nulls. The speaker-edge bias is scaled by p_ij, not by a rule confidence.
2. **Train on real A errors, not invented ones.** Replace the hand-set corruption (drop 20%, move 5–10%):
   - cross-fit A in 5 folds by author on the training volumes;
   - feed B the out-of-fold, temperature-scaled predictions.
   This matches train-time noise to test-time noise. Keep 10% extra link dropout for the webtoon gap.
3. **Lines become things to cluster, not only edges.** SSIC builds a character registry from dialogue alone and beats region fusion by 7.02 points. So B assigns an identity to:
   - every card;
   - every line A calls OFF_PANEL, from its text, its turn position and the line–line head.
   Training signal: Manga109Dialog lines whose speaker body was dropped (§3.3) keep their character id. A product payoff: off-panel lines get a voice.
4. **A line–line "same speaker" bias**, from A's auxiliary head, links lines across boxes.
5. **Memory per character:**
   - up to 8 visual exemplars (k-means over its cards) instead of one mean, because outfits change;
   - a "voice" prototype (mean mE5 of its attributed lines);
   - a name when known.
   The memory head cross-attends to the exemplars, with a NEW token.
6. **Update memory only from clusters where two cues agree** (a visual match plus a line-speaker match). Re:Cognize: naive growth adds the wrong character 62–89% of the time; its page-group gate is right 86.9% of the time (prior note).
7. **One A ↔ B round at most** (§3.3).

**Unchanged:** the 6×384 encoder (about 12M), the pair head, correlation clustering, the Hungarian match to memory, author splits, and late colour fusion.

**Baselines for B:**
- DINOv3 cosine + the same clustering, untrained;
- Maverick (cross-scene recall 0.42);
- B fed rule edges instead of A's;
- Opus 5.5 as the ceiling (0.99 / 0.98; identity note).
- Literature anchors: IMF character ID 44.0, or 55.5 with gold relations (+11.5 from link quality alone); SSIC 74.62 speaker identity from text.

## 5. Shared or separate?

**Recommendation: separate trainable models; shared data pipeline, token schema, frozen feature caches and evaluation code.**

| | Separate (chosen) | One multi-task trunk |
|---|---|---|
| Context scale | A: 3 boxes, ≤190 tokens. B: an episode, 250–1,000 tokens | One window must serve both; A pays B's cost |
| Risk to the 95.9% | A is gated against the rules alone | B's losses can pull the shared trunk off A's sharp geometry |
| Evidence | Magiv3's joint model: text–char AP −2.6 vs v2 while clustering rose (0.6456 → 0.6782 on M109). Standley et al. ([1905.07553](https://arxiv.org/abs/1905.07553)): competing tasks "often" give "inferior overall performance" together | IMF: coupling helps 1–2 rounds (+7.5 speaker from identity), then hurts Hard books |
| Labels | A has 454 in-domain lines; B has none yet | One release cycle for two maturity levels |
| Cost | Two ~12M models; features computed once anyway | Saves about 12M parameters, which is irrelevant on a 3060 |

**Cheap middle ground, as an ablation:** warm-start B's trunk from A's weights. Both read the same token schema. Keep it only if B's validation pairwise F1 rises by more than its noise (about 5 points on 500 cards; identity note).

## 6. Shared infrastructure

**Pipeline** (one `m109` loader writes the same "episode graph" JSON that the Zumi pipeline writes for a webtoon):
1. Parse the Manga109-s v2021 XML: frames, texts, bodies, faces, character ids.
2. Join Manga109Dialog on the v2021 ids (not v2026; identity note).
3. Join MangaSeg masks by box IoU ≥ 0.9 per class. Mask-to-box agreement is an automatic quality check.
4. Add COO polygons as SFX lettering. Merge split fragments through COO's links.
5. Derive frame order with our `reading_order` on MangaSeg frame masks, after mirroring right-to-left pages. Assign home frames with `home_frame`.
6. Compute tails with `tail_parts`, and rule features and rule picks with `features` / `_assign`. This is the same code as production, so features cannot drift between train and test.
7. Restack into pseudo-boxes:
   - 1–3 consecutive frames stacked vertically 70% of the time;
   - the whole page as one box 30% of the time, which keeps Hard pairs (speaker in another frame) inside one box;
   - balloons that cross a frame edge move with their home frame.
8. Translate (MADLAD-400, Apache-2.0) and embed (mE5) in English and Japanese.
9. Embed DINOv3 ViT-L/16 on grayscale masked crops of cards. Cache per element id, versioned by encoder and mask hash. The webtoon side writes the same cache.

**Disk:**
- Manga109-s: 3.3 GB;
- MangaSeg: 614 MB;
- features: about 2 GB **[estimate, from the identity note]**.

**Splits.** By author, about 70 / 8 / 9 volumes. Where possible, put Manga109-s volumes of the 23-book IMF/SSIC test set into our test split, so numbers sit next to theirs. Which of those 23 are in Manga109-s is **[unverified]**.

**Evaluation sets and metrics:**

| Model | Set | Metrics |
|---|---|---|
| A | Manga109-s test authors | per-line exact-set accuracy (as `speaker_eval.py`: kind matches, all speakers named, nothing outside their groups); R@#text; Easy/Hard; tail/tailless; per null class P/R; chorus set F1; ECE |
| A | P&C 36–39, 454 lines, evaluation only | same, plus named slices for the brief's error types: tail between two cards, chorus, context-only |
| A | **Fresh English colour set, untouched by rule tuning**: True Beauty's 65 lines (remap with `speaker_remap.py`) plus about 300 new lines from one webtoon and one European comic | same; this is the deciding set |
| B | identity note §7 | pairwise P/R/F1 (same-scene vs cross-scene), B-cubed, AMI, cluster-count error, Rank-1 against memory, new-character P/R; **new:** off-panel line identity accuracy |

**Labels we make** (I draft, the user corrects):
- A: about 300 fresh lines, with kind, speaker card(s) and error-type tags.
- A: a 200-text audit of the Manga109 null heuristic.
- A: a 50-balloon check of MangaSeg tails.
- B: the identity note's list (about 500 card ids, name lists, a scene id per box), plus the speaker of every off-panel line in those episodes.

## 7. Risks and rejected alternatives

**A, three biggest risks:**
1. **The domain gap eats the gain.**
   - Manga balloons, tails and frames differ from webtoon gutters and European layouts.
   - CoMix measured Magi at 57.2 R@#text on PopManga against 13–15 off manga (prior note).
   - Mitigation: the rule prior, the safety gate, and a dev set in English colour.
2. **Null labels are noisy.** Unlinked Manga109 text mixes narration, off-page speech and unknowns; thought and caption are unlabelled.
   - Mitigation: weak labels plus manufactured off-panel examples, and our Transcribe kind at test.
   - If the 200-text audit finds the heuristic under about 85% right, train a single "no card" null and let the kind decide narrator vs SFX **[estimate threshold]**.
3. **We cannot measure the win.** Five errors on P&C 36, with the rules tuned in-sample. Without the fresh set, any claim is noise.

**A, rejected:**

| Alternative | Reason |
|---|---|
| A VLM chooser (Haiku, Sonnet, Opus) | Measured below the rules: 105 and 99 vs 116; Opus 44 vs 48 on hard boxes |
| An LLM registry like SSIC as the product | GPT-5.4 per book; 56.72% with OCR'd input. Its idea (dialogue registry) moves into B |
| Fine-tuning Magi | Non-commercial weights |
| A rule-feature learner alone | LR 91.7% < rules 94.6% |
| GNN | At ≤190 tokens, full attention with edge biases covers it |

**B, three biggest risks:**
1. **Cascade errors.** A wrong speaker edge merges two characters. IMF shows link quality is worth 11.5 points of character ID. Out-of-fold training and probability-scaled edges limit this, but do not remove it.
2. **No in-domain identity labels yet.** Every B number before about 500 cards are labelled is manga-only.
3. **Black-and-white training, colour test.** Colour is the strongest webtoon cue and B never trains on it. Late fusion's weight is fitted on a few hundred cards.

**B, rejected:** as in the identity note (slots, kNN-GNN, LLM pseudo-label loops, closed-set classifiers, Magi encoders), plus:

| Alternative | Reason |
|---|---|
| Joint A+B trunk | §5 |
| More than one A ↔ B round | IMF Hard: 51.3 → 49.8 at iteration 3 |

## Sources

- Manga109 annotations: https://ar5iv.labs.arxiv.org/html/2005.04425
- Manga109-v2026: https://arxiv.org/html/2605.21182v2
- Manga109Dialog: https://arxiv.org/html/2306.17469v2
- COO: https://github.com/ku21fan/COO-Comic-Onomatopoeia · https://arxiv.org/abs/2207.04675
- MangaSeg:
  - paper: https://openaccess.thecvf.com/content/CVPR2025/papers/Xie_Advancing_Manga_Analysis_Comprehensive_Segmentation_Annotations_for_the_Manga109_Dataset_CVPR_2025_paper.pdf
  - supplement: https://openaccess.thecvf.com/content/CVPR2025/supplemental/Xie_Advancing_Manga_Analysis_CVPR_2025_supplemental.pdf
  - data: https://huggingface.co/datasets/MS92/MangaSegmentation
- Magiv2: https://arxiv.org/html/2408.00298 · Magiv3: https://arxiv.org/html/2503.23344v1
- IMF: https://arxiv.org/html/2404.13993v4
- SSIC: https://aclanthology.org/2026.emnlp-main.2632/ (PDF read in full)
- Zhang & Hotta 2025, IEEE MultiMedia 32(3):50–59 (cited by SSIC; not read)
- SuperGlue: https://arxiv.org/abs/1911.11763 · Graphormer: https://arxiv.org/abs/2106.05234 · Standley et al.: https://arxiv.org/abs/1905.07553
- Zumi measurements: `pipeline/segment/speakers.py` docstrings; `experiments/speaker_eval.py`
