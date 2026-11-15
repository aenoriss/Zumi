/* Validates episodes against schema/zumi.schema.json and checks what the schema cannot.

   node validate.mjs [target...]     a target is a .zumi file, an unpacked episode folder (manifest.json and its
                                     files), or a manifest.json alone. No target: every fixtures/<name>, as a folder
                                     when it holds files besides its manifest, else its manifest alone.

   On the manifest: formatVersion (not newer than the schema, and 1.1 fields only in a 1.1 file), unique ids,
   speakerId -> cast, anchorLayer -> layers, bubble frame -> the panel's frames, settings named by frames, tracks,
   places and spans, envelope keys -> music, the places timeline, scroll layouts, animation targets and timing.
   With the files (a .zumi or a folder) also: every path the manifest names exists; each scene.glb's nodes carry
   the extras the manifest points at (speakerCard and animation targets resolve to a node's extras.card, pins to
   cards of the shaken frame, lettering nodes name a bubble, cast ids exist); panel and place materials are unlit
   and no panel texture is over 2048 px; voice clips are 24 kHz mono 16-bit PCM WAV. */
import Ajv2020 from "ajv/dist/2020.js";
import addFormats from "ajv-formats";
import { closeSync, existsSync, openSync, readFileSync, readSync, readdirSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { inflateRawSync } from "node:zlib";

const here = path.dirname(fileURLToPath(import.meta.url));
const schema = JSON.parse(readFileSync(path.join(here, "schema/zumi.schema.json"), "utf8"));
const SCHEMA_VERSION = schema.$id.split("/").pop().split(".").map(Number);
const TEXTURE_MAX = 2048;
const ajv = new Ajv2020({ allErrors: true, strict: true, strictRequired: false });
addFormats(ajv);
const validate = ajv.compile(schema);

// ---- where an episode's files are read from: {has(name), read(name, offset, length)}
function zipFiles(file) {
  const fd = openSync(file, "r");
  const size = statSync(file).size;
  const at = (offset, length) => { const b = Buffer.alloc(length); readSync(fd, b, 0, length, offset); return b; };
  const tail = at(Math.max(0, size - 65557), Math.min(size, 65557));
  const eocd = tail.lastIndexOf(Buffer.from([0x50, 0x4b, 0x05, 0x06]));
  if (eocd < 0) throw new Error("not a zip");
  const count = tail.readUInt16LE(eocd + 10), dir = at(tail.readUInt32LE(eocd + 16), tail.readUInt32LE(eocd + 12));
  const entries = new Map();
  for (let p = 0, i = 0; i < count; i++) {
    const nameLen = dir.readUInt16LE(p + 28);
    entries.set(dir.toString("utf8", p + 46, p + 46 + nameLen), { method: dir.readUInt16LE(p + 10),
      packed: dir.readUInt32LE(p + 20), local: dir.readUInt32LE(p + 42), data: null });
    p += 46 + nameLen + dir.readUInt16LE(p + 30) + dir.readUInt16LE(p + 32);
  }
  const start = (e) => { const h = at(e.local, 30); return e.local + 30 + h.readUInt16LE(26) + h.readUInt16LE(28); };
  return {
    has: (name) => entries.has(name),
    read(name, offset = 0, length = Infinity) {
      const e = entries.get(name);
      if (e.method === 0) return at(start(e) + offset, Math.min(length, e.packed - offset));  // stored: only the part
      e.data ??= inflateRawSync(at(start(e), e.packed));
      return e.data.subarray(offset, Math.min(e.data.length, offset + length));
    },
    close: () => closeSync(fd),
  };
}
function folderFiles(root) {
  return {
    has: (name) => existsSync(path.join(root, name)),
    read(name, offset = 0, length = Infinity) {
      const b = readFileSync(path.join(root, name));
      return b.subarray(offset, Math.min(b.length, offset + length));
    },
    close() {},
  };
}

// ---- a GLB's JSON, and its images' sizes (PNG headers read in place)
function glb(files, name) {
  const head = files.read(name, 0, 20);
  if (head.toString("latin1", 0, 4) !== "glTF") throw new Error(`${name}: not a GLB`);
  const n = head.readUInt32LE(12);
  const json = JSON.parse(files.read(name, 20, n).toString("utf8"));
  const bin = 20 + n + 8;
  const sizes = (json.images ?? []).map((im) => {
    const v = json.bufferViews[im.bufferView];
    const b = files.read(name, bin + (v.byteOffset ?? 0), 24);
    return im.mimeType === "image/png" ? [b.readUInt32BE(16), b.readUInt32BE(20)] : null;
  });
  return { json, sizes };
}
const unlit = (g) => (g.json.materials ?? []).every((m) => m.extensions && "KHR_materials_unlit" in m.extensions);

function check(m, files, errors) {
  const v = String(m.formatVersion ?? "").split(".").map(Number);
  const newer = v[0] !== SCHEMA_VERSION[0] || v[1] > SCHEMA_VERSION[1] || (v[1] === SCHEMA_VERSION[1] && v[2] > SCHEMA_VERSION[2]);
  if (newer) errors.push(`formatVersion ${m.formatVersion} is newer than the schema's ${SCHEMA_VERSION.join(".")}`);
  const uses11 = [];  // fields that came with 1.1: a 1.0 file may not carry them
  const need = (what, p) => { if (p && !files?.has(p)) errors.push(`${what}: ${p} is not in the episode`); };
  const castIds = new Set(m.cast?.map((c) => c.id));
  const trackIds = new Set(m.episode?.music?.map((t) => t.id));
  const settingIds = new Set(m.episode?.settings?.map((s) => s.id));
  const setting = (what, s) => { if (s !== undefined && !settingIds.has(s)) errors.push(`${what}: unknown setting ${s}`); };
  const panelIds = new Set(m.panels?.map((p) => p.id));

  if (files) {
    need("series.cover", m.series?.cover);
    for (const r of m.series?.style?.references ?? []) need("series.style.references", r);
    need("episode.thumbnail", m.episode?.thumbnail);
  }
  for (const t of m.episode?.music ?? []) {
    setting(`track ${t.id}`, t.setting);
    if (files) need(`track ${t.id}`, t.file);
  }
  const score = m.episode?.score;
  if (score) {
    for (const [id, knots] of Object.entries(score.envelope)) {
      if (!trackIds.has(id)) errors.push(`score envelope names unknown track ${id}`);
      for (let i = 1; i < knots.length; i++) if (knots[i][0] < knots[i - 1][0]) { errors.push(`score envelope ${id}: knots out of order at ${knots[i][0]} s`); break; }
    }
    for (const s of score.spans ?? []) setting(`span ${s.from}`, s.setting);
  }

  // the scenes first: a bubble may name a card of another panel
  const scenes = new Map();  // panel id -> {cards: Map(card -> extras), frames: Set, g}
  if (files) for (const p of m.panels ?? []) {
    if (!p.scene || !files.has(p.scene)) continue;
    const g = glb(files, p.scene);
    const cards = new Map(), frames = new Set();
    for (const n of g.json.nodes ?? []) {
      const x = n.extras;
      if (!x) continue;
      if (x.frame !== undefined) frames.add(x.frame);
      if (x.card !== undefined) {
        if (cards.has(x.card)) errors.push(`panel ${p.id} scene: two nodes are card ${x.card}`);
        cards.set(x.card, x);
      }
    }
    scenes.set(p.id, { cards, frames, g });
  }

  const seen = new Set();
  for (const p of m.panels ?? []) {
    if (seen.has(p.id)) errors.push(`duplicate panel id ${p.id}`);
    seen.add(p.id);
    const at = `panel ${p.id}`;
    const layerIds = new Set(p.layers?.map((l) => l.id));
    const frameIds = new Set(p.frames?.map((f) => f.index));
    const bubbleIds = new Set();
    const sc = scenes.get(p.id);
    if (files) {
      for (const l of p.layers ?? []) { need(`${at} layer ${l.id}`, l.image); need(`${at} layer ${l.id} depthMap`, l.depthMap); }
      need(`${at} panorama`, p.panorama); need(`${at} scene`, p.scene); need(`${at} ambience`, p.ambience);
    }
    for (const f of p.frames ?? []) setting(`${at} frame ${f.index}`, f.setting);
    for (const b of p.bubbles ?? []) {
      const who = `${at} bubble ${b.id}`;
      if (bubbleIds.has(b.id)) errors.push(`${who}: duplicate id`);
      bubbleIds.add(b.id);
      if (b.speakerId && !castIds.has(b.speakerId)) errors.push(`${who}: unknown speaker ${b.speakerId}`);
      if (b.anchorLayer && !layerIds.has(b.anchorLayer)) errors.push(`${who}: unknown anchorLayer ${b.anchorLayer}`);
      if (b.frame !== undefined && frameIds.size && !frameIds.has(b.frame)) errors.push(`${who}: frame ${b.frame} is not one of the panel's frames`);
      if (b.kind === "sfx" && (b.audio || b.speakerCard || b.speakerId)) errors.push(`${who}: a sound effect has no speaker and no audio`);
      if (b.kind === "sfx" || b.frame !== undefined || b.speakerCard !== undefined) uses11.push(who);
      if (b.speakerCard !== undefined) {
        const [a, c] = b.speakerCard.includes("/") ? b.speakerCard.split("/") : [p.id, b.speakerCard];
        if (!panelIds.has(a)) errors.push(`${who}: speakerCard names unknown panel ${a}`);
        else if (files && scenes.has(a)) {
          const x = scenes.get(a).cards.get(c);
          if (!x) errors.push(`${who}: speakerCard ${b.speakerCard} is no node of panel ${a}'s scene`);
          else if (b.speakerId && x.cast !== b.speakerId) errors.push(`${who}: speakerCard ${b.speakerCard} is cast ${x.cast}, the bubble says ${b.speakerId}`);
        } else if (files) errors.push(`${who}: speakerCard ${b.speakerCard}, but panel ${a} has no scene`);
      }
      if (files && b.audio) {
        need(who, b.audio);
        if (files.has(b.audio)) {
          const h = files.read(b.audio, 0, 44);
          const ok = h.toString("latin1", 0, 4) === "RIFF" && h.toString("latin1", 8, 16) === "WAVEfmt " && h.readUInt16LE(20) === 1 &&
            h.readUInt16LE(22) === 1 && h.readUInt32LE(24) === 24000 && h.readUInt16LE(34) === 16 && h.toString("latin1", 36, 40) === "data";
          if (!ok) errors.push(`${who}: ${b.audio} is not 24 kHz mono 16-bit PCM WAV with a 44-byte header`);
        }
      }
    }
    const animIds = new Set();
    for (const a of p.animations ?? []) {
      const who = `${at} animation ${a.id}`;
      if (animIds.has(a.id)) errors.push(`${who}: duplicate id`);
      animIds.add(a.id);
      if (a.startTime !== undefined || a.pivot !== undefined || a.easing === "step") uses11.push(who);
      if (["translate", "rotate", "scale", "opacity"].includes(a.track) && !(a.keyframes?.length >= 2)) errors.push(`${who}: a ${a.track} track needs keyframes`);
      for (let i = 1; i < (a.keyframes?.length ?? 0); i++) if (a.keyframes[i].t < a.keyframes[i - 1].t) errors.push(`${who}: keyframes out of order`);
      if (a.startTime !== undefined && p.startTime !== undefined) {
        if (Math.abs(a.startTime - (p.startTime + (a.delay ?? 0))) > 0.011) errors.push(`${who}: startTime ${a.startTime} is not the panel's start ${p.startTime} + delay ${a.delay ?? 0}`);
        if (p.endTime !== undefined && a.loop === false && a.startTime + (a.duration ?? 2) > p.endTime + 0.011) errors.push(`${who}: runs past its panel's end`);
      }
      const frame = /^frame:(\d+)$/.exec(a.target);
      if (layerIds.has(a.target)) continue;
      if (p.renderMode !== "scene3d") { errors.push(`${who}: unknown target ${a.target}`); continue; }
      if (frame) {
        const n = Number(frame[1]);
        if (!frameIds.has(n)) errors.push(`${who}: target ${a.target} is not one of the panel's frames`);
        if (sc && !sc.frames.has(n)) errors.push(`${who}: no node of the scene is in frame ${n}`);
        for (const c of Object.keys(a.params?.pin ?? {})) {
          if (sc && sc.cards.get(c)?.frame !== n) errors.push(`${who}: pinned card ${c} is not a card of frame ${n}`);
        }
      } else if (sc ? !sc.cards.has(a.target) : !/^card-\d+$/.test(a.target)) errors.push(`${who}: target ${a.target} is no card of the panel's scene`);
    }
    if (sc) {
      for (const n of sc.g.json.nodes ?? []) {
        const x = n.extras;
        if (!x) continue;
        const who = `${at} scene node "${n.name}"`;
        if (x.kind !== "window" && x.card === undefined) errors.push(`${who}: no extras.card`);
        if (x.cast !== undefined && !castIds.has(x.cast)) errors.push(`${who}: unknown cast ${x.cast}`);
        if (x.frame !== undefined && frameIds.size && !frameIds.has(x.frame)) errors.push(`${who}: frame ${x.frame} is not one of the panel's frames`);
        if (x.kind === "lettering" && !bubbleIds.has(x.bubble)) errors.push(`${who}: extras.bubble ${x.bubble} is no bubble of the panel`);
      }
      if (!unlit(sc.g)) errors.push(`${at} scene: a material is not unlit`);
      sc.g.sizes.forEach((s, i) => { if (s && Math.max(...s) > TEXTURE_MAX) errors.push(`${at} scene: texture ${i} is ${s[0]} x ${s[1]} px, over ${TEXTURE_MAX}`); });
    }
    if (p.musicCue && p.musicCue.track !== "none" && !trackIds.has(p.musicCue.track)) errors.push(`${at}: musicCue names unknown track ${p.musicCue.track}`);
    for (const i of p.interactions ?? []) if (!layerIds.has(i.target)) errors.push(`${at} interaction ${i.id}: unknown target ${i.target}`);
  }

  const places = m.episode?.places;
  if (places) {
    const placeIds = new Set(places.meshes.map((p) => p.setting));
    for (const p of places.meshes) {
      setting(`place ${p.setting}`, p.setting);
      const scale = ["nearM", "medianM", "farM"].filter((k) => p[k] !== undefined);
      if (scale.length || p.props) uses11.push(`place ${p.setting}`);
      if (scale.length % 3) errors.push(`place ${p.setting}: nearM, medianM and farM come together`);
      else if (scale.length && !(p.nearM <= p.medianM && p.medianM <= p.farM)) errors.push(`place ${p.setting}: nearM <= medianM <= farM does not hold`);
      const names = new Set();
      for (const q of p.props ?? []) {
        if (names.has(q.name)) errors.push(`place ${p.setting}: two props are named ${q.name}`);
        names.add(q.name);
        if (files) need(`place ${p.setting} prop ${q.name}`, q.model);
      }
      if (files) for (const part of ["front", "back"]) {
        need(`place ${p.setting} ${part}`, p[part]);
        if (files.has(p[part]) && scale.length && !unlit(glb(files, p[part]))) errors.push(`place ${p.setting} ${part}: its material is not unlit`);
      }
    }
    let end = 0;
    for (const s of places.timeline) {
      if (!placeIds.has(s.setting)) errors.push(`places timeline at ${s.start} s names unpacked place ${s.setting}`);
      if (s.start < end || s.end < s.start) errors.push(`places timeline at ${s.start} s is out of order`);
      end = s.end;
    }
  }
  if (uses11.length && v[0] === 1 && v[1] < 1) errors.push(`formatVersion ${m.formatVersion}, but ${uses11[0]} uses fields of 1.1 (${uses11.length} such)`);

  const layout = m.episode?.layout;
  if (layout?.mode === "scroll") {
    let cursor = 0;
    for (const p of m.panels ?? []) {
      if (!p.strip) { errors.push(`panel ${p.id}: scroll layout needs strip placement`); continue; }
      if (p.strip.y < cursor) errors.push(`panel ${p.id}: strip.y ${p.strip.y} overlaps the previous panel (ends at ${cursor})`);
      cursor = p.strip.y + p.strip.h + (p.strip.gutterAfter ?? 0);
    }
    if (cursor > layout.height) errors.push(`panels run to ${cursor} px but layout.height is ${layout.height}`);
  }
}

const targets = process.argv.slice(2);
if (!targets.length) {
  for (const d of readdirSync(path.join(here, "fixtures"))) {
    const dir = path.join(here, "fixtures", d);
    targets.push(readdirSync(dir).length > 1 ? dir : path.join(dir, "manifest.json"));
  }
}

let failed = 0;
for (const target of targets) {
  const errors = [];
  let m, files = null, how = "manifest only";
  if (target.endsWith(".zumi")) { files = zipFiles(target); how = "with its files"; }
  else if (statSync(target).isDirectory()) { files = folderFiles(target); how = "with its files"; }
  try {
    m = JSON.parse(files ? files.read("manifest.json").toString("utf8") : readFileSync(target, "utf8"));
    if (!validate(m)) errors.push(...validate.errors.map((e) => `${e.instancePath || "/"} ${e.message}`));
    check(m, files, errors);
  } catch (e) {
    errors.push(String(e.message ?? e));
  }
  files?.close();
  const rel = path.relative(process.cwd(), target);
  if (errors.length) {
    failed++;
    console.error(`✗ ${rel} (${how})\n${errors.slice(0, 60).map((e) => "    " + e).join("\n")}${errors.length > 60 ? `\n    ... ${errors.length - 60} more` : ""}`);
  } else {
    const anims = m.panels.reduce((n, p) => n + (p.animations?.length ?? 0), 0);
    console.log(`✓ ${rel} (${how}; format ${m.formatVersion}, ${m.panels.length} panels, ${m.cast.length} cast, ${anims} animations)`);
  }
}
process.exit(failed ? 1 : 0);
