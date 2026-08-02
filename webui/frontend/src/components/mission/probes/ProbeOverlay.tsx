"use client";

import React, { useEffect, useRef, useState } from "react";
import type { ActiveProbePayload, Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { IsaProbe } from "./IsaProbe";
import { PostBlockScales, type PostBlockScaleValues } from "./PostBlockScales";
import { SagatFreeze } from "./SagatFreeze";

interface ProbeOverlayProps { locale: Locale; probe: ActiveProbePayload; onIsa: (rating: number) => void; onSagat: (answer: string) => void; onPostBlock: (values: PostBlockScaleValues) => void; pending?: boolean; }
export function ProbeOverlay({ locale, probe, onIsa, onSagat, onPostBlock, pending = false }: ProbeOverlayProps) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const previousFocus = useRef<HTMLElement | null>(null);
  const [remaining, setRemaining] = useState<number | null>(() => "timeout_ms" in probe ? Math.ceil(probe.timeout_ms / 1000) : null);
  useEffect(() => { previousFocus.current = document.activeElement as HTMLElement | null; dialogRef.current?.focus(); return () => { previousFocus.current?.focus?.(); }; }, [probe]);
  useEffect(() => { if (remaining === null || remaining <= 0) return; const timer = window.setInterval(() => setRemaining((value) => value === null ? null : Math.max(0, value - 1)), 1000); return () => window.clearInterval(timer); }, [remaining]);
  const isSagat = probe.kind === "SAGAT";
  return <div ref={dialogRef} tabIndex={-1} className="fixed inset-0 z-50 grid place-items-center bg-black/90 p-4 backdrop-blur-sm" role="dialog" aria-modal="true" aria-labelledby="probe-heading"><div className={`mission-panel w-full max-w-2xl p-6 sm:p-8 ${isSagat ? "border-warning/50" : "border-info/40"}`}><div className="flex items-start justify-between gap-4"><div><div className="page-kicker">{isSagat ? "SAGAT / operational state concealed" : probe.kind === "ISA" ? "ISA / response required" : "Post-block measures"}</div><h2 id="probe-heading" ref={headingRef} tabIndex={-1} className="mt-2 font-display text-2xl uppercase tracking-wide">{isSagat ? "Situation awareness" : probe.kind === "ISA" ? "Situation awareness" : t(locale, "post_block.title")}</h2></div>{remaining !== null && <div className="font-mono text-sm text-warning" aria-live="polite">{remaining}s</div>}</div><div className="mt-6">{probe.kind === "ISA" && <IsaProbe locale={locale} probe={probe} onSubmit={onIsa} pending={pending} />}{probe.kind === "SAGAT" && <SagatFreeze locale={locale} probe={probe} onSubmit={onSagat} pending={pending} />}{probe.kind === "POST_BLOCK" && <PostBlockScales locale={locale} onSubmit={onPostBlock} pending={pending} />}</div></div></div>;
}
