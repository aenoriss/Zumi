/* Validates every fixtures/* /manifest.json (or the paths passed as arguments) against schema/zumi.schema.json.
   Also checks cross-references the schema cannot: speakerId -> cast, animation target / anchorLayer -> layer ids, unique ids. */
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(await readFile(path.join(here, "schema/zumi.schema.json"), "utf8"));
const ajv = new Ajv2020({ allErrors: true, strict: true, strictRequired: false });
addFormats(ajv);
const validate = ajv.compile(schema);

const targets = process.argv.slice(2);
if (!targets.length) {
  for (const d of await readdir(path.join(here, "fixtures"))) targets.push(path.join(here, "fixtures", d, "manifest.json"));
}

let failed = 0;
for (const file of targets) {
  const m = JSON.parse(await readFile(file, "utf8"));
  const errors = [];
  if (!validate(m)) errors.push(...validate.errors.map((e) => `${e.instancePath || "/"} ${e.message}`));
  const castIds = new Set(m.cast?.map((c) => c.id));
  const trackIds = new Set(m.episode?.music?.map((t) => t.id));
  const seen = new Set();
  for (const p of m.panels ?? []) {
    if (seen.has(p.id)) errors.push(`duplicate panel id ${p.id}`);
    seen.add(p.id);
    const layerIds = new Set(p.layers?.map((l) => l.id));
    for (const b of p.bubbles ?? []) {
      if (b.speakerId && !castIds.has(b.speakerId)) errors.push(`panel ${p.id} bubble ${b.id}: unknown speaker ${b.speakerId}`);
      if (b.anchorLayer && !layerIds.has(b.anchorLayer)) errors.push(`panel ${p.id} bubble ${b.id}: unknown anchorLayer ${b.anchorLayer}`);
    }
    for (const a of p.animations ?? []) if (!layerIds.has(a.target)) errors.push(`panel ${p.id} animation ${a.id}: unknown target ${a.target}`);
    if (p.musicCue && p.musicCue.track !== "none" && !trackIds.has(p.musicCue.track)) errors.push(`panel ${p.id}: musicCue names unknown track ${p.musicCue.track}`);
    for (const i of p.interactions ?? []) if (!layerIds.has(i.target)) errors.push(`panel ${p.id} interaction ${i.id}: unknown target ${i.target}`);
  }
  const rel = path.relative(process.cwd(), file);
  if (errors.length) {
    failed++;
    console.error(`✗ ${rel}\n${errors.map((e) => "    " + e).join("\n")}`);
  } else {
    console.log(`✓ ${rel} (${m.panels.length} panels, ${m.cast.length} cast)`);
  }
}
process.exit(failed ? 1 : 0);
