"use client";

import React from "react";
import type { DebriefView, JsonValue, Locale } from "@/types/simulation";

interface ResearchSummaryProps { debrief: DebriefView; locale: Locale; }
function objectValue(value: JsonValue | undefined): Record<string, JsonValue> { return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, JsonValue> : {}; }
export function ResearchSummary({ debrief }: ResearchSummaryProps) {
  const metrics = objectValue(debrief.metrics);
  const isa = objectValue(metrics.isa);
  const sagat = objectValue(metrics.sagat);
  const tlx = objectValue(metrics.nasa_tlx);
  const bedford = objectValue(metrics.bedford);
  return <section aria-labelledby="research-heading" className="mission-panel p-4"><div className="page-kicker">Research protocol</div><h2 id="research-heading" className="mt-1 font-display text-xl uppercase tracking-wide">Measures and provenance</h2><dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4"><div className="metric-tile"><dt className="font-mono text-[10px] uppercase text-muted-foreground">ISA</dt><dd className="mt-1 font-semibold">{String(isa.mean ?? "—")}</dd></div><div className="metric-tile"><dt className="font-mono text-[10px] uppercase text-muted-foreground">SAGAT</dt><dd className="mt-1 font-semibold">{String(sagat.accuracy ?? "—")}</dd><small className="text-muted-foreground">{String(sagat.correct ?? 0)} / {String(sagat.total ?? 0)}</small></div><div className="metric-tile"><dt className="font-mono text-[10px] uppercase text-muted-foreground">NASA-TLX</dt><dd className="mt-1 font-semibold">{String(tlx.raw_tlx ?? "—")}</dd></div><div className="metric-tile"><dt className="font-mono text-[10px] uppercase text-muted-foreground">Bedford</dt><dd className="mt-1 font-semibold">{String(bedford.value ?? "—")}</dd></div></dl><div className="mt-4 border-t border-white/10 pt-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Replay checksums are retained with the sealed artifact provenance.</div></section>;
}
