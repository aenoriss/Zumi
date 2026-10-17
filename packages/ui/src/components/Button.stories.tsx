import type { Meta, StoryObj } from "@storybook/react-vite";
import { Button } from "./Button";

const meta = {
  title: "Components/Button",
  component: Button,
  args: { children: "Enter", variant: "cta", size: "md" },
  argTypes: {
    variant: { control: "radio", options: ["cta", "accent", "ghost", "link"] },
    size: { control: "radio", options: ["sm", "md", "lg"] },
  },
} satisfies Meta<typeof Button>;
export default meta;
type Story = StoryObj<typeof meta>;

export const CTA: Story = {};
export const Accent: Story = { args: { variant: "accent", children: "Read together" } };
export const Ghost: Story = { args: { variant: "ghost", children: "Log in" } };
export const Link: Story = { args: { variant: "link", children: "See all" } };
export const Disabled: Story = { args: { disabled: true } };

export const AllVariants: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3 p-4">
      <Button variant="cta">Enter</Button>
      <Button variant="cta" size="sm">Join</Button>
      <Button variant="accent">Read together</Button>
      <Button variant="ghost">Log in</Button>
      <Button variant="link">See all</Button>
    </div>
  ),
};
