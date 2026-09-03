"use client";

import React from "react";
import type { DebriefView, JsonValue, Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";

interface OutcomeCardsProps { debrief: DebriefView; locale: Locale; }
const outcomes = [
  ["coverage", "debrief.coverage"],
  ["contacts", "debrief.contacts"],
  ["assets", "debrief.assets"],
  ["timeliness", "debrief.timeliness"],
] as const;
function displayValue(value: JsonValue | undefined): string { if (typeof value === "number") return value.toLocaleString(); if (typeof value === "string") return value; return "—"; }
export function OutcomeCards({ debrief, locale }: OutcomeCardsProps) {
  const metrics = debrief.metrics && typeof debrief.metrics === "object" && !Array.isArray(debrief.metrics) ? debrief.metrics as Record<string, JsonValue> : {};
  return <section aria-labelledby="outcomes-heading" className="space-y-3"><div className="page-kicker">{t(locale, "debrief.outcome_model")}</div><h2 id="outcomes-heading" className="font-display text-xl uppercase tracking-wide">{t(locale, "debrief.component_outcomes")}</h2><div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{outcomes.map(([metric, label]) => <article key={metric} className="metric-tile"><div className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{t(locale, label)}</div><div className="mt-2 font-display text-2xl">{displayValue(metrics[metric])}</div></article>)}</div><p className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{t(locale, "debrief.composite_notice")}</p></section>;
}
