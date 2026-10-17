import * as React from "react";
import { cn } from "../lib/cn";
import { Button } from "./Button";
import { LiveDot } from "./LiveDot";
import { ZumiOrb, type MascotHue } from "./ZumiOrb";

export interface RoomReader {
  id: string;
  hue: MascotHue;
  name?: string;
}

export interface RoomCardProps extends React.HTMLAttributes<HTMLElement> {
  title: string;
  src?: string;
  readers: RoomReader[];
  capacity?: number;
  panel: number;
  panelCount: number;
  /** "Started 4 min ago", "Almost full", "Looking for readers". */
  status: string;
  onJoin?: () => void;
}

/** A live reading room: cover, who is inside as Zumi orbs, progress, and the amber Join. */
export function RoomCard({ title, src, readers, capacity = 8, panel, panelCount, status, onJoin, className, ...props }: RoomCardProps) {
  return (
    <article className={cn("grid grid-cols-[56px_1fr] items-center gap-3 rounded-panel bg-room-raised p-2.5", className)} {...props}>
      <div className="relative overflow-hidden rounded-container border border-hairline bg-paper" style={{ aspectRatio: "1 / 1.19" }}>
        {src ? <img src={src} alt="" className="absolute inset-0 size-full object-cover" loading="lazy" /> : <div aria-hidden className="absolute inset-0 bg-[linear-gradient(160deg,var(--color-room-raised),var(--color-hairline-strong))]" />}
      </div>
      <div className="min-w-0">
        <b className="block truncate font-body font-bold text-[13.5px] text-text-default">{title}</b>
        <div className="mt-1.5 flex items-center gap-1.5">
          {readers.map((r) => (
            <ZumiOrb key={r.id} hue={r.hue} size={22} label={r.name ?? "Reader"} />
          ))}
          <small className="ml-1 font-body text-xs text-text-dim tabular-nums">
            {readers.length} / {capacity} · panel {panel} of {panelCount}
          </small>
        </div>
        <div className="mt-1.5 flex items-center justify-between gap-2">
          <LiveDot>{status}</LiveDot>
          <Button variant="cta" size="sm" onClick={onJoin}>
            Join
          </Button>
        </div>
      </div>
    </article>
  );
}
