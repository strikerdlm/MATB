"use client";

import React, { useState } from "react";
import type { IsaProbePayload, Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { Button } from "@/components/ui/button";

interface IsaProbeProps { locale: Locale; probe: IsaProbePayload; onSubmit: (rating: number) => void; pending?: boolean; }
export function IsaProbe({ locale, probe, onSubmit, pending = false }: IsaProbeProps) {
  const [value, setValue] = useState<number | null>(null);
  return <form onSubmit={(event) => { event.preventDefault(); if (value !== null) onSubmit(value); }} className="space-y-6"><p className="text-base leading-relaxed">{probe.question}</p><fieldset><legend className="mb-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Situation awareness / 1–10</legend><div className="grid grid-cols-5 gap-2 sm:grid-cols-10">{Array.from({ length: 10 }, (_, index) => index + 1).map((rating) => <label key={rating} className="cursor-pointer"><input type="radio" name="isa-rating" value={rating} checked={value === rating} onChange={() => setValue(rating)} className="peer sr-only" /><span className="grid h-11 place-items-center rounded border border-white/15 bg-black/20 font-mono text-sm peer-checked:border-white peer-checked:bg-white peer-checked:text-black peer-focus-visible:ring-2 peer-focus-visible:ring-white">{rating}</span></label>)}</div></fieldset><Button type="submit" disabled={value === null || pending}>{pending ? t(locale, "command.pending") : "Submit rating"}</Button></form>;
}
