# Visual design and UX conventions of webtoon / web-comic platforms — 2026-10-15

Research date: 2026-10-15. Method: each platform's live homepage HTML and its main stylesheet were downloaded with `curl` and grepped for `font-family`, hex colours (frequency-ranked), `border-radius`, `aspect-ratio`, `<img width/height>`, `theme-color`, `prefers-color-scheme` / `.dark` / `[data-theme]` selectors, `:hover` and `transition` counts, and UI vocabulary (badge/tab/rank class names and visible labels). Traffic comes from Similarweb public pages (September 2026 data; the "visits" figure sits under a "Total Visits Last 3 Months" heading whose period is ambiguous, so treat it as relative scale, not absolute MAU), company IR/press pages, and app-store listings. Audience: daily readers 14–30, male-leaning, geek/otaku, large Asian share. Anything marked **[unverified]** rests on a secondary or community source; **[n/a]** means the site could not be read (geo-block, SPA without server-rendered CSS).

## Executive summary

1. **The habit is a white page with one saturated accent, a 2:3-ish cover grid, weekday tabs, a ranking rail and `UP`/`NEW` badges.** Nine of thirteen comic platforms read ship `background:#fff` by default (WEBTOON, Naver, Piccoma, LINE Manga, Jump+, Kuaikan, Tapas web, Tappytoon, MangaPlaza); dark-by-default is the minority (Kakao Webtoon `#121212`, KakaoPage, Bilibili Manhua `#1C1C1F`, Manta `#000`), and dark is *offered* by Naver, Lezhin, Tapas, KakaoPage and Kakao Webtoon via `prefers-color-scheme` / `.dark` / `[data-theme]` tokens.
2. **Typography is system-first and CJK-aware, almost never display-led.** Pretendard (Naver, KakaoPage, Lezhin, Tappytoon), Noto Sans JP + Poppins (Piccoma, Jump+), PingFang/HarmonyOS (Kuaikan, Bilibili), Inter/Poppins (Tapas, Manta). WEBTOON global is the only one with a licensed geometric display face (Volte), plus Kanit for Thai.
3. **The audience skews male 18–24 on every Asian-origin site Similarweb profiles** (Naver 70.6% M, Jump+ 69.2%, Bilibili Manhua 68.6%, KakaoPage 68.6%, MANGA Plus 67.3%, Piccoma 66.1%, WEBTOON 58.6%); the US-born manhwa licensors tilt female (Lezhin 55.2% F, MangaPlaza 52.2% F, Manta 50.7% F). Scale: WEBTOON ~155M MAU (company), Piccoma >10M MAU and ~50% of Japan's digital-comic market **[unverified]**, Jump+ 11–12.5M monthly (2023), Kuaikan ~40–50M MAU (2018–21 figures only).
4. **Monetisation vocabulary is standardised**: a coin currency, `Fast Pass` early access, and a 23–24 h "wait for free" timer (Piccoma `待てば¥0`, LINE Manga `¥0 Pass`, Kakao `기다리면 무료`, Tappytoon/Lezhin `Wait Until Free`). WEBTOON killed Daily Pass on 2025-05-29 in favour of ad-unlocks and whole-series purchase.
5. **Motion is sparse except at the two extremes**: Kakao Webtoon's IPX (animated character art, no thumbnail grid, dark canvas) and Piccoma (120 `transition:` rules). Everyone else uses hover scale 1.1–1.2 or nothing.
6. **The 2025–26 market is consolidating, not fragmenting**: Kakao folds Kakao Webtoon into KakaoPage and shuts Tapas (2027-03-31); WEBTOON launches the Marvel Comics app on 2026-11-16 (vertical + paged, $9.99/mo); Amazon Fliptoon (Japan beta, 23 h wait-free) explores North America; no ByteDance/TikTok comic reader was found.
7. **For Zumi**: adopt the 2:3 cover, 4–8 px radius, pill chips, weekday tab, `UP`/`NEW` badge grammar and a single accent; stand out with a dark-default canvas (only Kakao/Bilibili/Manta do it, all otaku-coded), Pretendard/Noto CJK-first type, and otaku-adjacent patterns (ranking with trend arrows, creator notes under episodes, daily check-in) that WEBTOON's 2025 redesign is moving *away* from.

---

## A. Comparison table

Visits = Similarweb Sep 2026 figure (period label ambiguous). M% = Similarweb male share. Accent = most frequent saturated hex in the live CSS. Default/dark = body background in CSS / dark-mode hooks present.

