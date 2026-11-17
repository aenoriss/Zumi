"""Step 0, finish: a comic drawn in pencil made into finished pages (clean ink, colour, shading, light), before the
rest of the pipeline. Optional and alone: the other steps run on its pages as on any coloured comic and know nothing
of it, and nothing else reads its bible.

The configuration the owner chose among every one tried (2026-11-13, finish_test/variantN):

1. The drawing is locked to the pencil: every panel frame, figure, face, object, sign and balloon stays where and as
   the pencil draws it, and the ink follows the pencil's own lines. What is new is the ink, the colour, the shading
   and the light; a background the pencil leaves almost empty may be completed as its place's entry describes it,
   behind the figures.
2. One image call per whole page, with Google's Nano Banana 2 (gemini_image.edit) unless --model klein asks for
   FLUX 3 Klein (bfl.flux3_klein). One model paints every sheet and page of a run. Both get the same prompts; only
   the call differs (paint), and what each model's sizes force (canvas_of): Klein edits an image at its own size;
   Nano Banana makes fixed shapes, so the page goes centred on a white canvas of the nearest one (2:3 at 4K for an
   A4 page of 2480 x 3508).
3. A bible: a folder with one entry per recurring character, prop and place, each a description in words (JSON)
   and a picture (a sheet). An entry in the folder is fixed, the artist's or the step's alike: no run renames,
   merges, drops or rewrites one; the step only adds what is missing. To have one written anew, delete its file.
4. The entries: one Claude Sonnet 5.5 call sees every pencil page and writes the entries the bible lacks, each with
   what the thing is (a character's whole build, part by part; a place's permanent things, nothing of one scene),
   its colours, and the page and box where it is drawn best (found.json). An entry says no pose, expression or
   what a face or screen shows: those are each panel's.
5. The sheets: each new character and prop has its most complete pencil drawing painted alone, from its
   description, by the run's image model: one figure, once, as the pencil draws it, on a flat grey ground. A place
   has a sheet only when a panel establishes it. A sheet that fails is asked for again in the next run; its pages
   are painted without it meanwhile.
6. The readings: one small Sonnet call per page, in order, given the entries and the place the page before ended
   in, reads where each panel's frame is in percentages of the page, where the paper is bare beyond margins and
   gutters, what the pencil draws on bare paper, and for each panel its place (the one before it unless the page
   shows a change, with what shows it) and its figures (a character of the bible or "other", with what tells who)
   (read/<page>.json). Without the layout the image model widened a narrow panel over the bare paper beside it and
   stood a second figure there; without places it set a scene in a park in the middle of a café; without figures
   it painted a main character in a bystander's place (2026-11-14). The episode's one call read the panels too at
   first and answered differently at every asking, so this is per page: a page read again changes that page, and
   the pages after it only when the place it ends in changed.
7. The pages: each is one call with the pencil page and the sheets of the entries on it; its prompt is the layout
   in words, what each panel holds (its place and its figures, counted), the rules, what the reference images are,
   then every entry on the page with its description and the number of the image that is its sheet. A character's
   build comes from its description and sheet, its pose and face from the pencil; a sheet stays outside the page
   and no figure is taken from one.
8. Typed lettering never comes from the model: left on the page it was set again in another type with wrong words
   (2 to 4 of 76 on the first page tried, 2026-11-12). SAM 3.1 finds the balloons and caption boxes on the pencil
   page (regions), and the page is sent with the whole inside of each flat pure white (blank), so the model inks
   empty balloons. After the call the paper inside each balloon, up to the outline the model drew, is made pure
   white again (clean: it comes back a shade off), and the pencil's letters go back as the pencil page's own
   pixels, their grey edge included (letter). The model moves the balloons a little, and not all alike, so each
   region's letters move, without scaling, to where the model drew that region's outline (placed). Lettering drawn
   into the art (a sign, a sound effect) is drawing: the model inks it.
9. No model returns the page exactly where the pencil has it. Before anything is read from the output or set on it,
   the page is cut from it and laid on the pencil's pixel grid by the scale, each way, and the move that put the
   most of its lines on the pencil's (laid); the mapping is in the report.
10. One pass, no retries, and it never stops: a call that fails, or that the day's budget refuses (spend.py), leaves
   its sheet or page out with the reason in the report, and the run goes on; a later run makes what is missing and
   pays nothing for what is done. Only an entries call that fails ends the run, with nothing painted, and a page
   that was not read is left out: painted without them, a page would be painted again once they came. Six
   checks are written to report.json; they cost nothing, they report, nothing is repaired, and a page that fails
   them is still written:
   added: blank paper the model enclosed outside the pencil's balloons and captions, each area at least the size
   of a small balloon (a balloon, a caption box or a panel it added and left empty), and the share of the pencil's
   open paper (margins, gutters) it painted. A measurement only: nothing is erased;
   lines: the share of the pencil's stroke pixels with an ink line of the finished page within NEAR pixels (kept),
   and the share of the page covered by ink lines with no pencil stroke that near (new), both once the page is laid
   back on the pencil by its whole-page shift, which is reported with the numbers before it;
   writing: the share of a balloon's or caption's inside that the model's own output left dark, with white paper
   all round it, before the letters go back: anything it wrote in a balloon it was told to leave empty (the worst
   region's share; the outline is not inside and is not counted);
   frames: how far each side of each panel's frame sits from the pencil's, and the largest move on the page (a frame
   the model paints as the edge of its colour, with no ink line, is not found);
   text: the share of the letter pixels of the finished page that are the pencil's exactly;
   balloons: whether every lettering region's outline was found on the output (LOST_FIT): where the model painted
   no balloon the letters land on the artwork, and the other checks see nothing.

11. The name (2026-11-16): once every page is read, one small Sonnet call over the readings' stories and the
   characters' names gives the comic a short title, plain and catchy, no quotes; the line under it is "Episode 1 ·
   N pages", written by the code, not the model (title.json: {"title", "line", "usd"}). Not before every page is
   read: a title asked on part of the story would be asked again.
12. The cover (2026-11-16, the owner's decision, accepting that a model can misspell): once every page is
   finished, one image call with the run's model paints a portrait front cover on a blank canvas (COVER_CANVAS:
   2:3 at Nano Banana's 2K), the title lettered prominently at the top exactly as given and no other text, the main
   characters (the COVER_CHARACTERS drawn in the most panels, by the readings) in a scene that sums up the story,
   each from its description and sheet, in the look of the first and last finished pages, sent with it (cover.png;
   report.json's "cover" names the title it was asked to letter). Not before every page is finished: a cover painted
   from part of the comic would be painted again.

Tried and dropped (2026-11-12 and 13; the owner compared the pages): a direction for every panel written by the
founding, a style sample and its description in words, a call per panel, a colour check against the bible, a check
of the drawn lettering by a reading model, and a single fixed prompt with no bible at all.

The bible folder:

    characters|props|places/<id>.json   {"name", "kind", "description", "palette": ["#rrggbb", ...]}
    characters|props|places/<id>.png    its colour sheet, when the artist gives one
    characters|props|places/<id>.<model>.png   the sheet this step painted with that model, used when there is no <id>.png
    found.json                     the entries call: the pages it saw, where each entry is drawn best
    stamps.json                    the stamps of the sheets this step painted

Everything made is stamped with what it is made from (fresh.py): the lettering regions by the pencil page and SAM's
recipe; the entries call by the pages (and it is asked again when an entry it founded has no file); a sheet by its
pencil crop, its prompt (the description inside it) and the model; a page's reading by the pencil page, the
reading's task, the entries and the place the page before ended in; a page's raw model output by the pencil page,
its lettering regions and the constants that clear their text, its prompt (the reading and the descriptions inside
it), the sheets sent and the model; the output
laid on the pencil's grid by the raw output and this file; the finished page by the laid output; the checks by the
finished page (what costs nothing is made again at any edit of this file); the title by its task, its model and the
stories and names it is given; the cover by its prompt (the title inside it), the sheets sent, the raw outputs of the
pages sent and the model. So a run with nothing changed makes no
call and writes nothing, and a changed description repaints its sheet and the pages that used it. The model is in
every paid stamp and in the name of every paid file, so a run with another model paints its own sheets and pages
and a run back to the first finds its own again.

The order of a run: the lettering regions of every page to paint (local, free), the entries, the readings, the
sheets, then the pages in the order given (a folder's pages by the numbers in their names: 2 before 10), then the
title and the cover. Each phase starts with a line "== 0 finish: <phase>" (lettering, bible, readings, sheets, pages,
title, cover), which the Modal service shows as its job's step. Before the first reading or image call the plan is
printed: the pages to read, the sheets and pages to paint and about what they cost. --only paints some of the pages;
all of them are still read, because a panel's place comes from the pages before it.

Under the out dir: <page>.png (the finished page, the pencil page's pixel size), sent/ (the pencil page as sent,
its text cleared), raw/<model>/ (the model's own output, and <page>.json: the prompt, what was asked and what it
cost), laid/ (that output on the pencil's grid, and its mapping), read/ (each page's reading), lettering/ (the
regions of the pencil page: a grey level per region), checks/<page>-lines.png (pencil strokes found in green,
missed in red, new ink in blue), title.json, cover.png (and cover.json: what was asked, what it cost),
report.json, stamps.json, and bible/ unless one is given.

    python finish.py <pencil pages dir or files> <out dir> [--bible <dir>] [--model nano|klein]
                     [--only <page name>,<page name>] [--reader <model id>] [--effort low|medium|high]
"""
from __future__ import annotations

import collections
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import (binary_dilation, binary_erosion, binary_fill_holes, binary_opening, find_objects,
                           grey_closing, label)

import bfl
import fresh
import gemini_image
import sam
from openrouter import ask_json, image_part, pricing
from prop_mesh import to_lab
from settings import slug
from spend import DAILY_CAP_USD, spent_today

FOUND_MODEL = "anthropic/claude-sonnet-5.5"  # writes the entries, one call for the episode
READER = "anthropic/claude-opus-5.5"  # reads each page, unless a run names another model (--reader). On the same task
                     # it named figures and things right where Sonnet 5.5 did not (a bystander taken for a character,
                     # a jet for a plank), for 0.045 USD a page against 0.022 (2026-11-14)
REASONING = "medium"
ANSWER_TOKENS = 6000   # the entries call's answer: an episode's entries, each a few sentences (nine took 2000)
FOUND_SIDE = 2048    # a page is sent to the founding at most this long, and its boxes are read in these pixels
KINDS = {"character": "characters", "prop": "props", "place": "places"}  # an entry's kind and its folder
PICTURES = (".png", ".jpg", ".jpeg", ".webp")  # the files a pencil page or an artist's sheet may be

MODELS = {"nano": gemini_image.NANO, "klein": bfl.KLEIN}  # the image models a run may paint with (--model): one
                     # for every sheet and page of the run, so the look is that model's throughout
REFS = {"nano": gemini_image.REFS, "klein": bfl.KLEIN_REFS}  # images each takes in a call, the edited one included
SEED = 1             # one seed for every Klein call, so a stamp that holds names one result (Nano Banana has none)
PAD = 0.06           # a sheet's pencil crop reaches this share of the box past each side: the founding's box is tight
SHEET_SIDE = 1024    # a sheet's long side: the 1k price tier, and enough to read a figure's colours
REF_SIDE = 1024      # a sheet is sent with a page at most this long: its colours show at that size
MAX_PIXELS = 16_822_272  # the largest image Klein makes (its 4k bin): a larger pencil page is sent smaller
MAX_SIDE = 6256      # Klein's longest side
SCALES = (0.03, 0.005, 0.001)  # the model's page is laid on the pencil's by trying scales, each way, up to the
                     # first value from 1 in steps of the second, then around the best in steps of the third: Klein
                     # redrew a page 1.4 % narrower on its own (848 x 1216 for 2480 x 3508, 2026-11-12)

LETTER_PROMPTS = ("speech bubble", "caption box")  # SAM's names for what holds typed text
LETTER_SCORE = 0.5   # SAM score from which a region is lettering (a probe on a pencil page: 0.75 to 0.90)
SAME = 0.5           # a SAM instance with this share of itself on one region already kept is that region seen again
                     # (a tile's partial view); with less than this share of itself free it is a group, and dropped
EDGE = 0.006         # a region is drawn in by this share of the page's width to get its inside, clear of the outline
                     # (at 0.004 specks of a pencilled outline stayed inside, 2026-11-12)
TEXT_INK = 80        # luminance under which a pixel inside a balloon is typed text: type is black, graphite grey
FRINGE = 2           # px around the text that go back with it: the grey edge of each letter
CORE = 0.02          # a region drawn in by this share of the page's width is inside the model's balloon too, however
                     # it moved or shrank it (up to 26 px and 5 % so far): where whitening starts from
GROW = 0.01          # a region grown by this share of the page's width reaches the model's outline: where it may end
WHITE_L = 80         # CIE lightness from which a pixel inside a balloon is paper: the model's cream centre was 98, its
                     # grey rim 94, and an outline's soft edge is darker than this within a pixel of the line
