import type { Meta, StoryObj } from "@storybook/react-vite";
import { ZumiOrb, MASCOT_HUES, type OrbMood } from "./ZumiOrb";

const MOODS: OrbMood[] = ["neutral", "happy", "wow", "laugh", "sleepy", "no", "think", "love"];

const meta = {
  title: "Components/Zumi orb",
  component: ZumiOrb,
  args: { hue: "orange", mood: "happy", size: 64, bob: true },
  argTypes: { hue: { control: "select", options: MASCOT_HUES }, mood: { control: "select", options: MOODS } },
} satisfies Meta<typeof ZumiOrb>;
export default meta;
type Story = StoryObj<typeof meta>;

export const Playground: Story = {};

export const Expressions: Story = {
  render: () => (
    <div className="flex flex-wrap gap-6 p-4">
      {MOODS.map((m, i) => (
        <div key={m} className="grid justify-items-center gap-2">
          <ZumiOrb mood={m} hue={MASCOT_HUES[i % MASCOT_HUES.length]} size={56} />
          <code className="font-body text-xs text-text-dim">{m}</code>
        </div>
      ))}
    </div>
  ),
};

export const Hues: Story = {
  render: () => (
    <div className="flex flex-wrap gap-4 p-4">
      {MASCOT_HUES.map((h) => (
        <ZumiOrb key={h} hue={h} mood="neutral" size={40} label={h} />
      ))}
    </div>
  ),
};
