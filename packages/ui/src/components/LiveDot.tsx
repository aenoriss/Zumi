import * as React from "react";
import { cn } from "../lib/cn";

export interface LiveDotProps extends React.HTMLAttributes<HTMLSpanElement> {
  /** Text after the dot, e.g. "14 reading now". */
  children?: React.ReactNode;
}

/** A breathing accent dot: the signal that someone is here. One of the few things allowed to animate. */
export function LiveDot({ className, children, ...props }: LiveDotProps) {
  return (
    <span className={cn("inline-flex items-center gap-1.5 text-accent font-body font-bold text-xs", className)} {...props}>
      <i aria-hidden className="motion-signal block size-1.5 rounded-pill bg-accent animate-[zumi-pulse_var(--motion-duration-pulse)_ease-in-out_infinite]" />
      {children}
    </span>
  );
}