PAPER_L = 96         # the same on the pencil page, where only bare paper may go white: graphite is grey, and at 80
                     # a pencilled outline came out thinned and broken (2026-11-12)
WHITE_C = 10         # CIE chroma up to which it is: the cream was 2; pale sky or skin beside a balloon is past 10
SHIFT = 32           # px at the checks' size: the farthest whole-page move looked for (2 % of the long side; the
                     # first pages moved 10 to 12)

CHECK_SIDE = 1600    # the checks work on the page at this long side: a line is a few pixels wide there
LINE = 11            # px at that size: a dark mark narrower than this is a line, a wider one a filled area
PENCIL_DELTA = 25    # how much darker than its surroundings a pencil stroke is (graphite on paper)
INK_DELTA = 50       # the same for an ink line of the finished page (black on colour)
NEAR = 5             # px at that size (0.3 % of the page's long side) within which an ink line follows a stroke
# What a page should reach: first guesses of 2026-11-12, not yet tuned on judged pages. They only set "ok" in the
# report; nothing is held back by them.
MIN_KEPT, MAX_NEW = 0.80, 0.05
MAX_WRITING = 0.002  # typed text darkens about 9 % of a balloon's inside; a stray mark or two stays under this
LOST_FIT = 0.25      # a lettering region whose pencilled outline has the output's ink on less than this share of it
                     # (placed's "fit") has no outline there: the model did not paint that balloon. Of 141 regions
                     # painted by 2026-11-14 the one lost balloon had 0.20, the lowest of the others 0.31
FRAME_RUN = 0.12     # a straight line, level or upright, as long as this share of the page's width is a side of a
                     # panel's frame: the lines of a drawing that long are rarely both straight and square to the page
FRAME_SLACK = 2      # px at the checks' size a ruled line may wander along its length and still be one line
PANEL_AREA = 0.03    # a frame that encloses less than this share of the page is not a panel
MAX_MOVE = 0.01      # of the page's long side: how far a side of a panel's frame may sit from the pencil's (35 px on
                     # a 3508 px page; a first guess like the others)

BLANK_L = 94         # CIE lightness from which a pixel of the model's output is blank paper: an empty balloon's
                     # inside came back at 94 to 98, the page's margins at 99
BLANK_C = 4          # and the chroma up to which it is: the balloons' cream was 2; a pale wall or a white coat is past it
BLANK_AREA = 0.004   # of the page: an enclosed blank area from this size is as large as a small balloon

READ_REASONING = "high"   # the reader's effort unless a run names another (--effort): at low it took a disc a
                          # figure hid behind for the figure's body and a bystander for a character, at high it
                          # read both right (2026-11-14)
READ_TOKENS = 6000        # its answer: per panel a box, a place and its elements, each a few lines; a box per bare
                          # area (2500 on a full page; the rest is room, since the thinking takes its share first)
READ_SIDE = 1568          # the page is sent to it at most this long: boxes are read to a percent of the page
READ_USD = 0.13           # about what one costs with READER at READ_REASONING, for the plan (0.13 measured at high,
                          # 0.057 at low, 2026-11-14)
FOUND_USD = 0.13          # about what the entries call costs for ten pages, for the plan (0.13 measured, 2026-11-14)

TITLE_MODEL = "anthropic/claude-sonnet-5.5"  # names the comic: one call over the readings' stories, text only
TITLE_REASONING = "low"
TITLE_TOKENS = 200        # its answer: a few words
TITLE_USD = 0.01          # about what it costs, for the plan (a first guess: a page of text in, a line out)
TITLE_LINE = "Episode 1 · {n} pages"  # the line under the title: step 0 makes a new comic, its first episode
COVER_CANVAS = (1696, 2528)  # the blank canvas the cover is painted on: 2:3 at Nano Banana's 2K (0.101 USD)
COVER_CHARACTERS = 3      # the main characters on the cover: those drawn in the most panels
COVER_PAGES = 2           # finished pages sent with it for the comic's look: the first and the last

FAILED =(OSError, RuntimeError, ValueError)  # a call that did not come back with what was asked: the budget
                     # (BudgetExceeded is a RuntimeError), the network, a refusal, a reply that is no answer

# The task and the prompts are those of the run the owner chose (variantN, 2026-11-12) with what the first whole
# episode showed missing (2026-11-14): each panel's place and figures and how each figure is known, entries that
# fix no pose or face, a sheet that is one reference and never page content, and that no balloon, caption or
# panel is added.
FOUND_TASK = """# Task: found the colour bible of a comic episode

The images are the pages of one comic episode, in reading order, drawn in pencil: not yet inked or coloured. An
image model will finish each page exactly as drawn. So that everything keeps its look from page to page it is
given a bible: one entry per recurring character, prop and place, with a description of what the thing is and its
colours. You write the entries the bible does not have yet.

## The entries the bible has
The notes at the end list the entries that exist. They are fixed: do not return them again, under their name or
another, do not split or merge them, and write no entry for a thing a note already covers. Return an entry only
for a character, prop or place of these pages that no note covers; an empty list when the notes cover them all.
After them may come the artist's corrections: each is the truth about the thing it names, and an entry you write
for that thing says what the correction says.

## What gets an entry
- character: each person or creature with a part in the story. Name it as the story names it: read the balloons
  and the captions. When the story gives no name, a short plain label.
- prop: an object or a substance the story cares about and that is drawn in more than one panel: named, handled,
  carried, thrown, hidden behind, or drawn again and again. A tool, a piece of furniture the action uses, and also
  what is not a solid thing: a liquid thrown or spilt, a jet, a splash, smoke, a beam. Say what it is from the
  script (the balloons and captions name it) and the pencil together, and give it the colour and look of that
  thing, so that it is the same in every panel. Clothing belongs to its wearer's description; furniture and parts
  of a building that only stand there belong to their place.
- place: each setting a scene happens in. Every panel is set in a place that has an entry, also when no panel
  shows that place whole.

## The description
Two to four sentences: what it is, then its colours part by part (for a character: skin or surface, hair, eyes,
each garment; for a prop or a place: each material and large surface, and for a place its light). Describe only
what the pencil draws: no garment, feature or object that is not on the page. Describe what the thing is and
always is: its build, its parts, its clothing, its materials, its colours. Never what it is doing or showing in one
drawing: no pose, no gesture, no expression, no mood, and nothing of what a face, a screen or a visor shows. Those
change from panel to panel and belong to each panel's drawing, not to the entry.

A character has two texts in place of `description`, both detailed, because a sheet shows it once and every panel
draws it anew.
- `appearance`: its permanent physical appearance, part by part, complete enough to paint it the same from any
  angle, taken from every panel it appears in. The head: its shape, and for a face, a screen or a visor its
  surface, its colour, and how features are drawn on it (their colour, as lines or as filled shapes, glowing or
  flat). The hair or what tops the head. The build of the body and how it ends. Limbs and hands. The clothing,
  piece by piece. The material and the colour of each part. Marks and details. What it does not have, when that
  matters. No pose, no gesture, no single expression. Six to ten sentences.
- `expression`: how it expresses itself, and how far. Which parts of it carry expression (eyebrows, eyes, a
  mouth, the features drawn on a screen, posture, arms) and which stay fixed whatever it feels (a helmet, a
  visor's frame, a screen's colour). The range these pages show, from the calmest to the most extreme, as the
  list of the distinct states the pencil draws, a few words each. And how far the drawing exaggerates: subtle and
  realistic, or broad as in a cartoon. It is a range, not an instruction for any panel. Three to five sentences.

A character's or a prop's description gives its whole build, part by part, in three to six sentences, as all the
panels it appears in show it taken together: look at every one of them, not only the best drawing. The head, the
body, the limbs, and how the body ends: for a machine or a creature, what it stands, rolls or floats on. Say what
it does not have where someone drawing it would add it: a body that ends in a base has no legs. Each part with its
colour and material. A part that is a bundle of separate items (wires, cables, tools, bottles, books) is said to
be so, with whether the items are one colour or several: several different colours, unless the pencil or the
story says they are alike.

A place's entry describes that place alone, and only what is always there: its architecture, its fixtures and
furniture, its materials, its light. What belongs to another location (another room, a gate or a street
elsewhere, also in the same building) has an entry of its own. What happens in the place in one scene is in no
entry: a barrier or a tape put up, a crowd, damage, a spill, a temporary sign. It is in that panel's pencil and
is painted from the pencil there. Every thing named in a place's entry may be painted in any panel set there.

A place has a second text, `around`, because every panel set in it is completed from its entry and most of them
do not show it whole. Go through every panel set in the place that is a closer view (figures with a little of the
place behind them) and say, in two to four sentences, what stands behind and beside the figures there: the wall
or the glass, a column, an opening, furniture, a plant, the floor, what shows through a window, each with its
colour and material. Take it from what the pencil draws in those panels, however faintly; where it draws little,
fill it in so that it belongs to the place described: a closer view must be completable from this text without
guessing another room. Never leave it empty for a place that has such panels.

Choose colours that fit what the thing is and the story's tone, that agree with the entries in the notes (a place
inside a building described there shares its materials) and that tell the entries apart at a glance. `palette`:
its three to six main colours as #rrggbb, the most present first.

## Where it is drawn best
For a character or a prop: the page and a tight box around the one drawing that shows the most of it, in that
page's pixels (the sizes are listed below). Its colour sheet is painted from that drawing and must carry its
build, so how much of it shows comes first: a drawing that shows it down to where its body ends is chosen before a
half figure, and a half figure before a head or a bust, also when the fuller drawing is smaller or a balloon
covers a little of it. Only among drawings that show as much, take a character in its calmest, most usual state,
then the largest and least covered. `shows` says
which it is: "whole", "half" or "head". For a place: the box of the panel that
establishes it, a panel drawn to show the place itself; `box` is null when no panel does (a place only glimpsed
behind the characters has no establishing panel).

## Output
Reply with ONE JSON object:

```json
{"entries": [{"kind": "character", "name": "as the story names it", "description": "props and places",
              "appearance": "characters only", "expression": "characters only", "around": "places only", "palette": ["#rrggbb"], "shows": "characters and props only",
              "page": 1, "box": [x0, y0, x1, y1]}],
 "notes": "anything uncertain"}
```

`kind`: character, prop or place.
"""

# A sheet is one reference and never page content: one figure, once, as the pencil crop draws it. The first sheets
# stood on white and one held a second, full-length view the pencil does not draw; that view was then painted into a
# page's margin (2026-11-14). No row of colour swatches: one sheet came back with labelled swatches unasked, and a
# swatch or a label is one more object a page call can copy; the colours are in the figure and in the description.
SHEET_PROMPT = ("Image 1 is a pencil drawing of {name}, a {kind} of a comic. Paint it as a colour reference for that "
                "{kind}, to take colours from and nothing else. Exactly the one {kind} the pencil draws, once, in "
                "the pose the pencil draws it, the same drawing line for line, as far as the pencil shows it and no "
                "further: not completed beyond the drawing, not repeated, no second view. Clean ink lines and flat "
                "colour with simple shading, on a plain flat pale grey ground: no background, no scene, no other "
                "figure or object, no speech balloon, no text, no label, no colour swatch. Its colours: {description}")
PLACE_PROMPT = ("Image 1 is the pencil panel that establishes {name}, a place of a comic. Paint it as a colour "
                "reference for that place, to take colours from and nothing else: the same drawing line for line, "
                "every building and object where the pencil draws it, in clean ink lines, colour, shading and light. "
                "It is a reference for the place alone: a figure the pencil draws in the panel stays a plain pale "
                "grey shape with its outline, with no colours of its own. No speech balloon, no caption, no text, "
                "and nothing the pencil does not draw. Its colours: {description}")
