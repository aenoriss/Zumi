"""Splitter thresholds. Each was measured on the research set; pipeline/tuning-log.md has the evidence."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Params:
    # blank rows
    tolerance: int = 20  # pixel vs its row's median colour; the knee of Sweet Home 14's JPEG grain
    max_outliers: float = 0.002  # a row with fewer outlier pixels than this share is blank
    max_break: int = 2  # non-blank runs this short between blank rows are grain (Sweet Home 14, y 25180)

    # gutters
    colour_match: int = 20  # two row colours within this are the same colour (page, fade, jumps, panel edges)
    min_gutter: int = 40  # a blank run this tall cuts on its own
    min_narrow: int = 8  # shorter runs cut only on page colour against a panel edge (Housecat grids, 11-31 px)
    page_window: int = 4000  # rows on each side searched for the local page colour
    min_span: int = 48  # colour travel across a blank run that makes it a fade, not flat art
    min_edge: float = 0.4  # a panel edge spans this share of the width; bubbles and sound effects stay under 0.2
    lone_h: int = 400  # past a narrow gutter, a block this short followed by a full gutter is the panel's text

    # beats
    speck_h: int = 300  # a slab this short ...
    speck_ink: float = 0.015  # ... with less ink than this is a speck and rejoins the gutter
    max_sliver: int = 8  # no beat is thinner; joins the nearer neighbour however far
    min_panel: int = 120  # shorter slabs are never panels
    max_floater: int = 700  # floater candidates (bubble, caption, sound effect) are shorter ...
    min_flatness: float = 0.85  # ... and at least this flat (share of pixels in the 4 most frequent colours)
    gap_factor: float = 0.75  # floaters group with each other across gaps under this x the median gutter
    tight: float = 0.25  # a fairly flat slab this close to a neighbour (x median gutter) is text bound to it
    min_tight_flatness: float = 0.7
    max_tight: int = 300
    max_attach: int = 100  # px at 800 wide: text farther than this from the art is its own beat (user, 2026-10-18)
    min_aspect: float = 0.25  # an art beat shorter than this x the width merges with a neighbour (user, 2026-10-19)
    merge_gap: float = 2.0  # ... never across a gap over this x the median gutter (a scene change)
    max_merge_gap: int = 150  # ... nor over this many px at 800 wide (Sweet Home's intertitle plates sit 197+ px apart)

    # bubbles that cross a gutter with a page-coloured fill (no outline: the gutter rows read blank)
    bay_band: float = 0.3  # rows searched into a panel from its edge, as a share of the width
    bay_min_w: float = 0.12  # a bay's chord along the panel edge, as a share of the width ...
    bay_max_w: float = 0.98  # Tower of God 223 f31: one bubble spans 0.94 of the width
    bay_end_share: float = 0.4  # a bay's ends reach at most this share of its deepest point (dome shape)
    bay_min_depth: float = 0.06  # ... and how far it reaches into the art
    bay_art_reach: float = 0.03  # a column where page colour reaches less than this into the panel is its edge
    bay_min_art: float = 0.5  # most of the rest of the edge must be art: a hard panel edge, not a fade
    bay_max_span: float = 1.0  # bay to bay across the gutter(s), as a share of the width
