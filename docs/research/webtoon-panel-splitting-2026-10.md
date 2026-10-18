# Splitting webtoon strips into panels, and sample data we may use — 2026-10-17

Research date: 2026-10-17. Method: primary sources only where they could be reached — GitHub repos (stars, last push and licence read from the GitHub API on the research date), Hugging Face model and dataset cards, arXiv/CVF papers, the WEBTOON 2021 upload notice and Creators Resource Handbook, peppercarrot.com's `0_sources` directory listings (one text-free page downloaded and measured), manga109.org and David Revoy's licence posts. Pages behind Cloudflare or bad TLS (Digital Comic Museum, Comic Book Plus, WEBTOON Zendesk, `git.univ-lr.fr`) are reported from secondary excerpts and marked **[unverified]**. Nothing here was run on an image; every "would work on sketches" judgement is reasoning, not measurement, and is labelled as such. Context: `docs/architecture/decisions.md` (pipeline is per panel; text is data, never baked into images).

## Executive summary

1. **No webtoon-specific panel-segmentation paper, model or dataset exists in the open** (searched arXiv/CVF/HF/Roboflow for "webtoon", "manhwa", "vertical comic"). Everything is page-based manga/comics; the one YOLO model card that mentions vertical webtoons lists them as a case it "may not generalize well to".
2. **For a strip with blank gutters, a 1-D row projection is enough and is what every webtoon tool does**: a row is a gutter if every pixel is within tolerance of the background colour; a speech bubble never fakes a gutter because the row also contains art. `stripcut` (Rust, MIT, pushed 2026-09-23) implements exactly this with `--gutters --json`; we should reimplement the ~100 lines in the pipeline rather than depend on a 0-star repo.
3. **Bleeding/borderless panels need a learned detector and the only strong open one is Magi** (panel AP 0.936 on Manga109 vs 0.513 for zero-shot Grounding DINO; 78.5 mean mAP across five comic datasets), but Magi/Magiv2/Magiv3 are **non-commercial** ("personal, research, non-commercial, not-for-profit"; other use by arrangement with the author). The Apache-2.0 alternative is `mosesb/best-comic-panel-detection` (YOLOv12x, mAP50 0.991 on its own validation set, rectangles only).
4. **Bubble detection is solved and permissively licensed**: `ogkalu/comic-speech-bubble-detector-yolov8m` (Apache-2.0, ~8k images incl. webtoon, resized not cropped so tall inputs work) and `Kiuyha/Manga-Bubble-YOLO` (Apache-2.0, mAP50 0.961, 27.5 ms on a T4). The text-mask models (`comic-text-detector`, `AnimeText_yolo`) are GPL-3.0.
5. **Rough pencil sketches break every learned detector's training distribution and nothing in the literature covers them.** The row projection survives if it is run on normalised ink density rather than exact colour; the realistic plan is a delivery spec (blank gutter ≥ 150 px, nothing bleeding, bubbles inside panels or in a script) plus a per-panel fallback.
6. **Pepper&Carrot is no longer usable for the demo.** Pages are CC BY 4.0 with text-free `gfx-only` renders at 2481×3504 px and bubble positions in SVG (perfect splitter ground truth), but David Revoy added "AI derivation prohibited" on 2026-10-08, retroactively. Use it only to test the splitter and bubble detector, never through the generative steps.
7. **The clean sample data is Golden Age public domain via the COMICS dataset** (1.2M panel crops with panel and textbox boxes, OCR CSV; code MIT) — we synthesise webtoon strips from its panels with known cut positions. Manga109-s (87 volumes cleared for commercial use, application form) and MangaSeg are for benchmarking detectors only.
8. **Ask the artist for per-panel files first; if strips, WEBTOON format** (800 px wide, slices ≤ 1280 px, JPG/PNG, ≤ 2 MB per image, ≤ 100 images / 20 MB per upload, per the 2021 notice and Handbook), with dialog in a script file rather than lettered, since our format stores text as data.

