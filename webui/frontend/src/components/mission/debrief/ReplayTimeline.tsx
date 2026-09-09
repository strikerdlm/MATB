"use client";
import React, { useEffect, useMemo, useState } from "react";
import type { DebriefView, Locale, JsonValue } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
export interface ReplayFrame {
  block_id?: string;
  simulation_time_ms: number;
  state_version: number;
  snapshot?: Record<string, JsonValue>;
  [key: string]: JsonValue | undefined;
}
export function framesFrom(debrief: DebriefView): ReplayFrame[] {
  if (!Array.isArray(debrief.frames)) return [];
  return debrief.frames.filter((raw): raw is Record<string, JsonValue> =>
    Boolean(
      raw &&
        typeof raw === "object" &&
        !Array.isArray(raw) &&
        typeof raw.simulation_time_ms === "number" &&
        typeof raw.state_version === "number",
    ),
  ) as ReplayFrame[];
}
export function ReplayTimeline({
  debrief,
  locale,
  onFrame,
}: {
  debrief: DebriefView;
  locale: Locale;
  onFrame?: (frame: ReplayFrame | null) => void;
}) {
  const all = useMemo(() => framesFrom(debrief), [debrief]);
  const blocks = useMemo(
    () => Array.from(new Set(all.map((frame) => frame.block_id ?? "LEGACY"))),
    [all],
  );
  const [block, setBlock] = useState(blocks[0] ?? "LEGACY"),
    [index, setIndex] = useState(0),
    [playing, setPlaying] = useState(false);
  const frames = useMemo(
    () =>
      all
        .filter((frame) => (frame.block_id ?? "LEGACY") === block)
        .sort((a, b) => a.simulation_time_ms - b.simulation_time_ms),
    [all, block],
  );
  const max = Math.max(0, frames.length - 1),
    frame = frames[index] ?? null;
  useEffect(() => {
    onFrame?.(frame);
  }, [frame, onFrame]);
  useEffect(() => {
    if (!playing || !frame) return;
    if (index >= max) {
      setPlaying(false);
      return;
    }
    const timer = window.setTimeout(
      () => setIndex((i) => Math.min(max, i + 1)),
      Math.max(
        1,
        frames[index + 1].simulation_time_ms - frame.simulation_time_ms,
      ),
    );
    return () => window.clearTimeout(timer);
  }, [playing, index, max, frame, frames]);
  const select = (value: number) => {
    setPlaying(false);
    setIndex(Math.max(0, Math.min(max, value)));
  };
  const seconds = Math.floor((frame?.simulation_time_ms ?? 0) / 1000);
  return (
    <section className="mission-panel p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2>{t(locale, "debrief.replay")}</h2>
        <label>
          {locale === "es-CO" ? "Bloque" : "Block"}{" "}
          <select
            className="bg-background"
            value={block}
            onChange={(e) => {
              setPlaying(false);
              setBlock(e.target.value);
              setIndex(0);
            }}
          >
            {blocks.map((id) => (
              <option key={id}>{id}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          disabled={!frames.length}
          onClick={() => {
            if (index === max) setIndex(0);
            setPlaying((v) => !v);
          }}
        >
          {playing
            ? locale === "es-CO"
              ? "Pausar"
              : "Pause"
            : locale === "es-CO"
              ? "Reproducir"
              : "Play"}
        </button>
        <span data-testid="replay-time">{`${Math.floor(seconds / 60)
          .toString()
          .padStart(
            2,
            "0",
          )}:${(seconds % 60).toString().padStart(2, "0")}`}</span>
      </div>
      <input
        type="range"
        className="mt-4 w-full"
        aria-label={t(locale, "debrief.replay_time")}
        min={0}
        max={max}
        value={index}
        disabled={!frames.length}
        onChange={(e) => select(Number(e.target.value))}
        onKeyDown={(e) => {
          if (e.key === "End") {
            e.preventDefault();
            select(max);
          }
          if (e.key === "Home") {
            e.preventDefault();
            select(0);
          }
        }}
      />
    </section>
  );
}
