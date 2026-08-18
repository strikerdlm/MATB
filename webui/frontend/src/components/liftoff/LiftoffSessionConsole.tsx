"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { getLiftoffReadiness, getLiftoffSession, transitionLiftoff } from "@/lib/liftoff/api";
import type { LiftoffAction, LiftoffReadiness, LiftoffSessionView } from "@/types/liftoff";

const STEPS: Array<{ action: LiftoffAction; label: string; phase: string }> = [
  { action: "baseline/start", label: "Start baseline", phase: "Baseline" },
  { action: "baseline/finish", label: "Finish baseline", phase: "Baseline" },
  { action: "task/start", label: "Start FPV task", phase: "FPV task" },
  { action: "task/finish", label: "Finish FPV task", phase: "FPV task" },
  { action: "recovery/start", label: "Start recovery", phase: "Recovery" },
  { action: "recovery/finish", label: "Finish recovery", phase: "Recovery" },
];

export function LiftoffSessionConsole({ sessionId }: { sessionId: string }) {
  const router = useRouter();
  const [session, setSession] = useState<LiftoffSessionView | null>(null);
  const [readiness, setReadiness] = useState<LiftoffReadiness | null>(null);
  const [stepIndex, setStepIndex] = useState(0);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const lease = typeof window === "undefined" ? null : sessionStorage.getItem(`matb.liftoff.${sessionId}.lease`);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const [sessionView, receiverView] = await Promise.all([
          getLiftoffSession(sessionId),
          getLiftoffReadiness(),
        ]);
        if (active) { setSession(sessionView); setReadiness(receiverView); }
      } catch (reason: unknown) {
        if (active) setError(reason instanceof Error ? reason.message : "Session state could not be read.");
      }
    };
    void refresh();
    const poll = window.setInterval(() => void refresh(), 1_000);
    const clock = window.setInterval(() => setElapsed((value) => value + 1), 1_000);
    return () => { active = false; window.clearInterval(poll); window.clearInterval(clock); };
  }, [sessionId]);

  const next = STEPS[stepIndex] ?? null;
  const phaseIndex = useMemo(() => Math.min(2, Math.floor(stepIndex / 2)), [stepIndex]);

  async function advance() {
    if (!next || !lease) { setError("Controller lease is missing. Return to setup."); return; }
    if ((next.action === "task/start" || next.action === "task/finish") && !window.confirm(`${next.label}?`)) return;
    setBusy(true);
    setError(null);
    try {
      const view = await transitionLiftoff(sessionId, next.action, lease);
      setSession(view);
      const newIndex = stepIndex + 1;
      setStepIndex(newIndex);
      setElapsed(0);
      if (newIndex >= STEPS.length) router.push(`/liftoff/debrief?session=${encodeURIComponent(sessionId)}`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Phase transition failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="mission-panel flex flex-col gap-4 p-5 md:flex-row md:items-end md:justify-between">
        <div><p className="page-kicker">Live FPV collection</p><h1 className="page-title">{session?.visit_code ?? "Session"} · {session?.status ?? "Loading"}</h1></div>
        <p className="font-mono text-3xl tabular-nums">{String(Math.floor(elapsed / 60)).padStart(2, "0")}:{String(elapsed % 60).padStart(2, "0")}</p>
      </header>
      <ol className="grid gap-3 md:grid-cols-3" aria-label="Collection phases">
        {["Baseline", "FPV task", "Recovery"].map((phase, index) => (
          <li key={phase} className={`mission-panel p-4 ${index === phaseIndex ? "border-white" : "border-white/10"}`}>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Phase {index + 1}</p>
            <p className="mt-2 font-display text-xl uppercase">{phase}</p>
          </li>
        ))}
      </ol>
      <div className="grid gap-4 md:grid-cols-4">
        <div className="metric-tile"><p className="page-kicker">Valid packets</p><p className="mt-2 font-display text-2xl">{readiness?.valid_packets ?? 0}</p></div>
        <div className="metric-tile"><p className="page-kicker">Invalid</p><p className="mt-2 font-display text-2xl">{readiness?.invalid_packet_count ?? 0}</p></div>
        <div className="metric-tile"><p className="page-kicker">Overflow</p><p className="mt-2 font-display text-2xl">{readiness?.overflow_count ?? 0}</p></div>
        <div className="metric-tile"><p className="page-kicker">Schema</p><p className="mt-2 font-display text-2xl">{readiness?.ready ? "Ready" : "Wait"}</p></div>
      </div>
      {error ? <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p> : null}
      {next ? <Button onClick={advance} disabled={busy || !readiness?.ready}>{busy ? "Recording marker…" : next.label}</Button> : <p>Collection phases complete. Opening debrief…</p>}
    </div>
  );
}
