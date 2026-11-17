# Brand typefaces: a brushy display face and a body face — 2026-10-28

Research date: 2026-10-28. The request was a display face that is "more brushy, but not too stylised", plus a second face for subtitles and body text.

**Method.**
- **Sources.** Each candidate's `METADATA.pb` in the google/fonts repository: licence, weights, axes and subsets.
- **Run.** Every candidate was rendered in Pencil on the board "Type research (candidates)", with the same strings in Latin and, where supported, Japanese or Korean. This also confirmed that each font loads in Pencil.
- **Labels.** **[inference]** = my judgement from the renders. Facts about licence, weights and subsets come from the metadata files.

## Answer

**Update, same day (user decision): exactly three faces, one per role.**
- **Display, titles and the wordmark:** Shantell Sans. It replaces Barlow Condensed and Dela Gothic One.
- **Subtitles:** Zen Maru Gothic 700.
- **Body:** Noto Sans. Japanese and Korean use Noto Sans JP and KR, the same design, so Jua is dropped.

The rest of this note is the research behind that pick.

- **Display: Shantell Sans.**
  - Facts: OFL; variable weight 300–800 plus BNCE, INFM and SPAC axes; Latin, Cyrillic and Vietnamese, with no CJK. ([metadata](https://raw.githubusercontent.com/google/fonts/main/ofl/shantellsans/METADATA.pb))
  - Why **[inference]**: at 700–800 it reads as a marker or brush stroke with calm letterforms, close to Zumi's brush line. It stays legible as numbers and counters, and one family covers H1 to H2.
- **Subtitle and body: Zen Maru Gothic.**
  - Facts: OFL; weights 300, 400, 500, 700 and 900; Latin, Japanese, Cyrillic and Greek. ([metadata](https://raw.githubusercontent.com/google/fonts/main/ofl/zenmarugothic/METADATA.pb))
  - Why **[inference]**: its rounded terminals echo the mascot's body, and it covers Japanese in the same face.
- **Korean fallback.** Neither face covers Korean.
  - Headings: Jua (OFL, Korean and Latin, one weight). ([metadata](https://raw.githubusercontent.com/google/fonts/main/ofl/jua/METADATA.pb))
  - Body: Noto Sans KR, already listed in brief decision B10.
- **Wordmark.** It stays in Dela Gothic One, as a stand-in until the artist draws one (brief decision B5).

## Candidates rejected

| Face | Facts (from METADATA.pb) | Why not **[inference]** |
|---|---|---|
| [Potta One](https://raw.githubusercontent.com/google/fonts/main/ofl/pottaone/METADATA.pb) | OFL, display, 400 only, JP + Latin | Brushiest of the set, but heavy and calligraphic: too stylised for every heading |
| [Darumadrop One](https://raw.githubusercontent.com/google/fonts/main/ofl/darumadropone/METADATA.pb) | OFL, display, 400 only, JP + Latin | Drippy, quirky letterforms (the `g`); reads as a novelty |
| [Yusei Magic](https://raw.githubusercontent.com/google/fonts/main/ofl/yuseimagic/METADATA.pb) | OFL, 400 only, JP + Latin | Readable marker, but one thin weight: too light for headings |
| [Zen Kurenaido](https://raw.githubusercontent.com/google/fonts/main/ofl/zenkurenaido/METADATA.pb) | OFL, 400 only, JP + Latin | Brush pen, but hairline-thin |
| [Gluten](https://raw.githubusercontent.com/google/fonts/main/ofl/gluten/METADATA.pb) | OFL, variable 100–900, Latin only | Soft and brushy, but stylised forms (the `r`) |
| [Gaegu](https://raw.githubusercontent.com/google/fonts/main/ofl/gaegu/METADATA.pb) | OFL, handwriting, 300/400/700, KR + Latin | Handwriting, wide spacing; too casual |
| [M PLUS Rounded 1c](https://raw.githubusercontent.com/google/fonts/main/ofl/mplusrounded1c/METADATA.pb) | OFL, 100–900, JP + Latin and more | A good body face; Zen Maru Gothic is warmer next to the mascot |

A web search for an open-licensed brush display face with Japanese support found only paid fonts, such as Vabi Dasabi and Shoganai on Fontspring. Under the OFL constraint, the CJK options are the Google Fonts faces above.

## Open

- Zen Maru Gothic 400 at 15 px looks light on cream. If body text reads thin on the Quest 3, use 500 for body.
- The Unity side needs TextMeshPro font assets with fallback chains: Shantell Sans → Jua; Zen Maru Gothic → Noto Sans KR.
