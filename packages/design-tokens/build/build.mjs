import StyleDictionary from "style-dictionary";
import { mkdir, writeFile, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const pkg = path.resolve(here, "..");
const dist = path.join(pkg, "dist");
const THEMES = ["paper", "midnight"];
const DEFAULT_THEME = "paper";

/* ---------- value transforms (DTCG composite values -> platform strings) ---------- */

const unitValue = (v) => (v && typeof v === "object" && "value" in v ? `${v.value}${v.unit ?? ""}` : v);

StyleDictionary.registerTransform({
  name: "zumi/dimension",
  type: "value",
  transitive: true,
  filter: (t) => ["dimension", "duration"].includes(t.$type),
  transform: (t) => unitValue(t.$value),
});

StyleDictionary.registerTransform({
  name: "zumi/cubicBezier",
  type: "value",
  transitive: true,
  filter: (t) => t.$type === "cubicBezier",
  transform: (t) => `cubic-bezier(${t.$value.join(", ")})`,
});

StyleDictionary.registerTransform({
  name: "zumi/fontFamily",
  type: "value",
  transitive: true,
  filter: (t) => t.$type === "fontFamily",
  transform: (t) => t.$value.map((f) => (/\s/.test(f) ? `"${f}"` : f)).join(", "),
});

StyleDictionary.registerTransformGroup({
  name: "zumi/css",
  transforms: ["name/kebab", "zumi/dimension", "zumi/cubicBezier", "zumi/fontFamily"],
});

/* ---------- helpers ---------- */

const refRe = /^\{([^}]+)\}$/;
const kebabPath = (p) => p.replace(/\./g, "-");
const cssName = (t) => `--${t.name}`;

/** CSS value: keep alias chain as var() when the original was a single reference. */
function cssValue(t) {
  const orig = t.original?.$value;
  if (typeof orig === "string") {
    const m = orig.match(refRe);
    if (m) return `var(--${kebabPath(m[1])})`;
  }
  return t.$value;
}

const isPrimitive = (t) => t.filePath.endsWith("primitives.tokens.json");
const isSemantic = (t) => !isPrimitive(t);

/* ---------- formats ---------- */

StyleDictionary.registerFormat({
  name: "zumi/css-block",
  format: ({ dictionary, options }) => {
    const sel = options.selector;
    const only = options.only; // "primitive" | "semantic" | undefined
    const lines = dictionary.allTokens
      .filter((t) => (only === "primitive" ? isPrimitive(t) : only === "semantic" ? isSemantic(t) : true))
      .map((t) => `  ${cssName(t)}: ${cssValue(t)};`);
    return `${sel} {\n${lines.join("\n")}\n}\n`;
  },
});

/** Unity USS: resolved values only (USS cannot use var() inside functions or arithmetic). */
StyleDictionary.registerFormat({
  name: "zumi/uss",
  format: ({ dictionary, options }) => {
    const lines = dictionary.allTokens
      .filter((t) => ["color", "dimension", "number", "fontWeight", "duration"].includes(t.$type))
      .map((t) => `  ${cssName(t)}: ${t.$value};`);
    return `/* Zumi tokens, theme: ${options.theme}. Generated, do not edit. */\n:root {\n${lines.join("\n")}\n}\n`;
  },
});

/** C#: one static class, nested per theme for colours, shared numbers at the top level. */
function pascal(p) {
  return p
    .split(".")
    .map((s) => s.replace(/(^|[-_])(\w)/g, (_, __, c) => c.toUpperCase()))
    .join("");
}
function csValue(t) {
  switch (t.$type) {
    case "color":
      return `Hex("${t.$value}")`;
    case "dimension":
    case "duration":
      return `${parseFloat(t.$value)}f`;
    case "number":
    case "fontWeight":
      return `${t.$value}f`;
    case "fontFamily":
      return `"${t.$value.replace(/"/g, "")}"`;
    case "cubicBezier":
      return `new[] { ${t.original.$value.map((n) => `${n}f`).join(", ")} }`;
    default:
      return null;
  }
}
function csType(t) {
  return { color: "Color", fontFamily: "string", cubicBezier: "float[]" }[t.$type] ?? "float";
}
function csLines(tokens, indent) {
  return tokens
    .map((t) => {
      const v = csValue(t);
      if (v == null) return null;
      const name = pascal(t.path.join("."));
      const doc = t.$description ? `${indent}/// <summary>${t.$description}</summary>\n` : "";
      return `${doc}${indent}public static readonly ${csType(t)} ${name} = ${v};`;
    })
    .filter(Boolean)
    .join("\n");
}