PAGE_PROMPT = """Image 1 is a comic page drawn in pencil. Finish it: the same page in clean ink lines, colour, shading and light.

{layout}{panels}
The drawing is locked to the pencil. Every panel frame, figure, pose, face, expression, hand, object, building and sign stays exactly where and as the pencil draws it, at the same size, and the ink follows the pencil's own lines. Nothing is redesigned, added, removed or moved. The page has exactly the panels, speech balloons and caption boxes the pencil draws: none is added, split or merged.

Balloons and caption boxes keep their place, shape and outline. They are empty and stay empty: the inside of each is plain white paper and stays plain white, with no shading, tint or gradient, and no writing, letter or mark anywhere in it.

Each panel has exactly the figures counted above, each where it is drawn. What a character is comes from its description and its sheet below: its build, its parts and their colours. A figure on the page has that build exactly: no part is added that the description and the sheet do not have, and none is left out, also where the pencil shows only part of the figure or draws it small. What comes from the pencil in each panel is where the figure is, its size, which way it is turned, its pose, its gesture, its expression and what its face, screen or visor shows, as said for each figure above; these differ from panel to panel. A figure seen from behind shows the back of its head and body: no face, screen or visor is painted on it. A face is painted only where the pencil shows one, with what the pencil draws there. A character's expression in a panel is the one the pencil draws there, rendered in the manner its description gives: a face, a screen or a visor keeps its surface and colour, its features keep their colour and their way of being drawn, and only their shapes change. It stays within the range given for the character: never a way of expressing that the range does not have. A sheet shows one state of that range and does not fix the expression. A figure that is none of the characters described below is someone else: it is not given a character's look, and has colours of its own, the same wherever that figure appears again.

The elements listed above for a panel are what the pencil draws there, from the nearest to the farthest, each where it is said to be. Each is a separate complete thing with its own outline, form and colours, painted as what it is said to be. Where two overlap, the one in front covers part of the other, as said under Overlaps, and neither takes the other's shape, material or colour: an object never merges into a figure's body, and a figure partly hidden by an object is a whole figure behind it. Nothing listed is left out and nothing unlisted is added. A substance (a liquid, a jet, a splash, smoke) has one colour and one look wherever it appears on the page: those of its description below when it has one.

Where the pencil leaves a panel's background almost empty, it is completed as the place that panel is in, from that place's description below, inside the panel's frame and behind the figures only: nothing new in front of or touching a character or a drawn object, and what the pencil draws in the background stays. A panel shows the part of its place that its own pencil lines indicate: what is drawn behind and beside the figures tells which part, and it is never another room or another view. A scene is never moved to another place.

One manner of painting and one light across the whole page, and each thing in the same colours in every panel.
{refs}{entries}"""
# The layout in words, before everything else: told only that nothing goes outside the frames, the model widened a
# narrow panel over the bare paper beside it and stood a second figure there, on three prompts (2026-11-14). It was
# never told where the panels end and where the paper is bare.
LAYOUT_PROMPT = ("\nThe layout of the page, in percentages of the page (x from its left edge, y from its top):\n{panels}\n"
                 "Bare white paper in the finished page: the margins round the page and the gutters between the "
                 "panels{bare}. {on_bare} Each panel ends at its frame, where it is given here: no panel is widened, "
                 "lengthened or moved to cover bare paper, and no figure, object or background is painted on bare paper. "
                 "A balloon or a caption that sticks out of a panel's frame keeps sticking out: the frame stays where "
                 "it is given and is not moved to take the balloon in.\n")
LAYOUT_PANEL = "- Panel {n} ({where}): x {x0} to {x1}, y {y0} to {y1}."
PANELS_PROMPT = "\nWhat each panel holds, in reading order:\n"
PANEL_PROMPT = "- {which}{place}: {figures}."  # a panel: its number, its place, its figures counted; its elements follow
REFS_PROMPT = ("\nThe images after image 1 are reference sheets and stay outside the page. Each shows what one thing "
               "is: its build and its colours. Nothing from them appears on the page as a picture: no figure is taken "
               "from a sheet onto the page, and its pose, its expression and its view on the sheet are not copied.\n")
ENTRIES_PROMPT = "\nWhat is drawn on this page, what it is and its colours:\n"
EXPRESSION_PROMPT = " How it expresses itself, and its range: {expression}"  # after a character's appearance
SHEET_REF = " Its sheet is image {k}."

READ_TASK = """# Task: read one page of a comic

The image is one page of a comic episode, drawn in pencil. Say where its panels are, where its paper is bare, and
for each panel where it is set and who is drawn in it. An image model will ink and colour the page from your
reading: it must keep every panel where it is, leave the bare paper bare, set no scene somewhere else and add,
lose or mistake no figure. So measure and look with care. Positions are percentages of the page: x from 0 at its
left edge to 100 at its right edge, y from 0 at its top to 100 at its bottom. The episode's characters, props and
places are listed at the end, with the place the page before this one ended in.

- `panels`: every panel, in reading order. For each:
  - `where`: its position in a few plain words.
  - `box`: [left, top, right, bottom], where the lines of its frame are drawn. Measure each side at the frame's
    own line, also where a balloon or a caption crosses that line or sticks out past it: the frame runs on behind
    the balloon, and the side is where that line is, not where the balloon ends. A panel ends at its frame: a
    balloon, a caption, a sound effect or a part of a figure that sticks out of the frame is not in its box. For a
    drawing with no frame, the box of what is drawn.
  - `place`: the name of the listed place it is set in, exactly as listed. A panel is in the place of the panel
    before it (for the page's first panel, the place the page before ended in) unless the page shows evidence of
    a change: a caption that moves the time or the location, a view drawn to establish another place,
    surroundings drawn differently. An empty background, speed lines, a close-up or a bare wall is not evidence:
    such a panel is still where the story was and gets that place, never "none" and never a guess at another
    listed place. "none" only when there is nothing to carry on: the page before ended in no listed place and
    this panel shows none. An inset (a small panel set into a larger one or overlapping it) is a panel like any
    other, with its own box, and is in the larger panel's place unless its own drawing shows another.
  - `evidence`: "same" when it is the place of the panel before; otherwise what shows the change, in a few words.
  - `elements`: ONE list of what the pencil draws in the panel, from front to back, the nearest to the viewer
    first: every figure (a person, a creature, a robot, also one seen only in part) and every object, substance
    or effect that someone painting the panel must know: a liquid thrown or spilt, a jet, a splash, smoke,
    sparks, an impact, a tool, a thing held. An object a figure holds, hides behind, leans on, sits on or is
    partly covered by is always an element of its own, never part of the figure. Not the place's fixtures
    standing in the background, and nothing the pencil does not draw in this panel, whatever the story would
    have there. An empty list when the panel has none. For each, in this order:
    - `label`: a letter, A for the first, to name it in `behind`.
    - `form`: first, the shape that is drawn, before any name comes to mind: its outline and its size in plain
      words (a large flat disc; a thin forked bundle of strands; a flowing wavy mass; a tall rounded body with
      a round head and puffy sleeves). Written from the drawing alone, never copied from a description.
    - `kind`: "figure" or "thing".
    - `is`: then what it is, checked against the form. For a figure: the name of the listed character those
      drawn features belong to, exactly as listed, or "other": when the features are not that character's
      (another head, another build, other clothing) it is "other", also where a main character would be
      expected; a bystander, a passer-by, an unnamed person is "other". For a thing: what it is, from its form
      first (a flowing or splashing mass is a liquid; thin lines, strands or a bundle of them are cables, ropes
      or wires; a rigid shape is an object), then named from the script: the balloons and captions of this page
      and the story so far say what is thrown, held or used. A figure may use several different things in one
      scene: a thing is the same as an earlier one only when it is drawn the same way, and then it has the same
      name; a thin forked bundle is not a jet of liquid because a liquid was thrown before. When neither the
      form nor the script tells what a thing is, "unclear".
    - `what`: for "other" and for "unclear", a few words that tell it from the rest.
    - `entry`: for a thing, the name of the listed prop it is, exactly as listed, or "".
    - `box`: [left, top, right, bottom] of the element in percentages of the PANEL (0, 0 its top left corner).
    - `behind`: the elements in front of it that cover a part of it; an empty list when nothing does. For each:
      `of`, that element's label; `hidden`, the part of this element it covers; `shows`, what of this element
      still shows past it (its body below the shoulders is hidden behind the disc; its head and both hands show
      past the disc's rim).
    - `of`: for a thing, how it stands to the figures: who throws, holds or is hit by it.
    - for a figure: `seen`, from the front, the side or behind, and how much of it shows (whole, to the waist,
      a hand only); `faces`, whom or what it is turned to (another figure, the viewer, away); `face`, what the
      pencil draws on its face, screen or visor in this panel in a few words (eyes closed, a flat line, a
      frown), or "not visible" when the pencil shows none: a figure drawn from behind, or with its face turned
      away or covered, has no visible face, whatever its character usually shows.
- `story`: what happens on this page in one or two plain sentences, naming the things the action is about as the
  script names them. No dialogue quoted: say what is said in your own words.
- `bare`: every area of bare paper larger than a margin or a gutter: the part of a row a narrower panel does not
  reach, an empty band between two rows, an empty corner. For each, `where` in a few plain words and its `box`.
  Paper with a balloon or a caption standing on it is still bare paper. An empty list when the panels fill the
  page but for its margins and gutters.
- `on_bare`: what the pencil draws on bare paper, outside every panel: each balloon, caption or sound effect that
  lies wholly or partly outside the frames, in a few words: what it is and where it lies, never its words. Quote
  no lettering: what you write is read by the image model, which would write it on the page. An empty list when
  there is none.

Reply with ONE JSON object:

```json
{"panels": [{"where": "...", "box": [0, 0, 100, 100], "place": "a listed place, or none", "evidence": "same",
             "elements": [{"label": "A", "form": "...", "kind": "figure", "is": "a listed character, or other",
                           "what": "...", "box": [0, 0, 100, 100], "behind": [], "seen": "...", "faces": "...",
                           "face": "... or not visible"},
                          {"label": "B", "form": "...", "kind": "thing", "is": "...", "what": "...",
                           "entry": "a listed prop, or empty", "box": [0, 0, 100, 100],
                           "behind": [{"of": "A", "hidden": "...", "shows": "..."}], "of": "..."}]}],
 "story": "...",
 "bare": [{"where": "...", "box": [0, 0, 100, 100]}],
 "on_bare": ["..."]}
```
"""

TITLE_TASK = """# Task: name a comic

Below are the characters of a comic and what happens on each of its pages. Give the comic its title, for its cover
and its shelf: one to four words, plain and catchy, the kind of name a reader remembers after one look. It may name
the main characters or the story's hook, and gives away no ending. Plain words only: no quotation marks, no colon,
no subtitle, no episode number, no emoji.

Reply with ONE JSON object: {"title": "..."}
"""
COVER_PROMPT = """Image 1 is a blank portrait canvas. Paint on it the front cover of a comic book.

At the top of the cover, the title, lettered prominently, large and easy to read, spelled exactly as given here, letter for letter: {title}
The title is the only text on the cover: no subtitle, author, issue number, price, logo, caption or speech balloon.

Below the title, {who}, in one scene that sums up the comic, posed as a cover shows its heroes. What the comic is about: {story}
{characters}
The look is the comic's own: {look}, in the same manner of ink lines, colour, shading and light."""
COVER_CHARACTER = "- {name}: {description}{sheet}"  # a character on the cover, after COVER_CHARACTERS_PROMPT
COVER_CHARACTERS_PROMPT = ("\nEach character is exactly as its description and its reference sheet show it: its build, "
                           "its parts and their colours. A sheet is a reference only: its pose and its view are not "
                           "copied.\n")
COVER_LOOK = "images {pages} are finished pages of the comic"


def _fit(img: Image.Image, side: int) -> Image.Image:
    """The image in RGB, made smaller when its long side passes `side`."""
    img = img.convert("RGB")
    s = side / max(img.size)
    return img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS) if s < 1 else img


def _save(path: Path, data: dict) -> None:
    """The JSON written only when it is not what the file already says: a run that changes nothing writes nothing."""
    text = json.dumps(data, indent=1, ensure_ascii=False)
    if not path.exists() or path.read_text(encoding="utf-8") != text:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def painted_sheet(file: Path, model: str) -> Path:
    """Where the sheet this step paints with `model` for the entry in `file` is kept: <id>.<model>.png."""
    return file.with_name(f"{file.stem}.{model}.png")


def entries(bible: Path, model: str | None = None) -> dict[str, dict]:
    """The bible's entries, {"character/<id>": its JSON with "kind", "file" (the JSON's path), "own" (the artist's
    picture, <id>.png, or None) and "sheet" (the picture to colour from: the artist's, or else the one painted with
    `model`, or None)}, characters first, then props, then places. "description" is what the thing is and its
    colours in every entry: a character's is its "appearance", beside which it has its "expression"."""
    out = {}
    for kind, folder in KINDS.items():
        for f in sorted((bible / folder).glob("*.json")):
            e = json.loads(f.read_text(encoding="utf-8"))
            e["description"] = e.get("appearance") or e.get("description") or ""
            own = next((f.with_suffix(s) for s in PICTURES if f.with_suffix(s).exists()), None)
            made = painted_sheet(f, model) if model else None
            out[f"{kind}/{f.stem}"] = {**e, "kind": kind, "file": f, "own": own,
                                       "sheet": own or (made if made and made.exists() else None)}
    return out


def recipe_of(model: str) -> list:
    """What shapes a model's result besides its prompt and images, for the stamps."""
    return {"klein": [bfl.KLEIN, SEED, bfl.KLEIN_STEPS, MAX_PIXELS, MAX_SIDE],
            "nano": [gemini_image.NANO, gemini_image.SIZES, gemini_image.JPEG]}[model]


