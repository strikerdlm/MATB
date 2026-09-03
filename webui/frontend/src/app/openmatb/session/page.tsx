"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { ExternalLink, Loader2, Pause, Play, RefreshCw, RotateCcw, StopCircle } from "lucide-react";

import { GuidedSteps, type GuidedStepState } from "@/components/layout/GuidedSteps";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppLocale } from "@/lib/i18n";
import {
  abortOpenMatbSession,
  controllerAction,
  getOpenMatbSession,
  readOpenMatbController,
  readOpenMatbParticipant,
} from "@/lib/openmatb/api";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import type { OpenMatbProfile, OpenMatbSession } from "@/types/openmatb";

const TERMINAL = new Set(["COMPLETE", "ABORTED", "FAILED", "INTERRUPTED"]);
const LABELS: Record<OpenMatbProfile, [string, string]> = {
  PRACTICE: ["PRÁCTICA", "PRACTICE"],
  LOW: ["BAJO", "LOW"],
  MEDIUM: ["MEDIO", "MEDIUM"],
  HIGH: ["ALTO", "HIGH"],
};

function stepState(complete: boolean, current: boolean): GuidedStepState {
  return complete ? "complete" : current ? "current" : "upcoming";
}

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
    try {
      setSession(await getOpenMatbSession(id));
    } catch (reason: unknown) {
      setError(openMatbErrorMessage(reason, copy, ["No se pudo consultar la sesión.", "Session could not be loaded."]));
    }
  }, [copy, id]);

  useEffect(() => {
    if (!id) {
      router.replace("/openmatb/setup");
      return;
    }
    void refresh();
    const timer = window.setInterval(() => void refresh(), 1000);
    return () => window.clearInterval(timer);
  }, [id, refresh, router]);

  async function action(value: "start" | "pause" | "resume" | "repeat-practice") {
    if (!id) return;
    const lease = readOpenMatbController(id);
    if (!lease) {
      setError(copy("Esta pestaña no conserva la credencial de control. Regrese a preparación.", "This tab does not hold the controller credential. Return to setup."));
      return;
    }
    setBusy(true);
    setError(null);
    try {
      setSession(await controllerAction(id, value, lease));
    } catch (reason: unknown) {
      setError(openMatbErrorMessage(reason, copy));
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function abort() {
    if (!id) return;
    const lease = readOpenMatbController(id);
    if (!lease || !window.confirm(copy("¿Abortar esta suite MATB-FAC?", "Abort this MATB-FAC suite?"))) return;
    setBusy(true);
    setError(null);
    try {
      setSession(await abortOpenMatbSession(id, lease));
    } catch (reason: unknown) {
      setError(openMatbErrorMessage(reason, copy, ["No se pudo abortar.", "Abort failed."]));
    } finally {
      setBusy(false);
    }
  }

  function openParticipant() {
    if (!id) return;
    const token = readOpenMatbParticipant(id);
    const suffix = token ? `#token=${encodeURIComponent(token)}` : "";
    window.open(`/openmatb/participant?session=${encodeURIComponent(id)}${suffix}`, "matb-fac-participant");
  }

  if (!session) {
    return <div className="grid min-h-[50vh] place-items-center text-muted-foreground">{error ?? copy("Cargando sesión…", "Loading session…")}</div>;
  }

  const nextBlock = session.block_order[session.current_block_index];
  const nextBlockLabel = nextBlock ? copy(LABELS[nextBlock][0], LABELS[nextBlock][1]) : copy("bloque", "block");
  const canStart = session.lifecycle === "READY" || session.lifecycle === "BETWEEN_BLOCKS";
  const instructionsComplete = session.lifecycle !== "INSTRUCTIONS";
  const launchCurrent = canStart || session.lifecycle === "STARTING" || session.lifecycle === "FAILED";
  const blockCurrent = session.lifecycle === "RUNNING" || session.lifecycle === "PAUSED";
  const scaleCurrent = session.lifecycle === "AWAITING_SCALE";
  const suiteComplete = session.lifecycle === "COMPLETE";

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Panel del investigador", "Researcher console")}
        title={`${session.visit_code} · ${session.participant_id}`}
        description={copy("Siga el paso resaltado. La aplicación nativa se abre únicamente desde el botón principal de este panel.", "Follow the highlighted step. The native application opens only from the primary button in this console.")}
        actions={<Button variant="outline" onClick={openParticipant}><ExternalLink className="mr-2 h-4 w-4" />{copy("Pantalla del participante", "Participant display")}</Button>}
        stats={[
          { label: copy("Estado", "Status"), value: session.lifecycle },
          { label: copy("Bloque", "Block"), value: session.active_block ? copy(LABELS[session.active_block][0], LABELS[session.active_block][1]) : nextBlockLabel },
          { label: "PID", value: session.active_pid ?? "—" },
        ]}
      />

      <GuidedSteps
        label={copy("Progreso de la ejecución", "Run progress")}
        steps={[
          { title: copy("Instrucciones", "Instructions"), description: copy("El participante lee y confirma.", "Participant reads and confirms."), state: stepState(instructionsComplete, session.lifecycle === "INSTRUCTIONS") },
          { title: copy("Abrir bloque", "Open block"), description: copy("El investigador abre la ventana nativa.", "Researcher opens the native window."), state: stepState(blockCurrent || scaleCurrent || suiteComplete, launchCurrent) },
          { title: copy("Realizar tarea", "Perform task"), description: copy("Complete el bloque en OpenMATB.", "Complete the block in OpenMATB."), state: stepState(scaleCurrent || suiteComplete, blockCurrent) },
          { title: copy("Escalas", "Scales"), description: copy("NASA-TLX y Bedford; después se repite el ciclo.", "NASA-TLX and Bedford; then the cycle repeats."), state: stepState(suiteComplete, scaleCurrent) },
        ]}
      />

      {error && <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {session.last_error && <p role="alert" className="border border-warning/40 bg-warning/5 p-3 text-sm text-warning">{openMatbErrorMessage(session.last_error, copy)}</p>}

      <Card className="border-info/40 bg-info/5">
        <CardHeader>
          <CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Acción siguiente", "Next action")}</CardTitle>
          <CardDescription>
            {session.lifecycle === "INSTRUCTIONS" && copy("El participante debe leer y confirmar las instrucciones antes de abrir la aplicación nativa.", "The participant must read and confirm the instructions before opening the native application.")}
            {canStart && copy(`La estación está lista para abrir ${nextBlockLabel}.`, `The station is ready to open ${nextBlockLabel}.`)}
            {session.lifecycle === "STARTING" && copy("Espere mientras aparece la ventana nativa; puede tardar hasta 20 segundos.", "Wait for the native window to appear; this may take up to 20 seconds.")}
            {session.lifecycle === "RUNNING" && copy("OpenMATB está activo en la pantalla seleccionada.", "OpenMATB is active on the selected display.")}
            {session.lifecycle === "PAUSED" && copy("El bloque está pausado. Reanúdelo cuando el participante esté listo.", "The block is paused. Resume when the participant is ready.")}
            {session.lifecycle === "AWAITING_SCALE" && copy("Abra la pantalla del participante para completar las escalas.", "Open the participant display to complete the scales.")}
            {suiteComplete && copy("La suite quedó completa y los resultados fueron guardados.", "The suite is complete and results were saved.")}
            {session.lifecycle === "FAILED" && copy("La ventana nativa no pudo iniciarse. Revise el mensaje y prepare una sesión nueva.", "The native window could not start. Review the message and prepare a new session.")}
            {session.lifecycle === "INTERRUPTED" && copy("La sesión fue interrumpida por un reinicio de la consola.", "The session was interrupted by a console restart.")}
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          {session.lifecycle === "INSTRUCTIONS" && <Button size="lg" onClick={openParticipant}><ExternalLink className="mr-2 h-4 w-4" />{copy("Abrir instrucciones del participante", "Open participant instructions")}</Button>}
          {canStart && <Button size="lg" disabled={busy} onClick={() => void action("start")}>{busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : <Play className="mr-2 h-4 w-4" />}{busy ? copy("Abriendo ventana nativa…", "Opening native window…") : copy(`Abrir OpenMATB e iniciar ${nextBlockLabel}`, `Open OpenMATB and start ${nextBlockLabel}`)}</Button>}
          {session.lifecycle === "STARTING" && <Button size="lg" disabled><Loader2 className="mr-2 h-4 w-4 animate-spin" />{copy("Abriendo ventana nativa…", "Opening native window…")}</Button>}
          {session.lifecycle === "RUNNING" && <Button size="lg" variant="outline" disabled={busy} onClick={() => void action("pause")}><Pause className="mr-2 h-4 w-4" />{copy("Pausar bloque", "Pause block")}</Button>}
          {session.lifecycle === "PAUSED" && <Button size="lg" disabled={busy} onClick={() => void action("resume")}><Play className="mr-2 h-4 w-4" />{copy("Reanudar bloque", "Resume block")}</Button>}
          {session.lifecycle === "AWAITING_SCALE" && <Button size="lg" onClick={openParticipant}><ExternalLink className="mr-2 h-4 w-4" />{copy("Completar escalas", "Complete scales")}</Button>}
          {(session.lifecycle === "FAILED" || session.lifecycle === "INTERRUPTED" || suiteComplete) && <Button asChild size="lg"><Link href="/openmatb/setup">{copy("Preparar una sesión nueva", "Prepare a new session")}</Link></Button>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Progreso de la suite", "Suite progress")}</CardTitle><CardDescription>{copy("PRÁCTICA seguida por el orden contrabalanceado asignado.", "PRACTICE followed by the assigned counterbalanced order.")}</CardDescription></CardHeader>
        <CardContent>
          <ol className="grid gap-3 md:grid-cols-4">
            {session.block_order.map((block, index) => {
              const done = index < session.current_block_index;
              const current = index === session.current_block_index && !TERMINAL.has(session.lifecycle);
              return <li key={block} className={`border p-4 ${current ? "border-white bg-white text-black" : done ? "border-success/50 bg-success/5" : "border-white/10 bg-black/20"}`}><div className="font-mono text-[10px] opacity-60">{String(index + 1).padStart(2, "0")}</div><div className="mt-1 font-display text-xl font-semibold">{copy(LABELS[block][0], LABELS[block][1])}</div><div className="mt-2 text-xs opacity-70">{done ? copy("Completado", "Completed") : current ? copy("Actual", "Current") : copy("Pendiente", "Pending")}</div></li>;
            })}
          </ol>
        </CardContent>
      </Card>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card>
          <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Controles secundarios", "Secondary controls")}</CardTitle><CardDescription>{copy("Use estos controles sólo si el protocolo lo requiere.", "Use these controls only when required by the protocol.")}</CardDescription></CardHeader>
          <CardContent className="flex flex-wrap gap-3">
            {session.lifecycle === "BETWEEN_BLOCKS" && session.current_block_index === 1 && <Button variant="outline" disabled={busy} onClick={() => void action("repeat-practice")}><RotateCcw className="mr-2 h-4 w-4" />{copy("Repetir práctica", "Repeat practice")}</Button>}
            {!TERMINAL.has(session.lifecycle) && <Button variant="destructive" disabled={busy} onClick={() => void abort()}><StopCircle className="mr-2 h-4 w-4" />{copy("Abortar sesión", "Abort session")}</Button>}
            <Button variant="ghost" disabled={busy} onClick={() => void refresh()}><RefreshCw className="mr-2 h-4 w-4" />{copy("Actualizar", "Refresh")}</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Procedencia", "Provenance")}</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm"><div><div className="font-mono text-[10px] uppercase text-muted-foreground">Preset</div><div>{session.preset_id} · v{session.preset_version}</div></div><div><div className="font-mono text-[10px] uppercase text-muted-foreground">SHA-256</div><div className="break-all font-mono text-[10px]">{session.preset_sha256}</div></div><div><div className="font-mono text-[10px] uppercase text-muted-foreground">{copy("Pantalla", "Display")}</div><div>{session.display_index}</div></div></CardContent>
        </Card>
      </div>
    </div>
  );
}

export default function OpenMatbSessionPage() {
  const { copy } = useAppLocale();
  return <Suspense fallback={<div className="grid min-h-[50vh] place-items-center text-muted-foreground">{copy("Cargando sesión…", "Loading session…")}</div>}><Content /></Suspense>;
}
