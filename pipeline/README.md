# Zumi pipeline

Python CLI. Stages run locally for iteration and on Modal when they need a GPU; progress goes to Weights & Biases (not yet wired). Built one stage at a time; each stage is approved before the next.

```
uv sync
uv run zumi intake <folder> --out out/ep.zumi --report out/cuts.png
```

Input is either a folder of per-panel files (`p01.png`, ...) or a folder of webtoon slices (`01.jpg`, ...), see `docs/pipeline/artist-delivery.md`. Output is a `.zumi` (see `packages/format`) with one flat `base` layer per panel and, for strips, a `scroll` layout with each panel's placement on the original strip.

Stages

| # | Stage | State |
|---|---|---|
| 1 | intake: stitch, gutter scan, pack | done; tuning stopped 2026-10-18 (two rounds, see `tuning-log.md`): about 2 % reader-visible errors on unseen episodes, remaining caption-ownership cases left to stage 2 |
| 2 | bubbles and text: find, read and assign to panels (first half of Understand) | proposed, not approved |
| 3 | understand | |
| 4 | regenerate | |
| 5 | layers (SAM 3.1, LaMa, depth) | |
| 6 | voices | |
| 7 | ambience and music | |
| 8 | animation | |
| 9 | immersive frames | |
| 10 | upload | |

`.data/` holds research-only test material and is gitignored.