def canvas_of(model: str, size: tuple[int, int]) -> dict:
    """How an image of `size` is put to the model: {"scale": it is made this much smaller first, "canvas": the
    size of the image sent, "pad": where it sits on it, "ask": the model's size request}. Klein makes any size up
    to its limits, so the image goes as it is. Nano Banana makes only its own aspect ratios: the image is centred
    on a white canvas of the nearest one, so nothing is cropped or stretched to fit, and asked at the smallest size
    that does not shrink it."""
    w, h = size
    if model == "klein":
        s = min(1.0, MAX_SIDE / max(size), (MAX_PIXELS / (w * h)) ** 0.5)
        return {"scale": s, "canvas": [int(w * s), int(h * s)], "pad": [0, 0], "ask": None}
    aspect = gemini_image.nearest(w, h)
    r = gemini_image.SIZES[aspect][0] / gemini_image.SIZES[aspect][1]
    cw, ch = (w, round(w / r)) if w / h > r else (round(h * r), h)
    return {"scale": 1.0, "canvas": [cw, ch], "pad": [(cw - w) // 2, (ch - h) // 2],
            "ask": [aspect, gemini_image.size_for(aspect, cw)]}


def frame_of(model: str, size: tuple[int, int], made: tuple[int, int]) -> list[float]:
    """The box of an image of `size` on what the model made from it (`made`, its pixel size), by canvas_of's
    layout: the model's canvas stretched onto its output."""
    c = canvas_of(model, size)
    kx, ky = made[0] / c["canvas"][0], made[1] / c["canvas"][1]
    return [c["pad"][0] * kx, c["pad"][1] * ky, (c["pad"][0] + size[0] * c["scale"]) * kx,
            (c["pad"][1] + size[1] * c["scale"]) * ky]


def price_of(model: str, size: tuple[int, int]) -> float:
    """About what one image call on an image of `size` costs, in USD, said before it is sent: Klein's worst case
    for its pixels, Nano Banana's list price for the size asked (the tokens sent add a little)."""
    c = canvas_of(model, size)
    if model == "klein":
        return bfl.klein_reserve_usd(c["canvas"][0] * c["canvas"][1])
    return gemini_image.PRICE[c["ask"][1]]


def paint(model: str, prompt: str, first: Image.Image, refs: list[Image.Image], tag: str) -> tuple[Image.Image, float]:
    """One image call, the only place the models differ: `first` edited by the prompt with the reference images.
    (the model's own output: `first` lies on it at frame_of; its cost in USD)."""
    c = canvas_of(model, first.size)
    if model == "klein":
        img, credits = bfl.flux3_klein(prompt, [first if c["scale"] == 1 else first.resize(c["canvas"], Image.LANCZOS)] + refs,
                                       tag=tag, seed=SEED)
        return img, (credits or 0) / 100
    sheet = Image.new("RGB", c["canvas"], (255, 255, 255))
    sheet.paste(first.convert("RGB"), tuple(c["pad"]))
    return gemini_image.edit(prompt, [sheet] + refs, *c["ask"], tag=tag)


def _listed(have: dict[str, dict]) -> str:
    """The bible's entries as text for a call: one line each, its kind, its name, its description."""
    return "\n".join(f"- {e['kind']} \"{e.get('name') or k.split('/')[1]}\": {e.get('description') or '(no description)'}"
                     for k, e in have.items()) or "(none)"


def _box(box, scale: float, size: tuple[int, int]) -> list[int] | None:
    """A reply's box on the page as sent, in the page's own pixels; None when it is not a box."""
    if not isinstance(box, list) or len(box) != 4:
        return None
    x0, y0, x1, y1 = (float(v) * scale for v in box)
    x0, x1 = sorted((max(0, min(size[0], round(x0))), max(0, min(size[0], round(x1)))))
    y0, y1 = sorted((max(0, min(size[1], round(y0))), max(0, min(size[1], round(y1)))))
    return [x0, y0, x1, y1] if x1 - x0 >= 16 and y1 - y0 >= 16 else None


def found(pages: list[Path], bible: Path) -> dict:
    """The bible's entries, founded (found.json: {"stamp", "entries": {key: {"page": stem, "box" or None}}: where
    each is drawn best, "notes", "cost": of the last call}). An entry in the folder is fixed, whoever wrote it: the
    call is given every one as a note and writes only entries for what none covers, so no later run renames,
    merges, drops or rewrites one. The call is asked when the pages are not those it last saw, or when an entry it
    founded has no file any more: to have an entry written anew, delete its file (and its sheet). One call for the
    whole episode, because an entry is what all its drawings show taken together. It was also asked each panel's
    place and figures at first, and gave another answer at every asking, with other places and names (2026-11-14):
    that is now each page's own reading (read)."""
    f = bible / "found.json"
    old = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    have = entries(bible)
    f_notes = bible / "corrections.txt"  # the artist's corrections, in their own words: what an entry must say
    corrections = f_notes.read_text(encoding="utf-8").strip() if f_notes.exists() else ""
    # A changed task or a new correction asks again, and can only add: to have it reach an entry, delete that entry.
    stamp = fresh.digest(*pages, FOUND_TASK, corrections, FOUND_MODEL, REASONING, FOUND_SIDE)
    if old.get("stamp") == stamp and all(key in have for key in old.get("entries", {})):
        return old
    sent = [_fit(Image.open(p), FOUND_SIDE) for p in pages]
    sizes = "\n".join(f"- Page {n}: {im.width} x {im.height} px" for n, im in enumerate(sent, 1))
    content = [{"type": "text", "text": f"{FOUND_TASK}\n## The notes: the entries that exist\n{_listed(have)}\n\n"
                                        f"## The artist's corrections\n{corrections or '(none)'}\n\n## The pages\n{sizes}\n"}]
    for n, im in enumerate(sent, 1):
        content += [{"type": "text", "text": f"Page {n}:"}, image_part(im, max_side=FOUND_SIDE)]
    print(f"  plan: the entries call over {len(pages)} pages with {len(have)} entries fixed, about {FOUND_USD:.2f} USD; "
          f"{spent_today():.3f} USD spent today of {DAILY_CAP_USD:.2f}")
    reply, cost = ask_json(FOUND_MODEL, content, f"finish found {pages[0].stem}", ANSWER_TOKENS, REASONING, brief=False)
    stems = {p.stem for p in pages}
    data = {"stamp": stamp, "entries": {k: w for k, w in old.get("entries", {}).items() if k in have and w["page"] in stems},
            "notes": reply.get("notes"), "cost": cost}
    for e in reply.get("entries") or []:
        if e.get("kind") not in KINDS or not e.get("name"):
            continue
        key = f"{e['kind']}/{slug(e['name'], 'entry')}"
        if key in have:
            continue  # it exists: fixed, also where the call returned it again
        number = re.search(r"\d+", str(e.get("page")))  # 2, "2" and "Page 2" are all page 2
        n = int(number.group()) if number and 1 <= int(number.group()) <= len(pages) else 1
        full = Image.open(pages[n - 1]).size
        data["entries"][key] = {"page": pages[n - 1].stem, "box": _box(e.get("box"), full[0] / sent[n - 1].width, full)}
        hexes = [c for c in e.get("palette") or [] if re.fullmatch("#[0-9a-fA-F]{6}", str(c))]
        said = lambda k: str(e.get(k) or "").strip()
        _save(bible / KINDS[e["kind"]] / f"{key.split('/')[1]}.json",
              {"name": e["name"], "kind": e["kind"],
               **({"appearance": said("appearance") or said("description"), "expression": said("expression")}
                  if e["kind"] == "character" else  # a place's one description: the whole, then its closer views
                  {"description": " ".join(t for t in (said("description"), e["kind"] == "place" and said("around")) if t)}),
               "palette": hexes})
    _save(f, data)
    return data


def sheet_crop(page: Image.Image, box: list[int]) -> Image.Image:
    """The pencil drawing a sheet is painted from: the box and PAD around it, SHEET_SIDE on its long side."""
    x0, y0, x1, y1 = box
    px, py = (x1 - x0) * PAD, (y1 - y0) * PAD
    crop = page.convert("RGB").crop((int(max(0, x0 - px)), int(max(0, y0 - py)),
                                     int(min(page.width, x1 + px)), int(min(page.height, y1 + py))))
    s = SHEET_SIDE / max(crop.size)
    return crop.resize((round(crop.width * s), round(crop.height * s)), Image.LANCZOS)


def sheet_jobs(pages: dict[str, Path], bible: Path, fd: dict, model: str, st: fresh.Stamps) -> list[dict]:
    """The colour sheets still to paint with `model`: one for every founded entry that has a box, no picture of the
    artist's and no sheet whose stamp holds. [{"key", "prompt", "page": the pencil page's stem, "box", "stamp",
    "target": where it is kept (painted_sheet)}]."""
    jobs, have = [], entries(bible)
    for key, where in fd["entries"].items():
        e = have.get(key)
        if e is None or not where.get("box") or e["own"]:
            continue  # no entry file, nothing to paint from, or the artist's own picture
        prompt = (PLACE_PROMPT if e["kind"] == "place" else SHEET_PROMPT).format(
            name=e.get("name") or key, kind=e["kind"], description=e.get("description") or "")
        stamp = fresh.digest(pages[where["page"]], where["box"], prompt, recipe_of(model), PAD, SHEET_SIDE)
        target = painted_sheet(e["file"], model)
        if not st.current(f"{key}/{model}", stamp, target):
            jobs.append({"key": key, "prompt": prompt, "page": where["page"], "box": where["box"], "stamp": stamp,
                         "target": target})
    return jobs


def sheets(jobs: list[dict], pages: dict[str, Path], bible: Path, report: dict, model: str, st: fresh.Stamps) -> None:
    """Each job's sheet painted (sheet_jobs) and kept per model, so a run with another model paints its own and a
    run back finds this one. The sheet is the model's whole output: a reference to colour from, never laid back on
    the page. report["sheets"][key/model] gets what was painted and its cost, or why it was not. Each is asked for
    once in a run; one that failed is a job again in the next run, a provider's refusal for content included: the
    same call was refused and then passed (2026-11-14)."""
    for job in jobs:
        key = job["key"]
        try:
            img, usd = paint(model, job["prompt"], sheet_crop(Image.open(pages[job["page"]]), job["box"]), [],
                             f"finish sheet {key}")
        except FAILED as err:
            report["sheets"][f"{key}/{model}"] = {"error": str(err)[:300]}
            print(f"  sheet {key}: not painted, {str(err)[:200]}")
            continue
        img.save(job["target"])
        st.made(f"{key}/{model}", job["stamp"])
        report["sheets"][f"{key}/{model}"] = {"file": str(job["target"].relative_to(bible)), "from": [job["page"], job["box"]],
                                              "prompt": job["prompt"], "usd": usd}
        print(f"  sheet {key}: {img.width} x {img.height}, {usd:.3f} USD")


def _read_text(have: dict[str, dict], before: str | None) -> str:
    """What a page's reading is asked: the task, the bible's entries, and what came before the page (`before`:
    {"place": the key of the place the page before ended in, or None; "story": the pages before, a line or two
    each, as their readings told them})."""
    place = before["place"]
    came = f"\"{have[place].get('name') or place}\"" if place in have else "none: this is the first page, or the page before ended in no listed place"
    story = "\n".join(f"- Page {n}: {t}" for n, t in enumerate(before["story"], 1)) or "(this is the first page)"
    return (f"{READ_TASK}\n## The episode's characters, props and places\n{_listed(have)}\n\n"
            f"## The story so far\n{story}\n\n## The place the page before ended in\n{came}\n")


def read(page: Path, have: dict[str, dict], before: dict, reader: str = READER,
         effort: str = READ_REASONING) -> tuple[dict, float]:
    """One page as a small call reads it (READ_TASK), with the bible's entries, the story so far and the place the
    page before ended in (`before`, as _read_text takes it): ({"panels": [{"where", "box": [x0, y0, x1, y1] in
    percentages of the page, "place": an entry's key or None, "evidence", "figures": [{"who": an entry's key or
    "other", "by", "what", "seen"}], "things": [{"is", "entry": a prop's key or None, "of", "where"}]}] in reading
    order, "story": the page in a line or two, "bare": [{"where", "box"}] for each area of bare paper larger than a
    margin or a gutter, "on_bare": [what the pencil draws outside every panel, in words]}, the call's cost). One
    call per page, apart from the entries: it sees one page at full size, costs a fraction of the episode's call,
    and asked again changes that page and no entry or sheet. The things are read because a thrown liquid named
    nowhere was painted as steam, flame and a beam on three pages, and a table a figure hid behind was fused with
    the figure (2026-11-14). Boxes read by the local frame check (panels_of) were not used: it loses a panel whose
    frame balloons cross."""
    sent = _fit(Image.open(page), READ_SIDE)
    reply, cost = ask_json(reader, [{"type": "text", "text": _read_text(have, before)}, image_part(sent, max_side=READ_SIDE)],
                           f"finish read {page.stem}", READ_TOKENS, effort, brief=False)
    by_name = {e.get("name"): key for key, e in have.items()}
    known = lambda name, kind: by_name.get(name) if have.get(by_name.get(name), {}).get("kind") == kind else None
    rows_of = lambda key: [r for r in (reply.get(key) if isinstance(reply.get(key), list) else []) if isinstance(r, dict)]
    numbers = [v for r in rows_of("panels") + rows_of("bare") for v in (r.get("box") if isinstance(r.get("box"), list) else [])
               if isinstance(v, (int, float))]
    # A reading that gives its boxes in the image's pixels, not in percentages (one page of ten did, 2026-11-14),
    # has a value past 100: its boxes are brought to percentages by the size of the image it was sent.
    kx, ky = (100 / sent.width, 100 / sent.height) if max(numbers, default=0) > 100 else (1, 1)

    def boxed(rows) -> list[dict]:
        out = []
        for r in rows:
            box = r.get("box")
            if isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box):
                x0, y0, x1, y1 = (max(0, min(100, round(v * k))) for v, k in zip(box, (kx, ky, kx, ky)))
                if x1 > x0 and y1 > y0:
                    out.append({**r, "where": str(r.get("where") or ""), "box": [x0, y0, x1, y1]})
        return out

    def element(e: dict) -> dict:
        """One element of a panel as the prompt takes it: "key" is its entry (a figure's character, a thing's
        prop) or None; "box" its place in the panel in percentages, or None when the reply gave none."""
        figure, text = e.get("kind") == "figure", lambda k: str(e.get(k) or "").strip()
        box = e.get("box") if isinstance(e.get("box"), list) and len(e["box"]) == 4 else None
        box = [max(0, min(100, round(v))) for v in box] if box and all(isinstance(v, (int, float)) for v in box) else None
        return {"label": text("label"), "kind": "figure" if figure else "thing", "form": text("form"),
                "key": known(e.get("is"), "character") if figure else known(e.get("entry"), "prop"),
                "is": text("is"), "what": text("what"), "box": box if box and box[2] > box[0] and box[3] > box[1] else None,
                "behind": [{k: str(b.get(k) or "").strip() for k in ("of", "hidden", "shows")}
                           for b in e.get("behind") or [] if isinstance(b, dict) and b.get("of")],
                "of": text("of"), "seen": text("seen"), "faces": text("faces"), "face": text("face")}

    panels = [{"where": r["where"], "box": r["box"], "place": known(r.get("place"), "place"), "evidence": str(r.get("evidence") or ""),
               "elements": [element(e) for e in r.get("elements") or [] if isinstance(e, dict)]}
              for r in boxed(rows_of("panels"))]
    return {"panels": panels, "story": str(reply.get("story") or ""),
            "bare": [{"where": r["where"], "box": r["box"]} for r in boxed(rows_of("bare"))],
            "on_bare": [str(t) for t in reply.get("on_bare") or [] if str(t).strip()]}, cost


