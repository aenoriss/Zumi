/* Copies the page and the built token CSS into dist/. Deploy dist/ to Vercel or GitHub Pages. */
import { cp, mkdir, access } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const here = path.dirname(fileURLToPath(import.meta.url));
const dist = path.join(here, "dist");
const tokensCss = path.resolve(here, "../../packages/design-tokens/dist/css/tokens.css");

await access(tokensCss).catch(() => {
  throw new Error("tokens.css not built. Run `pnpm tokens` first.");
});
await mkdir(path.join(dist, "assets"), { recursive: true });
await cp(path.join(here, "src"), dist, { recursive: true });
await cp(tokensCss, path.join(dist, "tokens.css"));
console.log("landing -> apps/landing/dist");
