# @zumi/design-tokens

Single source of truth for Zumi's visual tokens across web (CSS variables), Unity (USS + C#) and Storybook docs.

## Flow

```
design/zumi.pen                SOURCE OF TRUTH: Pencil variables + "mode" theme (paper | midnight) and every screen
    │  export (Pencil MCP get_variables -> DTCG JSON; script todo, done by hand until then)
    ▼
tokens/*.tokens.json           W3C Design Tokens (DTCG 2025.10), a mirror of the Pencil variables
    │  style-dictionary build  (config in build/)
    ▼
dist/css/tokens.css            :root + [data-theme] custom properties for apps/web and packages/ui
dist/uss/paper.uss, midnight.uss   resolved values per theme for Unity UI Toolkit (USS has no var() in functions)
dist/csharp/ZumiTokens.cs      static class for apps/xr
```

## Files

- `tokens/primitives.tokens.json`: raw palette, type, space, radius, motion. The only tier with literal values.
- `tokens/semantic.paper.tokens.json`: intent tokens for the Paper theme (web default). Aliases only.
- `tokens/semantic.midnight.tokens.json`: same keys for the Midnight theme (XR default, web optional).
- `tokens/xr.tokens.json` (todo): reading distance, carousel spacing, depth scale, orb glow radius. Unity only.

## Rules

- No literal colour outside `primitives.tokens.json`.
- Theme files must have identical key sets; the build fails otherwise.
- Names: `group.sub.name` in DTCG become `--group-sub-name` in CSS, `--group-sub-name` in USS, `Group.Sub.Name` in C#.
- Edit tokens in Pencil, not here. Names: Pencil `group/sub/name` = DTCG `group.sub.name` = CSS/USS `--group-sub-name` = C# `GroupSubName`.

Design decisions behind the values: `docs/design/brief.md`.