def on_page(seen: dict, stem: str, where: dict) -> list[str]:
    """The entries on a page: the places, the characters and the props of its panels, as its reading has them, and
    every entry drawn best on it (`where`: found.json's entries)."""
    drawn = [k for pn in seen["panels"] for k in [pn["place"], *(e["key"] for e in pn["elements"])] if k]
    return list(dict.fromkeys(drawn + [k for k, w in where.items() if w["page"] == stem]))


def placed_words(box: list[int]) -> str:
    """An element's box in its panel (percentages) as words: where it is and about how large."""
    third = lambda a, b, low, mid, high: low if (a + b) / 2 < 38 else high if (a + b) / 2 > 62 else mid
    share = lambda v: next(w for limit, w in ((20, "a small part"), (30, "a quarter"), (42, "a third"), (58, "half"),
                                              (75, "two thirds"), (101, "most")) if v < limit)
    across, down = third(box[0], box[2], "left", "centre", "right"), third(box[1], box[3], "upper", "middle", "lower")
    where = "in the middle" if (across, down) == ("centre", "middle") else f"at the {down} {across}"
    return f"{where} of the panel, {share(box[2] - box[0])} of its width and {share(box[3] - box[1])} of its height"


def page_prompt(on: list[str], have: dict[str, dict], used: list[str], seen: dict) -> str:
    """A page's prompt, in this order: the layout as the page's reading has it (`seen`: each panel's box, the bare
    paper, what stands on it), what each panel holds (its place, its figures counted, then its elements from front
    to back, each with where it is in the panel, and every overlap as a sentence), the rules, what the reference
    images are, then every entry on the page with its description, and for those in `used` the number of the
    image that is its sheet. A figure that is no entry is "someone else"; a known character is named without its
    drawn form, which its description gives."""
    name = lambda k: have[k].get("name") or k

    def said(e: dict) -> str:
        """An element's name in the prompt."""
        if e["key"] in have:
            return name(e["key"]) + (f" ({e['is']})" if e["kind"] == "thing" and e["is"] else "")
        return (f"someone else ({e['what'] or e['form'] or 'no entry'})" if e["kind"] == "figure"
                else e["is"] + (f" ({e['what'] or e['form']})" if e["what"] or (e["form"] and e["is"] == "unclear") else ""))

    def panel(n: int, pn: dict) -> str:
        figures, by_label = sum(e["kind"] == "figure" for e in pn["elements"]), {e["label"]: e for e in pn["elements"]}
        head = PANEL_PROMPT.format(which=f"Panel {n}", place=f", in {name(pn['place'])}" if pn["place"] in have else "",
                                   figures=f"{figures} figure{'s' if figures > 1 else ''}" if figures else "no figure")
        rows = [f"  {e['label']}. {said(e)}"
                + (f": {e['form']}" if e["form"] and e["kind"] == "thing" and e["is"] != "unclear" else "")
                + (f"; {placed_words(e['box'])}" if e["box"] else "")
                + "".join(f"; {word}: {e[k]}" for k, word in (("of", "it"), ("seen", "seen"), ("faces", "turned to"), ("face", "face"))
                          if e[k]) + "."
                for e in pn["elements"]]
        over = [f"  {said(by_label[b['of']])} is in front of {said(e)}"
                + (f": of {said(e)}, {b['hidden']} is hidden" if b["hidden"] else "") + (f"; {b['shows']}" if b["shows"] else "") + "."
                for e in pn["elements"] for b in e["behind"] if b["of"] in by_label]
        return "\n".join([head + (" From front to back:" if rows else "")] + rows + (["  Overlaps:"] + over if over else []))

    box = lambda b: {"x0": b[0], "y0": b[1], "x1": b[2], "y1": b[3]}
    told = [panel(n, pn) for n, pn in enumerate(seen["panels"], 1)]
    bare = "".join(f"; {b['where'] or 'an empty area'} (x {b['box'][0]} to {b['box'][2]}, y {b['box'][1]} to {b['box'][3]})"
                   for b in seen["bare"])
    on_bare = ("On that bare paper the pencil draws only: " + "; ".join(seen["on_bare"]) + "."
               if seen["on_bare"] else "The pencil draws nothing on that bare paper.")
    placed_ = LAYOUT_PROMPT.format(panels="\n".join(LAYOUT_PANEL.format(n=n, where=p["where"] or "in reading order", **box(p["box"]))
                                                    for n, p in enumerate(seen["panels"], 1)), bare=bare, on_bare=on_bare)
    lines = [f"- {name(k)} ({have[k]['kind']}): {have[k].get('description') or ''}"
             + (EXPRESSION_PROMPT.format(expression=have[k]["expression"]) if have[k].get("expression") else "")
             + (SHEET_REF.format(k=2 + used.index(k)) if k in used else "") for k in on]
    return PAGE_PROMPT.format(layout=placed_, panels=PANELS_PROMPT + "\n".join(told) + "\n" if told else "",
                              refs=REFS_PROMPT if used else "", entries=ENTRIES_PROMPT + "\n".join(lines) if lines else "")


def regions(seg: sam.Segmenter, page: Image.Image) -> np.ndarray:
    """The page's balloons and caption boxes, one label per region (page size, 0 outside, 1 on from the top of the
    page): SAM's instances of LETTER_PROMPTS, the smallest first. An instance that holds no kept region is a new
    region; one that holds a single kept region is that region seen again, larger, and adds its free pixels to it
    (SAM reads a tall page tile by tile, and a balloon across two tiles comes back as a part and as a whole; a
    caption comes back under both prompts); one that holds several is a group of touching balloons and is dropped
    (kept, it gave three balloons one centre, 2026-11-12). A region is held when SAME of it lies in the instance."""
    lab = np.zeros((page.height, page.width), np.uint8)
    n = 0
    for _, m, _ in sorted(seg.find(page.convert("RGB"), [(p, LETTER_SCORE) for p in LETTER_PROMPTS]), key=lambda t: t[1].sum()):
        on = np.bincount(lab[m], minlength=n + 1)[1:]  # its pixels on each kept region
        held = np.nonzero(on >= SAME * np.bincount(lab.ravel(), minlength=n + 1)[1:])[0] if n else []
        if len(held) == 1:
            lab[m & (lab == 0)] = 1 + int(held[0])
        elif len(held) == 0 and m.any() and n < 255:
            n += 1
            lab[m & (lab == 0)] = n
    order = sorted(range(1, n + 1), key=lambda k: find_objects(lab)[k - 1][0].start)
    return np.concatenate([[0], np.argsort(order) + 1]).astype(np.uint8)[lab]


def inside_of(region: np.ndarray, width: int) -> np.ndarray:
    """A region drawn in by EDGE of the page's width: its inside, clear of its outline."""
    return binary_erosion(region, iterations=max(1, round(EDGE * width)))


def parts(lab: np.ndarray, k: int, sl: tuple) -> tuple[tuple, np.ndarray, np.ndarray, np.ndarray]:
    """Region k on its box widened by GROW (the first value): its inside (drawn in by EDGE), its core (drawn in by
    CORE, or the inside when that leaves nothing) and its zone (grown by GROW)."""
    w = lab.shape[1]
    g = max(1, round(GROW * w))
    win = (slice(max(0, sl[0].start - g), min(lab.shape[0], sl[0].stop + g)),
           slice(max(0, sl[1].start - g), min(w, sl[1].stop + g)))
    reg = lab[win] == k
    inside, core = inside_of(reg, w), binary_erosion(reg, iterations=max(1, round(CORE * w)))
    return win, inside, core if core.any() else inside, binary_dilation(reg, iterations=g)


def whiten(view: np.ndarray, core: np.ndarray, zone: np.ndarray, floor: float) -> np.ndarray:
    """A balloon's paper made pure white, in place: the nearly white pixels of the zone (lightness from `floor`,
    chroma up to WHITE_C) that are joined to the core through nearly white pixels. The outline is not nearly
    white, so the white stops at it and nothing beyond it is reached; a mark inside the balloon is not nearly white
    either and stays. Returns the pixels made white."""
    tone = to_lab(view)
    near = zone & (tone[..., 0] >= floor) & (np.hypot(tone[..., 1], tone[..., 2]) <= WHITE_C)
    joined, _ = label(near)
    keep = near & np.isin(joined, np.unique(joined[core & near]))
    view[keep] = 255
    return keep


def blank(pencil: np.ndarray, lab: np.ndarray) -> np.ndarray:
    """The pencil page as it is sent: the whole inside of every region flat pure white, text and paper grain alike,
    and the paper between the inside and the pencilled outline with it (whiten). The outlines are untouched. Only
    the text was cleared at first, to a flat tone the paper around it did not have, and the model painted that
    faint step as a cream centre in a grey rim (2026-11-12)."""
    out = pencil.copy()
    for k, sl in enumerate(find_objects(lab), 1):
        win, inside, _, zone = parts(lab, k, sl)
        out[win][inside] = 255
        whiten(out[win], inside, zone, PAPER_L)
    return out


def _moved(sl: tuple, offset: list[int], shape: tuple) -> tuple[tuple, tuple]:
    """A box moved by offset (dx, dy) and cut to the page: (where it lands on the page, the part of the box that
    lands there)."""
    y0, x0 = sl[0].start + offset[1], sl[1].start + offset[0]
    cy0, cy1 = max(0, y0), min(shape[0], sl[0].stop + offset[1])
    cx0, cx1 = max(0, x0), min(shape[1], sl[1].stop + offset[0])
    return (slice(cy0, cy1), slice(cx0, cx1)), (slice(cy0 - y0, cy1 - y0), slice(cx0 - x0, cx1 - x0))


def placed(sent: Image.Image, painted: Image.Image, lab: np.ndarray) -> list[dict]:
    """Where the model drew each lettering region, [{"region", "offset": [dx, dy] in page pixels, "fit"}]: the move,
    up to SHIFT each way at the checks' size, that lays the most of the output's ink on the region's pencilled
    outline (the strokes of the page as sent, text cleared, within GROW of the region's edge); "fit" is the share
    of that outline the ink then covers. Each region is placed on its own, because a model moves balloons apart
    from each other and from the page (one panel 52 px shorter, the next unmoved, 2026-11-12). SAM on the output
    was the first way: it found 2, 0 and 0 of 6 regions on three pages, and once matched two touching balloons as
    one, which moved a balloon's letters 189 px onto its neighbour's."""
    s = CHECK_SIDE / max(sent.size)
    size = (round(sent.width * s), round(sent.height * s))
    strokes = lines_of(sent.resize(size, Image.LANCZOS), PENCIL_DELTA)
    ink = lines_of(painted.resize(size, Image.LANCZOS), INK_DELTA)
    small = np.asarray(Image.fromarray(lab).resize(size, Image.NEAREST))
    g = max(2, round(GROW * size[0]))
    out = []
    for k, sl in enumerate(find_objects(small), 1):
        win = tuple(slice(max(0, a.start - SHIFT - g), min(n, a.stop + SHIFT + g)) for a, n in zip(sl, small.shape))
        reg = small[win] == k
        outline = strokes[win] & binary_dilation(reg, iterations=g) & ~binary_erosion(reg, iterations=g)
        peak, dy, dx = _peak(np.fft.rfft2(outline.astype(np.float32)), ink[win])
        out.append({"region": k, "offset": [round(-dx / s), round(-dy / s)],
                    "fit": round(peak / max(1, int(outline.sum())), 3)})
    return out


