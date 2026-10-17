import type { Meta, StoryObj } from "@storybook/react-vite";

const meta = { title: "Tokens/Type and space", parameters: { layout: "padded" } } satisfies Meta;
export default meta;

const sizes = ["xs", "sm", "md", "lg", "xl", "2xl", "3xl", "4xl", "numeral"] as const;
const spaces = [1, 2, 3, 4, 5, 6, 7, 8] as const;
const radii = ["container", "panel", "control", "bubble", "pill"] as const;

export const Type: StoryObj = {
  render: () => (
    <div className="grid gap-6 p-4">
      <h1 className="font-display font-extrabold text-4xl uppercase tracking-[0.01em]">Wednesday series · Barlow Condensed 800</h1>
      <h2 className="font-display font-bold text-2xl tracking-[0.01em]">Reading now · Barlow Condensed 700</h2>
      <p className="font-body text-md max-w-[64ch]">Body · Noto Sans 13. Ren finally opens the door. The city behind it is not the one he left.</p>
      <p className="font-body text-sm text-text-dim">Meta · Noto Sans 12 · Haeun · Ep. 7 · 2h ago</p>
      <p className="font-body text-md" style={{ fontFamily: '"Noto Sans KR", sans-serif' }}>한국어 · Noto Sans KR 13 · 오늘 밤 같이 읽어요</p>
      <div className="grid gap-2 mt-4">
        {sizes.map((s) => (
          <div key={s} className="flex items-baseline gap-4">
            <code className="w-20 font-body text-xs text-text-dim">text-{s}</code>
            <span className={`font-display font-bold text-${s} leading-none`}>Zumi {s}</span>
          </div>
        ))}
      </div>
    </div>
  ),
};

export const Space: StoryObj = {
  render: () => (
    <div className="grid gap-3 p-4">
      {spaces.map((s) => (
        <div key={s} className="flex items-center gap-4">
          <code className="w-16 font-body text-xs text-text-dim">space-{s}</code>
          <div className="h-4 bg-accent rounded-container" style={{ width: `var(--space-${s})` }} />
        </div>
      ))}
      <h3 className="font-display font-bold text-xl mt-6 uppercase">Radius</h3>
      <div className="flex gap-4">
        {radii.map((r) => (
          <div key={r} className="grid gap-1.5 justify-items-center">
            <div className={`size-16 bg-room-raised border border-hairline-strong rounded-${r}`} />
            <code className="font-body text-xs text-text-dim">{r}</code>
          </div>
        ))}
      </div>
    </div>
  ),
};
