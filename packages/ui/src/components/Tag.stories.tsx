import type { Meta, StoryObj } from "@storybook/react-vite";
import { Tag } from "./Tag";

const meta = { title: "Components/Tag", component: Tag } satisfies Meta<typeof Tag>;
export default meta;
type Story = StoryObj<typeof meta>;

export const All: Story = {
  render: () => (
    <div className="flex flex-wrap items-center gap-3 p-4">
      <Tag variant="up">UP</Tag>
      <Tag variant="new">NEW</Tag>
      <Tag variant="mark">15+</Tag>
      <Tag variant="alert">Released today</Tag>
      <Tag variant="chip">Mon</Tag>
      <Tag variant="chipActive">Wed</Tag>
      <Tag variant="hash">#slice-of-life</Tag>
    </div>
  ),
};