def clean(painted: np.ndarray, lab: np.ndarray, places: list[dict]) -> tuple[np.ndarray, list[dict]]:
    """The model's output with every balloon's and caption's paper pure white (whiten, on each pencil region moved
    by its offset: no match on the output is needed), and per region what was found there: {"white": the share of
    the balloon's inside (the white with its holes filled) that is paper, "written": the share that is as dark as
    type (a mark with white all round it; the outline has the balloon's outside on its other side and is not
    counted), "outline_dark": the zone's dark pixels before and after, which whitening must leave equal}."""
    out, boxes, rows = painted.copy(), find_objects(lab), []
    for p in places:
        win, _, core, zone = parts(lab, p["region"], boxes[p["region"] - 1])
        dst, src = _moved(win, p["offset"], lab.shape)
        view = out[dst]
        before = zone[src] & (np.asarray(Image.fromarray(view).convert("L")) < TEXT_INK)
        white = whiten(view, core[src], zone[src], WHITE_L)
        filled = binary_fill_holes(white)
        after = zone[src] & (np.asarray(Image.fromarray(view).convert("L")) < TEXT_INK)
        rows.append({"white": round(float(white.sum() / max(1, filled.sum())), 5),
                     "written": round(float((filled & before).sum() / max(1, filled.sum())), 5),
                     "outline_dark": [int(before.sum()), int(after.sum())]})
    return out, rows


def letter(img: np.ndarray, pencil: np.ndarray, lab: np.ndarray, places: list[dict]) -> tuple[np.ndarray, float]:
    """The cleaned output with the pencil's letters on it, and the share of the letter pixels that are the pencil's
    exactly (1 when the page has none). Each region's text pixels (the dark pixels of its inside, under TEXT_INK),
    with FRINGE around them, are the pencil page's own values, set down at the region's offset: on pure white
    paper that is the pencil's lettering pixel for pixel, where darkening the model's paper (the first way, on a
    tinted inside) only kept its shapes."""
    out, lum = img.copy(), np.asarray(Image.fromarray(pencil).convert("L"))
    boxes, blocks = find_objects(lab), []
    for p in places:
        sl = boxes[p["region"] - 1]
        inside = inside_of(lab[sl] == p["region"], lab.shape[1])
        dst, src = _moved(sl, p["offset"], lab.shape)
        glyph = (binary_dilation(inside & (lum[sl] < TEXT_INK), iterations=FRINGE) & inside)[src]
        out[dst][glyph] = pencil[sl][src][glyph]
        blocks.append((dst, pencil[sl][src], glyph))
    same = sum(int((out[dst][glyph] == was[glyph]).all(-1).sum()) for dst, was, glyph in blocks)
    total = sum(int(glyph.sum()) for _, _, glyph in blocks)
    return out, round(same / total, 5) if total else 1.0


def lines_of(img: Image.Image, delta: int) -> np.ndarray:
    """The picture's lines: the pixels darker by `delta` than the lightest tone that closes over them within LINE
    pixels. A stroke is found on paper and an outline on colour alike; a filled dark area is not a line."""
    lum = np.asarray(img.convert("L"), np.int16)
    return grey_closing(lum, size=(LINE, LINE)) - lum > delta


def line_maps(pencil: Image.Image, other: Image.Image, mask: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
    """At CHECK_SIDE: (the pencil's strokes outside its lettering, the other picture's ink lines, the pencil's
    lettering mask, the scale from the page to that size)."""
    s = CHECK_SIDE / max(pencil.size)
    size = (round(pencil.width * s), round(pencil.height * s))
    out = np.asarray(Image.fromarray(mask).resize(size, Image.NEAREST))
    return (lines_of(pencil.resize(size, Image.LANCZOS), PENCIL_DELTA) & ~out,
            lines_of(other.resize(size, Image.LANCZOS), INK_DELTA), out, s)


def _peak(f_strokes: np.ndarray, ink: np.ndarray) -> tuple[float, int, int]:
    """(the most ink pixels a whole-picture move of up to SHIFT each way lays on the strokes, that move as dy, dx):
    the peak of the two line maps' cross-correlation. f_strokes: the strokes' transform (rfft2)."""
    c = np.fft.irfft2(f_strokes * np.conj(np.fft.rfft2(ink.astype(np.float32))), s=ink.shape)
    r = np.arange(-SHIFT, SHIFT + 1)
    win = c[np.ix_(r, r)]
    i, j = np.unravel_index(int(win.argmax()), win.shape)
    return float(win[i, j]), int(r[i]), int(r[j])


def laid(pencil: Image.Image, made: Image.Image, frame: list[float], mask: np.ndarray) -> tuple[Image.Image, dict]:
    """The model's output brought onto the pencil page's pixel grid, and the mapping found. The page is first cut
    from the output at `frame` (frame_of) and brought to the pencil's size; a model does not keep that exactly (it
    redraws the page a little narrower, taller or moved), so the cut page's line map is then scaled about its centre,
    each way on its own (SCALES), and moved, to where the most of its ink lies on the pencil's strokes, each scale
    scored by its best move's overlap over the root of its ink. The output is resampled once, by the whole mapping.
    {"frame", "scale": [x, y], "shift": [dx, dy] in page pixels, "found": whether a scale was found}: the cut page
    is scaled by `scale` about the page's centre, then moved by `shift`."""
    w, h = pencil.size
    cut = made.transform((w, h), Image.Transform.EXTENT, frame, Image.Resampling.BICUBIC)
    strokes, ink, _, s = line_maps(pencil, cut, mask)
    f_strokes = np.fft.rfft2(strokes.astype(np.float32))
    flat = Image.fromarray(ink.astype(np.uint8) * 255)
    cy, cx = (ink.shape[0] - 1) / 2, (ink.shape[1] - 1) / 2

    def score(sx: float, sy: float) -> tuple:
        scaled = np.asarray(flat.transform(flat.size, Image.Transform.AFFINE,
                                           (1 / sx, 0, cx - cx / sx, 0, 1 / sy, cy - cy / sy))) > 127
        peak, dy, dx = _peak(f_strokes, scaled)
        return peak / max(1.0, float(scaled.sum())) ** 0.5, sx, sy, dy, dx

    span, coarse, fine = SCALES
    steps = np.arange(-span, span + coarse / 2, coarse)
    best = max(score(1 + a, 1 + b) for a in steps for b in steps)
    steps = np.arange(-coarse, coarse + fine / 2, fine)
    _, sx, sy, dy, dx = max(score(best[1] + a, best[2] + b) for a in steps for b in steps)
    # A best scale at the end of the range is the search running out, not a fit: the model changed the layout in a
    # way one scale cannot undo (a page with one panel made 3 % shorter and the other left as it was gave 0.965 and
    # a 44 px move that put every balloon off its letters, 2026-11-12; the best move alone was 48 px, as wrong).
    # The page is then left as the model returned it, and each balloon is found on its own (placed).
    found_ = max(abs(sx - 1), abs(sy - 1)) < span + coarse - fine / 2
    if not found_:
        sx, sy, dy, dx = 1.0, 1.0, 0, 0
    kx, ky, mx, my = (frame[2] - frame[0]) / w, (frame[3] - frame[1]) / h, (w - 1) / 2, (h - 1) / 2
    on_grid = made.transform((w, h), Image.Transform.AFFINE,
                             (kx / sx, 0, frame[0] + kx * (mx - (mx + dx / s) / sx),
                              0, ky / sy, frame[1] + ky * (my - (my + dy / s) / sy)), Image.Resampling.BICUBIC,
                             fillcolor=(255, 255, 255))
    return on_grid, {"frame": [round(v, 1) for v in frame], "scale": [round(float(sx), 4), round(float(sy), 4)],
                     "shift": [round(dx / s), round(dy / s)], "found": bool(found_)}


def line_check(pencil: Image.Image, finished: Image.Image, mask: np.ndarray) -> tuple[dict, Image.Image]:
    """The lines check outside the lettering, at CHECK_SIDE, with the finished page laid back on the pencil by its
    whole-page shift (the move of its ink, up to SHIFT each way, that lays the most of it on the strokes): ({"kept":
    share of the pencil's stroke pixels with an ink line within NEAR, "new": share of the page covered by ink with
    no stroke within NEAR, "shift": that shift as [dx, dy] in page pixels, "unaligned": the two shares without
    it}, the picture of the aligned check)."""
    strokes, ink, out, s = line_maps(pencil, finished, mask)
    _, dy, dx = _peak(np.fft.rfft2(strokes.astype(np.float32)), ink)

    def shares(ink):
        ink = ink & ~out
        kept = strokes & binary_dilation(ink, iterations=NEAR)
        new = ink & ~binary_dilation(strokes, iterations=NEAR)
        return kept, new, {"kept": round(float(kept.sum() / max(1, strokes.sum())), 4),
                           "new": round(float(new.sum() / max(1, (~out).sum())), 4)}

    kept, new, aligned = shares(np.roll(ink, (dy, dx), (0, 1)))
    pic = np.full((*strokes.shape, 3), 255, np.uint8)
    pic[out] = (232, 232, 232)
    pic[new] = (40, 90, 255)
    pic[strokes & ~kept] = (230, 30, 30)
    pic[kept] = (20, 160, 60)
    return {**aligned, "shift": [round(-dx / s), round(-dy / s)], "unaligned": shares(ink)[2]}, Image.fromarray(pic)


def panels_of(lines: np.ndarray, lettering: np.ndarray) -> list[list[int]]:
    """The panels of a page from its line map, as boxes [x0, y0, x1, y1] in reading order: the long straight lines,
    level and upright (FRAME_RUN, FRAME_SLACK), joined where they meet; each joined set that has both kinds and
    encloses PANEL_AREA of the page is a panel's frame, and the box of its lines the panel. Balloons break frames:
    two pieces of frame that end on the same lettering region (`lettering`, grown by twice GROW) are one frame, the
    region joining them without adding to the box (without this a panel whose right half lay behind balloons was
    measured 530 px too narrow, 2026-11-12). A box inside another is a drawing's own straight lines, and goes."""
    h, w = lines.shape
    run, slack = max(3, round(FRAME_RUN * w)), 2 * FRAME_SLACK + 1
    level = binary_opening(binary_dilation(lines, structure=np.ones((slack, 1), bool)), structure=np.ones((1, run), bool))
    upright = binary_opening(binary_dilation(lines, structure=np.ones((1, slack), bool)), structure=np.ones((run, 1), bool))
    hold = binary_dilation(lettering, iterations=max(1, round(2 * GROW * w)))  # the outline, and its thickness
    level, upright = level & ~hold, upright & ~hold  # a balloon's own outline can run straight: it is no frame
    joined, _ = label(level | upright | hold, structure=np.ones((3, 3), bool))
    boxes = []
    for k, sl in enumerate(find_objects(joined), 1):
        part = joined[sl] == k
        if (part & level[sl]).any() and (part & upright[sl]).any():
            ys, xs = np.nonzero(part & (level[sl] | upright[sl]))
            box = [sl[1].start + int(xs.min()), sl[0].start + int(ys.min()), sl[1].start + int(xs.max()) + 1,
                   sl[0].start + int(ys.max()) + 1]
            if (box[2] - box[0]) * (box[3] - box[1]) >= PANEL_AREA * h * w:
                boxes.append(box)
    inside = lambda a, b: a is not b and a[0] >= b[0] - slack and a[1] >= b[1] - slack and a[2] <= b[2] + slack and a[3] <= b[3] + slack
    return sorted((a for a in boxes if not any(inside(a, b) for b in boxes)), key=lambda b: (b[1], b[0]))


def _overlap(a: list[int], b: list[int]) -> float:
    """How much two boxes are one: the area they share over the area they cover."""
    both = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    return both / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - both)


