/* Guards: identical key sets across theme files, no literal colours outside primitives, every alias resolves. */
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const pkg = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const read = async (f) => JSON.parse(await readFile(path.join(pkg, "tokens", f), "utf8"));

function leaves(obj, prefix = [], out = []) {
  for (const [k, v] of Object.entries(obj)) {
    if (k.startsWith("$")) continue;
    if (v && typeof v === "object" && "$value" in v) out.push({ path: [...prefix, k].join("."), value: v.$value });
    else if (v && typeof v === "object") leaves(v, [...prefix, k], out);
  }
  return out;
}

const prim = leaves(await read("primitives.tokens.json"));
const primPaths = new Set(prim.map((t) => t.path));
const themes = { paper: leaves(await read("semantic.paper.tokens.json")), midnight: leaves(await read("semantic.midnight.tokens.json")) };

const errors = [];
const keyA = themes.paper.map((t) => t.path).sort().join("\n");
const keyB = themes.midnight.map((t) => t.path).sort().join("\n");
if (keyA !== keyB) errors.push("theme key sets differ between paper and midnight");

for (const [name, toks] of Object.entries(themes)) {
  for (const t of toks) {
    if (typeof t.value === "string") {
      const m = t.value.match(/^\{([^}]+)\}$/);
      if (m) {
        if (!primPaths.has(m[1]) && !toks.some((x) => x.path === m[1])) errors.push(`${name}: ${t.path} -> unresolved alias {${m[1]}}`);
      } else if (/^#[0-9a-f]{8}$/i.test(t.value) && !/glow$/.test(t.path)) {
        errors.push(`${name}: ${t.path} has a literal colour outside primitives`);
      } else if (/^#[0-9a-f]{3,6}$/i.test(t.value)) {
        errors.push(`${name}: ${t.path} has a literal colour outside primitives`);
      }
    }
  }
}

if (errors.length) {
  console.error(errors.map((e) => `  ✗ ${e}`).join("\n"));
  process.exit(1);
}
console.log(`✓ ${prim.length} primitives, ${themes.paper.length} semantic tokens per theme, key sets match, aliases resolve`);
