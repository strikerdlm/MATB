"use client";

import React, { useState } from "react";
import type { Locale, SagatProbePayload } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { Button } from "@/components/ui/button";

interface SagatFreezeProps { locale: Locale; probe: SagatProbePayload; onSubmit: (answer: string) => void; pending?: boolean; }
export function SagatFreeze({ locale, probe, onSubmit, pending = false }: SagatFreezeProps) {
  const [answer, setAnswer] = useState<string | null>(null);
  return <form onSubmit={(event) => { event.preventDefault(); if (answer !== null) onSubmit(answer); }} className="space-y-6"><p className="text-base leading-relaxed">{probe.question}</p><fieldset><legend className="mb-3 font-mono text-[10px] uppercase tracking-wider text-warning">{t(locale, "probe.sa_level", { level: probe.sa_level, domain: probe.domain })}</legend><div className="grid gap-2">{probe.options.map((option) => <label key={option} className="cursor-pointer"><input type="radio" name="sagat-answer" value={option} checked={answer === option} onChange={() => setAnswer(option)} className="peer sr-only" /><span className="block rounded border border-white/15 bg-black/20 px-4 py-3 text-sm peer-checked:border-white peer-checked:bg-white peer-checked:text-black peer-focus-visible:ring-2 peer-focus-visible:ring-white">{option}</span></label>)}</div></fieldset><Button type="submit" disabled={answer === null || pending}>{pending ? t(locale, "command.pending") : t(locale, "probe.answer")}</Button></form>;
}
