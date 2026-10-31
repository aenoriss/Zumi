# Frame and bubble reading order: what the established methods do — 2026-10-27

Research date: 2026-10-27. Frame and bubble *detection* is covered in [webtoon-panel-splitting-2026-10.md](webtoon-panel-splitting-2026-10.md), and speaker attribution in [comic-speaker-attribution-2026-10.md](comic-speaker-attribution-2026-10.md). This note covers only the order in which frames and bubbles are read.

**Method.**
- **Code read in full.**
  - Magi v1 and v2 ordering code: `utils.py` on the HuggingFace model repos ([magi](https://huggingface.co/ragavsachdeva/magi/blob/main/utils.py), [magiv2](https://huggingface.co/ragavsachdeva/magiv2/blob/main/utils.py)). The two files are identical in their ordering functions.
  - Kumiko at [`9d587ae`](https://github.com/njean42/kumiko/tree/9d587ae9498bc84dfda06fc19c6ad89f421bec14) (2024-12-22).
  - Manga109's [panel-order-estimator](https://github.com/manga109/panel-order-estimator/tree/623509750a69debf240fb406b507653da4d7b672) at `6235097` (2022-11-14), which implements Kovanen & Aizawa's frame order.
  - manga-image-translator at [`d6de6ab`](https://github.com/zyddnys/manga-image-translator/tree/d6de6ab62a7be6afc0d07a3184149cdefbcd32f2) (2026-10-11).
  - ComicRack CE (`ImageDisplayControl.cs`, via the GitHub API).
- **Papers read in full text:**
  - Sachdeva & Zisserman 2024 (Magi);
  - Hinami et al. 2021;
  - Tanaka et al. 2007;
  - Iyyer et al. 2017 (COMICS);
  - Vivoli et al. 2024 (CoMix);
  - Cohn 2013;
  - Ikuta et al. 2023;
  - Wang et al. 2021 (LayoutReader);
  - the eBDtheque poster.
- **Specs and first-party docs:** EPUB Region-Based Navigation 1.0, Amazon KDP's Region Magnification page, the comiXology press release, ACBF's feature list, and the Llama 4 model card.
- **Abstract or secondary only:** Kovanen & Aizawa 2015 (paywalled, never read in full), Guérin 2012/2017 (HAL refused the download), Arai & Tolle 2010, Cohn & Campbell 2015, Kirtley et al. 2022.
- **Run.** Synthetic layouts only (§8.4). No comic data was downloaded, and the images that came with the cloned repos were deleted unseen.
- **Labels.** **[inference]** = my reasoning. **[measured]** = my run, on synthetic rectangles or masks, not on P&C. **[unverified]** = abstract only, secondary, or not found.

**Terms.**
- **Z-path:** rows top to bottom, each left to right.
- **Blockage:** Cohn's term for two or more stacked frames beside one tall frame. The user's failing example is a blockage.
- **Guillotine cut:** a straight line that crosses the whole region without cutting a frame. It is also called the XY-cut.

## Answer

1. **Why Zumi's order is wrong.** `reading()` builds rows greedily. A frame joins the current row when it overlaps the *row's first frame* by more than half the smaller height, and sits beside every frame already in the row.
   - Take the user's layout: A top-left, B bottom-left, C tall on the right. C overlaps A by 100 % of A's height, so C joins A's row. B then starts a new row. The result is **A C B** **[measured, synthetic spans]**.
   - It stays A C B when C starts 40 px lower or 40 px higher than A. That makes it a rule error, not a threshold to tune.
   - The rule has no notion of a gutter that spans the whole region. That is exactly what tells a reader to finish the left column first.
   - manga-image-translator's `_sort_panels_fill` has the same flaw. Its docstring says it "keeps vertically stacked panels together", but the code groups frames by top-y and also returns **A C B** **[measured]**.
   - The same `reading()` orders bubbles inside a frame, so bubbles inherit the bug.
2. **The established core is a recursive guillotine cut, horizontal cuts first.**
   - Three lines of work use it:
     - Tanaka et al. 2007 ("most of comic pages can be divided into scene frames by recursive guillotine cut"; order = depth-first walk of the cut tree);
     - Kovanen & Aizawa 2015, as implemented in Manga109's estimator;
     - Hinami et al. 2021 (91.9 % of 258 manga pages fully correct).
   - On a grid it gives the Z-path. When a tall frame blocks every horizontal cut it falls back to a vertical cut, so it reads **A B C**.
   - That matches the majority of human readers: in Cohn 2013, 91 of 145 participants took the blockage path, against 40 of 145 for the Z-path.
3. **Non-guillotine layouts are where every method fails or degrades.** These are overlapping frames, diagonal gutters, insets and pinwheels.
   - Tanaka puts insets out of scope.
   - Manga109's estimator gives an inseparable group a single order index.
   - Hinami's 8.2 % failures are "diagonally separated, multiple frames overlapping".
   - Magi replaces the global cut with pairwise "largely above / largely right-of" tests and a topological sort, because cuts "fail in the case of overlapping panels".
4. **Bubble order in published systems is two steps.**
   - (a) Assign each text to one frame: largest box intersection (Magi) or centre inside (manga-image-translator); nearest frame otherwise.
   - (b) Sort the texts inside the frame by their distance to the frame's top-right corner (manga: Magi, Hinami) or top-left corner (comics: CoMix's adaptation).
   - Kovanen & Aizawa report "over 95 % transition accuracies" with a three-layer method that I could not read **[unverified]**.
   - I found no published rule for bubbles that straddle a gutter, or for tail-linked chains. The letterer's convention is that joined balloons are "of the same thought process" (Blambot), so a joined cluster is read as a unit.
5. **Commercial readers do not infer order; people author it.**
   - Kindle Panel View: a per-region `ordinal`, the "reading order of the magnification areas".
   - EPUB Region-Based Navigation: an ordered `<ol>` of regions, with balloons nested inside panels.
   - comiXology's Guided View: made with "the actual tools we use at comiXology".
   - ACBF: frames in document order, plus the "reading order of text areas".
   - ComicRack CE's part view is a viewport-sized grid, not detected panels.
6. **Recommendation for Zumi:**
   - frames: recursive cut on masks, horizontal first, with a 15 % crossing tolerance; insets read right after their parent; a pairwise tournament for groups no cut can split;
   - bubbles: the same cut on bubble clusters within each frame;
   - flags on every ambiguous decision, and a Llama 4 Maverick A/B check only on flagged boxes, through the spend guard;
   - a manual per-box override as the last word.

   On 10 synthetic layouts the prototype gives the reading I would expect on 9. The 10th is a pinwheel, which has no single accepted order, and the prototype flags it (§8.4).

| Method | Frames | Bubbles | Insets / overlap | Reported accuracy | Licence |
|---|---|---|---|---|---|
| Zumi `reading()` today | Greedy rows keyed to the row's first frame | Same rule per frame, on clusters | Container before its parts | Blockage → A C B **[measured]** | — |
| Recursive XY-cut, horizontal first (Tanaka 2007; Kovanen 2015 via Manga109; Hinami 2021) | Cut tree, depth-first | Hinami: distance to the frame's top-right | Tanaka: out of scope. Manga109: one order for the whole group | 91.9 % of 258 pages (Hinami); 80 % of 672 pages segmented *and* ordered (Tanaka) | Manga109 estimator: MIT |
| Magi v1/v2 (Sachdeva & Zisserman 2024) | Pairwise tournament + cycle break + topological sort | Largest-overlap frame, then distance to the top-right | Pairwise erosion until disjoint | Not evaluated for order | "academic research purposes only" |
| Kumiko | Comparator sort, then "after my top neighbour and all my left neighbours" | — | Panels merged, de-overlapped first | None published | AGPL-3.0 |
| COMICS (Iyyer 2017) | Morton (Z-curve) order of frame midpoints | Morton order within the frame | — | "incorrect orderings only for rare and complicated panel layouts" (no number) | — |
| manga-image-translator | Rows by top-y (±0.3 × mean height) | Within frame: by spread axis, 15-20 px gaps | — | None | GPL-3.0 |
| Kovanen & Aizawa 2015 | Recursive cuts (per the Manga109 port) | "three layers … hierarchically sorted" | — | > 95 % transition accuracy, 1,769 pages **[abstract only]** | Paper |
| Authored (Kindle, EPUB, comiXology, ACBF) | Explicit ordinal or list order | Nested list (EPUB), text-area order (ACBF) | Whatever the author says | Exact by construction | Formats |

## 1. Zumi today

The code is in `pipeline/segment/speakers.py`: `order_bubbles` (l. 184) and `reading` (l. 241).

- **Frames.** `order_bubbles` ranks frames with `reading([_vspan(f) for f in frames])`. That works on bounding spans (top, bottom, left, right), not on masks.
- **The row rule.** `reading` sorts the spans by top. A span joins the last row if two things hold:
  - `share(height, row[0]) > 0.5`, the overlap divided by the smaller height;
  - it is beside every span in the row (horizontal share < 0.5).
- **Bubbles.**
  - **Frame:** each bubble goes to the frame with the largest mask overlap (`fr = argmax(share)`, l. 174-175), or else the nearest by EDT.
  - **Clusters:** bubbles within `CLUSTER_PX = 8` are one cluster, read together.
  - **Order:** clusters are ordered by `reading` within the cluster's first frame. Inside a cluster, the members are ordered by `reading` too, with a container placed before its first part.

What the run of `reading()` gives (spans on a 1000 px box) **[measured]**:

| Layout | Expected (Western) | `reading()` |
|---|---|---|
| Blockage: A, B stacked left; C tall right | A B C | **A C B** |
| Same, C starts 40 px lower | A B C | **A C B** |
| Same, C starts 40 px higher than A | A B C | **A C B** |
| Mirror: C tall left; A, B stacked right | C A B | C A B |
| 2×2 grid | Z | Z |
| Staggered rows | Z | Z |
| Inset D inside wide top frame A | A D B C | A D B C |

The failure is structural.
- The row is anchored to its first frame, and the "beside every frame" test checks only horizontal overlap. A tall frame therefore joins the row of whatever frame is level with its top.
- No step asks whether a horizontal line can pass between the rows without cutting a frame.
- The mirror case works only because the tall frame is the first in reading order anyway.

## 2. Frame-order algorithms

### 2.1 Recursive guillotine (XY) cut

- **Tanaka, Shoji, Toyama & Miyamichi, IJCAI 2007** ([PDF](https://www.ijcai.org/Proceedings/07/Papers/464.pdf)).
  - **The model.** "most of comic pages can be divided into scene frames by recursive guillotine cut, and … the process of the guillotine cut makes the tree structure of the scene frames which has an information to determine the order". "The order of scene frames is decided by ordering the leaves of this tree by means of the depth first search."
  - **Which cut first.** Division lines are found from accumulated density gradients along candidate lines. A "T-type division line judgment" fixes a case where the vertical line scored higher but the horizontal line must be cut first.
  - **Insets are out of scope:** "In the case where scene frames exist inside of a scene frame, the page can not form the tree structure … it is considered one scene frame including the scene frame which exists in the inside."
  - **Result:** "80 percent of 672 pages in four print comic booklets are successfully divided into scene frames", up from 60 % for their earlier method. This is segmentation and order together.
- **Kovanen & Aizawa, ICIP 2015** ([DOI](https://doi.org/10.1109/ICIP.2015.7351614)) **[abstract only]**.
  - Abstract, as quoted in the search result: the method "classifies and orders page and text position information on three layers, which are hierarchically sorted to obtain the final ordering".
  - Evaluated on 1,769 manga pages with 14,726 hand-annotated text positions: "over 95 % transition accuracies and vastly outperforms a naive implementation".
  - The full text is closed (Semantic Scholar: `"status": "CLOSED"`).
- **Manga109 panel-order-estimator** (Hikaru Ikuta, MIT; [order_estimator.py](https://github.com/manga109/panel-order-estimator/blob/623509750a69debf240fb406b507653da4d7b672/order_estimator.py)). This is the public implementation of "the method described by Kovanen et al." The README states the tree construction phase:
  1. "If the current set of panels is separable into two parts with a horizonal line (the pivot)", separate and recurse.
  2. "Otherwise, if … separable … with a vertical line", separate and recurse.
  3. "Otherwise, mark the set as inseparable".

  The tree is read top branch first, then right branch first (manga).
  - **Candidate cuts:** every box edge, tried top to bottom (or right to left), and the first valid one wins.
  - **Tolerance.** A pivot may pass through a box if the smaller part is at most `interception_ratio_threshold = 0.25`. The code measures this *along the axis* ((pivot − zmin)/(zmax − zmin)). The README says area.
  - **Inseparable leaves** "are either individual panels or a set of overlapping panels". The set "as a whole is given a single order".
  - **Two-page spreads:** the estimator forces an initial vertical cut at the page centre, because otherwise "the algorithm will mix up the rows of each page as one single row".
- **Hinami, Ishiwatari, Yasuda & Matsui, AAAI 2021** ([HTML](https://arxiv.org/html/2012.14271v3)).
  - **The model:** "each page consists of one or more rows, each consisting of one or more columns, recursively repeating … Each page is read sequentially from the top row, and each row is read from the right column."
  - **The method:** "we estimate the reading order by recursively splitting manga page vertically and horizontally".
  - **Result:** "correct reading order of 91.9% of the 258 pages we tested … The remaining 8.2% were irregular cases (e.g., diagonally separated, multiple frames overlapping, etc.)".
  - **Failures:** "the system cannot handle some irregular cases such as the frames diagonally separated".
- **The origin in document analysis.** The recursive X-Y cut is Nagy & Seth (ICPR 1984), with the bounding-box variant by Ha, Haralick & Phillips (ICDAR 1995). I did not read either **[unverified]**.

### 2.2 Magi / Magiv2 (Sachdeva & Zisserman, CVPR 2024; Magiv2 ACCV 2024)

- **The paper** ([HTML](https://arxiv.org/html/2401.10224v3), §4 and App. B).
  - **Why not cuts:** prior methods "use 'cuts' to recursively split the panels"; "it fails in the case of overlapping panels, where there is no clean way to 'cut' the page."
  - **Instead:** "represent the panels as a directed acyclic graph (DAG) where each directed edge represents the relative reading order", "by relaxing the constraint of 'strictly' above/below/left/right to 'largely' above/below/left/right … By considering panels in pairs, we do not require global clean 'cuts' to exist."
  - The paper does **not** evaluate reading order.
- **The code** (`sort_panels`, `is_there_a_directed_edge`, `use_cuts_to_determine_edge_from_a_to_b`, identical in v1 and v2). It is for right-to-left reading.
  1. Erode every box by 5 % "to account for imperfect detections".
  2. For **every** pair, add one edge, so the graph is a tournament. The edge weight is the box distance. For a pair (A, B), the tests are tried in this order:
     - A first if A is strictly above B and not strictly left of B;
     - A first if A is strictly right of B and not strictly below B;
     - the same two tests with A and B swapped;
     - if one box is below and right of the other (the diagonal case), a local cut: merge the y-ranges of all boxes that touch the pair's joint bounding box, and if the two fall in different bands, the upper band wins; else the same with x-ranges, the right band first.
     - If the boxes still intersect, erode both by 5 % and retry.
  3. While a cycle exists, delete the heaviest (longest-distance) edge of the first cycle found by `nx.simple_cycles`. Then return `nx.topological_sort`.
  4. Texts: `get_text_to_panel_mapping` assigns each text to the frame of largest intersection area, or to the nearest frame if it overlaps none. `sort_texts_within_panel` sorts the texts of one frame by distance from the point (max x2, min y1) of *those texts* (not of the frame).
- **On the user's layout, mirrored for left-to-right reading** **[inference]**:
  - A before B (A strictly above, not beyond in the reading direction);
  - A before C, because C spans the full height, so neither box is strictly below the other;
  - B before C.

  So A B C. This is the same answer as the cut, reached without a global cut.
- **Cost** **[inference]**: `simple_cycles` on a tournament can enumerate exponentially many cycles. It is fine for ≤ 12 frames but should not be run per bubble.
- **Licence:** "available for academic research purposes only". Reimplement the idea; do not copy the code.

### 2.3 Kumiko (kumiko.ink)

- **The initial sort** ([`panel.py` `__lt__`](https://github.com/njean42/kumiko/blob/9d587ae9498bc84dfda06fc19c6ad89f421bec14/lib/panel.py#L64)) is a comparator with a 10 % tolerance (`wt()` = w/10, `ht()` = h/10). Its four tests, in order:
  - "panel is above other": `other.y >= self.b - ht`;
  - else below;
  - else left (true for `ltr`);
  - else right.

  It is not transitive **[inference]**.
- **The fix pass** ([`page.py` `fix_panels_numbering`](https://github.com/njean42/kumiko/blob/9d587ae9498bc84dfda06fc19c6ad89f421bec14/lib/page.py#L351), "issue #12"). It repeats until nothing moves: each panel is moved after its `find_top_panel()` and after every `find_all_left_panels()` panel (`find_all_right_panels()` for `rtl`).
  - `same_row` holds when the y-ranges overlap by ≥ 1/3 of the smaller height, or when one range contains the other.
  - `same_col` is the same test on x.
- **On the user's layout** **[inference from the code]**: C's left neighbours are A and B, because C's y-range contains both. So C moves after B and the order is A B C. Kumiko gets blockage right through a precedence constraint, not through cuts.
- **The README** only says "The numbering is left-to-right, or right-to-left if requested."
- **Licence:** AGPL-3.0.

### 2.4 Other systems

- **COMICS** (Iyyer et al., CVPR 2017, [PDF](https://arxiv.org/pdf/1611.05118)). "We compute the midpoint of each panel and sort them using Morton order, which gives incorrect orderings only for rare and complicated panel layouts". Textboxes are sorted the same way within each panel.
  - On the blockage layout, C's midpoint sits on the page's vertical half-line. The Morton key then puts C after B (A B C) or before B (A C B) depending on a one-pixel difference **[inference, arithmetic]**.
- **manga-image-translator.** Detection runs a vendored copy of Kumiko. `_sort_panels_fill` ([sort.py l. 153](https://github.com/zyddnys/manga-image-translator/blob/d6de6ab62a7be6afc0d07a3184149cdefbcd32f2/manga_translator/utils/sort.py#L153)) then re-sorts the panels into rows by top-y (±max(10, 0.3 × mean height)) and returns A C B on the blockage layout **[measured]**.
  - Each text goes to the panel containing its centre, or else the nearest.
  - Inside a panel, the texts are sorted along whichever axis has the larger standard deviation, grouped by 15-20 px gaps.
- **Dwango Media Village, 2026-08-13** ([article](https://dmv.nico/en/articles/comic_computing_13/)): Meta's SAM3 detects panel and bubble regions, then "heuristics based on their spatial relationships" estimate the order. No numbers are given.
- **Guérin 2012** ([HAL record via API](https://hal.science/hal-00743480)): "We focus on the panels, computing the reading order thanks to their spatial relations", using ontologies. The 2017 Information Sciences framework (Guérin, Rigaud, Bertet, Revel) and Rigaud's thesis also infer "the reading order" in an expert system. HAL blocked the PDFs, so the rules are **[unverified]**.
- **Arai & Tolle 2010** (IJUC 1(1); ITNG 2010). Augereau et al.'s survey describes it only as extracting "frames, balloon, and text based on connected components and fixed thresholds" ([survey](https://arxiv.org/pdf/1804.05490)). I found no ordering method in it **[secondary, unverified]**.
- **ComicRack CE** has no panel detection. `GetPartGridSize` divides the zoomed page into viewport-sized cells, and `GetPartRectangle` walks them row by row, mirroring x for `RightToLeftReadingMode.FlipParts` ([ImageDisplayControl.cs](https://github.com/maforget/ComicRackCE/blob/master/ComicRack.Engine.Display.Forms/ImageDisplayControl.cs)). Its "parts" are screenfuls, not frames.
- **Webtoon tools.** In a vertical strip, frame order is top to bottom by construction. I found no primary source on a 2D order step in webtoon tooling **[inference]**.

## 3. Hard layouts: how each method handles them

| Layout | XY-cut (Manga109 / Tanaka / Hinami) | Magi | Kumiko | Human readers (Cohn 2013, n = 145) |
|---|---|---|---|---|
| Blockage (tall frame beside a stack) | Horizontal cut blocked → vertical first → stack, then tall frame | Same, by pairwise tests | Same, through the left-neighbour constraint | 91 of 145 took the blockage path, 40 the Z-path. Blockage-path use rose with comic-reading frequency |
| Grid | Z | Z | Z | Z-path mean 0.941 |
| Staggered rows | Z (a horizontal cut exists) | Z | Z | Z-path 131 of 145 (mean 0.90) |
| Separation (a wide gap) | Ignores gap widths: Z | Z | Z | Z-path 84 of 145 (mean 0.717) |
| Overlapping frames | Within tolerance: cut. Otherwise one leaf with one index (Manga109) | Erode the pair until disjoint | Merges or de-overlaps first | Z-path mean 0.50, a trend toward following the overlap |
| Inset | Tanaka: the outer frame counts as one. Manga109: one leaf | Equal centres: the larger first. Otherwise erosion | — | Dominant before enclosed, 84 of 145 ("60 %"; my arithmetic gives 58 %) |
| Diagonal gutter | Fails (Hinami's 8.2 %) | Pairwise tests + local cut | Comparator on boxes | Not tested |
| Bleed to the page edge | Boxes reach the edge; cuts unaffected | Unaffected | Expansion toward the page edge | Not tested |
| Borderless art | Order is fine if the frames are found; detection is the problem | Learned detector | Contours fail | Not tested |

**Human data in more detail.** Cohn 2013 ([Frontiers in Psychology 4:186](https://www.frontiersin.org/articles/10.3389/fpsyg.2013.00186/full)):
- **Task:** 145 Comic-Con attendees numbered empty panels on 12 pages.
- **Definition:** "Blockage occurs when panels are stacked vertically next to a panel that runs the distance of the vertical panels."
- **The derived order of preference rules:**
  1. follow the outer border;
  2. follow the inner border;
  3. move right;
  4. move straight down;
  5. if nothing is to the right, go far left and down;
  6. go to the next unread panel.
- **Entry:** start top-left, or failing that at the highest and/or leftmost panel.

Two follow-ups agree:
- Cohn & Campbell 2015 (Applied Cognitive Psychology 29(2)): the more a layout departs from a grid, the less the Z-path is used **[abstract only]**.
- Kirtley et al. 2022 ([DOI 10.1002/acp.4018](https://doi.org/10.1002/acp.4018)), eye-tracking: panel outlines drive most choices, and content matters in ambiguous layouts **[abstract only]**.

## 4. Bubble order

- **Assignment to a frame.**
  - Magi: the largest box intersection, else the nearest frame.
  - manga-image-translator: the frame that contains the centre, else the nearest.
  - Zumi already uses the largest *mask* share, which is finer than both.
- **Order inside a frame.**
  - Magi: distance from the texts' joint top-right point.
  - Hinami: "determined by the distance from the upper right point of each frame".
  - CoMix, adapting Magi for Western pages: "ordered based on the vicinity with the panel's top-right corner (manga) or top-left corner (comics)" ([HTML](https://arxiv.org/html/2407.03550)).
  - Magi itself: "There is no absolute rule that determines the order of texts within the panel."
- **Where the corner distance goes wrong** **[inference, arithmetic]**. Take a 400 px wide frame with bubble P at the top right (x = 350, y = 0) and bubble Q at the mid left (x = 0, y = 200). Q is nearer the top-left corner (200 vs 350), so Q is read first, although P is higher.
  - A horizontal-first cut reads P first whenever the two do not overlap vertically.
  - That matches the lettering convention that the higher balloon reads first. That convention is a letterer's rule, not one I found in a primary text **[unverified]**.
- **Stacks and joined balloons.** Blambot ([Comic Book Grammar & Tradition](https://blambot.com/pages/comic-book-grammar-tradition)) says "Balloons directly joined together are generally of the same thought process". In back-and-forth conversation, "Their balloons will be staggered and joined with connectors".
  - So a joined cluster is read as one unit, top part first. Zumi's `CLUSTER_PX` clustering already does that.
  - The staircase of a staggered exchange is read top-down by a horizontal-first cut **[inference]**.
- **Bubbles crossing borders.** Blambot: overlapping a border "tends to look a little amateurish, but can be necessary due to space constraints". For an off-panel speaker, "the tail of the balloon generally butts against the panel border".
  - No source gives a rule for which frame a straddling bubble is read with.
  - The tail tip is the best evidence I know of: the speaker's frame **[inference]**.
- **Learned bubble order.**
  - The only comics model is Kovanen & Aizawa's three layers (> 95 % transition accuracy on manga) **[abstract only]**.
  - In documents, LayoutReader learns reading order with a seq2seq model ([Wang et al., EMNLP 2021](https://arxiv.org/abs/2108.11591)), and so does a sparse graph network ([Wang, Fujii & Bissacco, ICDAR 2023](https://arxiv.org/abs/2305.02577)). Both need training data that Zumi does not have.
- **VLMs on order.** On AI4VA-FG (Franco-Belgian comics; [Chen, Ren & Süsstrunk 2025](https://arxiv.org/html/2511.06490)), two-way multiple-choice tasks with a 50 % chance level:
  - **dialog reordering (OCR text given):** 76.8 % GPT-4o, 90.5 % Gemini-2.5-pro, 54.8-71.4 % for Qwen2.5-VL 7B-32B;
  - **panel reordering:** 45-63 % for every model.

  Llama 4 was not tested. So a VLM is a usable tie-breaker for *text* order when given the text. It is weak at judging panel *sequence* from content **[inference]**.

## 5. Authored order: products and formats

- **Kindle Panel View.** The Region Magnification JSON carries an `ordinal`: "reading order of the magnification areas (the order in which panels appear as part of the reading flow)". Without publisher panels, Virtual Panels divide "every page … into four panels based on the primary-writing-mode value" ([KDP help](https://kdp.amazon.com/en_US/help/topic/G9GSTY4LTRT39D4Z)).
- **EPUB Region-Based Navigation 1.0** (IDPF Recommended Specification, 2015-08-26; [spec](https://idpf.org/epub/renditions/region-nav/)).
  - "The sequence of list items in this navigation element defines a possible path through the content."
  - Nested `ol`s give "ever more granular Regions of Interest": balloons inside panels.
  - Regions are `#xywh=percent:` rectangles.
- **comiXology Guided View.** Creators get "a tool-set to prepare their comics for comiXology's patent-pending Guided View", "the actual tools we use at comiXology when creating Guided View" ([press release](https://www.comicsbeat.com/press-releases/comiXology-offers-guided-view-authoring-tools), undated). The order is made by people with tools, not inferred.
- **ACBF:** "Definition of comic book structure (pages, frames) as well as order in which they follow" and the "reading order of text areas" ([MobileRead wiki](https://wiki.mobileread.com/wiki/ACBF)). The schema-level attribute is **[unverified]**.
- **Ground-truth datasets.**
  - eBDtheque stores `<metadata rank="3"/>` on each panel polygon and `rank="9"` on balloons ([2013 poster](https://ebdtheque.univ-lr.fr/download/poster/2013_Guerin_eBDtheque_a_representative_database_of_comics.pdf)). Balloon rank looks page-wide in the example **[inference]**.
  - CoMix annotated reading order on DCM, eBDtheque, COMICS and PopManga pages, "to assess the corner-cases of these so-common used euristics".
  - Manga109 has no order. Ikuta, Wöhler & Aizawa 2023 ([Sci. Rep.](https://www.nature.com/articles/s41598-023-47120-w)) generated orders with Kovanen's heuristic, then "all of the panel orders were manually inspected and fixed by hand". They do not say how many needed fixing.

## 6. Metrics and reported accuracy

| Metric | Definition | Used by | Reported |
|---|---|---|---|
| Page exact match | Whole order correct | Hinami 2021 | 91.9 % of 258 manga pages |
| Segmentation + order success | Page divided correctly into the cut tree | Tanaka 2007 | 80 % of 672 pages |
| Transition accuracy | Share of consecutive pairs correct **[my reading of the term]** | Kovanen 2015 | > 95 %, 1,769 pages, 14,726 texts **[abstract]** |
| Edit distance | On the sorted detected text boxes, matched to the ground truth | CoMix 2024 | No figure found in the HTML table **[unverified]** |
| Average page-level BLEU; ARD | ARD = mean \|k − index of eₖ in the prediction\|, with a penalty n for a missing element | LayoutReader (documents) | — |
| Share of readers on a path | Human agreement per layout | Cohn 2013 | Grid 0.94; blockage path 91 of 145 |

For Zumi: per-box exact match plus pairwise accuracy (the share of ordered pairs correct, equivalent to Kendall's τ). Report frames and bubbles separately **[inference]**.

## 7. Prototype check **[measured, synthetic]**

- **Setup:** 200×200 boolean masks, 4 px gutters. The script is in a temp folder, not the repo: `C:/Users/Usuario/AppData/Local/Temp/zumi-ro/proto/order_proto.py`.
- **What it implements:** §8.1-8.2: mask cuts with τ = 0.15, inset ring ≥ 0.6, a pairwise tournament for leaves.

| Layout | Prototype | Leaves left to the tournament |
|---|---|---|
| Blockage (A, B left; C tall right) | A B C | none |
| Same, C 10 px higher than A | A B C | none |
| Mirror (C tall left) | C A B | none |
| 2×2 grid | A B C D | none |
| Staggered rows | A B C D | none |
| Inset D inside wide top A; B, C below | A D B C | none |
| L-shaped A with B in its notch | A B | 1 group of 2 |
| C (lower right) pokes 30 px into A (top) | A B C | 1 group of 3 |
| Diagonal gutter between A and B, C below | A B C | 1 group of 2 |
| Pinwheel (A top-left, B right, C centre, D bottom, E left) | A E C B D | 1 group of 5: flag |

The pinwheel has no single accepted reading. It is exactly the case to send to the fallback.

## 8. Recommendation for Zumi

### 8.1 Frames

Inputs: `frames` (boolean H×W masks), the reading direction `ltr`, and the gutter `g` in px (already estimated in the segmentation; else 6).

```
precompute per frame: row = mask.sum(1), col = mask.sum(0), cumulative sums, bbox, area

# 1. Insets: a frame mostly surrounded by one bigger frame is its child (Cohn: dominant first, 58 %)
for each frame c:
    ring = dilate(c, g+3) & ~dilate(c, 2)
    parent[c] = the frame p with area(p) >= 2*area(c) and |ring & p| / |ring| >= 0.6, else None
top = frames with no parent

# 2. Recursive cut on masks, horizontal first (Tanaka, Kovanen/Manga109, Hinami)
def xy(S):
    if |S| <= 1: return S
    for axis in (rows, cols):                       # rows first: the Z-path in grids
        for pos in sorted({first and last+1 pixel of each frame in S on that axis}):
            frac[f] = share of f's mask before pos    # from the cumulative sums: O(1) per frame
            if every frac <= TAU or >= 1-TAU, and both sides are non-empty:
                return xy(before) + xy(after)        # before = top, or left for ltr
    flag(S)                                          # no cut: a non-guillotine group
    return tournament(S)

# 3. Groups no cut splits: pairwise precedence, Copeland ranking (the Magi idea, on masks)
def first(a, b):
    sc = shared columns / narrower width;  sr = shared rows / smaller height
    if sc == sr == 0:                                # diagonal neighbours
        return top(a) < top(b) - 0.5*min(h)  or (|top(a)-top(b)| <= 0.5*min(h) and left(a) < left(b))
    if sc >= sr:  return mean y of a over the shared columns < mean y of b there   # above first
    else:         return mean x of a over the shared rows    < mean x of b there   # left first
def tournament(S):
    wins[a] = #{b: first(a, b)};  flag if any 3-cycle
    return sorted(S, key = (-wins, top, left))

order = []
for f in xy(top): order += [f] + xy(children of f)   # an inset right after its parent
```

- **Parameters.**
  - TAU = 0.15 of the frame's *mask area* on the minor side. Manga109 uses 0.25 of the *extent*. Area is stricter on L-shapes and on frames poking across a gutter **[inference]**.
  - The inset ring share is 0.6 and the parent must be at least 2× larger. For an L and its notch, the notch touches the L on 2 of 4 sides, which is ≈ 50 %, so it stays a sibling **[inference, prototype case]**.
- **Cost.** Under 1 ms per box once the projections exist **[inference]**: about 10 frames, about 20 candidate cuts per level, an O(1) test per frame.
- **Mirror** the axis direction for right-to-left reading. P&C is left to right.

### 8.2 Bubbles

```
units = clusters of bubbles within CLUSTER_PX (as now); keep the container rule (container just before its first part)
for each unit:
    share[f] = |unit ∩ f| / |unit|
    if max share >= 0.65:                  frame = argmax
    elif the tail tip lies in one of the top two frames:  frame = that one (the speaker's frame)   [inference]
    elif share > 0:                        frame = the earlier-ranked of the top two; flag   [inference]
    else:                                  frame = nearest by EDT (as now)
per frame in frame order:
    xy(units of that frame, TAU_B = 0.15)  # higher reads first; level → left first
    leaves: sort by distance from the frame's top-left corner (CoMix's Western adaptation of Magi); flag if > 2
per unit: xy(members)                       # a stack reads top part first
```

### 8.3 Known failure modes

- **The minority blockage reading.** 40 of 145 readers took the Z-path through a blockage. Some artists draw for it, especially when the tall frame's top is level with the first frame and its content continues it.
  - Geometry cannot see that.
  - Flag a vertical cut whenever a horizontal cut would have been valid at TAU = 0.35. That is a near-miss, so it goes to the VLM check.
- **Pinwheels and other non-guillotine groups:** the tournament gives *an* order (A E C B D above), with no evidence it is the intended one. Always flagged.
- **Overlap.** Readers split 50/50 on following the overlapping frame (Cohn). A cut within tolerance hides the overlap. Flag any frame crossed at 5-15 %.
- **Segmentation errors dominate.** A merged frame or a missed borderless frame reorders everything after it. Order quality is bounded by the frame masks (see the panel-splitting note).
- **Wide separations** are ignored. That matches readers 84 of 145 times, not always.
- **Bubble stacks drawn as a staircase** whose steps overlap vertically by more than 15 % fall to a vertical cut, so the left one reads first. That is usually right for a left-to-right staircase, and wrong for a right-high staircase **[inference]**.
- **Straddlers without a tail** go to the earlier frame. That is a guess, and they are flagged.
- **Caption boxes** at a frame's top-left come first naturally. A caption at the *bottom* meant as a lead-in to the next frame is read last in its frame **[inference]**.
- **Box boundaries.** The order is within one box. Order across boxes stays the episode's sequence.

### 8.4 Fallback

- **When.** Only when a box has a flag: an uncut group, a near-miss blockage, a 5-15 % crossing, a straddler, or a 3-cycle.
- **What to send.**
  - One image (Llama 4 is "tested for image understanding up to 5 input images"; [model card](https://github.com/meta-llama/llama-models/blob/main/models/llama4/MODEL_CARD.md)). Show the box at reduced size with the frame outlines drawn and two candidate orders as large numerals, side by side. The candidates are the geometric order and its alternative: the other cut priority at the flagged node, or the top two tournament orders.
  - For bubbles, also give the OCR text of the flagged bubbles in both orders. On AI4VA-FG, text made dialog reordering far easier than panel reordering for every model.
- **Answer format.** Ask Maverick (`segment/understand.py` already calls it through OpenRouter, under the 2 USD/day spend guard) for "A" or "B" plus one sentence of reason. Accept only "A" or "B", and default to geometry on anything else.
- **Why A/B and not free ordering.** VLMs were near chance at panel reordering (45-63 %), so let the model choose between geometric candidates rather than invent an order **[inference]**.
- **Last word: a manual per-box order override,** the way Kindle (`ordinal`), EPUB (list order) and comiXology (authoring tools) all do it. The speaker labelling page is the natural place to record it **[inference: not designed here]**.

### 8.5 How to check it

- **Measure.** Hand-label the frame and bubble order of the boxes the user flagged, then compare today's `reading()` with §8.1-8.2 on per-box exact match and pairwise accuracy (§6).
- **What would change the plan.** If the minority blockage reading turns up in P&C, lower the near-miss threshold rather than switch to vertical-first.
- **Licences.** Manga109's estimator is MIT and can be adapted with attribution. Do not copy code from Magi (academic only), Kumiko (AGPL-3.0) or manga-image-translator (GPL-3.0); reimplement the ideas.

## 9. Not verified

- **Papers not read in full:**
  - Kovanen & Aizawa 2015 (the three layers and the exact "transition accuracy" definition);
  - Guérin 2012/2017 and Rigaud 2015 (ordering rules: HAL served an Anubis block);
  - Arai & Tolle 2010;
  - Cohn & Campbell 2015, Kirtley et al. 2022;
  - Nagy & Seth 1984, Ha et al. 1995.
- **Not found:** CoMix's numeric reading-order result. The Kindle Virtual Panels order exists only in diagrams. ACBF's schema attribute for order. A comiXology Guided View patent text. Any webtoon tool's ordering code.
- **Not measured:** Llama 4 Maverick on comic reading order.
- **The prototype:** synthetic rectangles and masks only. It was not run on P&C boxes, real masks, or bubbles. Magi and Kumiko were not run (missing `shapely`); their behaviour on the user's layout is read from the code.
