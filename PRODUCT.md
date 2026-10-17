# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary: daily webtoon readers, 14 to 30, often male, geek and otaku, with a large Asian share. They read on WEBTOON, Naver, Kakao, Piccoma and Bilibili every day and own or want a Meta Quest 3. Situation: evening, at home, headset on, looking for something to read with other people in the room. Job: find an episode, drop into a room, read together without effort.

Secondary: the comic artist whose series is processed for the demo (needs to see their art respected), and the Meta VR developer competition judges (need to understand the product in three minutes).

## Product Purpose

Zumi turns rough comic sketches into living XR episodes: parallaxed paper panels in the reader's own room, voiced characters, ambience, animation, and immersive scenes. People read them together in rooms of up to eight, represented by glowing orb mascots. Success for the competition: one series, several episodes, a multiplayer reading session that judges can watch in a trailer and try on a Quest 3.

The web is not a creation platform (descoped 2026-10-17). It exists for two surfaces: a coming-soon landing with the Meta Quest store badge, and a series home page kept as a design-method test bed and possible future showcase.

## Positioning

The only comic reader where the episode is generated from sketches by a Meta-model pipeline and read together in mixed reality. Neighbouring products either read flat comics on a phone or put a flat video in a VR theatre; none regenerates the art into layered, voiced panels or puts friends' avatars around the panel.

## Operating Context

- Read in mixed reality on Quest 3: passthrough room, panel at about one metre, automated pacing, pause by vote.
- Rooms are auto-matched per episode; friends join via Meta invites.
- Vocabulary: Creator, Series, Episode, Panel, Scene (panorama or 3D), Room, Zumi (the orb mascot and reader avatar), Emote. "Comic" only in marketing copy.
- Platform habits the audience expects (measured from the top platforms, see `docs/research/webtoon-platforms-design-2026-10.md`): weekday tabs, ranking rails with trend arrows, UP and NEW badges, 2:3 or 1:1.19 covers, dense grids, genre chips, "reading now" style live counters.

## Capabilities and Constraints

- Design tokens are the source of truth: `packages/design-tokens/tokens/*.tokens.json`, built to CSS (`dist/css/tokens.css`), Unity USS and C#. Two themes, Paper and Midnight, identical key sets.
- Web stack: Next.js 16 and Tailwind v4 bridging the token variables; components in `packages/ui` on Radix primitives. Landing is static HTML on the token CSS.
- Content on the web is mock data until the pipeline produces real episodes. Cover images are placeholders (picsum.photos) until the artist's art exists; they must be marked as placeholders and never presented as real series art.
- English only for the MVP; Korean and Japanese are later locales, so UI type must have CJK companions.
- Deadline: Meta VR developer competition, about 2026-11-14. One developer plus one artist.

## Brand Commitments

- Name: Zumi. Mascot: Zumi, a flat-shaded glowing sphere with a face (two eyes, one mouth, a single `mood` parameter), one of eight bright hues per reader, none near the brand accent.
- Theme, binding: "a magical library at midnight". Lofi, cosy, communal. The lighting model is one warm amber lamp inside a cool blue-black room (Ghibli night interiors, Kazuo Oga's low-chroma paint-on-paper look). Comics always sit on warm paper inside the room.
- Locked palette and type in `docs/design/brief.md`: Paper theme (white field, brown accent #A5673E, amber CTA #F0B03A with dark ink) and Midnight theme (#121A22 room, cream text, amber lamp #E0A24A); Barlow Condensed for display and numerals, Noto Sans with Noto Sans KR/JP for body.
- Tone of voice: fan-native, light meme and fandom register, "Episode" not "Chapter".
- Imagery rules: only Zumi and a few library props drawn by the artist may illustrate the UI; no stock illustration, no AI-generated UI art, no halftone in the UI; subtle grain on the room field only; amber glow on hover.
- Reference the user endorsed: Naver Webtoon's home structure (`docs/design/references/네이버-웹툰-2026-10-15.png`) and Deadlock's "City Never Sleeps" page for hand-made feel.

## Evidence on Hand

- Research reports in `docs/research/` (models, voices, audio, platform conventions, lofi and Ghibli study, design tooling).
- No real series, covers, testimonials, user numbers, or store listing yet. Do not fabricate any. Series names in mock data are placeholders.
- Meta's official "Available on Meta Quest" badge must come from Meta's brand resources; it is not in the repo yet.

## Product Principles

1. The art is the brightest thing on any screen; the UI recedes on reading surfaces and shows personality only through Zumi and live signals.
2. Native to the webtoon habit first (density, badges, rankings, weekday rhythm), distinctive second (midnight library atmosphere).
3. Presence is the product: anything that says "someone is here" (live counters, rooms, orbs) gets the accent and the motion; everything else is still paper.
4. Meta first: Meta models, Meta XR SDK, Meta Platform features, documented exceptions only.
5. Ship what a three-minute trailer can show flawlessly over what half-works.

## Accessibility & Inclusion

Text contrast 4.5:1 minimum on both themes (brown on white is reserved for text, never white on brown for large controls). Reduced-motion: the orb bob and live pulse stop. Hand-tracking-only input in XR, 48 dp minimum targets per Meta's guidelines.
