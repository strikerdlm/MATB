"use client";

import React, { useMemo, useState } from "react";
import type { Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { Button } from "@/components/ui/button";

export interface PostBlockScaleValues { nasa_tlx: Record<string, number>; bedford: number | null; }
interface PostBlockScalesProps { locale: Locale; onSubmit: (values: PostBlockScaleValues) => void; pending?: boolean; }
const TLX = ["mental_demand", "physical_demand", "temporal_demand", "performance", "effort", "frustration"] as const;
export function PostBlockScales({ locale, onSubmit, pending = false }: PostBlockScalesProps) {
  const [tlx, setTlx] = useState<Partial<Record<(typeof TLX)[number], number>>>({});
  const [bedford, setBedford] = useState<number | null>(null);
  const complete = useMemo(() => TLX.every((key) => typeof tlx[key] === "number") && bedford !== null, [bedford, tlx]);
  return <form onSubmit={(event) => { event.preventDefault(); if (complete) onSubmit({ nasa_tlx: tlx as Record<string, number>, bedford }); }} className="space-y-5"><div className="grid gap-3 sm:grid-cols-2">{TLX.map((key) => <label key={key} className="space-y-1"><span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{key.replaceAll("_", " ")}</span><input aria-label={key.replaceAll("_", " ")} type="range" min={0} max={10} step={1} value={tlx[key] ?? 0} onChange={(event) => setTlx((current) => ({ ...current, [key]: Number(event.target.value) }))} className="w-full accent-white" /><span className="font-mono text-xs">{tlx[key] ?? "—"}</span></label>)}</div><label className="block space-y-1"><span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">{t(locale, "post_block.bedford")}</span><input aria-label="Bedford" type="range" min={1} max={10} step={1} value={bedford ?? 1} onChange={(event) => setBedford(Number(event.target.value))} className="w-full accent-white" /><span className="font-mono text-xs">{bedford ?? "—"}</span></label><Button type="submit" disabled={!complete || pending}>{pending ? t(locale, "command.pending") : t(locale, "post_block.submit")}</Button></form>;
}