def frame_check(pencil: Image.Image, finished: Image.Image, lab: np.ndarray, places: list[dict]) -> dict:
    """The layout check: the panels of the pencil page and of the finished page (panels_of, at CHECK_SIDE, with
    the lettering regions where each page has them: the pencil's, and those moved by their offsets), each pencil
    panel paired with the finished panel that overlaps it most (by half at least, or it is lost). {"panels":
    [{"box": the pencil's, in page pixels, "found": the finished page's or None, "moved": how far its left, top,
    right and bottom sides sit from the pencil's}], "extra": finished panels the pencil does not have, "largest":
    the largest move on the page, None when a panel is lost or the pencil has none}."""
    s = CHECK_SIDE / max(pencil.size)
    size = (round(pencil.width * s), round(pencil.height * s))
    there = np.zeros(lab.shape, bool)
    for p, sl in zip(places, find_objects(lab)):
        dst, src = _moved(sl, p["offset"], lab.shape)
        there[dst] |= (lab[sl] == p["region"])[src]
    small = lambda m: np.asarray(Image.fromarray(m).resize(size, Image.NEAREST))
    drawn = panels_of(lines_of(pencil.resize(size, Image.LANCZOS), PENCIL_DELTA), small(lab > 0))
    made = panels_of(lines_of(finished.resize(size, Image.LANCZOS), INK_DELTA), small(there))
    rows, taken = [], set()
    for a in drawn:
        b = max(made, key=lambda m: _overlap(a, m), default=None)
        ok = b is not None and _overlap(a, b) >= 0.5
        taken.update([made.index(b)] if ok else [])
        rows.append({"box": [round(v / s) for v in a], "found": [round(v / s) for v in b] if ok else None,
                     "moved": [round((q - p) / s) for p, q in zip(a, b)] if ok else None})
    whole = bool(rows) and all(r["moved"] for r in rows)
    return {"panels": rows, "extra": len(made) - len(taken),
            "largest": max(abs(v) for r in rows for v in r["moved"]) if whole else None}


def added_check(sent: Image.Image, painted: Image.Image, lab: np.ndarray, places: list[dict]) -> dict:
    """What the model put on the paper the pencil leaves open (its margins and gutters: the paper joined to the
    page's edge without crossing a stroke), outside the pencil's lettering regions where the model drew them, read
    on the model's output on the pencil's grid. {"areas": the blank areas it added, as boxes [x0, y0, x1, y1] in
    page pixels: each an area of blank paper (BLANK_L, BLANK_C) that the output encloses (it does not reach the
    page's edge), as large as a small balloon (BLANK_AREA) and mostly on that open paper: an empty balloon, caption
    box or panel the pencil does not have; "painted": the share of that open paper that is no longer blank: a
    figure or a background painted outside the frames}. A blank area added inside a panel is not looked for: one
    whose outline the pencil does not draw was tried (2026-11-14) and it took a pale sky, a cloud and a glass dome
    for added boxes on three pages of five."""
    s = CHECK_SIDE / max(sent.size)
    size = (round(sent.width * s), round(sent.height * s))
    edge = lambda joined: np.unique(np.concatenate([joined[0], joined[-1], joined[:, 0], joined[:, -1]]))
    walls = binary_dilation(lines_of(sent.resize(size, Image.LANCZOS), PENCIL_DELTA), iterations=FRAME_SLACK)
    paper, _ = label(~walls)
    open_ = np.isin(paper, edge(paper)[edge(paper) > 0])
    there = np.zeros(lab.shape, bool)
    for p, sl in zip(places, find_objects(lab)):
        dst, src = _moved(sl, p["offset"], lab.shape)
        there[dst] |= (lab[sl] == p["region"])[src]
    there = binary_dilation(np.asarray(Image.fromarray(there).resize(size, Image.NEAREST)), iterations=max(1, round(GROW * size[0])))
    tone = to_lab(np.asarray(painted.resize(size, Image.LANCZOS)))
    blank_ = (tone[..., 0] >= BLANK_L) & (np.hypot(tone[..., 1], tone[..., 2]) <= BLANK_C)
    joined, _ = label(blank_)
    areas = []
    for k, sl in enumerate(find_objects(joined), 1):
        part = joined[sl] == k
        n = int(part.sum())
        if (k not in edge(joined) and n >= BLANK_AREA * joined.size and (part & open_[sl]).sum() > n / 2
                and (part & there[sl]).sum() < n / 2):
            areas.append([round(sl[1].start / s), round(sl[0].start / s), round(sl[1].stop / s), round(sl[0].stop / s)])
    free = open_ & ~there
    return {"areas": areas, "painted": round(float((free & ~blank_).sum() / max(1, free.sum())), 4)}


def name_comic(pages: list[Path], reads: dict, have: dict[str, dict], out: Path, st: fresh.Stamps) -> dict:
    """The comic's title (TITLE_TASK, one call over every page's story and the characters' names) and the line under
    it (TITLE_LINE), saved as title.json and stamped by what the call is given: {"title", "line", "usd"}. Raises
    what the call raises (FAILED)."""
    f = out / "title.json"
    names = "\n".join(f"- {e.get('name') or k}" for k, e in have.items() if e["kind"] == "character") or "(none)"
    story = "\n".join(f"- Page {n}: {reads[p.stem]['story']}" for n, p in enumerate(pages, 1))
    text = f"{TITLE_TASK}\n## The characters\n{names}\n\n## The pages\n{story}\n"
    stamp = fresh.digest(text, TITLE_MODEL, TITLE_REASONING, TITLE_TOKENS, TITLE_LINE.format(n=len(pages)))
    if st.current("title", stamp, f):
        return json.loads(f.read_text(encoding="utf-8"))
    reply, usd = ask_json(TITLE_MODEL, [{"type": "text", "text": text}], f"finish title {pages[0].stem}", TITLE_TOKENS,
                          TITLE_REASONING, brief=False)
    title = " ".join(str(reply.get("title") or "").split()).strip("\"'“”‘’«»")
    if not title:
        raise ValueError(f"the title call gave no title ({json.dumps(reply)[:200]})")
    named = {"title": title, "line": TITLE_LINE.format(n=len(pages)), "usd": usd}
    _save(f, named)
    st.made("title", stamp)
    print(f"  title: {title} ({named['line']}), {usd:.4f} USD")
    return named


def cover_ask(pages: list[Path], reads: dict, have: dict[str, dict], title: str, model: str, out: Path,
              st: fresh.Stamps) -> dict:
    """What the cover's call is made of: {"prompt", "sheets": the main characters' sheets sent, "pages": the
    finished pages sent, "stamp"}. The main characters are the COVER_CHARACTERS figures drawn in the most panels of
    the readings; each with a sheet is sent with it, after the canvas, then the first and last finished pages."""
    drawn = collections.Counter(e["key"] for r in reads.values() for pn in r["panels"] for e in pn["elements"]
                                if e["kind"] == "figure" and e["key"] in have)
    main = [k for k, _ in drawn.most_common(COVER_CHARACTERS)]
    sheets = [k for k in main if have[k]["sheet"]]
    looks = list(dict.fromkeys([pages[0], pages[-1]]))[:COVER_PAGES]
    name = lambda k: have[k].get("name") or k
    who = ("the main characters, " + ", ".join(name(k) for k in main)) if main else "the comic's main characters"
    rows = [COVER_CHARACTER.format(name=name(k), description=have[k].get("description") or "",
                                   sheet=SHEET_REF.format(k=2 + sheets.index(k)) if k in sheets else "") for k in main]
    first_look = 2 + len(sheets)
    prompt = COVER_PROMPT.format(
        title=title, who=who, story=" ".join(reads[p.stem]["story"] for p in pages),
        characters=COVER_CHARACTERS_PROMPT + "\n".join(rows) + "\n" if rows else "",
        look=COVER_LOOK.format(pages=" and ".join(str(first_look + i) for i in range(len(looks)))))
    stamp = fresh.digest(prompt, *[have[k]["sheet"] for k in sheets], [st.get(f"{p.stem}/raw/{model}") for p in looks],
                         recipe_of(model), COVER_CANVAS, REF_SIDE)
    return {"prompt": prompt, "sheets": sheets, "pages": [p.stem for p in looks], "stamp": stamp}


def cover(pages: list[Path], reads: dict, have: dict[str, dict], title: str, model: str, out: Path,
          st: fresh.Stamps) -> dict:
    """The comic's front cover (cover_ask) painted on a blank COVER_CANVAS with the title lettered in it, saved as
    cover.png, the model's whole output: {"file", "title": the title it was asked to letter, "sheets", "pages",
    "prompt", "usd"}. Raises what the call raises (FAILED)."""
    f, facts = out / "cover.png", out / "cover.json"
    ask = cover_ask(pages, reads, have, title, model, out, st)
    if st.current(f"cover/{model}", ask["stamp"], f, facts):
        return json.loads(facts.read_text(encoding="utf-8"))
    print(f"  cover: asking {MODELS[model]} for it, about {price_of(model, COVER_CANVAS):.3f} USD")
    refs = [_fit(Image.open(have[k]["sheet"]), REF_SIDE) for k in ask["sheets"]]
    refs += [_fit(Image.open(out / f"{stem}.png"), REF_SIDE) for stem in ask["pages"]]
    img, usd = paint(model, ask["prompt"], Image.new("RGB", COVER_CANVAS, (255, 255, 255)), refs, f"finish cover {title}")
    img.save(f)
    made = {"file": f.name, "title": title, "model": MODELS[model], "size": list(img.size),
            **{k: v for k, v in ask.items() if k != "stamp"}, "usd": usd}
    _save(facts, made)
    st.made(f"cover/{model}", ask["stamp"])
    print(f"  cover: {img.width} x {img.height}, lettered \"{title}\", {usd:.3f} USD")
    return made


