import type { Meta, StoryObj } from "@storybook/react-vite";
import manifest from "@zumi/design-tokens/manifest";

type Token = { name: string; path: string; type: string; value: unknown; tier: "primitive" | "semantic"; description: string | null; ref: string | null };
const paper = manifest.paper as Token[];
const midnight = manifest.midnight as Token[];
const byPath = (list: Token[]) => Object.fromEntries(list.map((t) => [t.path, t]));
const mid = byPath(midnight);

function Swatch({ t }: { t: Token }) {
  const m = mid[t.path];
  return (
    <div className="grid gap-1.5 min-w-0">
      <div className="h-16 rounded-container border border-hairline-strong" style={{ background: `var(--${t.name})` }} />
      <b className="truncate font-body text-sm text-text-default">{t.path}</b>
      <small className="font-body text-xs text-text-dim tabular-nums">
        {String(t.value)}
        {m && m.value !== t.value ? ` / ${String(m.value)}` : ""}
      </small>
      {t.ref && <small className="truncate font-body text-xs text-text-faint">→ {t.ref}</small>}
      {t.description && <small className="font-body text-xs text-text-dim leading-snug">{t.description}</small>}
    </div>
  );
}

function Group({ title, tokens, cols = 6 }: { title: string; tokens: Token[]; cols?: number }) {
  if (!tokens.length) return null;
  return (
    <section className="grid gap-3">
      <h3 className="font-display font-bold text-xl uppercase tracking-[0.02em] text-text-default">{title}</h3>
      <div className="grid gap-4" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {tokens.map((t) => (
          <Swatch key={t.path} t={t} />
        ))}
      </div>
    </section>
  );
}

const colors = paper.filter((t) => t.type === "color");
const sem = colors.filter((t) => t.tier === "semantic");
const prim = colors.filter((t) => t.tier === "primitive");
const pick = (prefix: string, list = prim) => list.filter((t) => t.path.startsWith(prefix));

const meta = {
  title: "Tokens/Colour",
  parameters: { layout: "padded" },
} satisfies Meta;
export default meta;

export const Semantic: StoryObj = {
  name: "Semantic (both themes)",
  render: () => (
    <div className="grid gap-8 p-4">
      <p className="font-body text-sm text-text-dim max-w-[64ch]">
        Values shown as Paper / Midnight. Switch the theme in the toolbar to see the swatches change. Components only use these; primitives are for the token files.
      </p>
      <Group title="Room" tokens={sem.filter((t) => /^color\.(room|paper|hairline)/.test(t.path))} cols={5} />
      <Group title="Text" tokens={sem.filter((t) => t.path.startsWith("color.text"))} cols={5} />
      <Group title="Accent, CTA, signals" tokens={sem.filter((t) => /^color\.(accent|cta|alert|wood)/.test(t.path))} cols={5} />
    </div>
  ),
};

export const Primitives: StoryObj = {
  render: () => (
    <div className="grid gap-8 p-4">
      <Group title="Cream" tokens={pick("color.cream")} />
      <Group title="Ink" tokens={pick("color.ink")} />
      <Group title="Night" tokens={pick("color.night")} cols={7} />
      <Group title="Brown, amber, brass, red" tokens={[...pick("color.brown"), ...pick("color.amber"), ...pick("color.brass"), ...pick("color.red")]} />
      <Group title="Mascot hues" tokens={pick("color.mascot")} cols={8} />
    </div>
  ),
};
