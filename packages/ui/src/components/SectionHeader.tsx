import * as React from "react";
import { cn } from "../lib/cn";

export interface SectionHeaderProps extends React.HTMLAttributes<HTMLDivElement> {
  title: string;
  /** Sort or segment links rendered after the title. */
  children?: React.ReactNode;
  /** "All Wednesday series" link text. */
  more?: string;
  moreHref?: string;
}

/** Condensed display title, optional sort links, "More ›" on the right. */
export function SectionHeader({ title, children, more, moreHref, className, ...props }: SectionHeaderProps) {
  return (
    <div className={cn("flex items-baseline gap-4", className)} {...props}>
      <h2 className="font-display font-bold text-2xl tracking-[0.01em] text-text-default">{title}</h2>
      {children && <div className="flex gap-2.5 font-body text-sm text-text-dim">{children}</div>}
      {more && (
        <a href={moreHref ?? "#"} className="ml-auto font-body text-sm text-text-dim hover:text-accent">
          {more} <span aria-hidden>›</span>
        </a>
      )}
    </div>
  );
}
