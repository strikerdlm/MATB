"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { getLiftoffReadiness, getLiftoffSession, transitionLiftoff } from "@/lib/liftoff/api";
import type { LiftoffAction, LiftoffReadiness, LiftoffSessionView } from "@/types/liftoff";
import { useAppLocale } from "@/lib/i18n";

const STEPS: Array<{ action: LiftoffAction; label: [string, string] }> = [
  { action: "baseline/start", label: ["Iniciar línea basal", "Start baseline"] },
  { action: "baseline/finish", label: ["Finalizar línea basal", "Finish baseline"] },
  { action: "task/start", label: ["Iniciar tarea FPV", "Start FPV task"] },
  { action: "task/finish", label: ["Finalizar tarea FPV", "Finish FPV task"] },
  { action: "recovery/start", label: ["Iniciar recuperación", "Start recovery"] },
  { action: "recovery/finish", label: ["Finalizar recuperación", "Finish recovery"] },
];

export function LiftoffSessionConsole({ sessionId }: { sessionId: string }) {
  const { copy } = useAppLocale();
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
        if (active) setError(reason instanceof Error ? reason.message : copy("No se pudo consultar el estado de la sesión.", "Session state could not be read."));
      }
    };
    void refresh();
    const poll = window.setInterval(() => void refresh(), 1_000);
    const clock = window.setInterval(() => setElapsed((value) => value + 1), 1_000);
    return () => { active = false; window.clearInterval(poll); window.clearInterval(clock); };
  }, [copy, sessionId]);

  const next = STEPS[stepIndex] ?? null;
  const phaseIndex = useMemo(() => Math.min(2, Math.floor(stepIndex / 2)), [stepIndex]);

  async function advance() {
    if (!next || !lease) { setError(copy("Falta la autorización de control. Regrese a la configuración.", "Controller lease is missing. Return to setup.")); return; }
    const nextLabel = copy(next.label[0], next.label[1]);
    if ((next.action === "task/start" || next.action === "task/finish") && !window.confirm(`${nextLabel}?`)) return;
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
      setError(reason instanceof Error ? reason.message : copy("Falló la transición de fase.", "Phase transition failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <header className="mission-panel flex flex-col gap-4 p-5 md:flex-row md:items-end md:justify-between">
        <div><p className="page-kicker">{copy("Recolección FPV en vivo", "Live FPV collection")}</p><h1 className="page-title">{session?.visit_code ?? copy("Sesión", "Session")} · {session?.status ?? copy("Cargando", "Loading")}</h1></div>
        <p className="font-mono text-3xl tabular-nums">{String(Math.floor(elapsed / 60)).padStart(2, "0")}:{String(elapsed % 60).padStart(2, "0")}</p>
      </header>
      <ol className="grid gap-3 md:grid-cols-3" aria-label={copy("Fases de recolección", "Collection phases")}>
        {[["Línea basal", "Baseline"], ["Tarea FPV", "FPV task"], ["Recuperación", "Recovery"]].map((phase, index) => (
          <li key={phase[1]} className={`mission-panel p-4 ${index === phaseIndex ? "border-white" : "border-white/10"}`}>
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{copy("Fase", "Phase")} {index + 1}</p>
            <p className="mt-2 font-display text-xl uppercase">{copy(phase[0], phase[1])}</p>
          </li>
        ))}
      </ol>
      <div className="grid gap-4 md:grid-cols-4">
        <div className="metric-tile"><p className="page-kicker">{copy("Paquetes válidos", "Valid packets")}</p><p className="mt-2 font-display text-2xl">{readiness?.valid_packets ?? 0}</p></div>
        <div className="metric-tile"><p className="page-kicker">{copy("Inválidos", "Invalid")}</p><p className="mt-2 font-display text-2xl">{readiness?.invalid_packet_count ?? 0}</p></div>
        <div className="metric-tile"><p className="page-kicker">{copy("Desbordamiento", "Overflow")}</p><p className="mt-2 font-display text-2xl">{readiness?.overflow_count ?? 0}</p></div>
        <div className="metric-tile"><p className="page-kicker">{copy("Esquema", "Schema")}</p><p className="mt-2 font-display text-2xl">{readiness?.ready ? copy("Listo", "Ready") : copy("Espere", "Wait")}</p></div>
      </div>
      {error ? <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p> : null}
      {next ? <Button onClick={advance} disabled={busy || !readiness?.ready}>{busy ? copy("Registrando marcador…", "Recording marker…") : copy(next.label[0], next.label[1])}</Button> : <p>{copy("Fases de recolección completas. Abriendo el informe…", "Collection phases complete. Opening debrief…")}</p>}
    </div>
  );
}
