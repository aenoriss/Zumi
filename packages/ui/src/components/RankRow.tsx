import * as React from "react";
import { cn } from "../lib/cn";
import { Tag } from "./Tag";

export interface RankRowProps extends React.HTMLAttributes<HTMLElement> {
  rank: number;
  title: string;
  meta?: string;
  src?: string;
  up?: boolean;
  /** Positive = climbed, negative = fell. */
  trend?: number;
  href?: string;
}

/** Right-rail ranking row: square thumb, big display numeral, title with UP, meta, trend arrow. */
export function RankRow({ rank, title, meta, src, up, trend, href, className, ...props }: RankRowProps) {
  const Root: any = href ? "a" : "div";
  return (
    <Root href={href} className={cn("grid grid-cols-[48px_24px_1fr] items-center gap-2.5 min-w-0", className)} {...props}>
      <div className="relative aspect-square overflow-hidden rounded-container border border-hairline bg-paper">
        {src ? <img src={src} alt="" className="absolute inset-0 size-full object-cover" loading="lazy" /> : <div aria-hidden className="absolute inset-0 bg-[linear-gradient(160deg,var(--color-room-raised),var(--color-hairline-strong))]" />}
      </div>
      <span className="font-display font-extrabold text-2xl text-center text-text-default tabular-nums">{rank}</span>
      <span className="min-w-0">
        <span className="flex items-center gap-1.5 min-w-0">
          {up && <Tag variant="up">UP</Tag>}
          <b className="truncate font-body font-bold text-md text-text-default">{title}</b>
          {trend != null && trend !== 0 && (
            <span className={cn("shrink-0 font-body font-bold text-[10px] tabular-nums", trend > 0 ? "text-accent" : "text-text-dim")}>
              {trend > 0 ? "▲" : "▼"} {Math.abs(trend)}
            </span>
          )}
        </span>
        {meta && <small className="block truncate font-body text-xs text-text-dim">{meta}</small>}
      </span>
    </Root>
  );
}