---

## 1. Classical splitters (rule-based)

Stars/last push/licence from the GitHub API, 2026-10-17. "Bleed" = behaviour when panels touch or art crosses the gutter. "Bubbles" = behaviour with floating bubbles between panels.

| Tool | What it does | Method | Bleed | Bubbles | Licence | Stars · push |
|---|---|---|---|---|---|---|
| [stripcut](https://github.com/printemps-tokyo/stripcut) (Rust) | Cuts an 800×N strip into upload tiles at gutters; `--gutters` lists gutter runs, `--json` report | Background = mode colour of edge rows/cols (transparent counts as bg); row is gutter if all pixels within `--tolerance` (6/channel); runs ≥ `--min-gutter` (12 px) | No gutter → cuts at `--max-height`, flags `HARD-CUT`, never hides it | Bubble row contains art, so not a gutter (stated in README) | MIT | 0 · 2026-09-23 |
| [kumiko](https://github.com/njean42/kumiko) (Python) | Page → JSON of panel boxes, numbered LTR or `--rtl`; `-s` saves crops; Gradio UI in `avan06/KumikoMangaPanelExtractor` | OpenCV contour detection on thresholded page; non-white/black bg since v1.5 | Fails; "detect non-framed panels" and "separate intertwined panels" are open roadmap items | Not addressed | "Other" (no SPDX) | 203 · 2024-12-22 |
| [panelizer](https://github.com/hummat/panelizer) (Python) | CV first (adaptive threshold, contours, XY-cut, confidence), ML fallback (YOLOv12 panels, SAM 2/3 polygons, DeepPanel) | Two-stage | CV "fails on borderless panels, irregular layouts, art bleeding into gutters" → ML stage | Not addressed | MIT | 6 · 2026-08-01, "development paused indefinitely" |
| [ManhwaFormatter](https://github.com/eskutcheon/ManhwaFormatter) | Re-stacks badly cropped webtoon tiles, exports CBZ/PDF | Low-variance horizontal regions | Not handled | Not addressed | MIT | 4 · 2025-06-22 |
| [cropybara](https://github.com/aaa4xu/cropybara) (TS, browser) | Stitch tiles into one strip, suggest cuts, drag to adjust | Projection + manual | Manual | Manual | none | 5 · 2026-05-05 |
| [comics-splitter](https://github.com/Ajira-FR/comics-splitter), [Manga-Panel-Extractor](https://github.com/pvnieo/Manga-Panel-Extractor) | Page → panels for e-readers | Contours / gutter cuts | Not handled | Not addressed | none / Apache-2.0 | 27 · 2024-07 / 17 · 2023-12 |
| [StitchTool](https://github.com/Aeonss/StitchTool) (Java) | Creator utility: stitch, split at fixed height, denoise, upscale, watermark | Fixed-height split, not panel-aware | n/a | n/a | MIT | 71 · 2026-04-08 |

Literature behind these: Ho, Burie, Ogier 2012 (region growing + morphology; 100 % on simple pages, 85.7 % on complex) and Stommel 2012 (outline-based, tolerant of textured backgrounds); the 2019 Bengali-comics paper notes all of them "do not perform well in case of complex panel layout or the absence of white margin". That sentence is the whole story for bleeding webtoon panels.

## 2. Learned detectors

| Model | Detects | Input | Evidence | Licence | Notes |
|---|---|---|---|---|---|
| [Magi](https://github.com/ragavsachdeva/magi) v1 (CVPR 2024, ResNet-50 + DETR-style) | panels, characters, text; reading order; speaker matching; OCR | shorter side → 800 px, long side capped at 1333 px (a tall strip must be tiled) | Manga109 panel AP **0.9357** vs Grounding-DINO 0.5131; text AP 0.92 on PopManga. CDF cross-dataset panel mAP (DCM/Comics100/eBD/M109/Pop): **89.0/73.9/62.1/65.3/92.8**, mean 78.5 | README: "academic research purposes only" | Trained on B&W manga; example code converts input to grayscale |
| [Magiv2](https://huggingface.co/ragavsachdeva/magiv2) (ACCV 2024) | + tails, chapter-wide names via character bank | pages as RGB arrays, CUDA | best speaker diarisation in the series (paper) | "unrestricted use in personal, research, non-commercial, and not-for-profit endeavors"; else email author | |
| [Magiv3](https://huggingface.co/ragavsachdeva/magiv3) (ICCV 2025, Florence-2 based, 0.8B) | panels, characters, text, tails, OCR, caption grounding | image + task prompt | paper: higher detection precision than v2 at similar recall; no numbers on card | same as v2 | ~2.4k downloads/month |
| [mosesb/best-comic-panel-detection](https://huggingface.co/mosesb/best-comic-panel-detection) (YOLOv12x) | one class "Comic Panel" | 640 px training | mAP50 **0.991**, mAP50-95 0.985 on its own Roboflow validation set (size not stated) | Apache-2.0 | "may struggle with highly irregular or overlapping panel shapes"; no webtoon mention |
| [ShadowB/Manga109-panel-balloon-text-yolov26-segmentation](https://huggingface.co/ShadowB/Manga109-panel-balloon-text-yolov26-segmentation) (YOLO26s-seg) | frame, text, balloon masks | 1280 px | Manga109 val (12 books, 1,468 imgs): mask mAP50 **0.970**, box mAP50 0.975 | MIT (training data has its own terms) | card: may not generalise to "Western comics, colored comics, and vertical webtoons" |
| Faster R-CNN / YOLO / Grounding DINO baselines ([CDF, ICDAR 2024](https://arxiv.org/html/2407.03540v1)) | panel | pages | mean panel mAP 79.5 / 74.3 / 64.7 (zero-shot) | various | Faster R-CNN beats Magi on Western pages (DCM 86.3, Comics100 88.9), Magi wins on manga |
| [SAM 3](https://huggingface.co/facebook/sam3) (0.9B, gated, licence "other") | any noun phrase, e.g. "comic panel" | image | no comic evaluation anywhere **[unverified for panels]** | Meta licence | already in our pipeline for cut-outs (SAM 3.1); worth one experiment, not a plan |

Datasets with panel labels: Manga109 (10,602 pages, panel boxes), [MangaSeg](https://huggingface.co/datasets/MS92/MangaSegmentation) (CVPR 2025, >700k masks on 10,130 pages; gated; "academic and commercial use" with the credit "Copyrighted by Minshan Xie"), [CoMix](https://arxiv.org/html/2407.03550) (NeurIPS 2024; public val split of 466 images, test via server; images fetched from original sources), COMICS (panel + textbox boxes, section 5), DCM772 (772 Golden Age pages, panel/character/text). Webtoon-specific: only a Roboflow set, "[Webtoon Text Detection](https://universe.roboflow.com/furoran-shikan-etye1/webtoon-text-detection)" (290 images, text boxes only, ODbL).

## 3. Speech bubbles and text

| Model | Output | Data | Evidence | Speed | Licence |
|---|---|---|---|---|---|
| [ogkalu/comic-speech-bubble-detector-yolov8m](https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m) | bubble boxes | ~8k manga/webtoon/manhua/Western images, trained at 1024, "resized, not cropped" so extreme aspect ratios work | none reported; used by 7 Spaces (translators) | n/a | Apache-2.0 |
| [Kiuyha/Manga-Bubble-YOLO](https://huggingface.co/Kiuyha/Manga-Bubble-YOLO) (YOLO26n/s, NMS-free) | text/bubble boxes | 5,595 imgs (Manga109-s + Mangadex EN/VI, Mangadex part auto-labelled by Magi) | test 600 imgs: mAP50 **0.947 / 0.961**, mAP50-95 0.765 / 0.802 | 11.0 / 27.5 ms per image, T4, 1280 px | Apache-2.0 |
| [kitsumed/yolov8m_seg-speech-bubble](https://huggingface.co/kitsumed/yolov8m_seg-speech-bubble) | bubble masks (.pt + ONNX) | not read | card admits wavy mask edges | n/a | not checked |
| [comic-text-detector](https://github.com/dmMaze/comic-text-detector) (YOLOv5 + UNet mask + DBNet lines; BallonsTranslator) | text mask, text lines, blocks | not published | none published | n/a | GPL-3.0; 386 stars, last push 2023-08 |
| [deepghs/AnimeText_yolo](https://huggingface.co/deepghs/AnimeText_yolo) (YOLO12, arXiv 2510.07951) | text blocks in anime/comic scenes | AnimeText: ~735k images, 4.2M blocks | paper benchmark | n/a | model GPL-3.0 (gated), dataset CC BY-NC-SA 4.0 |

For Zumi the bubble detector is a cross-check and a mask source for step 2 ("Remove dialog"); the Understand step already asks the vision model for bubble boxes and speakers. A YOLO box per bubble costs tens of milliseconds and gives a hard geometric answer the LLM can be checked against.

## 4. Reading order

- **Magi** (Appendix B of [2401.10224](https://arxiv.org/html/2401.10224v2)): panels are nodes in a DAG with "read before" edges from strict above/below and right/left relations; overlapping panels are morphologically eroded until disjoint; ambiguous top-left/bottom-right pairs are resolved by trying a horizontal cut, then a vertical one; topological sort gives the order; text inside a panel sorted by distance to the top-right corner (manga) — CoMix uses top-left for Western comics. Manga109Dialog uses a rule-based recursive split of frame boxes and reports it is reliable enough to be assumed correct.
- **Webtoons are the easy case**: one column, top to bottom. Our own rule (design, not measured): sort panels by top edge; two panels whose vertical ranges overlap > 50 % are a side-by-side pair, ordered left→right (manhwa and webtoon are LTR); bubbles sorted by top edge then left edge; a bubble lying in a gutter is attached to the panel whose edge is nearest, ties to the panel above (it is almost always a continuation).

## 5. Rough pencil sketches: what survives

No paper, model or tool found for panel detection on sketches/storyboards (searched "storyboard", "rough sketch", "pencil", "sketch layout analysis"). Reasoning from the mechanisms:

| Stage | Finished art | Rough sketch | Why |
|---|---|---|---|
| Row projection (gutter = rows equal to bg) | works | works **only** if run on normalised ink density: divide by a large-kernel blur of the page (removes paper shading and scanner vignette), threshold ink, then gutter = rows with ink fraction < 0.5 % for ≥ 60 px | exact-colour matching fails on paper texture; density is robust to low contrast but needs the artist to leave the gutter truly empty |
| Contour/XY-cut (kumiko) | works with borders | fails | sketch borders are broken, double-stroked or absent |
| YOLO panel / bubble detectors | works | expect degradation **[unverified]** | trained on inked, high-contrast pages; faint grey strokes at 640–1280 px look like noise. Must be measured on the artist's first sketches, cheap to do |
| Magi | works on manga | unknown | same distribution argument; and licence blocks production use anyway |
| Vision LLM (our Understand step) | works | likely the most robust **[unverified]** | it reads the sketch semantically; we can ask for approximate panel boxes and use them to seed the cut |

Practical implication: for sketches the splitter should be a projection on ink density plus a human-confirmable preview, and the delivery spec (section 7) should make the gutters unambiguous.

## 6. Sample data: licences

| Source | Content | Licence / terms | Fit |
|---|---|---|---|
| [Pepper&Carrot](https://www.peppercarrot.com/en/license/index.html) `0_sources/epNN_*/` | 40 episodes; `hi-res/gfx-only/*.jpg` text-free pages (measured ep39 P01: **2481×3504 px**), `hi-res/gfx-only/lossless/*.png`, `lang/<xx>/*.svg` bubbles as Inkscape vectors over `gfx_*.png`, `zip/*_art-pack.zip` (ep39: 1.04 GB, Krita layers) | CC BY 4.0 (MiniFantasyTheater CC BY-SA 4.0). **2026-10-08: "AI derivation prohibited on all my art, lore, stories, and comics"**, "backport it to previous artworks and comics"; no research/demo exemption; no permission process ("I'm rejecting requests") | Splitter + bubble-detector tests only (SVG gives bubble ground truth). **Not** for regeneration, SAM/LaMa/depth experiments or the demo |
| [COMICS](https://obj.umiacs.umd.edu/comics/index.html) (Iyyer et al., CVPR 2017) | 1.2M panel crops from ~4k Golden Age books (Digital Comic Museum), `panels_annotations.zip`, `textboxes_annotations.zip`, OCR CSV, page images | Code MIT; data has no licence file; source is DCM's volunteer-researched public domain (pre-1960, excluded publishers) **[DCM terms unverified: site behind Cloudflare]** | **Primary.** Panels + text boxes already cut; we stack them into synthetic 800-px strips with known gutters and bubbles |
| DCM772 (Nguyen, Rigaud, Burie 2018) | 772 pages, 27 books, panel/character/text/face boxes | hosted at `git.univ-lr.fr`, "public domain" per the paper **[unverified]** | Page-level eval of panel detectors |
| [Manga109 / Manga109-s](http://www.manga109.org/en/) | 109 vols, 21,142 pages (site) / 10,602 double pages; boxes for frames, text, faces, bodies | Manga109: "academic, non-commercial purposes", institutional email. Manga109-s: 87 volumes "approved for commercial use", Google-form application, no redistribution, credit "©Author" | Benchmark only; do not ship |
| [MangaSeg](https://huggingface.co/datasets/MS92/MangaSegmentation) | >700k masks (frame, balloon, text, character, face) on Manga109 | gated; "academic and commercial use" with credit line; images still need Manga109 | Fine-tune a panel/balloon model if ever needed |
| [PopManga test](https://huggingface.co/datasets/ragavsachdeva/popmanga_test) | annotations only, images downloaded from MangaPlus on first run | gated; research framing; copyrighted manga | No |
| [eBDtheque](https://ebdtheque.univ-lr.fr/registration/) | 100 pages, panels/balloons/text lines | academic-email registration, "scientific use" | No (small, gated) |
| [CoMix](https://github.com/emanuelevivoli/CoMix-dataset) val | 466 images across the above | research; images from original sources | No |
| CC-licensed webtoon series | searched Canvas/Tapas/itch.io/GitHub | none found; "Tales of Alvina" not found at all | — |

Golden Age panels are Western, paged and lettered; they are a stand-in for the mechanics (gutters, bubbles, order), not for the look. The only data that represents the real distribution is the artist's first sketches — ask for three panels this week, before the splitter is written.

## 7. Platform specs the artist should match

| Platform | Width | Height per image | Size | Formats | Source |
|---|---|---|---|---|---|
| WEBTOON (global, CANVAS) | 800 px | ≤ 1280 px; taller uploads "automatically sliced" | ≤ 2 MB/image; ≤ 20 MB and ≤ 100 images per upload | JPG, JPEG, PNG | [Notice 1766, 2021-05-18](https://www.webtoons.com/en/notice/detail?noticeNo=1766) (800×1280, auto-slice); [Creators Resource Handbook](https://webtoons-static.pstatic.net/creator101/en/pdf/Creators-Resource-Handbook-Updated.pdf) for size/count/format (PDF too large to fetch; figures from its indexed text) **[partly unverified]** |
| Naver 도전만화 | 690 px | 1280 px per slice **[unverified]** | 5 MB/image, 50 MB/episode | JPG, GIF (no PNG) | [Clip Studio](https://www.clipstudio.net/drawing/archives/157017), toonslicer.com; no Naver help page reachable **[unverified]** |
| LINE Manga indies / comico / Tapas | 800 rec. / 800 rec. / 940 | ≤ 10,000 / ≤ 10,000 / n.p. | 2 MB / 2 MB + 20 MB ep. / 10 MB | png, jpg | stripcut presets, "verified 2026-08-12" by its author **[secondary]** |

Gutter guidance attributed to WEBTOON (via Clip Studio tips, **[secondary]**): ≥ 200 px between panels on an 800-px canvas, 600–1,000 px for scene changes. These numbers make the row projection trivially reliable on finished webtoon art.

---

## 8. Test data pulled (2026-10-18)

Research-only set for scoring the splitter and the bubble detector. Downloaded with Zehina/Webtoon-Downloader 2.4.0 (MIT) into `pipeline/.data/webtoons/<slug>/<episode>/NN.jpg`, one folder per episode, one file per served slice. The folder is gitignored.

Rules, decided with the user:
- Copyrighted material. It never enters a generative step, never appears in the demo, trailer or submission, never leaves this machine and is deleted once the intake stage is scored. The competition entry uses artist material and public domain only.
- Three episodes per series (first, a mid-run one, the latest) so layout drift across a run is covered. Seven WEBTOON Originals ordered by views on 2026-10-18 plus two Canvas titles from the popular list:

| Series | Views | Subs | Layout case |
|---|---|---|---|
| Lore Olympus | 1.4B | 6.6M | borderless colour fields, no real gutters |
| unOrdinary | 1.4B | 6.3M | clean white gutters (baseline) |
| Tower of God | 1.3B | 4.2M | bordered panels, dense action |
| True Beauty | 1.0B | 7.5M | clean gutters, romance layout |
| Omniscient Reader | 599M | 4.5M | bleeding action, panels crossing slices |
| Cursed Princess Club | 291M | 2.3M | simple art, bubbles in gutters |
| Sweet Home | 272M | 3.5M | dark backgrounds, black gutters |
| Witch And Her Corgi (Canvas) | – | – | amateur layout |
| The Housecat Philosophy (Canvas) | – | – | amateur layout |

Measured on Cursed Princess Club ep. 1: 58 slices, all 800 px wide, 1005–1280 px tall, 73 965 px total. The splitter input is therefore the vertical concatenation of an episode's slices; slice seams can fall inside a panel, so the splitter must never treat a seam as a cut.

Let's Play (Mongie) was planned but is no longer served by WEBTOON (connect error on its title page); True Beauty took its slot.

## Recommendation

### A. Splitter

**Finished art (strip in).** Three stages, all in `pipeline/`, Python, CPU for stages 1–2:
1. *Gutter projection.* Background = mode of the outer 8 px of the strip; per row, fraction of pixels farther than tolerance 12/channel from it; gutter = run of ≥ 40 rows with fraction < 0.2 %; emit slabs between gutters. This is stripcut's algorithm; reimplement (≈100 lines, NumPy) so the pipeline has no Rust dependency and can emit `panels.json`. A slab taller than 2.5× its width or with no gutter for > 3,000 px is flagged `bleed`.
2. *Bubbles.* Run `Kiuyha/Manga-Bubble-YOLO` (s) at 1280 px on each slab (and on a 400-px margin above and below, to catch gutter bubbles); boxes feed the Understand prompt as hints and step 2's removal mask; attach gutter bubbles to the nearest panel edge.
3. *Bleed slabs only.* Run `mosesb/best-comic-panel-detection` (Apache-2.0) at 1024 px; accept boxes with confidence ≥ 0.5 that cover ≥ 40 % of the slab width; if none, keep the slab as one panel and flag for review. Do **not** use Magi in production (non-commercial); keep it as an offline reference to measure our stage 1+3 against, and try SAM 3 with "comic panel" once, logged to W&B.
Evaluation: 200 synthetic strips from COMICS panels (6–12 panels, gutters 150–400 px, white and tinted backgrounds, 20 % of bubbles placed in gutters, 10 % of gutters removed to simulate bleed); report panel-boundary recall at ±20 px and bubble-to-panel attachment accuracy.

**Rough sketches.** Stage 1 on ink density: normalise (`img / gaussian_blur(img, σ=width/8)`), threshold, gutter = run ≥ 60 rows with ink fraction < 0.5 %. Skip stage 3 (not trained on sketches); send bleed slabs to the artist. Stage 2 runs but its boxes are advisory; the Understand step's boxes win on disagreement. Fallbacks, in order: (i) artist adds a full-width 2-px cut line between panels, detected as the only row with ink fraction > 95 %; (ii) artist delivers per-panel files — then the splitter is skipped entirely, which is the recommended default anyway.

### B. Sample data to pull now

- COMICS: `raw_panel_images.tar.gz`, `panels_annotations.zip`, `textboxes_annotations.zip`, `COMICS_ocr_file.csv` from https://obj.umiacs.umd.edu/comics/index.html — "Code MIT (github.com/miyyer/comics); images from Digital Comic Museum public-domain Golden Age scans; cite Iyyer et al., CVPR 2017." Build the synthetic strip generator on it; it is also the only candidate safe for the public demo (pre-1960 US public domain, credit DCM uploader where listed).
- Pepper&Carrot ep39 for splitter/bubble ground truth only: `https://www.peppercarrot.com/0_sources/ep39_The-Tavern/hi-res/gfx-only/` and `lang/en/*.svg` — "Pepper&Carrot © David Revoy, CC BY 4.0, AI derivation prohibited (2026-10-08): no generative step, not in the demo."
- Manga109-s only if we want a detector benchmark: apply via the Google form linked from manga109.org; "87 volumes approved for commercial use; no redistribution; credit ©Author."
- Skip PopManga, eBDtheque, CoMix, DCM772 until a licence file is actually read.

### C. Delivery spec for the artist

1. **Per panel, one file**: `epNN/pNN.png`, RGB(A), ≥ 1600 px on the long side, sRGB, no lettering, no bubble text. Bubble outlines are allowed (we detect and inpaint them) but a bubble-free panel plus the script is better.
2. **Script**: `epNN/script.md` or CSV with `panel, speaker, text, anchor (approx. x%, y%), kind (speech | thought | narration)`. This is what `bubbles[k]` in the `.zumi` manifest needs; lettering inside the art is thrown away.
3. **If strips instead**: WEBTOON CANVAS format — 800 px wide (1600 is fine, we downscale), PNG or JPG q ≥ 90, one tall file or ≤ 1280-px slices named in order; blank gutters ≥ 150 px, same flat colour as the margins, nothing crossing them; no bubbles in gutters; side-by-side panels only if separated by a vertical blank ≥ 60 px.
4. **Sketch scans**: ≥ 300 dpi or ≥ 2000 px wide, levels adjusted so paper is near white and pencil is clearly darker; no spiral-binding shadow; one page per file.
5. **Order and ids** are the file order; a `panels.json` sidecar (`[{id, file, cutY?}]`) is optional and overrides detection.

## Sources

- stripcut — https://github.com/printemps-tokyo/stripcut · kumiko — https://github.com/njean42/kumiko · panelizer — https://github.com/hummat/panelizer · ManhwaFormatter — https://github.com/eskutcheon/ManhwaFormatter · cropybara — https://github.com/aaa4xu/cropybara · comics-splitter — https://github.com/Ajira-FR/comics-splitter · Manga-Panel-Extractor — https://github.com/pvnieo/Manga-Panel-Extractor · StitchTool — https://github.com/Aeonss/StitchTool
- Magi repo — https://github.com/ragavsachdeva/magi · The Manga Whisperer (CVPR 2024) — https://arxiv.org/html/2401.10224v2 · Magiv2 card — https://huggingface.co/ragavsachdeva/magiv2 · Magiv3 card — https://huggingface.co/ragavsachdeva/magiv3 · From Panels to Prose (ICCV 2025) — https://arxiv.org/pdf/2503.23344 · PopManga test — https://huggingface.co/datasets/ragavsachdeva/popmanga_test
- Comics Datasets Framework (ICDAR 2024) — https://arxiv.org/html/2407.03540v1 · CoMix (NeurIPS 2024) — https://arxiv.org/html/2407.03550 · MangaSeg (CVPR 2025) — https://huggingface.co/datasets/MS92/MangaSegmentation · Manga109Dialog — https://arxiv.org/pdf/2306.17469
- best-comic-panel-detection — https://huggingface.co/mosesb/best-comic-panel-detection · Manga109 YOLO26 seg — https://huggingface.co/ShadowB/Manga109-panel-balloon-text-yolov26-segmentation · SAM 3 — https://huggingface.co/facebook/sam3, https://arxiv.org/pdf/2511.16719
- Bubble/text: https://huggingface.co/ogkalu/comic-speech-bubble-detector-yolov8m · https://huggingface.co/Kiuyha/Manga-Bubble-YOLO · https://huggingface.co/kitsumed/yolov8m_seg-speech-bubble · https://github.com/dmMaze/comic-text-detector · https://huggingface.co/deepghs/AnimeText_yolo · Roboflow Webtoon Text Detection — https://universe.roboflow.com/furoran-shikan-etye1/webtoon-text-detection
- Classical literature: Ho, Burie, Ogier 2012 — https://ebdtheque.univ-lr.fr/download/articles/2012_Ho_Panel%20and%20speech%20balloon%20extraction%20from%20comic%20books.pdf · Stommel 2012 — https://link.springer.com/chapter/10.1007/978-3-642-33564-8_76 · Bengali comics 2019 — https://arxiv.org/pdf/1910.09233
- Data: COMICS downloads — https://obj.umiacs.umd.edu/comics/index.html, https://github.com/miyyer/comics · Manga109 — http://www.manga109.org/en/ · Manga109-s on HF — https://huggingface.co/datasets/hal-utokyo/Manga109-s · eBDtheque — https://ebdtheque.univ-lr.fr/database/ · DCM772 (IAPR TC10 listing) — https://iapr-tc10.univ-lr.fr/?page_id=71 · Digital Comic Museum forum rules (secondary) — https://digitalcomicmuseum.com/forum/index.php/topic,1806.0/wap2.html
- Pepper&Carrot: licence page — https://www.peppercarrot.com/en/license/index.html · sources — https://www.peppercarrot.com/0_sources/ · AI-derivation update (2026-10-08) — https://www.davidrevoy.com/article1178/license-update-ai-derivation-prohibited-on-all-my-art-lore-stories-and-comics · page size post — https://www.davidrevoy.com/article543/printer-friendly-full-refactoring · translation repo — https://framagit.org/peppercarrot/webcomics
- Platform specs: WEBTOON notice 1766 — https://www.webtoons.com/en/notice/detail?noticeNo=1766 · Creators Resource Handbook — https://webtoons-static.pstatic.net/creator101/en/pdf/Creators-Resource-Handbook-Updated.pdf · Clip Studio (Naver/Daum specs) — https://www.clipstudio.net/drawing/archives/157017 · Clip Studio WEBTOON tips (gutter px) — https://tips.clip-studio.com/en-us/articles/9420 · toonslicer Naver page — https://toonslicer.com/naver-webtoon
