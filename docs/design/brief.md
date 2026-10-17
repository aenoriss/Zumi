# Zumi design brief

Status: BRIEF COMPLETE 2026-10-15 (component inventory to confirm during Storybook setup). Amends `docs/architecture/decisions.md`.

## Audience

Primary: daily webtoon readers, 14-30, often male, geek/otaku, large Asian share. They live in WEBTOON, Kakao, Piccoma, Bilibili, Crunchyroll, Discord, Steam, gacha launchers.
Secondary: comic artists on the web tool (must trust their art is respected); competition judges.
Reference the user likes: Deadlock "City Never Sleeps" page (hand-made feel, dark stage, one hot accent, pinned cards).

## Decisions so far

| # | Question | Decision |
|---|---|---|
| B2 | Tone of voice | Fan-native everywhere: light meme/fandom register, webtoon vocabulary. "Episode", not "chapter". |
| B3 | Theme default | FINAL 2026-10-15: midnight by default on web and XR (deep indigo-black room with amber lamp light, comics and covers on warm paper cards inside it; not pure black). "Daytime shop" warm-paper light theme secondary, and the editor canvas keeps a neutral ground. Rationale: the theme is cozy + community on every screen; the otaku side of the audience (Kakao, Bilibili, Manta, Steam, Discord) is dark-native, while the top-traffic platforms are white, so both themes ship from the same tokens. |
| B4 | Art vs UI | UI recedes on reading surfaces (gallery, reader, editor canvas: near-monochrome chrome, one accent). The orb carries personality on social surfaces (orbs, emotes, end card, landing hero, loading). The orb is the mascot and logo mark. |
| B5 | Display type | Condensed geometric sans for headings with a CJK companion face (later localisation must not break the brand). Hand-drawn wordmark, ideally by the artist. Comic lettering lives only inside comics and orb bubbles. |
| B6 | Density | Dense structure native to Asian platforms (rankings, weekday rows, badges, counters as first-class components), controlled by a tight spacing scale and strong hierarchy so the front page is full with 6 comics. |
| B7 | Motion | Expressive only on the orb and on live signals (reading-now counters, new-episode badges, end card); minimal elsewhere. One motion token set shared with Unity. |
| B9 | Shape language | Two registers: sharp (0-2 px) for content containers so art edges stay printed; round for controls and the orb; bubbles their own shape. Tokens: `radius.container`, `radius.control`, `radius.bubble`. |
| B11 | Vocabulary | Creator, Series, Episode, Panel, Scene (panorama / 3D), Room, Zumi (the orb mascot: reader avatar in XR, loading mark on web, logo mark), Emote, `.zumi` episode file. "Comic" only in marketing copy. |
| B12 | Mascot | Zumi has a face: one flat-shaded sphere, ~10 expressions driven by a single `mood` parameter (two eye shapes, one mouth path) so web and Unity animate the same data. Expression sheet drawn by the artist. Emote set maps 1:1 to expressions. Each reader's Zumi gets a random colour from a curated token set of ~8 hues (all legible on the dark field and on white), unique within a room when possible. |
| D2 | Token source of truth | REVISED 2026-10-17 (Pencil dropped): the W3C DTCG JSON in `packages/design-tokens/tokens` is the source of truth, edited in code and reviewed in Storybook's token pages -> Style Dictionary -> CSS vars, USS, C#. XR-only tokens in `xr.tokens.json`. Manual visual tweaks happen in Storybook with live token controls, not in a design tool. |
| D3 | Component base | Radix Primitives + Tailwind v4 reading token variables; Storybook 10 catalogue with a11y addon. |
| D4 | Preview renderer | react-three-fiber (shares depth, carousel and animation-track math with Unity). |

## Theme (2026-10-15)

**"A magical library at midnight."** Lofi, cozy, a place to stay and read together. The lighting model from the research (`docs/research/lofi-midnight-bookshop-2026-10.md`): one warm lamp inside a cool blue-black room, Ghibli's night interiors as the reference (Kazuo Oga: subdued, low-chroma, paint on paper; lamps are soft value gradients, no hard bloom). Comics always sit on warm paper inside the room.

