"use client";

import React, { useMemo, useState } from "react";
import type { DebriefView, Locale, JsonValue } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";

export interface ReplayFrame {
  simulation_time_ms: number;
  state_version: number;
  snapshot?: Record<string, JsonValue>;
  [key: string]: JsonValue | undefined;
}

function framesFrom(debrief: DebriefView): ReplayFrame[] {
  const raw = debrief.frames;
  if (!Array.isArray(raw)) return [];
  const frames: ReplayFrame[] = [];
  for (const item of raw) {
    if (!item || typeof item !== "object" || Array.isArray(item)) continue;
    const candidate = item as Record<string, JsonValue>;
    if (typeof candidate.simulation_time_ms !== "number" || typeof candidate.state_version !== "number") continue;
    frames.push(item as unknown as ReplayFrame);
  }
  return frames.sort((left, right) => left.simulation_time_ms - right.simulation_time_ms);
}

interface ReplayTimelineProps { debrief: DebriefView; locale: Locale; onFrame?: (frame: ReplayFrame | null) => void; }
export function ReplayTimeline({ debrief, locale, onFrame }: ReplayTimelineProps) {
  const frames = useMemo(() => framesFrom(debrief), [debrief]);
  const [index, setIndex] = useState(0);
  const frame = frames[index] ?? null;
  const select = (value: number) => { const next = Math.max(0, Math.min(frames.length - 1, value)); setIndex(next); onFrame?.(frames[next] ?? null); };
  const elapsed = Math.max(0, Math.round((frame?.simulation_time_ms ?? 0) / 1000));
  const max = Math.max(0, frames.length - 1);
  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Home") { event.preventDefault(); select(0); }
    if (event.key === "End") { event.preventDefault(); select(max); }
    if (event.key === "ArrowRight") { event.preventDefault(); select(index + 1); }
    if (event.key === "ArrowLeft") { event.preventDefault(); select(index - 1); }
  };
  return <section aria-labelledby="replay-heading" className="mission-panel p-4"><div className="flex items-center justify-between gap-3"><div><div className="page-kicker">Replay</div><h2 id="replay-heading" className="font-display text-lg uppercase tracking-wide">{t(locale, "debrief.timeline")}</h2></div><span data-testid="replay-time" className="font-mono text-sm text-info">{`${Math.floor(elapsed / 60).toString().padStart(2, "0")}:${(elapsed % 60).toString().padStart(2, "0")}`}</span></div><div role="slider" tabIndex={frames.length ? 0 : -1} aria-label="Replay time" aria-valuemin={0} aria-valuemax={max} aria-valuenow={frames.length ? index : 0} onKeyDown={onKeyDown} onClick={() => select(index)} className="relative mt-4 h-3 w-full cursor-pointer rounded-full bg-white/10 outline-none focus-visible:ring-2 focus-visible:ring-white"><span className="absolute inset-y-0 left-0 rounded-full bg-info" style={{ width: `${max ? (index / max) * 100 : 0}%` }} /></div><div className="mt-2 flex justify-between font-mono text-[10px] uppercase text-muted-foreground"><span>Start</span><span>{frame ? `State ${frame.state_version}` : "No sealed frames"}</span><span>End</span></div></section>;
}

export { framesFrom };
