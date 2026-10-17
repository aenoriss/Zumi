import * as React from "react";
import { cn } from "../lib/cn";
import { Tag } from "./Tag";
import { LiveDot } from "./LiveDot";

export interface CoverCardProps extends React.HTMLAttributes<HTMLElement> {
  title: string;
  /** Author or "Ep. 7 · 2h ago". */
  meta?: string;
  /** Cover image URL. Falls back to a paper placeholder. */
  src?: string;
  alt?: string;
  /** Height/width ratio. Home rows use 1.19 (Naver), rails use 1, episode lists 1.5. */
  ratio?: 1 | 1.19 | 1.5;
  /** Round accent badge beside the title. */
  up?: boolean;
  /** Corner mark on the cover: NEW, 15+, etc. */
  mark?: { text: string; variant?: "new" | "mark" };
  /** Red release sticker on the cover's right edge. */
  sticker?: string;
  /** "14 reading now" live line above the title. */
  readingNow?: number;
  href?: string;
}

export function CoverCard({ title, meta, src, alt = "", ratio = 1.19, up, mark, sticker, readingNow, href, className, ...props }: CoverCardProps) {
  const Root: any = href ? "a" : "article";
  return (
    <Root href={href} className={cn("group grid gap-1.5 min-w-0", className)} {...props}>
      <div
        className="relative overflow-hidden rounded-container border border-hairline bg-paper transition-shadow duration-base ease-standard group-hover:shadow-[0_0_0_1px_var(--color-accent-default),0_0_20px_var(--color-accent-glow)]"
        style={{ aspectRatio: `1 / ${ratio}` }}
      >
        {src ? <img src={src} alt={alt} className="absolute inset-0 size-full object-cover" loading="lazy" /> : <div aria-hidden className="absolute inset-0 bg-[linear-gradient(160deg,var(--color-room-raised),var(--color-hairline-strong))]" />}
        {mark && <Tag variant={mark.variant ?? "new"} className="absolute left-1.5 top-1.5">{mark.text}</Tag>}
        {sticker && <Tag variant="alert" className="absolute right-0 top-2.5 rounded-r-none pl-2.5">{sticker}</Tag>}
      </div>
      {readingNow != null && <LiveDot>{readingNow} reading now</LiveDot>}
      <div className="flex items-center gap-1.5 min-w-0">
        {up && <Tag variant="up">UP</Tag>}
        <b className="truncate font-body font-bold text-[13.5px] text-text-default">{title}</b>
      </div>
      {meta && <small className="truncate font-body text-sm text-text-dim">{meta}</small>}
    </Root>
  );
}
