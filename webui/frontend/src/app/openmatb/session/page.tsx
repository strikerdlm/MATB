"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ExternalLink, Pause, Play, RefreshCw, RotateCcw, StopCircle } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppLocale } from "@/lib/i18n";
import { abortOpenMatbSession, controllerAction, getOpenMatbSession, readOpenMatbController, readOpenMatbParticipant } from "@/lib/openmatb/api";
import type { OpenMatbProfile, OpenMatbSession } from "@/types/openmatb";

const TERMINAL = new Set(["COMPLETE", "ABORTED", "FAILED", "INTERRUPTED"]);
const LABELS: Record<OpenMatbProfile, string> = { PRACTICE: "PRÁCTICA", LOW: "BAJO", MEDIUM: "MEDIO", HIGH: "ALTO" };

function Content() {
  const params = useSearchParams();
  const router = useRouter();
  const { copy } = useAppLocale();
  const id = params.get("session");
  const [session, setSession] = useState<OpenMatbSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!id) return;
    try { setSession(await getOpenMatbSession(id)); } catch (reason) { setError(reason instanceof Error ? reason.message : copy("No se pudo consultar la sesión.", "Session could not be loaded.")); }
  }, [copy, id]);

  useEffect(() => { if (!id) { router.replace("/openmatb/setup"); return; } void refresh(); const timer = window.setInterval(() => void refresh(), 1000); return () => window.clearInterval(timer); }, [id, refresh, router]);

  async function action(value: "start" | "pause" | "resume" | "repeat-practice") {
    if (!id) return;
    const lease = readOpenMatbController(id);
    if (!lease) { setError(copy("Esta pestaña no conserva la credencial de control.", "This tab does not hold the controller credential.")); return; }
    setBusy(true); setError(null);
    try { setSession(await controllerAction(id, value, lease)); } catch (reason) { setError(reason instanceof Error ? reason.message : copy("La acción no se pudo completar.", "The action could not be completed.")); } finally { setBusy(false); }
  }

  async function abort() {
    if (!id) return;
    const lease = readOpenMatbController(id);
    if (!lease || !window.confirm(copy("¿Abortar esta suite MATB-FAC?", "Abort this MATB-FAC suite?"))) return;
    setBusy(true);
    try { setSession(await abortOpenMatbSession(id, lease)); } catch (reason) { setError(reason instanceof Error ? reason.message : copy("No se pudo abortar.", "Abort failed.")); } finally { setBusy(false); }
  }

  function openParticipant() {
    if (!id) return;
    const token = readOpenMatbParticipant(id);
    const suffix = token ? `#token=${encodeURIComponent(token)}` : "";
    window.open(`/openmatb/participant?session=${encodeURIComponent(id)}${suffix}`, "matb-fac-participant");
  }

  if (!session) return <div className="grid min-h-[50vh] place-items-center text-muted-foreground">{error ?? copy("Cargando sesión…", "Loading session…")}</div>;
  const canStart = session.lifecycle === "READY" || session.lifecycle === "BETWEEN_BLOCKS";
  const nextBlock = session.block_order[session.current_block_index];

  return <div className="space-y-6">
    <PageHeader kicker={copy("Panel del investigador", "Researcher console")} title={`${session.visit_code} · ${session.participant_id}`} description={copy("Controle el proceso nativo sin intervenir en las respuestas del participante.", "Control the native process without intervening in participant responses.")} actions={<Button variant="outline" onClick={openParticipant}><ExternalLink className="mr-2 h-4 w-4" />{copy("Pantalla del participante", "Participant display")}</Button>} stats={[{ label: copy("Estado", "Status"), value: session.lifecycle }, { label: copy("Bloque", "Block"), value: session.active_block ? LABELS[session.active_block] : nextBlock ? LABELS[nextBlock] : "—" }, { label: "PID", value: session.active_pid ?? "—" }]} />
    {error && <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p>}
    {session.last_error && <p role="alert" className="border border-warning/40 bg-warning/5 p-3 text-sm text-warning">{session.last_error}</p>}

    <Card><CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Progreso de la suite", "Suite progress")}</CardTitle><CardDescription>{copy("PRÁCTICA seguida por el orden contrabalanceado asignado.", "PRACTICE followed by the assigned counterbalanced order.")}</CardDescription></CardHeader><CardContent><ol className="grid gap-3 md:grid-cols-4">{session.block_order.map((block, index) => { const done = index < session.current_block_index; const current = index === session.current_block_index && !TERMINAL.has(session.lifecycle); return <li key={block} className={`border p-4 ${current ? "border-white bg-white text-black" : done ? "border-success/50 bg-success/5" : "border-white/10 bg-black/20"}`}><div className="font-mono text-[10px] opacity-60">{String(index + 1).padStart(2, "0")}</div><div className="mt-1 font-display text-xl font-semibold">{LABELS[block]}</div><div className="mt-2 text-xs opacity-70">{done ? copy("Completado", "Completed") : current ? copy("Actual", "Current") : copy("Pendiente", "Pending")}</div></li>; })}</ol></CardContent></Card>

    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Card><CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Controles", "Controls")}</CardTitle><CardDescription>{session.lifecycle === "INSTRUCTIONS" ? copy("El participante debe leer y confirmar las instrucciones.", "The participant must read and acknowledge the instructions.") : session.lifecycle === "AWAITING_SCALE" ? copy("Esperando NASA-TLX y Bedford en la pantalla del participante.", "Waiting for NASA-TLX and Bedford on the participant display.") : canStart ? copy(`Listo para iniciar ${nextBlock ? LABELS[nextBlock] : ""}.`, `Ready to start ${nextBlock ?? ""}.`) : copy("OpenMATB está bajo supervisión del backend local.", "OpenMATB is supervised by the local backend.")}</CardDescription></CardHeader><CardContent className="flex flex-wrap gap-3">
        {canStart && <Button disabled={busy} onClick={() => void action("start")}><Play className="mr-2 h-4 w-4" />{copy(`Iniciar ${nextBlock ? LABELS[nextBlock] : "bloque"}`, `Start ${nextBlock ?? "block"}`)}</Button>}
        {session.lifecycle === "RUNNING" && <Button variant="outline" disabled={busy} onClick={() => void action("pause")}><Pause className="mr-2 h-4 w-4" />{copy("Pausar", "Pause")}</Button>}
        {session.lifecycle === "PAUSED" && <Button disabled={busy} onClick={() => void action("resume")}><Play className="mr-2 h-4 w-4" />{copy("Reanudar", "Resume")}</Button>}
        {session.lifecycle === "BETWEEN_BLOCKS" && session.current_block_index === 1 && <Button variant="outline" disabled={busy} onClick={() => void action("repeat-practice")}><RotateCcw className="mr-2 h-4 w-4" />{copy("Repetir práctica", "Repeat practice")}</Button>}
        {!TERMINAL.has(session.lifecycle) && <Button variant="destructive" disabled={busy} onClick={() => void abort()}><StopCircle className="mr-2 h-4 w-4" />{copy("Abortar", "Abort")}</Button>}
        <Button variant="ghost" disabled={busy} onClick={() => void refresh()}><RefreshCw className="mr-2 h-4 w-4" />{copy("Actualizar", "Refresh")}</Button>
      </CardContent></Card>
      <Card><CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Procedencia", "Provenance")}</CardTitle></CardHeader><CardContent className="space-y-3 text-sm"><div><div className="font-mono text-[10px] uppercase text-muted-foreground">Preset</div><div>{session.preset_id} · v{session.preset_version}</div></div><div><div className="font-mono text-[10px] uppercase text-muted-foreground">SHA-256</div><div className="break-all font-mono text-[10px]">{session.preset_sha256}</div></div><div><div className="font-mono text-[10px] uppercase text-muted-foreground">{copy("Pantalla", "Display")}</div><div>{session.display_index}</div></div></CardContent></Card>
    </div>
  </div>;
}

export default function OpenMatbSessionPage() {
  const { copy } = useAppLocale();
  return <Suspense fallback={<div className="grid min-h-[50vh] place-items-center text-muted-foreground">{copy("Cargando sesión…", "Loading session…")}</div>}><Content /></Suspense>;
}