| Platform | Visits · top region | M% | Accent (CSS) | Default / dark | Body type (CSS) | Cover | Radius (modal) | Weekday tab | Rank rail | UP/NEW | Wait-free | Motion |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| WEBTOON global | 20.8M · US 32%, TW 6.6%, FR 6.4% | 58.6 | `#00DC64` (69×) | white / none in CSS | Volte, Kanit, system | 232×301 (0.77) | 4 / 8 / 24 px, 50% | MON–SUN | 1–30 + trend ▲▼ | `badge_up2`, `badge_new` | Fast Pass, ad pass | hover scale 1.1 |
| Naver Webtoon (KR) | 45.9M · KR 93% | 70.6 | `#00DC64`, `#FF952B` | white / `.darkmode` + `prefers` | `--wcc-ui-font-family` (Pretendard **[unverified]**) | 2:3 **[unverified]** | .25rem, 9999px | yes | yes | UP pink `#FF3478` **[unverified]** | Cookie / daily pass | low |
| Kakao Webtoon (KR) | 2.3M · KR 88% | 65.7 | `#3E92FC` | **dark `#121212`** / `[data-theme=light]` | Roboto, AppleSDGothicNeo, Dotum; custom `KwNumber`, `KwBadge` | no grid (IPX) | 25 px pills | 요일 | 랭킹 | `UP` ×30, `NEW` | 기다리면 무료 | animated IP art |
| KakaoPage (KR) | 8.4M · KR 89% | 68.6 | `#F7C900` (Kakao yellow) **[unverified]** | **dark** (`body.light` is the override) / `.dark` ×20 | Pretendard (loaded), Tailwind system stack | `aspect-ratio:1/1.8` | .125–.25rem, pill | yes | yes | yes | yes | low |
| Tapas (US) | 2.9M · US 37% | 51.7 | `#004EFF`, `#F64656` | white / `.dark` tokens `#000…#fff` | Inter, Poppins | 110×220 (1:2) & 110×83 | 4–9 px | Daily | Top/Trending | New | Ink + keys | none |
| Tappytoon (US) | 1.6M · US 31% | 51.2 | `#00EBB2` mint | white (`theme-color #fff`) / — | PretendardStd, LexendDeca | — | — | Daily | Trending | New | Time Till Free 24 h | — |
| Lezhin (US) | 3.1M · US 42%, VN 8% | 44.9 | `#ED1C24` / `#EB0014` | `--bg-default:#fff` / `#1c1c1c` via `prefers` + `.dark` | Pretendard Variable, Pretendard JP | `3/4`, `9/16`, `1/1` | 4 / 6 / 12, 999px | Daily | Ranking ×20 | New | WUF | hover scale 1.2 |
| Manta (US) | 2.1M · US 25%, IN 5% | 49.3 | `#676BFF` violet | `--bg:#000` / `#fff` | Poppins | — | 6 / 8 | Daily | Trending | — | subscription $4.99 | scale .98 press |
| Piccoma (JP) | 32.2M · JP 94% | 66.1 | `#FDDD09` yellow, `#FF4C4C` | white / none | Poppins, Noto Sans JP, Hiragino | — | 2–7 px | 曜日 | ランキング ×77 | 新作 | 待てば¥0 (23 h) | 120 transitions |
| LINE Manga (JP) | 1.2M web (app-first) · JP 91% | 58.9 | neutrals; brand green **[n/a]** | white `#fff/#fcfcfc` / none | Meiryo, MS PGothic, Hiragino | — | 2–3 px | yes | yes | — | Every Day Free 23 h, ¥0 Pass 2 h | low |
| Shonen Jump+ (JP) | 19M · JP 87% | 69.2 | `#E53935` red (152×) | white / none | Noto Sans JP, Roboto | 168×245 (0.69 ≈ 2:3) | 8 / 20 / 30 px | 毎日 updates | ランキング | 新連載, 読切 | all free first read | 274 hover rules |
| MANGA Plus (global) | 13.1M · US 14%, TH 9%, ID 9%, FR 8% | 67.3 | red **[n/a]** (SPA) | dark app **[unverified]** | **[n/a]** | — | — | — | — | — | MAX $1.99/$4.99 | — |
| Bilibili Manhua (CN) | 2M · CN 74%, HK 8% | 68.6 | `#FB7299` pink (theme-color), `#C98A5D` gold | **dark `#1C1C1F`** | Tailwind SSR; PingFang/HarmonyOS | — | — | 周× | 排行 | 新作 | 漫读券 | — |
| Kuaikan (CN) | 1.4M web (app-first) · CN 31%, TW 23% | 63.5 | `#FFD806` yellow, `#1EAB50` | white / none | PingFang SC, Hiragino, YaHei | — | 4 px | 周× (更新 ×57) | 排行 | 新作 | VIP + 会员 | 19 transitions |
| MangaPlaza (US) | 2.4M · US 18%, JP 7% | 47.8 | — (store-style) | white | **[n/a]** (tiny CSS) | 990×330 banners | 50% | — | — | — | $6.99 Premium | — |

