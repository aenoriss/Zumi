import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../lib/cn";

const tag = cva("inline-flex items-center justify-center shrink-0 leading-none", {
  variants: {
    variant: {
      /** Round accent badge beside a title (Naver convention). */
      up: "size-[18px] rounded-pill bg-accent text-text-on-accent font-body font-extrabold text-[8px]",
      /** Dark square mark on a cover corner. */
      new: "h-[18px] px-1.5 rounded-container bg-text-default text-room-field font-display font-extrabold text-xs tracking-[0.06em] uppercase",
      /** Accent square mark on a cover corner. */
      mark: "h-[18px] px-1.5 rounded-container bg-accent text-text-on-accent font-display font-extrabold text-xs tracking-[0.06em] uppercase",
      /** Red release sticker. */
      alert: "h-[18px] px-2 rounded-pill bg-alert text-white font-body font-bold text-xs",
      /** Filter chip, quiet. */
      chip: "h-7 px-3 rounded-pill border border-hairline text-text-dim font-body text-sm",
      /** Filter chip, selected. */
      chipActive: "h-7 px-3 rounded-pill border border-accent bg-accent text-text-on-accent font-display font-bold text-md tracking-[0.05em]",
      /** Hashtag tile. */
      hash: "h-7 px-2.5 rounded-container bg-room-raised text-text-dim font-body text-sm",
    },
  },
  defaultVariants: { variant: "chip" },
});

export interface TagProps extends React.HTMLAttributes<HTMLSpanElement>, VariantProps<typeof tag> {}

export function Tag({ className, variant, ...props }: TagProps) {
  return <span className={cn(tag({ variant }), className)} {...props} />;
}