### B8 Colour, decided 2026-10-15 ("Ghibli midnight" room, chosen on the Naver-layout mock-up)

LOCKED 2026-10-15 on the Naver-layout mock-up (`zumi-midnight-home.html`).

| Token | Midnight | Paper (default on web) | Note |
|---|---|---|---|
| `room` | #121A22 | #FFFFFF | page field |
| `room.raised` | #1B2430 | #F7F4EF | cards, rail, inputs, chips |
| `hairline` | #2A3340 (brass-tinted) | #EAE4DA | separators, never neutral grey |
| `hairline.strong` | #343E4D | #E2DCD1 | input borders |
| `paper` | #F5EDDC | #FFFFFF | comic covers and panels |
| `text` | #EDE4D3 (13.9:1) | #222222 | |
| `text.dim` | #9AA0A8 | #8A8178 | metadata |
| `text.faint` | #6D747D | #B5ADA3 | placeholders, disabled |
| `accent` | #E0A24A lamp amber | #A5673E cozy brown | links, active tab, UP badges, rank numbers, live dots, sort-active |
| `accent.ink` | #2A211B | #FFFFFF | text on accent fills (brown+white is 4.2:1, so brown is never used for large CTAs) |
| `cta` | #E0A24A | #F0B03A lamp amber | Enter, Join, Creator's, primary buttons |
| `cta.ink` | #2A211B | #2A211B | 9.6:1 on the CTA fill |
| `banner` | #1B2430 | #F4ECE4 | promo strips (Naver's light-blue band) |
| `glow` | rgba(224,162,74,.22) | rgba(165,103,62,.18) | hover halo on covers and rooms, orb glow |
| `alert` | #E5332A | #E5332A | "N" new dots, release stickers (Naver convention) |
| `wood` | #5A4330 | #5A4330 | XR furniture, hero tint |
| mascot hues | #FFB13D #5AD1FF #9BFF6A #FF6A6A #C49BFF #FFE14D #4DFFC3 #FF9BD6 | same | one per reader, none near the accent |

Rules: Midnight is at least 60% blue-black with one amber pocket, never #121212. Only accent-coloured signals (badges, live counters, rank numbers), CTAs and the orb may animate or glow; everything else is still paper. Theme names in the UI: Paper, Dusk, Midnight. Dusk is a later interpolation, not built in MVP.

### B10 Imagery rules, decided 2026-10-15

- Cover ratios: 1:1.19 (Naver home rows), 1:1 squares in rails, lists and "new this month", 2:3 only on episode lists and in XR.
- Paper grain: one tiled texture token on the room field only, 4 to 6% opacity, off under reduced-data. Never on covers.
- No halftone in the UI; it belongs inside the comics.
- Illustration in the UI: only Zumi (the orb, with face) and a small set of library props (lamp, stacked books, floating wisps) drawn by the artist, used in empty states, the end card, side skins and the landing hero. No stock, no AI-generated UI art.
- Hover: amber glow halo on covers and room cards (`glow` token), scale stays 1.0.
- Type stays: Barlow Condensed for headings and numerals, Noto Sans + Noto Sans KR/JP for body (Pretendard is the production candidate if self-hosted).

## Pending

- Component inventory (D4 list in conversation, to confirm during Storybook setup).

## Process

1. Brief (this file) -> 2. tokens as DTCG JSON in `packages/design-tokens/tokens` (done 2026-10-15) -> 3. Style Dictionary build (CSS, USS, C#) + Storybook token pages -> 4. components in `packages/ui` with stories -> 5. Unity consumes USS/C# output.
Skills installed in `.claude/skills/`: design-tokens, style-dictionary, storybook (Tyler-R-Kendrick) plus dylantarre scale/a11y/theming recipes.
