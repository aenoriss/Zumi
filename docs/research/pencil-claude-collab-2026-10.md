# Pencil (pen.dev) ↔ Claude Code: how the designer's changes reach the developer agent — 2026-10-17

Research date: 2026-10-17. Primary sources: docs.pen.dev (pencil.dev redirects there since 2026-09), pen.dev homepage and FAQ, the installed Pencil app (1.1.69, `Pencil.exe` VersionInfo) and its MCP server binary (`mcp-server-windows-x64.exe --help`, `get_editor_state(include_schema)`, `get_guidelines`, `get_variables` run in this session), Anthropic's Claude Code docs (hooks, MCP, scheduled tasks), GitHub API for community repos (stars / push dates 2026-10-17). Blog posts and third-party skills are labelled as such. No official Pencil GitHub org or changelog was found (the homepage links only a Discord [S1]). Anything else is marked **unverified**. Companion to `design-quality-tooling-2026-10.md` (fidelity loop, Meta UI Set) which this file does not repeat.

## Executive summary

1. **`.pen` is plain JSON, not encrypted.** The draft open right now (`~/.pencil/documents/…/pencil-new.pen`) starts `{"version":"2.6","children":[…` and `file` reports "JSON text data"; the docs say "JSON-based", "View diffs in Git (text-based format)" [S2, S3]. The "encrypted" line comes only from the MCP server's own instruction string and the docs still say "do not edit the JSON directly" [S2].
2. **Nothing pushes changes to Claude.** No webhook, file-change event, version history, comments, dev-mode or diff tool exists in Pencil or its MCP [S2, S4, S5]; the server's rules even warn the agent "the document can change while you work, so the state you remember may be stale … re-read" [S6]. Detection is therefore Claude Code's job: `FileChanged` hook on `design/zumi.pen` (needs the file saved in the repo, not as a Draft) or a `/loop` [S12, S13].
3. **Our MCP is a generation behind the docs.** Installed server: schema 2.14, tools `get_editor_state/batch_get/batch_design/…`; docs: schema 2.21, tools `execute/get_app_state/read_skill/get_style` [S5, S7]. Expect a breaking tool rename on the next app update.
4. **`note`/`prompt`/`context` nodes have a schema but no documented semantics** (just `content`, `prompt` adds `model`); every node also has a free `context?: string` [S6, S7]. Use `note` for designer→Claude instructions by convention, not because Pencil routes them.
5. **No Pencil→Unity path exists.** Sanest route: `batch_get(resolveVariables, resolveInstances)` JSON → our own converter (Pencil's layout model is single-axis flex with `fit_content/fill_container/gap/padding`, which maps onto USS flexbox or uGUI LayoutGroups); `export_html` only as a reference or as input to `html2uuitk` [S15, S16].
6. **Tokens:** `get_variables` returns Pencil JSON (`{themes:{mode:[paper,midnight]}, variables:{"color/accent/default":{type,value:[{theme,value}]}}}`), not DTCG; one script converts it into `packages/design-tokens/tokens/*.json` for the existing style-dictionary build [S6, repo].
7. **Recommended loop (section 5):** designer saves `design/zumi.pen` to the repo, renames a screen frame `screen/<name>` and sets `placeholder:false` + a `note` child "READY vN"; a `FileChanged` hook tells Claude; Claude reads `batch_get` + `export_nodes` PNG, builds, captures Unity, compares; token edits go through the converter script.

---

## 1. Pencil facts that matter

| Question | Answer | Source |
|---|---|---|
| File format | JSON object tree: `{version, themes, imports, variables, children}`; "pen.dev also accepts JSON comments". Verified on disk (`file` → "JSON text data"). The server's "encrypted: access only via pencil MCP tools" text is a policy string, not a property of the file. | [S2, S7], local check |
| Schema version | Docs `version: "2.21"`; installed app 1.1.69 returns `"2.14"` from `get_editor_state`; the open draft is `"2.6"`. "This is a live documentation, and we reserve the right to introduce breaking changes in the .pen format." | [S7], local |
| Git | "Commit `.pen` files like code files", "View diffs in Git (text-based format)", "Branch and merge designs with code". Rules: save and close before switching branches; keep images/fonts/libraries at relative paths; on conflict keep both versions, pick one as base and redo the other's changes in pen.dev, never by editing JSON. | [S2, S3] |
| Versions / history | None. "The recovery backup is not version history and does not replace Git"; "Use Git history to revert if needed." | [S2, S4, S8] |
| Comments / handoff / dev mode | None documented. Sharing = snapshot link "anyone with the link can view and download"; updated with "Update snapshot". Properties panel has a **Code** section (HTML + Tailwind / HTML + CSS copy or export). | [S4, S9] |
| Multiple files / imports | Top-level `imports: {alias: relative URI}`; `.lib.pen` libraries ("cannot be undone"); "Saved changes to a library … load in documents that import it when you reopen them." Installed server rules: "You cannot reference components across files … copy it over" (older behaviour). | [S7, S10, S6] |
| CLI | `npm install -g @pen.dev/cli` (Node ≥ 22.19). `pen --in design.pen --export design.png` (`--export-type png|jpeg|webp|pdf`), `pen interactive -o design.pen` runs "a local editor without a GUI", `pen interactive -a desktop -i file.pen` drives the running app. No `watch`, `diff`, or standalone `mcp` command; "an export can fail without a nonzero exit status". | [S5] |
| File-change event / webhook | None in app, CLI or MCP. Only Script nodes watch their `.js` on disk. In VS Code/Cursor the IDE offers Reload when the file changed on disk. | [S2, S11, S5] |
| "What changed" / diff tool | None. MCP tools (installed): `get_editor_state, get_guidelines, batch_get, batch_design, get_variables, get_screenshot, snapshot_layout, export_nodes, export_html`. No MCP resources: Claude Code adds list/read-resource tools "when servers support them" and none appeared in this session [S14]. `strings` on the server exe found no `resources/` or `notifications/` strings (**weak evidence**). | [S14], local |
| `export_html` | HTML + Tailwind (default) or HTML + CSS; optional scaffold, layer names (default on) and layer IDs as `data-` attributes; "Image assets are always referenced with relative paths (never embedded)". No fidelity statement anywhere in the docs. | tool schema, [S9] |
| `export_nodes` | PNG/JPEG/WEBP/PDF, "2x scale and 8192 max resolution", one file per node named by node ID; PDF = one multi-page doc. | tool schema |
| Variables / themes | Four types (color, number, string, boolean); themes are axes (`themes: {mode: [paper, midnight]}`), "the default value of each theme axis is the first value", "the value that wins … is the *last* one whose theme is satisfied"; a node's `theme` applies a mode to its subtree. `get_variables` returns raw Pencil JSON (51 variables in our draft), not DTCG/CSS; docs' token sync is "Ask the agent to apply token changes to both files" (CSS ↔ pen). | [S7, S17], local |

## 2. Pencil's own guidance for coding agents

- **Design ↔ Code page** [S18]: "Save the `.pen` file in your project workspace", "The AI agent can access both files"; prompts point at "this button / this form"; tokens: "Import design tokens from src/styles/tokens.css" and "Update globals.css with these pen.dev variables"; code→design: "Recreate the Button component from src/components/Button.tsx" then review "component structure and hierarchy, layout and positioning, styling". **No** naming conventions, no "ready" marker, no rules file, no screenshot comparison.
- **AI integration** [S19]: external client ↔ server over stdio, server ↔ app over "a local Unix socket … or a named pipe on Windows"; one active document; "Open the intended `.pen` file and include its full path in your prompt"; "Ask the agent to check `get_app_state()` and confirm the active document before editing" (our server: `get_editor_state`, which also returns the current selection: verified, it returned `TZ5nP (frame): Token sheet`).
- **Skills** [S20]: "Skills add instructions to an agent request"; custom `SKILL.md` via the composer slash menu; external agents call `read_skill()` (ours: `get_guidelines`, 8 guides incl. `Code`, `Design System`, `Tailwind`, 26 styles).
- **Installed `Code` guide** (primary, this server) [S6]: identify refs used in the frame, `batch_get` each component "ONE AT A TIME", `get_screenshot` "on instances in context", "Compare with rendered React component. Verify pixel-perfect match", `batch_get includePathGeometry:true` for SVG, map `$primary → var(--primary)`, "use the same text labels, icons and spacing as what is in the design". Web-only vocabulary (React, Tailwind).
- **Naming** [S6, S21]: only hints: component names like `Button/*`, `Input Group/*`; "sometimes their node name is prefixed `component/`"; `batch_get` has a `name` regex filter, so a prefix convention is searchable. `placeholder: true` marks a root frame as work-in-progress ("Remove `placeholder: true` as soon as the frame is done").
- **`note` / `prompt` / `context` nodes** [S7, S6]: schema only: `Note {content}`, `Prompt {content, model}`, `Context {content}`; `Entity.context?: string` on every node. The docs page "does not explain what these nodes are for" and no page mentions them. **Unverified** assumption: `prompt` feeds the in-app agent composer, `context` is read as agent context. They are returned by `batch_get` (type filter includes `note`), so a convention works regardless.
- **Staleness rule shipped with the server** [S6]: "Pencil is a collaborative multiplayer environment: the document can change while you work, so the state you remember may be stale. If a node is missing or no longer matches what you expected, re-read instead of recreating it, and don't undo changes the user made in the meantime."

## 3. Claude Code side

| Mechanism | What it does | Fit for Zumi | Source |
|---|---|---|---|
| `FileChanged` hook | Filesystem watcher; matcher is split on `\|` and "each segment is registered as a literal filename in the working directory"; input has `file_path` and `event` (`change/add/unlink`); fires "no matter what changed the file … or a process outside Claude Code entirely"; `watchPaths` from `SessionStart` adds absolute paths. | Best fit, once `zumi.pen` lives in the repo. Hook returns `additionalContext` → Claude reads it on the next model request. | [S12] |
| `UserPromptSubmit` / `SessionStart` | Plain stdout "added as context that Claude can see"; `additionalContext` JSON. | Inject "pen mtime changed since last build" on every prompt (cheap poll). | [S12] |
| `PreToolUse` `mcp__pencil__.*` | Matcher works per tool (`mcp__pencil__batch_design`). | Block `batch_design` on Zumi's file so Claude never edits the designer's canvas. | [S12] |
| `/loop` | Min 1 min; `/loop 5m` creates `*/5 * * * *` which fires 4 m 45 s after the previous run; fires only between turns; 7-day expiry; `Monitor` tool "avoids polling altogether". | Fallback when the file is not in the repo. | [S13] |
| MCP resources / notifications | `@server:resource` only "when servers support them"; `list_changed` refresh. Pencil exposes none (section 1). | Not available. | [S14] |
| Images from MCP | Image results are shown inline and saved to `~/.claude/projects/…/tool-results/` (v2.1.283+). | `get_screenshot` output is reusable as a comp file. | [S14] |

Community examples (none automates detection; all re-read on request): Jerad Bitner, 2026-04: one shared library (56 colour variables, 16 components), seven versions in one 3 h thread, screenshots per version, no tool names [S22]. atalupadhyay, 2026-02: older tool names (`get_selected_frames`, `get_style_guide`), "select a specific frame and ask Claude to read the selected frame", right-click annotations, fidelity by side-by-side + dev tools, "start Pencil before Claude Code" [S23]. `Nisus74/pencil-skill` (25 stars, pushed 2026-07-26, MIT): `filePath: ""` targets the active editor; `get_editor_state(include_schema:true)` once per session; legacy `icon_font` filter does not match 2.14 `icon` nodes [S24]. `phrazzld/agent-skills` `pencil-to-code` (4 stars): `batch_get(readDepth 10, resolveInstances, resolveVariables)` → `get_variables` → Tailwind `@theme` → optional screenshot compare [S25]. A Chinese "compound-engineering" page pairs the same tools with Playwright screenshot diffs [S26].

## 4. Pencil → Unity

Nothing exists for `.pen`; Pencil's docs never mention Unity or game engines [S9]. Adjacent tools: `fake-skate/html2uuitk` (61 stars, pushed 2026-10-16): HTML + CSS → UXML/USS, "73+ USS properties", `div→ui:VisualElement`, `p/span/h1→ui:Label`, `button→ui:Button`, `display:grid→flex`, rem→px; no JS, tables warned [S15, S16]. `TrackMan/Unity.Package.FigmaToUnity` is Figma-only and "experimental" [S27].

Sanest path, in order of fidelity:
1. **`batch_get` JSON → own converter** (`packages/format` already has schema + C# tooling). Pencil nodes are a flex tree: `layout: vertical|horizontal|none`, `gap`, `padding`, `justifyContent`, `alignItems`, `fit_content`/`fill_container`, `cornerRadius`, `stroke`, text with `fontFamily/fontSize/lineHeight`, `$var` references [S6]. That is a near 1:1 map to USS (`flex-direction`, `justify-content`, `align-items`, `flex-grow:1` for `fill_container`) or to uGUI `HorizontalLayoutGroup`/`LayoutElement` for the headset panels (companion research recommends uGUI/Meta UI Set there). Resolve `ref` instances with `resolveInstances:true` or map them to prefabs by component name.
2. **`export_html` → `html2uuitk`** as a bootstrap for UI Toolkit screens (landing/dev tooling), then hand-fix; fidelity **unverified**.
3. **`export_nodes` PNG (2x)** as the comp for the visual check, never as the source.

## 5. Recommended loop for Zumi

| Step | Designer (Pencil) | Claude Code | Verified? |
|---|---|---|---|
| 0 Setup | **File → Save As `design/zumi.pen`** (today the active doc is a Draft under `~/.pencil/documents`, invisible to git and to `FileChanged`). Commit it. | `.claude/settings.json`: `FileChanged` matcher `zumi.pen` (literal filename; hook script compares mtime/`git diff --stat design/zumi.pen` and returns `additionalContext: "design/zumi.pen changed: frames X,Y"`); `PreToolUse` on `mcp__pencil__batch_design` → deny. | Hook semantics [S12]; Pencil-side behaviour of Save As standard |
| 1 Mark ready | Screen = top-level frame named `screen/<Name>` with `clip:true`; while editing keep `placeholder:true`; when done set `placeholder:false` and add a child `note` named `status` with content `READY v3 — <what changed>`. Instructions for Claude go in `note` nodes or the frame's `context` string. | `batch_get({patterns:[{name:"^screen/"}], readDepth:1})` then filter `placeholder !== true` and read the `status` note. | Names/`placeholder`/`note` are schema facts [S6, S7]; Pencil does not interpret the note (**convention**) |
| 2 Detect | Save (`Ctrl+S`). | `FileChanged` fires → Claude re-reads the changed screens (the server rule says re-read, never trust memory [S6]). Without the repo file: `/loop 5m` asking "check get_editor_state + batch_get for screens whose status note changed". | [S12, S13] |
| 3 Read | — | `get_variables` (tokens), `batch_get(nodeIds:[screen], readDepth:6, resolveInstances:true, resolveVariables:false)` so `$color/…` names survive into code; `includePathGeometry:true` for icons; `export_nodes` PNG as comp into `design/comps/`. | tool schemas; Code guide [S6] |
| 4 Build | — | Converter emits UXML/USS or uGUI prefab data; variables map to the C# Theme ScriptableObject from `@zumi/design-tokens`. | repo |
| 5 Check | Looks at Claude's capture, replies in the `status` note or chat. | `Unity_Camera_Capture` of the panel vs the PNG comp; the companion file's numeric done criteria; `snapshot_layout(problemsOnly:true)` catches clipped/overlapping nodes on the design side before blaming the build. | tool schema; fidelity method [companion] |
| 6 Tokens | Edit variables in the panel; `mode` axis stays `paper\|midnight`. | `scripts/pen-tokens.mjs`: `get_variables` JSON → DTCG (`color/accent/default` → `{ "color": { "accent": { "default": { "$type":"color", "$value": …}}}}`, themed values → one file per mode) → `pnpm -F @zumi/design-tokens build`. Diff `dist/tokens.json` in the PR. | `get_variables` shape verified; converter to write |

Unverified / open: whether `prompt`/`context` nodes are read by the in-app agent; whether `.lib.pen` component refs across files work in 1.1.69 (server rules say no, docs say yes); jitter of `/loop` on this machine; whether the next Pencil update renames the tools (docs already show `execute`), which would break any hook matcher on `mcp__pencil__batch_design`.

## Sources

- [S1] pen.dev homepage — https://www.pen.dev/ ("just a JSON file … Schema fully opened"; Discord link)
- [S2] `.pen Files` — https://docs.pen.dev/core-concepts/pen-files
- [S3] Design as Code — https://docs.pen.dev/core-concepts/design-as-code (last updated 2026-10-13)
- [S4] Share a design — https://docs.pen.dev/core-concepts/sharing
- [S5] pen.dev CLI — https://docs.pen.dev/for-developers/pen-cli
- [S6] Installed Pencil 1.1.69 MCP server: `get_editor_state(include_schema:true)`, `get_guidelines("Code")`, `get_guidelines("Design System")`, `get_variables` outputs, 2026-10-17 (`C:\Users\Usuario\AppData\Local\Programs\Pencil\resources\app.asar.unpacked\out\mcp-server-windows-x64.exe`, flags `-agent -app -conversation_id -enable_spawn_agents`)
- [S7] The .pen Format — https://docs.pen.dev/for-developers/the-pen-format
- [S8] pen.dev Interface — https://docs.pen.dev/core-concepts/pencil-interface
- [S9] Import and Export — https://docs.pen.dev/core-concepts/import-and-export ; FAQ — https://www.pen.dev/faq
- [S10] Design Libraries — https://docs.pen.dev/core-concepts/design-libraries
- [S11] Code on Canvas — https://docs.pen.dev/core-concepts/code-on-canvas
- [S12] Claude Code hooks reference — https://code.claude.com/docs/en/hooks (FileChanged, UserPromptSubmit, SessionStart, MCP matchers)
- [S13] Claude Code scheduled tasks — https://code.claude.com/docs/en/scheduled-tasks
- [S14] Claude Code MCP — https://code.claude.com/docs/en/mcp (resources, list_changed, image results)
- [S15] html2uuitk README — https://github.com/fake-skate/html2uuitk
- [S16] Unity Discussions showcase, 2025-06-13 — https://discussions.unity.com/t/html-css-converter-to-ui-toolkit/1655030
- [S17] Variables — https://docs.pen.dev/core-concepts/variables
- [S18] Design ↔ Code — https://docs.pen.dev/design-and-code/design-to-code
- [S19] AI Integration — https://docs.pen.dev/getting-started/ai-integration ; Installation — https://docs.pen.dev/getting-started/installation ; Troubleshooting — https://docs.pen.dev/troubleshooting
- [S20] AI agents and Skills — https://docs.pen.dev/core-concepts/ai-agents
- [S21] Components — https://docs.pen.dev/core-concepts/components
- [S22] Jerad Bitner, "Designing with Pencil and Claude Code", 2026-04 (blog) — https://jeradbitner.com/2026/04/designing-with-pencil-and-claude-code/
- [S23] atalupadhyay, "Pencil.dev + Claude Code Workflow", 2026-02-25 (blog) — https://atalupadhyay.wordpress.com/2026/02/25/pencil-dev-claude-code-workflow-from-design-to-production-code-in-minutes/
- [S24] Nisus74/pencil-skill `references/mcp-tools.md` (community) — https://github.com/Nisus74/pencil-skill
- [S25] phrazzld/agent-skills `pencil-to-code` (community) — https://market.lobehub.com/s/skills/phrazzld-agent-skills-pencil-to-code
- [S26] compound-engineering Pencil page (community, zh) — https://jerrylalala.github.io/compound-engineering/pencil.html
- [S27] TrackMan/Unity.Package.FigmaToUnity — https://github.com/TrackMan/Unity.Package.FigmaToUnity
