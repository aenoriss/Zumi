import * as React from "react";
import { cn } from "../lib/cn";

export const MASCOT_HUES = ["orange", "sky", "lime", "coral", "lilac", "yellow", "mint", "pink"] as const;
export type MascotHue = (typeof MASCOT_HUES)[number];

/** Expression set, 1:1 with the emote set. The same `mood` parameter drives the Unity orb. */
export type OrbMood = "neutral" | "happy" | "wow" | "laugh" | "sleepy" | "no" | "think" | "love";

export interface ZumiOrbProps extends React.HTMLAttributes<HTMLSpanElement> {
  hue?: MascotHue;
  mood?: OrbMood;
  /** Diameter in px. */
  size?: number;
  /** Float loop on; off by default inside lists. */
  bob?: boolean;
  /** Accessible name, e.g. the reader's display name. */
  label?: string;
}

const mouth: Record<OrbMood, React.CSSProperties> = {
  neutral: { left: "36%", top: "60%", width: "28%", height: "14%", borderRadius: "0 0 1em 1em" },
  happy: { left: "34%", top: "58%", width: "32%", height: "20%", borderRadius: "0 0 1em 1em" },
  wow: { left: "41%", top: "58%", width: "18%", height: "22%", borderRadius: "50%" },
  laugh: { left: "32%", top: "56%", width: "36%", height: "24%", borderRadius: "0 0 1.2em 1.2em" },
  sleepy: { left: "40%", top: "64%", width: "20%", height: "6%", borderRadius: "1em" },
  no: { left: "36%", top: "66%", width: "28%", height: "6%", borderRadius: "1em" },
  think: { left: "42%", top: "64%", width: "18%", height: "6%", borderRadius: "1em", transform: "rotate(-12deg)" },
  love: { left: "34%", top: "58%", width: "32%", height: "20%", borderRadius: "0 0 1em 1em" },
};

const eyes: Record<OrbMood, React.CSSProperties> = {
  neutral: { height: "18%" },
  happy: { height: "12%", borderRadius: "1em 1em 0 0" },
  wow: { height: "24%", width: "16%" },
  laugh: { height: "8%", borderRadius: "1em 1em 0 0" },
  sleepy: { height: "5%", borderRadius: "1em" },
  no: { height: "10%", transform: "rotate(14deg)" },
  think: { height: "14%", transform: "translateY(-6%)" },
  love: { height: "18%", borderRadius: "50%" },
};

/** Zumi, the reader mascot: one flat sphere, a face driven by `mood`, a hue per reader, a lamp-coloured glow. */
export function ZumiOrb({ hue = "orange", mood = "neutral", size = 40, bob = false, label, className, style, ...props }: ZumiOrbProps) {
  return (
    <span
      role="img"
      aria-label={label ?? `Zumi, ${mood}`}
      className={cn("relative inline-block shrink-0 rounded-pill", bob && "motion-signal animate-[zumi-bob_var(--motion-duration-bob)_ease-in-out_infinite]", className)}
      style={{ width: size, height: size, fontSize: size, background: `var(--color-mascot-${hue})`, boxShadow: "0 0 0.45em var(--color-accent-glow)", ...style }}
      {...props}
    >
      <span aria-hidden className="absolute bg-[#1a1410]" style={{ left: "26%", top: "32%", width: "14%", borderRadius: "50%", ...eyes[mood] }} />
      <span aria-hidden className="absolute bg-[#1a1410]" style={{ left: "60%", top: "32%", width: "14%", borderRadius: "50%", ...eyes[mood] }} />
      <span aria-hidden className="absolute bg-[#1a1410]" style={mouth[mood]} />
    </span>
  );
}
