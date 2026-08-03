"use client";

import React from "react";
import type { DebriefView, JsonValue, Locale } from "@/types/simulation";

interface OutcomeCardsProps { debrief: DebriefView; locale: Locale; }
const labels = ["Coverage", "Contacts", "Assets", "Timeliness"] as const;
function displayValue(value: JsonValue | undefined): string { if (typeof value === "number") return value.toLocaleString(); if (typeof value === "string") return value; return "—"; }
export function OutcomeCards({ debrief }: OutcomeCardsProps) {
  const metrics = debrief.metrics && typeof debrief.metrics === "object" && !Array.isArray(debrief.metrics) ? debrief.metrics as Record<string, JsonValue> : {};
  return <section aria-labelledby="outcomes-heading" className="space-y-3"><div className="page-kicker">Outcome model</div><h2 id="outcomes-heading" className="font-display text-xl uppercase tracking-wide">Component outcomes</h2><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{labels.map((label) => <article key={label} className="metric-tile"><div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{label}</div><div className="mt-2 font-display text-2xl">{displayValue(metrics[label.toLowerCase()])}</div></article>)}</div><p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Composite is descriptive feedback only; component values remain first-class research outputs.</p></section>;
}
