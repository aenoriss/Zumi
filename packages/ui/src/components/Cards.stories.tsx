import type { Meta, StoryObj } from "@storybook/react-vite";
import { CoverCard } from "./CoverCard";
import { RankRow } from "./RankRow";
import { RoomCard } from "./RoomCard";
import { SectionHeader } from "./SectionHeader";

const meta = { title: "Components/Cards", parameters: { layout: "padded" } } satisfies Meta;
export default meta;

export const CoverRow: StoryObj = {
  render: () => (
    <div className="grid gap-4 p-4 max-w-[760px]">
      <SectionHeader title="Wednesday series" more="All Wednesday series">
        <span>Popular</span>
        <span>Updated</span>
        <b className="text-accent">Reading now</b>
        <span>Rating</span>
      </SectionHeader>
      <div className="grid grid-cols-5 gap-4">
        <CoverCard title="Winter Passing By" meta="Haeun" up mark={{ text: "NEW" }} sticker="Released today" readingNow={14} />
        <CoverCard title="Nanomachine" meta="Hyun Jeolmu · Han Jungwol" up readingNow={6} />
        <CoverCard title="Strongest Legend Kang Haehyo" meta="Choi Byungyeol" up />
        <CoverCard title="Kubera" meta="Currygom" up />
        <CoverCard title="Almost Forty" meta="Seokons" mark={{ text: "15+", variant: "mark" }} />
      </div>
    </div>
  ),
};

export const Ranking: StoryObj = {
  render: () => (
    <div className="grid gap-3 p-4 w-[300px]">
      <SectionHeader title="Reading now" />
      <RankRow rank={1} title="Starry Shop" meta="Heono · 14 in rooms" trend={2} />
      <RankRow rank={2} title="Nanomachine" meta="Hyun Jeolmu · 11" up trend={-1} />
      <RankRow rank={3} title="Return of the Mount Hua Sect" meta="ARCHE · LICO · 9" trend={5} />
      <RankRow rank={4} title="World Apocalypse Legend" meta="Punchkick · 8" up />
      <RankRow rank={5} title="Barbarian in the Game World" meta="Midnight Studio · 7" />
    </div>
  ),
};

export const Rooms: StoryObj = {
  render: () => (
    <div className="grid grid-cols-2 gap-3.5 p-4 max-w-[720px]">
      <RoomCard title="Winter Passing By · Ep. 7" readers={[{ id: "a", hue: "orange" }, { id: "b", hue: "sky" }, { id: "c", hue: "lime" }]} panel={12} panelCount={30} status="Started 4 min ago" />
      <RoomCard title="Nanomachine · Ep. 112" readers={[{ id: "a", hue: "lilac" }, { id: "b", hue: "coral" }]} panel={3} panelCount={41} status="Started just now" />
      <RoomCard title="Kubera · Ep. 530" readers={[{ id: "a", hue: "yellow" }, { id: "b", hue: "mint" }, { id: "c", hue: "pink" }, { id: "d", hue: "sky" }, { id: "e", hue: "orange" }, { id: "f", hue: "lime" }, { id: "g", hue: "coral" }]} panel={28} panelCount={36} status="Almost full" />
      <RoomCard title="Almost Forty · Ep. 1" readers={[{ id: "a", hue: "sky" }]} panel={1} panelCount={24} status="Looking for readers" />
    </div>
  ),
};
