"use client";

import React from "react";

import { formatTimelineTime } from "@/lib/experiment-designer";
import { cn } from "@/lib/utils";
import type { ExperimentTimelineEvent } from "@/types";
import { useAppLocale } from "@/lib/i18n";

const ROWS = [
  { task: "sysmon", label: "SYSMON" },
  { task: "communications", label: "COMM" },
  { task: "track", label: "TRACK" },
  { task: "resman", label: "RESMAN" },
  { task: "genericscales", label: "PROBES" },
  { task: "automation", label: "AUTOMATION" },
] as const;

const TASK_STYLES: Record<string, string> = {
  sysmon: "border-success/70 bg-success/10 text-success",
  communications: "border-info/70 bg-info/10 text-info",
  track: "border-white/40 bg-white/[0.06] text-white",
  resman: "border-warning/70 bg-warning/10 text-warning",
  genericscales: "border-info/60 bg-info/[0.07] text-info",
  automation: "border-danger/70 bg-danger/10 text-danger",
};

interface ExperimentTimelineProps {
  events: ExperimentTimelineEvent[];
  durationSeconds: number;
  selectedKey: string | null;
  onSelect: (eventKey: string) => void;
}

export function ExperimentTimeline({
  events,
  durationSeconds,
  selectedKey,
  onSelect,
}: ExperimentTimelineProps) {
  const { copy } = useAppLocale();
  const tickCount = 6;
  const ticks = Array.from({ length: tickCount + 1 }, (_, index) => (
    Math.round((durationSeconds / tickCount) * index)
  ));

  return (
    <section className="overflow-hidden border border-white/15 bg-black/30" aria-label={copy("Línea de tiempo del experimento", "Experiment timeline")}>
      <div className="overflow-x-auto">
        <div className="min-w-[58rem]">
          <div className="grid grid-cols-[8.5rem_minmax(45rem,1fr)] border-b border-white/15 bg-white/[0.025]">
            <div className="border-r border-white/15 px-4 py-3 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              {copy("Tareas", "Tasks")}
            </div>
            <div className="relative h-14">
              <span className="absolute left-3 top-2 font-mono text-[10px] uppercase tracking-[0.15em] text-muted-foreground">
                {copy("Tiempo mm:ss", "Time mm:ss")}
              </span>
              {ticks.map((tick, index) => (
                <span
                  key={tick}
                  className="absolute bottom-2 -translate-x-1/2 font-mono text-[10px] text-muted-foreground"
                  style={{ left: `${(index / tickCount) * 100}%` }}
                >
                  {formatTimelineTime(tick)}
                </span>
              ))}
            </div>
          </div>

          {ROWS.map(({ task, label }) => {
            const rowEvents = events.filter((event) => event.task === task);
            return (
              <div
                key={task}
                className="grid min-h-20 grid-cols-[8.5rem_minmax(45rem,1fr)] border-b border-white/10 last:border-b-0"
              >
                <div className="flex items-center border-r border-white/15 px-4 font-display text-sm font-semibold tracking-[0.08em]">
                  {label}
                </div>
                <div
                  className="relative bg-[repeating-linear-gradient(90deg,transparent_0,transparent_calc(10%_-_1px),rgb(255_255_255/0.06)_10%)]"
                >
                  {rowEvents.length === 0 ? (
                    <p className="absolute inset-0 flex items-center px-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground/50">
                      {copy("Sin eventos asignados", "No events assigned")}
                    </p>
                  ) : null}
                  {rowEvents.map((event) => {
                    const left = Math.min(99, Math.max(0, (event.atSeconds / durationSeconds) * 100));
                    const rawWidth = event.durationSeconds === null
                      ? 1.1
                      : (event.durationSeconds / durationSeconds) * 100;
                    const width = Math.max(1.1, Math.min(100 - left, rawWidth));
                    return (
                      <button
                        key={event.eventKey}
                        type="button"
                        onClick={() => onSelect(event.eventKey)}
                        aria-pressed={selectedKey === event.eventKey}
                        className={cn(
                          "absolute top-3 h-14 overflow-hidden border px-2 text-left font-mono text-[10px] transition",
                          "focus-visible:z-20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white",
                          TASK_STYLES[task],
                          selectedKey === event.eventKey
                            ? "z-10 border-white text-white shadow-[0_0_0_1px_rgb(255_255_255/0.6)]"
                            : "hover:border-white/70",
                        )}
                        style={{ left: `${left}%`, width: `${width}%`, minWidth: "1rem" }}
                        title={`${event.command} · ${copy("en", "at")} ${formatTimelineTime(event.atSeconds)}`}
                      >
                        <span className="block truncate font-semibold">{event.command}</span>
                        <span className="mt-1 block truncate opacity-75">
                          {formatTimelineTime(event.atSeconds)}
                          {event.durationSeconds !== null
                            ? `–${formatTimelineTime(event.atSeconds + event.durationSeconds)}`
                            : ""}
                        </span>
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