/* ---------- build ---------- */

async function buildTheme(theme) {
  const sd = new StyleDictionary({
    usesDtcg: true,
    source: [path.join(pkg, "tokens/primitives.tokens.json"), path.join(pkg, `tokens/semantic.${theme}.tokens.json`)],
    log: { verbosity: "default", warnings: "error" },
    platforms: {
      css: { transformGroup: "zumi/css" },
      uss: {
        transformGroup: "zumi/css",
        buildPath: `${dist}/uss/`,
        files: [{ destination: `${theme}.uss`, format: "zumi/uss", options: { theme } }],
      },
    },
  });
  await sd.hasInitialized;
  await sd.buildPlatform("uss");
  const cssDict = await sd.getPlatformTokens("css");
  return cssDict;
}

await mkdir(path.join(dist, "css"), { recursive: true });
await mkdir(path.join(dist, "csharp"), { recursive: true });

const dicts = {};
for (const theme of THEMES) dicts[theme] = await buildTheme(theme);

/* CSS: primitives + default-theme semantics on :root, other themes on [data-theme]. */
const blocks = [];
const fmt = StyleDictionary.hooks.formats["zumi/css-block"];
blocks.push(fmt({ dictionary: dicts[DEFAULT_THEME], options: { selector: ":root" } }));
for (const theme of THEMES.filter((t) => t !== DEFAULT_THEME)) {
  blocks.push(fmt({ dictionary: dicts[theme], options: { selector: `:root[data-theme="${theme}"]`, only: "semantic" } }));
  blocks.push(
    `@media (prefers-color-scheme: dark) {\n` +
      fmt({ dictionary: dicts[theme], options: { selector: `  :root[data-theme="system"]`, only: "semantic" } }).replace(/\n/g, "\n  ") +
      `\n}\n`,
  );
}
await writeFile(path.join(dist, "css/tokens.css"), `/* Zumi tokens. Generated from packages/design-tokens/tokens, do not edit. */\n\n${blocks.join("\n")}`);

/* C# */
const shared = dicts[DEFAULT_THEME].allTokens.filter((t) => isPrimitive(t) && t.$type !== "color");
const cs = `// Zumi tokens. Generated from packages/design-tokens/tokens, do not edit.
using UnityEngine;

namespace Zumi.Design
{
    public static class ZumiTokens
    {
        static Color Hex(string hex) { ColorUtility.TryParseHtmlString(hex, out var c); return c; }

${csLines(shared, "        ")}

${THEMES.map(
  (theme) => `        public static class ${pascal(theme)}
        {
${csLines(dicts[theme].allTokens.filter((t) => t.$type === "color"), "            ")}
        }`,
).join("\n\n")}
    }
}
`;
await writeFile(path.join(dist, "csharp/ZumiTokens.cs"), cs);

/* Manifest for Storybook token pages */
const manifest = Object.fromEntries(
  THEMES.map((theme) => [
    theme,
    dicts[theme].allTokens.map((t) => ({
      name: t.name,
      path: t.path.join("."),
      type: t.$type,
      value: t.$value,
      tier: isPrimitive(t) ? "primitive" : "semantic",
      description: t.$description ?? null,
      ref: typeof t.original?.$value === "string" && refRe.test(t.original.$value) ? t.original.$value.slice(1, -1) : null,
    })),
  ]),
);
await writeFile(path.join(dist, "tokens.json"), JSON.stringify(manifest, null, 2));

const n = dicts[DEFAULT_THEME].allTokens.length;
console.log(`tokens: ${n} per theme, themes: ${THEMES.join(", ")} -> dist/css/tokens.css, dist/uss/*.uss, dist/csharp/ZumiTokens.cs, dist/tokens.json`);