def finish(pages: list[Path], out: Path, bible: Path | None = None, model: str = "nano",
           only: list[str] | None = None, reader: str = READER, effort: str = READ_REASONING) -> dict:
    """Every pencil page finished under `out` with the image model `model` (see the module docstring), or of the
    pages only those whose names are in `only`, each page read by `reader`; the report, also saved as report.json:
    {"found", "reads", "sheets": {key/model: what was painted or "error"}, "pages": {stem: what was asked, the
    mapping, the lettering, the checks and "ok" per check, or "error"}, "usd": the cost of what is in `out`}."""
    bible = bible or out / "bible"
    bible.mkdir(parents=True, exist_ok=True)
    f_report = out / "report.json"
    report = json.loads(f_report.read_text(encoding="utf-8")) if f_report.exists() else {}
    report = {"found": report.get("found", {}), "reads": report.get("reads", {}), "sheets": report.get("sheets", {}),
              "pages": report.get("pages", {}), "title": report.get("title", {}), "cover": report.get("cover", {})}
    st = fresh.Stamps(out / "stamps.json")

    # What costs nothing first: the lettering regions of every page to paint, with one SAM loaded only when a
    # page's are not saved.
    print("== 0 finish: lettering")
    painted_pages = [p for p in pages if only is None or p.stem in only]
    recipe = [LETTER_PROMPTS, LETTER_SCORE, SAME, fresh.recipe(sam, skip=("BATCH",))]  # what shapes the regions
    lettering = {p.stem: (out / "lettering" / f"{p.stem}.png", fresh.digest(p, recipe)) for p in painted_pages}
    seg = None
    for p in painted_pages:
        f_lab, lab_stamp = lettering[p.stem]
        if not st.current(f"{p.stem}/lettering", lab_stamp, f_lab):
            seg = seg or sam.Segmenter()
            f_lab.parent.mkdir(parents=True, exist_ok=True)
            Image.fromarray(regions(seg, Image.open(p).convert("RGB"))).save(f_lab)
            st.made(f"{p.stem}/lettering", lab_stamp)
    if seg:
        del seg
        import torch
        torch.cuda.empty_cache()

    print("== 0 finish: bible")
    try:
        fd = found(pages, bible)
        report["found"] = {"usd": fd["cost"], "entries": list(fd["entries"]), "notes": fd.get("notes")}
    except FAILED as err:  # no entries, no page: a page painted without them is the page this step exists to avoid,
        report["found"] = {"error": str(err)[:300]}  # and it would be paid for twice
        print(f"  entries: none, {str(err)[:200]}; nothing is painted")
        return _closed(report, f_report, pages)
    have = entries(bible, model)

    # Each page's reading, in order: a page is read with the story so far and the place the page before ended in,
    # so its stamp holds those, the entries, the page, the reader and the reading's task and recipe. A page read
    # again re-reads the pages after it when its story or the place it ends in changed. The reading is in the
    # page's prompt and so in the stamp of its raw output, and in nothing else's.
    def reading_of(p: Path, before: dict) -> tuple[Path, str]:
        return out / "read" / f"{p.stem}.json", fresh.digest(p, _read_text(have, before), reader, effort,
                                                             READ_TOKENS, READ_SIDE)

    def after(seen: dict, before: dict) -> dict:
        """What the next page is read with: the place this one ends in and the story with this page's lines."""
        return {"place": seen["panels"][-1]["place"] if seen["panels"] else before["place"],
                "story": before["story"] + [seen["story"]]}

    reads, before = {}, {"place": None, "story": []}
    for p in pages:  # those that hold as they are, up to the first that does not
        f_read, stamp = reading_of(p, before)
        if not st.current(f"{p.stem}/read", stamp, f_read):
            break
        reads[p.stem] = json.loads(f_read.read_text(encoding="utf-8"))
        before = after(reads[p.stem], before)
    unread = pages[len(reads):]

    def asked(stem: str, have: dict[str, dict]) -> dict:
        """What a page's call is made of, with the bible as it stands: the entries on it, the sheets sent, the
        prompt, and the stamp of its raw output."""
        on = [k for k in have if k in on_page(reads[stem], stem, fd["entries"])]
        with_sheet = [k for k in on if have[k]["sheet"]]
        used = with_sheet[: REFS[model] - 1]
        prompt = page_prompt(on, have, used, reads[stem])
        size = Image.open(by_stem[stem]).size
        stamp = fresh.digest(by_stem[stem], lettering[stem][1], [EDGE, GROW, PAPER_L, WHITE_C], prompt,
                             *[have[k]["sheet"] for k in used], recipe_of(model), REF_SIDE, canvas_of(model, size))
        return {"entries": on, "sheets": used, "sheets_left_out": with_sheet[len(used):], "prompt": prompt, "stamp": stamp}

    def raw_of(stem: str) -> tuple[Path, Path]:
        """The model's own output for a page, and what was asked and what it cost: kept per model."""
        return out / "raw" / model / f"{stem}.png", out / "raw" / model / f"{stem}.json"

    by_stem = {p.stem: p for p in pages}
    bible_st = fresh.Stamps(bible / "stamps.json")
    jobs = sheet_jobs(by_stem, bible, fd, model, bible_st)
    waiting = {j["key"] for j in jobs}  # a page with a sheet still to paint, or still to read, is painted after it
    to_paint = [p for p in painted_pages if p in unread or waiting & set(on_page(reads[p.stem], p.stem, fd["entries"]))
                or not st.current(f"{p.stem}/raw/{model}", asked(p.stem, have)["stamp"], *raw_of(p.stem))]
    named = (out / "title.json").exists() and (out / "cover.png").exists()  # a changed title or cover is not foreseen here
    if unread or jobs or to_paint or not named:
        usd = (sum(price_of(model, sheet_crop(Image.open(by_stem[j["page"]]), j["box"]).size) for j in jobs)
               + sum(price_of(model, Image.open(p).size) for p in to_paint)
               + (READ_USD * len(unread) * pricing(reader)[1] / pricing(READER)[1] if unread else 0)
               + (0 if named else TITLE_USD + price_of(model, COVER_CANVAS)))
        print(f"  plan: up to {len(unread)} pages to read with {reader}, {len(jobs)} sheets and {len(to_paint)} pages to "
              f"paint with {MODELS[model]}{'' if named else ', the title and the cover'}, about {usd:.2f} USD; "
              f"{spent_today():.3f} USD spent today of {DAILY_CAP_USD:.2f}")
    print("== 0 finish: readings")
    for p in unread:
        f_read, stamp = reading_of(p, before)
        if not st.current(f"{p.stem}/read", stamp, f_read):  # a later page holds when what came before it did
            try:
                seen, usd = read(p, have, before, reader, effort)
            except FAILED as err:  # the pages after it wait with it: each needs what the one before tells
                report["reads"][p.stem] = {"error": str(err)[:300]}
                print(f"  {p.stem}: not read, {str(err)[:200]}; the pages from it on wait")
                break
            _save(f_read, seen)
            st.made(f"{p.stem}/read", stamp)
            report["reads"][p.stem] = {"usd": usd, "panels": len(seen["panels"]), "bare": len(seen["bare"])}
            print(f"  {p.stem}: read, {len(seen['panels'])} panels and {len(seen['bare'])} bare areas, {usd:.4f} USD")
        reads[p.stem] = json.loads(f_read.read_text(encoding="utf-8"))
        before = after(reads[p.stem], before)
    print("== 0 finish: sheets")
    sheets(jobs, by_stem, bible, report, model, bible_st)
    have = entries(bible, model)

    print("== 0 finish: pages")
    for p in painted_pages:
        stem = p.stem
        if stem not in reads:
            continue  # not read, not painted: painted without its reading, it would be painted again once it came
        pencil = Image.open(p).convert("RGB")
        lab = np.asarray(Image.open(lettering[stem][0]))
        sent = Image.fromarray(blank(np.asarray(pencil), lab))
        ask = asked(stem, have)
        raw, facts = raw_of(stem)
        if not st.current(f"{stem}/raw/{model}", ask["stamp"], raw, facts):
            (out / "sent").mkdir(parents=True, exist_ok=True)
            sent.save(out / "sent" / f"{stem}.png")
            print(f"  {stem}: asking {MODELS[model]} for the page, about {price_of(model, sent.size):.3f} USD")
            try:
                img, usd = paint(model, ask["prompt"], sent, [_fit(Image.open(have[k]["sheet"]), REF_SIDE) for k in ask["sheets"]],
                                 f"finish page {stem}")
            except FAILED as err:
                report["pages"][stem] = {"error": str(err)[:300]}
                print(f"  {stem}: not finished, {str(err)[:200]}")
                continue
            raw.parent.mkdir(parents=True, exist_ok=True)
            img.save(raw)
            _save(facts, {"model": MODELS[model], **{k: v for k, v in ask.items() if k != "stamp"},
                          "asked": canvas_of(model, sent.size), "model_size": list(img.size), "usd": usd})
            st.made(f"{stem}/raw/{model}", ask["stamp"])
            print(f"  {stem}: painted {img.width} x {img.height} with {len(ask['sheets'])} sheets, {usd:.3f} USD")
        row = report["pages"].setdefault(stem, {})
        if row.get("model") != MODELS[model]:
            row.clear()  # an error, or another model's page
        row.update({k: v for k, v in json.loads(facts.read_text(encoding="utf-8")).items() if k != "prompt"})

        # The output on the pencil's grid, before anything is read from it or set on it. From here on nothing costs
        # money, so any edit of this file makes it again (fresh.py).
        f_laid, f_map = out / "laid" / f"{stem}.png", out / "laid" / f"{stem}.json"
        laid_stamp = fresh.digest(ask["stamp"], fresh.source(sys.modules[__name__]))
        if not st.current(f"{stem}/laid", laid_stamp, f_laid, f_map):
            made = Image.open(raw).convert("RGB")
            on_grid, mapping = laid(sent, made, frame_of(model, sent.size, made.size), lab > 0)
            f_laid.parent.mkdir(parents=True, exist_ok=True)
            on_grid.save(f_laid)
            _save(f_map, mapping)
            st.made(f"{stem}/laid", laid_stamp)
            print(f"  {stem}: laid on the pencil's grid, {mapping}")
        row["mapping"] = json.loads(f_map.read_text(encoding="utf-8"))

        page, page_stamp = out / f"{stem}.png", fresh.digest(laid_stamp, "page")
        if not st.current(f"{stem}/page", page_stamp, page) or "lettering" not in row:
            painted = Image.open(f_laid).convert("RGB")
            places = placed(sent, painted, lab)
            cleaned, seen = clean(np.asarray(painted), lab, places)
            lettered, there = letter(cleaned, np.asarray(pencil), lab, places)
            Image.fromarray(lettered).save(page)
            st.made(f"{stem}/page", page_stamp)
            row.update({"file": page.name, "size": list(pencil.size), "text": there,
                        "writing": max((r["written"] for r in seen), default=0.0),
                        "lettering": [{**pl, **r} for pl, r in zip(places, seen)]})
            print(f"  {stem}: {len(places)} lettering regions moved by {[pl['offset'] for pl in places]} px, letters the "
                  f"pencil's {there:.2%}, most written in one {row['writing']:.2%}")

        lines_pic, check_stamp = out / "checks" / f"{stem}-lines.png", fresh.digest(page_stamp, "checks")
        if not st.current(f"{stem}/checks", check_stamp, lines_pic) or "lines" not in row:
            finished = Image.open(page)
            lines, pic = line_check(pencil, finished, lab > 0)
            frames = frame_check(pencil, finished, lab, row["lettering"])
            added = added_check(sent, Image.open(f_laid).convert("RGB"), lab, row["lettering"])
            lines_pic.parent.mkdir(parents=True, exist_ok=True)
            pic.save(lines_pic)
            st.made(f"{stem}/checks", check_stamp)
            row.update({"lines": lines, "frames": frames, "added": added,
                        "ok": {"lines_kept": lines["kept"] >= MIN_KEPT, "lines_new": lines["new"] <= MAX_NEW,
                               "writing": row["writing"] <= MAX_WRITING, "text": row["text"] == 1.0,
                               "balloons": all(pl["fit"] >= LOST_FIT for pl in row["lettering"]),
                               "added": not added["areas"],
                               "frames": frames["largest"] is not None and frames["largest"] <= MAX_MOVE * max(pencil.size)}})
            print(f"  {stem}: shift {lines['shift']} px; lines kept {lines['kept']:.1%} (unaligned "
                  f"{lines['unaligned']['kept']:.1%}), new {lines['new']:.1%}; {len(frames['panels'])} panels, largest "
                  "move of a frame side "
                  + (f"{frames['largest']} px" if frames["largest"] is not None else "not measured (a panel not found)")
                  + f"; {len(added['areas'])} blank areas added, {added['painted']:.1%} of the open paper painted; failing: " + (", ".join(k for k, v in row["ok"].items() if not v) or "nothing"))

    # The title once every page is read, the cover once every page is finished: asked on part of the comic, either
    # would be asked again when the rest came.
    if len(reads) < len(pages):
        return _closed(report, f_report, pages)
    print("== 0 finish: title")
    try:
        report["title"] = name_comic(pages, reads, have, out, st)
    except FAILED as err:
        report["title"] = {"error": str(err)[:300]}
        print(f"  title: not named, {str(err)[:200]}")
        return _closed(report, f_report, pages)
    if not all((out / f"{p.stem}.png").exists() and "error" not in report["pages"].get(p.stem, {}) for p in pages):
        return _closed(report, f_report, pages)
    print("== 0 finish: cover")
    try:
        report["cover"] = {k: v for k, v in cover(pages, reads, have, report["title"]["title"], model, out, st).items()
                           if k != "prompt"}
    except FAILED as err:
        report["cover"] = {"error": str(err)[:300]}
        print(f"  cover: not painted, {str(err)[:200]}")
    return _closed(report, f_report, pages)


def missing_of(report: dict, pages: list[Path], out: Path) -> dict[str, str]:
    """What the comic still lacks after a run: {a page's stem, "title" or "cover": why}, empty when every page is
    finished, the comic named and its cover painted. The Modal service fails a job on it (run_episodes.py)."""
    error = lambda row: str(row["error"]) if isinstance(row, dict) and row.get("error") else None
    missing = {}
    for p in pages:
        row = report["pages"].get(p.stem, {})
        if not (out / f"{p.stem}.png").exists() or error(row):
            missing[p.stem] = (error(report["found"]) or error(report["reads"].get(p.stem)) or error(row)
                               or "not painted: not read yet, or left out by --only")
    if not (out / "title.json").exists():
        missing["title"] = error(report["title"]) or "not named: a page is not read"
    if not (out / "cover.png").exists():
        missing["cover"] = error(report["cover"]) or "not painted: a page is not finished, or the comic not named"
    return missing


def _closed(report: dict, file: Path, pages: list[Path]) -> dict:
    """The report with the cost of everything in it and what the comic still lacks ("missing", missing_of),
    saved."""
    report["missing"] = missing_of(report, pages, file.parent)
    report["usd"] = round(sum(float(r.get("usd") or 0) for r in [report["found"], *report["reads"].values(),
                                                                 *report["sheets"].values(), *report["pages"].values(),
                                                                 report.get("title", {}), report.get("cover", {})]), 4)
    _save(file, report)
    return report


def _by_number(f: Path) -> list:
    """A file's place in a folder read as people number pages: the digits in its name as numbers, 2 before 10."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", f.name)]


if __name__ == "__main__":
    args = sys.argv[1:]
    bible_dir, name, some, who, how = None, "nano", None, READER, READ_REASONING
    if "--reader" in args:
        k = args.index("--reader")
        who = args[k + 1]
        del args[k: k + 2]
    if "--effort" in args:
        k = args.index("--effort")
        how = args[k + 1]
        del args[k: k + 2]
    if "--only" in args:
        k = args.index("--only")
        some = [s.strip() for s in args[k + 1].split(",")]
        del args[k: k + 2]
    if "--bible" in args:
        k = args.index("--bible")
        bible_dir = Path(args[k + 1])
        del args[k: k + 2]
    if "--model" in args:
        k = args.index("--model")
        name = args[k + 1]
        del args[k: k + 2]
    files = [f for a in args[:-1] for f in (sorted(Path(a).iterdir(), key=_by_number) if Path(a).is_dir() else [Path(a)])
             if f.suffix.lower() in PICTURES]
    done = finish(files, Path(args[-1]), bible_dir, name, some, who, how)
    missing = [k for k, r in done["sheets"].items() if "error" in r] + list(done["missing"])
    print(f"  finish: {len(files)} pages, {done['usd']:.3f} USD for what is in {args[-1]}; "
          f"{spent_today():.3f} USD spent today in all" + (f"; not made: {', '.join(missing)}" if missing else ""))