Adjacent brands: Crunchyroll `#FF5E00` **[third-party]**, Crunchyroll Atyp + DM Sans/Lato, dark hero `#151515` over white, 48 px radius; Discord `#5865F2` Blurple (official), ABC Ginto, radius 8/16/40+; Steam `#1B2838`/`#171A21`, `#66C0F4`, Motiva Sans, radius 0–2 px; Bilibili `#00AEEC` + `#FF6699`, HarmonyOS Sans, radius 4–8 px; HoYoLAB 5-tab bottom bar, white; hololive `#27C7FF`, Rubik + Noto Sans JP, 50 px pills.

## B. Per-platform notes

### WEBTOON (Naver, global) — https://www.webtoons.com/en/
1. ~155M MAU, 150+ countries, 27M creators (https://about.webtoon.com/our-brands). FY2025 MAU 157M, −7.1% YoY, Korea paying ratio 15.1% (Q4 2025 call, https://www.aol.com/articles/webtoon-wbtn-q4-2025-earnings-232039689.html). Ads deck: "85.6M+ Global MAUs" (https://shared-comic.pstatic.net/fileShare/2025_BrandedWebtoonPkg_v2_.pdf). Similarweb Sep 2026: 20.8M visits, rank #1,959, US 32.3% / TW 6.55% / FR 6.39% / TH 3.79% / ID 3.47%, 58.6% male, 18–24 largest (https://www.similarweb.com/website/webtoons.com/).
2. `#00DC64` is the single most frequent colour in `linewebtoon-*.css` (69 occurrences); neutrals `#8C8C8C`, `#E0E0E0`, `#3C3C3C`, `#242424`; secondary blue `#3B6CEF`. `body{background:#fff}`; **no** `prefers-color-scheme`/`.dark` rule in the web CSS (users install a userscript, https://greasyfork.org/scripts/577859-webtoons-dark-mode). No official brand hex found; media kit lists logos only (https://about.webtoon.com/media-kit).
3. `font-family: volte, -apple-system, …` (38 rules) and `kanit` (27, Thai locale); all-caps for `UP`, `NEW`, `CANVAS`, weekday abbreviations.
4. Vertical canvas. Home: cover images served at 232×301 and 192×249 (ratio 0.77, between 3:4 and 2:3), 192×192 squares for creator-drawn icons; `webtoon_list _daily_tab` with MON…SUN; `ranking_number_1…30` + `trending.up/down`; `view_count type_like`; `genre` label on every card; `badge_up2`/`badge_new` sprites; `thumbnail{border-radius:50%;54px}` creator avatars; radii 4 / 8 / 24 px. June 2025 redesign replaced the hero banner with a 5-up "Trending and Popular" strip and switched the schedule from creator-drawn character icons to cover art, aligning with Naver KR (https://kcomicsbeat.com/2025/06/11/webtoon-got-a-new-facelift-what-do-we-think/).
5. Medium density, flat, no mascot, hover `scale(1.1)`. May 2025 added "New & Hot" tab with trailer-style previews, onboarding genre pick, AI recs, keyword search, whole-series unlock (https://about.webtoon.com/press-release/183).
6. Episode list, per-episode comments with `super_like`, `creator_note`, likes, offline download, notifications, Fast Pass, ad pass; Daily Pass discontinued 2025-05-29 (https://kcomicsbeat.com/2025/05/29/no-youre-not-losing-it-webtoon-got-rid-of-daily-pass/). A 2026 Pratt critique praises the reader ("interface recedes") and faults coin opacity and cliffhanger paywalls (https://ixd.prattsi.org/2026/02/design-critique-webtoon-ios-app/).
7. General-public: white, green, cover-art uniformity; the otaku signals (creator art icons, hero banner) were removed in 2025.

### Naver Webtoon (Korea) — https://comic.naver.com/webtoon
1. Similarweb: 45.9M visits, KR 93.4%, **70.6% male**, 18–24 (https://www.similarweb.com/website/comic.naver.com/). Korea ~20.4M MAU, 26% paying **[unverified, undated]** (https://www.baijing.cn/article/41467).
2–3. `kw-owner/prod-1.0/index.css`: `#00DC64` ×7, orange `#FF952B`, greys `#171717…#F3F3F3`; `.darkmode` and `@media (prefers-color-scheme: dark)` both present; type via `--wcc-ui-font-family`. Third-party token gallery lists Pretendard 800/700/500, UP pink `#FF3478`, 2:3 thumbnails, "thumbnail radius above 8 px prohibited", 480 px mobile container (https://www.oppadu.com/tools/design-systems-site/brand/naver-webtoon.html) **[unverified]**.
4–7. Same grammar as global but denser; Korea is the template WEBTOON global converged to in 2025.

### Kakao Webtoon (Korea) — https://webtoon.kakao.com/
1. Similarweb 2.3M visits, KR 88.3%, 65.7% male (https://www.similarweb.com/website/webtoon.kakao.com/). ~1.8M domestic app MAU June 2025 **[unverified]** (https://en.namu.wiki/w/카카오웹툰). Merging into KakaoPage by end-2026 (https://en.wikipedia.org/wiki/Kakao_Webtoon).
2. `theme-color #121212`, `<html data-theme="dark">` default, `[data-theme=light]` ×50 as the alternative; accent `#3E92FC`/`#4095FF`.
3. `Roboto, AppleSDGothicNeo, Dotum`; bespoke icon fonts `KwNumber`, `KwBadge` for ranking numerals and badges.
4. "Broke away from small rectangular thumbnails"; characters animated "as if alive", content scrolls in all four directions; tabs Webtoon Originals / Novel Originals / Ranking (https://view.asiae.co.kr/en/article/2021072715253755144). Buttons `border-radius:25px`; HTML shows `UP` ×30, `무료` ×22, `기다리면`.
5–7. The most "otaku" visual on the list: dark, cinematic, moving IP art ("IPX"). Low web traffic suggests the look did not win the mass market.

### KakaoPage (Korea) — https://page.kakao.com/
1. Similarweb 8.4M visits, KR 88.6%, 68.6% male (https://www.similarweb.com/website/page.kakao.com/).
2–3. Pretendard loaded (`pretendard.css`); Tailwind system stack; `body` tokens default to black (`--element-el-10: 0 0 0`) with `body.light` override → dark default; accents `#F7C900` yellow, `#00A447`, `#3280FF` **[hierarchy unverified]**.
4. `aspect-ratio:1/1.8` tall cards; pill radii. Becomes Kakao's single consumer surface (webtoon + web novel) in 2026.

### Tapas (US, Kakao) — https://tapas.io/
1. Similarweb 2.9M, US 37.3%, DE 5.3%, PH 5.3%, 51.7% male (https://www.similarweb.com/website/tapas.io/). "10M+ app subscribers" (https://kcomicsbeat.com/2024/09/25/guide-to-webtoon-platforms/). Shuts 2027-03-31; Ink sales stopped 2026-10-01 (https://en.wikipedia.org/wiki/Tapas_(website)).
2–4. Inter + Poppins; `.dark{--base10:#000…--base60:#fff}`; accents `#004EFF`, `#F64656`; thumbs 110×220 (1:2) and 110×83; tabs Comics / Novels / Community / Mature; radii 4–9 px. 2021 audience: mostly women 18–24.

### Tappytoon (US) — https://www.tappytoon.com/en
1. Similarweb 1.6M, US 30.6%, 51.2% male (https://www.similarweb.com/website/tappytoon.com/); 7M+ registered 2022, 78% US (https://en.wikipedia.org/wiki/Tappytoon).
2–4. `PretendardStd-*` + `LexendDeca-Medium`; mint `#00EBB2` on `#0F0F0F` text, `theme-color #fff`; copy counts: Free 87, Points 57, Romance 36, Mature 32, BL 29, Daily 18. Points + Tappytoon Club; 48 h tickets.

### Lezhin (KR/US) — https://www.lezhinus.com/en
1. Similarweb 3.1M, US 41.8%, VN 8.2%, **55.2% female** (https://www.similarweb.com/website/lezhinus.com/).
2–4. `Pretendard Variable` / `Pretendard JP Variable`; red `#ED1C24`/`#EB0014`/`#F72832`; `--bg-default:#fff` and `#1c1c1c` under `prefers-color-scheme:dark` + `.dark`; `aspect-ratio: 3/4, 9/16, 1/1`; radii 4/6/12, `--full:999px`; `Ranking` ×20, genres Fantasy / Drama / Romance / BL; hover `scale(1.2)`. Coin-heavy, mature-forward, "high production values" (https://unstar.app/blog/webtoon-tapas-manga-plus-tappytoon-lezhin-comic-reader-apps-ranked-2026).

### Manta (RIDI, US) — https://manta.net/
1. Similarweb 2.1M, US 24.6%, IN 5.2%, 50.7% female (https://www.similarweb.com/website/manta.net/). Subscription $4.99/mo + Gems; "second-largest paid-user comic platform in the US" (kcomicsbeat guide above).
2–4. Poppins; `--bg:#000` / `#fff` tokens; violet `#676BFF`/`#543DFF`; radii 6/8; tabs COMIC / MANGA / NOVEL; sections Daily / Completed / Trending; press `scale(.98)`. Netflix-style, romantasy, no badges in SSR.

### Piccoma (Kakao, Japan) — https://piccoma.com/web/
1. Similarweb 32.2M, JP 94.2%, rank #836, **66.1% male** (https://www.similarweb.com/website/piccoma.com/). MAU >10M Q3 2025, ~50% share **[unverified]** (https://baike.baidu.com/en/item/Piccoma/3490342); #1 consumer spend in Japan 2024, #2 in H1 2025 (https://www.animenewsnetwork.com/news/2025-07-11/line-manga-tops-japan-app-revenue-rankings-in-1st-half-of-2025/.226535).
2–3. Yellow `#FDDD09` (28×), red `#FF4C4C` (30×), dark-brown text `#332C02`; `body #fff`, no dark mode; `"Poppins"` + `"Noto Sans Jp"` + Hiragino.
4–6. Copy counts: 無料 ×895, 話 ×571, SMARTOON ×138, ¥0 ×79, ランキング ×77, 待てば ×33. Radii 2–7 px; 120 `transition` rules (most motion of any white-canvas site). "待てば¥0" = one episode per title per 23 h (https://www.gigazine.net/gsc_news/en/20180610-comic-app-piccoma). SMARTOON = full-colour vertical section.
7. General-public, convenience-store bright; otaku signal is the sheer density of free/¥0 badges.

### LINE Manga (Naver/LY, Japan) — https://manga.line.me/ (HTTP 412 outside Japan)
1. Top-grossing app in Japan H1 2025 across all categories (data.ai via ANN, link above). Web traffic small (1.2M, JP 91%, https://www.similarweb.com/website/manga.line.me/) — app-first.
2–4. CSS reachable: Meiryo / MS PGothic / Hiragino; neutrals `#2B2B2A` text on `#F8F8F8`; radii 2–3 px. "Every Day Free" 23 h, "¥0 Pass" 2 h wait, up to 13 chapters/day, 700k titles **[store-listing claims]** (https://apkcombo.com/lineマンガ/jp.naver.linemanga.android/).

### Shonen Jump+ (Shueisha, Japan) — https://shonenjumpplus.com/
1. Similarweb 19M, JP 86.6%, rank #2,589, **69.2% male** (https://www.similarweb.com/website/shonenjumpplus.com/). 2023: 2.6M daily / 6.7M weekly / 11–12.5M monthly users (natalie.mu via https://www.einerd.com/shonen-jump-celebra-10-anos-com-exposicao-especial-no-japao/) **[secondary]**.
2–4. Red `#E53935` (152×) / `#D6201C`; white body; `'Noto Sans JP'`, Roboto; thumb 168×245 (≈2:3); radii 8 / 20 / 30 px; 274 `:hover` rules; copy 読切 (one-shots) ×14, 新連載, ランキング. Paged manga, free first read of all originals; MANGA Plus is its overseas mirror.
7. Magazine-coded: red masthead, "ジャンプ" ×111 on the page. The most publisher-flavoured, male-skewed site in the set.

### MANGA Plus (Shueisha, global ex JP/CN/KR) — https://mangaplus.shueisha.co.jp/
1. Similarweb 13.1M, US 13.7%, TH 9.3%, ID 8.6%, FR 7.8%, DE 6.4%, 67.3% male (https://www.similarweb.com/website/mangaplus.shueisha.co.jp/); 28M downloads May 2024 (https://www.anitrendz.com/news/2024/06/03/shueishas-manga-plus-app-launches-limited-time-manga-creator-support-feature). MAX plans $1.99 / $4.99 since Oct 2023 (https://www.anitrendz.com/news/2023/10/03/shueisha-launches-manga-plus-max-subscription-with-new-standard-deluxe-plans).
2–6. SPA shell only (2.3 kB), CSS **[n/a]**; HTML carries `#5D0914` and `#000000`. Paged reader with vertical option, per-chapter comments, creator section (https://en.wikipedia.org/wiki/Manga_Plus).

### Bilibili Manhua (China) — https://manga.bilibili.com/
1. Similarweb 2M, CN 74.2%, HK 8.1%, 68.6% male (https://www.similarweb.com/website/manga.bilibili.com/). MAU second to Kuaikan, close to Tencent Comics (Jan 2023, https://news.qq.com/rain/a/20230119A01JMW00). Overseas edition closed 2024-02-29 (https://duckprintspress.com/2022/05/15/how-to-read-manhua-on-bilibili-legal-free-and-in-english/).
2–4. `theme-color #FB7299` (Bilibili pink); page tokens `#1C1C1F` ×191, `#90929B` ×153 → **dark default**; gold `#C98A5D` (VIP), `#32AAFF`, `#FF9D11`; Tailwind SSR; copy 推荐 / 新作 / 排行 / 追漫 (follow) / 漫读券 (reading vouchers).
7. Inherits Bilibili's ACG identity (22娘/33娘 mascots, 小电视 logo, https://www.bilibili.com/html/aboutUs.html); dark canvas + gold VIP = gacha-launcher coding.

### Kuaikan Manhua (China) — https://www.kuaikanmanhua.com/
1. Web 1.4M (CN 30.6%, TW 23%, 63.5% male, https://www.similarweb.com/website/kuaikanmanhua.com/) — app-first. 45.51M MAU end-2018 (QuestMobile via https://www.sixthtone.com/news/1001291); 200M+ cumulative users, 85% under 25 (Aug 2021, https://investinchina.chinadaily.com.cn/s/202108/09/WS6110f5d4498e6a12c120431a/comic-platform-to-invest-big-on-original-content.html); "50M+ MAU" **[unverified]** (https://www.swotanalysis.com/kuaikan-manhua). Female-skewing per Chinese press (qq.com above).
2–4. White body; `PingFang SC, Hiragino Sans GB, Microsoft YaHei`; yellow `#FFD806`, orange `#F5A623`, green `#1EAB50`, red `#F56C6C`; radius 4 px; `更新` (updated) ×57, weekday 周× chips, 排行, VIP/会员.

### MangaPlaza (NTT Solmare, US) — https://mangaplaza.com/
1. Similarweb 2.4M, US 18.4%, JP 7.5%, 52.2% female (https://www.similarweb.com/website/mangaplaza.com/). 150k+ chapters, 120+ publishers, $6.99 Premium (https://www.businesswire.com/news/home/20251127612542/en/3-Hit-MangaPlaza-Titles-Coming-to-Print-at-Select-U.S.-Bookstores).
2–7. White e-bookstore look; 990×330 banner carousel; CSS too small to profile. Paged manga, store-first, not a "daily" habit product.

### 2025–2026 entrants
- **Marvel Comics app by WEBTOON** — launches 2026-11-16, 35k+ comics, paged **and** vertical, $9.99/mo or $69.99/yr, Ultimate $12.49; Marvel Unlimited sunsets 2026-12-07 (https://www.animenewsnetwork.com/news/2026-10-09/webtoon-to-launch-new-marvel-comics-app-in-november/.242617).
- **Amazon Fliptoon** — Japan beta of vertical originals inside Kindle with 23 h wait-for-free; continuous-scroll added to Kindle; North-America launch under exploration (Mar 2026, https://www.asiae.co.kr/en/article/2026031123134291623; https://www.amazon.co.jp/-/en/b?ie=UTF8&node=23819878051).
- **Apple Books** vertical-manga page in Japan (same asiae article). **ByteDance/TikTok**: no comic reader found in 2025–26 searches **[absence, not proof]**.

### Adjacent brands this audience uses daily
- **Crunchyroll** — Jul 2024 rebrand: orange / black / white / taupe, Crunchyroll Atyp display, eye-mark logo (https://www.advanced-television.com/2024/07/19/crunchyroll-unveils-rebrand/); live site preloads Atyp + Lato; orange `#FF5E00`, dark hero `#151515` over white sections, 48 px radii **[third-party extraction]** (https://www.shadcn.io/design/crunchyroll/raw).
- **Discord** — Blurple `#5865F2`, Light Blurple `#E0E3FF`, black (https://discord.com/branding); CSS: ABC Ginto family, `#5865F2` ×230, dark `#23272A`, radii 8 / 16 / 40–64 px; Wumpus/Clyde mascots.
- **Steam** — `#171A21` theme-color, `#1B2838` canvas, `#66C0F4`/`#67C1F5` link blue, Motiva Sans, radii 0–2 px, 940 px dense column (https://store.steampowered.com/, https://www.webdesignhot.com/design.md/steam/ **[third-party]**).
- **Bilibili** — `#00AEEC` blue + `#FF6699` pink in CSS, HarmonyOS Sans Regular/Medium, radii 4 / 6 / 8 px, `.dark` theme; mascots 22娘/33娘 + 小电视 (https://www.bilibili.com/html/aboutUs.html).
- **HoYoLAB** — social-first community app, 5-button bottom bar, daily check-in, Battle Chronicle, fan-art feed, 13+ (https://apps.apple.com/us/app/hoyolab/id1559483982).
- **hololive production** — `#27C7FF` sky blue, Rubik (EN) + Noto Sans JP, 50–100 px pill radii (https://hololivepro.com/en/).

## C. Synthesis

### A. Common denominator (what every big one shares)
- **Vertical-scroll canvas for webtoons, paged for manga, and the reader hides its own UI** — WEBTOON's reader is the one part even critics praise (Pratt 2026). Jump+/MANGA Plus/MangaPlaza stay paged because the source is paged.
- **Home = card grid of portrait covers (2:3 ± a bit: 0.69 Jump+, 0.77 WEBTOON, 3:4 Lezhin, 1:1.8 KakaoPage, 1:2 Tapas) with 4–8 px corners**, title + genre + like-count under each; the one platform that abolished the grid (Kakao Webtoon) is being folded away.
- **Weekday tab** (MON–SUN / 요일 / 曜日 / 周×) on every Korean, Japanese and Chinese site; **ranking rail** numbered 1–N (WEBTOON adds ▲▼ trend); **`UP` / `NEW` badges** in two fixed colours; **like counter**; **round creator avatar** (WEBTOON 54 px, 50%).
- **One saturated brand accent on neutral greys**, body text ≥ `#171717`/`#191919`, never pure black on white: green, yellow, red, pink, blurple — each brand owns exactly one.
- **System/CJK sans, weights 500/700/800, tight tracking, all-caps micro-labels**; no serif, no display type except WEBTOON's Volte.
- **Economy grammar**: coins → `Fast Pass` early access + 23–24 h wait-free timer + ad unlock; per-episode comments; follow/bookmark; push on new episode; offline download.

### B. Where they differ and what it signals
| Axis | Pole 1 | Pole 2 | Signal |
|---|---|---|---|
| Canvas | White (WEBTOON, Naver, Piccoma, LINE, Jump+, Kuaikan) | Dark default (Kakao Webtoon, KakaoPage, Bilibili Manhua, Manta) | White = mass-market, store-like; dark = otaku/gamer, binge, "theatre" |
| Cover grid | Uniform cover art (WEBTOON 2025) | Creator-drawn icons / animated IP (Kakao IPX, old WEBTOON) | Uniform = scale & exposure; bespoke = fandom identity (readers missed it) |
| Accent | Cool green/blue/violet | Hot yellow/red/pink | Cool = platform neutrality; hot = publisher/magazine (Jump+ red) or convenience (Piccoma yellow) |
| Badge density | Sparse (Manta, Tapas) | Saturated (Piccoma 無料 ×895, Tappytoon Free ×87) | Sparse = subscription; saturated = freemium timers |
| Motion | None/hover scale | Transitions everywhere (Piccoma), living art (Kakao) | Motion correlates with Asian home markets, not with platform size |
| Radius | 2–4 px (Piccoma, LINE, Kuaikan, Steam) | 24–48 px pills (Kakao 25, Crunchyroll 48, hololive 50) | Small = utilitarian/dense; pill = brand-forward Western-facing |
| Type | Pretendard / Noto CJK-first | Poppins / Inter / Volte Latin-first | CJK-first reads native to the Asian cohort; Latin geometric reads "US app" |
| Gender | Male 65–70% (Naver, Jump+, Piccoma, Bilibili) | Female-leaning (Lezhin, Manta, MangaPlaza, Kuaikan) | Romance/BL catalogues flip the ratio regardless of UI |

### C. Design tokens / decisions for Zumi
Adopt to feel native:
- Cover `aspect-ratio: 2/3`, `border-radius: 6px` (≤ 8 px — the Naver gallery's rule and every live site's range), 2-line title 13–14 px/700, genre + ♥ count 11–12 px/500 beneath.
- Pill genre chips (`border-radius: 9999px`, 32 px tall), weekday tab row with today pre-selected, numbered ranking rail with ▲▼ trend glyphs, `UP` and `NEW` badges in two fixed colours at 9–10 px/800 uppercase, radius 3 px.
- Type: `Pretendard Variable, "Noto Sans JP", "Noto Sans SC", system-ui` — CJK-first stack, weights 500/700/800, letter-spacing −0.01 to −0.025 em on headings; no display face.
- One accent, used only for CTA/active tab/focus, never body text; neutrals ramp `#0E0E10 → #F5F5F5`.
- Economy vocabulary readers already parse: coins, Fast Pass, 23 h wait-free timer, "ad unlock"; show real-money equivalent next to coin prices (the Pratt critique's top fix).
- Reader: chrome hides on scroll, per-episode comments with creator note first, like, bookmark, next-episode cue, offline download, notification bell with per-series toggle.

Stand out while staying native:
- **Dark default (`#0E0E10`/`#121212`) with light as the opt-in** — the Kakao/Bilibili/Manta/Steam/Discord side of the split, i.e. the otaku-gamer side, where WEBTOON ships none.
- **Creator-drawn square icons for the "Daily" row, cover art elsewhere** — restores the identity WEBTOON's readers said they lost in June 2025, at no cost to the grid.
- **Daily check-in + streak (HoYoLAB / Lezhin pattern) and reading-vouchers (Bilibili 漫读券) instead of a bare coin shop** — gacha-launcher coded, familiar to this cohort, absent from Western readers.
- **Trailer-style "New & Hot" motion previews** (WEBTOON May 2025) done sparingly — motion is the one lever the white-canvas giants under-use.
- Avoid: pure-white canvas + pill-everything (Tapas/Manta "romantasy app" code), hot-red masthead (reads as Jump+), and more than one accent.

### D. Non-comic visual references this audience admires
1. **Steam store** — https://store.steampowered.com/ — dark navy `#1B2838`, 0–2 px radii, 940 px dense column, Motiva Sans light; the benchmark for "serious, dense, mine" among male 18–30 gamers.
2. **Discord** — https://discord.com/branding — single ownable accent (`#5865F2`) on `#23272A` dark, illustration-led (Wumpus), generous 8–16 px radii; the social layer where webtoon fandoms already live.
3. **HoYoLAB / HoYoverse launchers** — https://www.hoyolab.com/home — daily check-in, gold-on-dark premium tier, character-art-first cards; the gacha habit loop readers of the same age run daily.
4. **Crunchyroll 2024 identity** — https://www.advanced-television.com/2024/07/19/crunchyroll-unveils-rebrand/ — orange `#FF5E00` + black, custom Atyp display, dark hero over white body; shows how an anime brand went mass-market without losing the fandom.
5. **Bilibili** — https://www.bilibili.com/ — blue/pink duo, mascots, HarmonyOS Sans, 4–8 px radii, danmaku culture; the Chinese-speaking cohort's home.

## Sources (all accessed 2026-10-15)
Live CSS/HTML: webtoons.com `linewebtoon-1be2271e310973e0801f.css`; ssl.pstatic.net `kw-owner/prod-1.0/index.css`; kr-a.kakaopagecdn.com `web/5.12.1/_next/static/css/316f2832ef3dabfa.css`; page.kakaocdn.net `csr/real/2.43.1/_next/static/css/87636eb7e4d9c1f1.css`; static.tapas.io `7.8.2/_next/static/css/3823c9d3824a96d4.css`; lezhinus.com `_next/static/css/4a5af9e3355e6249.css`, `63a9e2e08fc5e951.css`; manta.net `_next/static/css/0444d1a25644dcb9.css`; piccoma.com `static/web/css/pcm_web_v65.0.css`, `home/pcm_web_home_v23.0.css`; cdn-manga-static-file-origin.ldf-static.net `pc_main_e34f898e….css`; cdn-ak.shonenjumpplus.com `css/jump_plus.css`; s1.hdslb.com `laputa-home/assets/index-3f345f9f.css`; static3w.kuaikanmanhua.com `_nuxt/static-kkfront-pc/css/app.c278f04e….css`; store.akamai.steamstatic.com `shared_global.css`; cdn.prod.website-files.com `discord-2022.shared.f0e7d3991.min.css`; hololivepro.com `css/common.css`.
Traffic: Similarweb pages for webtoons.com, comic.naver.com, webtoon.kakao.com, page.kakao.com, tapas.io, tappytoon.com, lezhinus.com, manta.net, piccoma.com, manga.line.me, shonenjumpplus.com, mangaplus.shueisha.co.jp, manga.bilibili.com, kuaikanmanhua.com, mangaplaza.com (Sep 2026).
Company/press: about.webtoon.com/our-brands, /media-kit, /press-release/183; WEBTOON Q4 2025 call (aol.com); 2025_BrandedWebtoonPkg_v2_.pdf; asiae.co.kr 2021-07-27 (Kakao IPX) and 2026-03-11 (Amazon/Apple); ANN 2025-07-11 and 2026-10-09; anitrendz 2023-10-03, 2024-06-03; businesswire 2025-11-27; discord.com/branding; advanced-television.com 2024-07-19; bilibili.com/html/aboutUs.html; apps.apple.com HoYoLAB.
Secondary (flagged in text): kcomicsbeat.com 2024-09-25, 2025-05-29, 2025-06-11; unstar.app 2026-05-31; ixd.prattsi.org 2026-02; oppadu.com Naver Webtoon gallery; shadcn.io Crunchyroll and webdesignhot Steam extractions; en.wikipedia.org Kakao_Webtoon, Tapas_(website), Tappytoon, Manga_Plus; en.namu.wiki 카카오웹툰; baike.baidu.com Piccoma; baijing.cn/article/41467; news.qq.com 2023-01-19; sixthtone.com/news/1001291; investinchina.chinadaily.com.cn 2021-08-09; swotanalysis.com/kuaikan-manhua; einerd.com (natalie.mu); gigazine.net 2018-06-10; apkcombo.com LINE Manga listing.
Not obtainable: official brand hex for WEBTOON, Kakao, Piccoma, LINE Manga, Bilibili, Crunchyroll, hololive (values above are live-CSS measurements); MANGA Plus and Crunchyroll CSS (SPA); Kakao Webtoon / Piccoma / Kakao Webtoon app-store pages (404/403); 2025 MAU for Kuaikan, Bilibili Manhua, LINE Manga, Tapas, Lezhin, Manta, Tappytoon.
