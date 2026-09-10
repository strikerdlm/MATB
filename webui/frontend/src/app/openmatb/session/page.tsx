"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { ExternalLink, Pause, Play, RefreshCw, StopCircle } from "lucide-react";
import { ExecutionPurposeBadge } from "@/components/experiments/ExperimentGuide";
import { GuidedSteps } from "@/components/layout/GuidedSteps";
import { PageHeader } from "@/components/layout/PageHeader";
import { BlockProgress } from "@/components/openmatb/BlockProgress";
import { SessionReceipt } from "@/components/openmatb/SessionReceipt";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppLocale } from "@/lib/i18n";
import { withExecutionPurpose } from "@/lib/execution-purpose";
import { useReportExperimentFlow, type ExperimentFlowStage } from "@/lib/experiment-flow";
import { useSerializedPolling } from "@/lib/serialized-polling";
import { abortOpenMatbSession, controllerAction, getOpenMatbSession, getOpenMatbReceipt, getOpenMatbDisplays,
  readOpenMatbController, readOpenMatbParticipant, retryOpenMatbEvidence } from "@/lib/openmatb/api";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import { openMatbStage, OPENMATB_TERMINAL } from "@/lib/openmatb/progress";
import { readParticipantWindowState, saveParticipantWindowState, type ParticipantWindowState } from "@/lib/openmatb/participant-window";

const PROFILE_LABELS = { PRACTICE: ["Práctica", "Practice"], LOW: ["Bajo", "Low"], MEDIUM: ["Medio", "Medium"], HIGH: ["Alto", "High"] } as const;
const LIFECYCLE_LABELS: Record<string, [string, string]> = {
  PREFLIGHT_READY: ["Preparación nativa pendiente", "Native preflight pending"],
  PREFLIGHT_STARTING: ["Resolviendo la preparación nativa", "Resolving native preparation"],
  PREFLIGHT_HELD: ["Preparado sin iniciar adquisición", "Prepared; acquisition has not started"],
  INSTRUCTIONS: ["Instrucciones", "Instructions"], READY: ["Listo para abrir la tarea", "Ready to open task"], STARTING: ["Abriendo la ventana de tarea", "Task window opening"],
  RUNNING: ["Tarea en ejecución", "Task running"], PAUSED: ["Tarea en pausa", "Task paused"], AWAITING_SCALE: ["Esperando escalas", "Waiting for ratings"],
  BETWEEN_BLOCKS: ["Entre bloques", "Between blocks"], COMPLETE: ["Sesión completada", "Session completed"], ABORTED: ["Sesión abortada", "Session aborted"],
  FAILED: ["Sesión detenida por un error", "Session stopped by an error"], INTERRUPTED: ["Sesión interrumpida", "Session interrupted"],
};

function Content() {
  const params = useSearchParams();
  const { copy } = useAppLocale();
  const id = params.get("session");
  const idRef = useRef(id); idRef.current = id;
  const [busy, setBusy] = useState(false);
  const [retrying, setRetrying] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [credentials, setCredentials] = useState<{ id: string; lease: string | null; participant: string | null } | null>(null);
  const [windowState, setWindowState] = useState<ParticipantWindowState>("unknown");
  const sessionPoll = useSerializedPolling({ enabled: Boolean(id), resetKey: id, intervalMs: 1000,
    poll: () => getOpenMatbSession(id!), errorMessage: reason => openMatbErrorMessage(reason, copy) });
  const receiptPoll = useSerializedPolling({ enabled: Boolean(id), resetKey: id, intervalMs: 2000,
    poll: () => getOpenMatbReceipt(id!), errorMessage: reason => openMatbErrorMessage(reason, copy) });
  const session = sessionPoll.value?.id === id ? sessionPoll.value : null;
  const receipt = receiptPoll.value?.session_id === id ? receiptPoll.value : null;
  const stage = openMatbStage(session?.lifecycle);
  useReportExperimentFlow("openmatb", stage, session?.execution_purpose);

  const blockedParam = params.get("participant_window") === "blocked";
  useEffect(() => {
    setActionError(null);
    if (!id) return;
    try { setCredentials({ id, lease: readOpenMatbController(id), participant: readOpenMatbParticipant(id) }); }
    catch { setCredentials({ id, lease: null, participant: null }); }
    const stored = readParticipantWindowState(id);
    setWindowState(stored === "unknown" && blockedParam ? "blocked" : stored);
  }, [id, blockedParam]);
  const lease = credentials?.id === id ? credentials.lease : null;

  async function action(value: "start" | "pause" | "resume" | "repeat-practice") {
    if (!id || !session || !lease || busy) return;
    setBusy(true); setActionError(null);
    try {
      if (value === "start") {
        const displays = await getOpenMatbDisplays();
        if (!displays.some(display => display.index === session.display_index)) throw new Error(copy("La pantalla seleccionada se desconectó. Vuelva a preparación y seleccione una pantalla disponible.", "The selected display disconnected. Return to preparation and select an available display."));
      }
      const next = await controllerAction(id, value, lease);
      if (idRef.current === id) sessionPoll.acceptActionValue(next);
    } catch (reason) { if (idRef.current === id) setActionError(openMatbErrorMessage(reason, copy)); }
    finally { setBusy(false); }
  }
  async function abort() {
    if (!id || !lease || busy || !window.confirm(copy("¿Abortar esta suite MATB - FAC?", "Abort this MATB - FAC suite?"))) return;
    setBusy(true); setActionError(null);
    try {
      const next = await abortOpenMatbSession(id, lease);
      if (idRef.current === id) sessionPoll.acceptActionValue(next);
    } catch (reason) { if (idRef.current === id) setActionError(openMatbErrorMessage(reason, copy)); }
    finally { setBusy(false); }
  }
  async function retry(blockId: string) {
    if (!id || !lease || retrying) return;
    setRetrying(blockId); setActionError(null);
    try {
      const next = await retryOpenMatbEvidence(id, blockId, lease);
      if (idRef.current === id) receiptPoll.acceptActionValue(next);
    } catch (reason) { if (idRef.current === id) setActionError(openMatbErrorMessage(reason, copy)); }
    finally { setRetrying(null); }
  }
  function openParticipant() {
    if (!id) return;
    const token = credentials?.id === id ? credentials.participant : null;
    if (!token) { setActionError(copy("Esta pestaña no conserva la credencial del participante. Use la pestaña donde preparó la sesión.", "This tab does not hold the participant credential. Use the tab where the session was prepared.")); return; }
    const opened = window.open(`/openmatb/participant?session=${encodeURIComponent(id)}#token=${encodeURIComponent(token)}`, "matb-fac-participant");
    const next = opened ? "opened" : "blocked";
    saveParticipantWindowState(id, next); setWindowState(next);
  }
  function refresh() { void sessionPoll.refresh(); void receiptPoll.refresh(); }

  if (!id) return <p>{copy("Seleccione una sesión desde", "Select a session from")} <Link className="text-info underline" href="/openmatb/setup">{copy("Preparar", "Prepare")}</Link>.</p>;
  if (!session) return <div className="space-y-3 py-8">
    {sessionPoll.pollingError ? <p role="alert" className="text-danger">{sessionPoll.pollingError}</p> : <p role="status">{copy("Cargando sesión…", "Loading session…")}</p>}
    <Button variant="outline" onClick={refresh}>{copy("Actualizar", "Refresh")}</Button>
  </div>;

  const terminal = OPENMATB_TERMINAL.has(session.lifecycle);
  const nextBlock = session.block_order[session.current_block_index];
  const nextBlockLabel = nextBlock ? copy(PROFILE_LABELS[nextBlock][0], PROFILE_LABELS[nextBlock][1]) : "—";
  const canStart = session.lifecycle === "READY" || session.lifecycle === "BETWEEN_BLOCKS" || session.lifecycle === "PREFLIGHT_HELD";
  const startBlocked = busy || !lease || session.evidence_processing || session.native_recovery_required;
  const flowSteps: Array<[ExperimentFlowStage, string]> = [["prepare", copy("Preparar", "Prepare")], ["instructions", copy("Instrucciones", "Instructions")], ["perform", copy("Realizar actividad", "Run activity")], ["complete", copy("Completar", "Complete")]];
  const currentStage = flowSteps.findIndex(([key]) => key === stage);

  return <div className="min-w-0 space-y-6 text-base [&_button]:text-sm [&_button]:normal-case [&_button]:tracking-normal">
    <ExecutionPurposeBadge purpose={session.execution_purpose} />
    <PageHeader kicker={copy("Panel del investigador", "Researcher console")} title={`${session.visit_code} · ${session.participant_id}`}
      description={copy(...LIFECYCLE_LABELS[session.lifecycle])}
      actions={<Button variant="outline" onClick={openParticipant}><ExternalLink className="mr-2 h-4 w-4" />{copy("Pantalla del participante", "Participant display")}</Button>} />
    {stage && <GuidedSteps label={copy("Progreso de la sesión", "Session progress")} steps={flowSteps.map(([key, title], index) => ({ title,
      description: key === "perform" ? copy("Tarea y escalas de cada bloque.", "Task and ratings for each block.") : "",
      state: index < currentStage || stage === "complete" ? "complete" : index === currentStage ? "current" : "upcoming" }))} />}
    {sessionPoll.pollingError && <p role="alert" className="rounded border border-warning/40 p-3 text-sm text-warning">{copy("Conexión interrumpida; reintentando. ", "Connection interrupted; retrying. ")}{sessionPoll.pollingError}</p>}
    {receiptPoll.pollingError && <p role="alert" className="text-warning">{copy("No se pudo actualizar el estado de guardado; reintentando. ", "Save status could not be refreshed; retrying. ")}{receiptPoll.pollingError}</p>}
    {actionError && <p role="alert" className="rounded border border-danger/40 p-3 text-sm text-danger">{actionError}</p>}
    {windowState === "blocked" && <div className="rounded border border-warning/40 bg-warning/5 p-4 text-sm"><p role="alert">{copy("El navegador bloqueó la ventana de instrucciones del participante. Permita ventanas emergentes para esta consola y vuelva a abrirla.", "The browser blocked the participant instructions window. Allow popups for this console and reopen it.")}</p><Button variant="outline" className="mt-3 h-auto whitespace-normal" onClick={openParticipant}>{copy("Reabrir instrucciones del participante", "Reopen participant instructions")}</Button></div>}
    {session.native_recovery_required && <p role="alert" className="rounded border border-warning/40 p-3 text-warning">{openMatbErrorMessage("openmatb_native_recovery_required", copy)}</p>}
    <Card className="border-info/40 bg-info/5"><CardHeader><CardTitle className="text-xl">{copy("Acción siguiente", "Next action")}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {!lease && !terminal && <p className="text-sm text-warning">{copy("Esta pestaña no conserva la credencial de control. Use la pestaña donde preparó la sesión.", "This tab does not hold the controller credential. Use the tab where the session was prepared.")}</p>}
        {session.lifecycle === "INSTRUCTIONS" && <><p>{copy("El participante debe leer y confirmar las instrucciones.", "The participant needs to read and confirm the instructions.")}</p><Button onClick={openParticipant}>{copy("Abrir instrucciones del participante", "Open participant instructions")}</Button></>}
        {canStart && <><p>{copy(`Siguiente bloque: ${nextBlockLabel}. Abra la tarea cuando el participante esté listo.`, `Next block: ${nextBlockLabel}. Open the task when the participant is ready.`)}</p>
          {session.evidence_processing && <p role="status">{openMatbErrorMessage("openmatb_evidence_processing_active", copy)}</p>}
          <Button size="lg" className="h-auto max-w-full whitespace-normal" disabled={startBlocked} onClick={() => void action("start")}><Play className="mr-2 h-4 w-4 shrink-0" />{busy ? copy("Abriendo ventana nativa…", "Opening native window…") : copy(`Abrir OpenMATB e iniciar ${nextBlockLabel}`, `Open OpenMATB and start ${nextBlockLabel}`)}</Button></>}
        {session.lifecycle === "STARTING" && <p role="status">{copy("Abriendo la ventana de tarea. Espere la confirmación de OpenMATB; puede tardar hasta 20 segundos.", "Task window opening. Wait for OpenMATB to confirm; this may take up to 20 seconds.")}</p>}
        {session.lifecycle === "RUNNING" && <><p>{copy("La tarea está activa en la pantalla seleccionada.", "The task is active on the selected display.")}</p><Button variant="outline" disabled={busy || !lease} onClick={() => void action("pause")}><Pause className="mr-2 h-4 w-4" />{copy("Pausar bloque", "Pause block")}</Button></>}
        {session.lifecycle === "PAUSED" && <><p>{copy("El bloque está en pausa. Reanúdelo cuando el participante esté listo.", "The block is paused. Resume when the participant is ready.")}</p><Button disabled={busy || !lease} onClick={() => void action("resume")}>{copy("Reanudar bloque", "Resume block")}</Button></>}
        {session.lifecycle === "AWAITING_SCALE" && <><p>{copy("El participante debe guardar las escalas de este bloque.", "The participant needs to save ratings for this block.")}</p><Button onClick={openParticipant}>{copy("Completar escalas", "Complete scales")}</Button></>}
        {terminal && <><p>{session.lifecycle === "COMPLETE" ? copy("La ejecución terminó. Revise el comprobante para saber qué se guardó y qué queda por procesar.", "The run has ended. Review the receipt to see what was saved and what still needs processing.") : copy("La ejecución se detuvo. Revise los bloques y los archivos disponibles antes de preparar otra sesión.", "The run stopped. Review the available blocks and files before preparing another session.")}</p>
          {session.last_error && session.lifecycle !== "COMPLETE" && <p className="text-sm text-warning">{openMatbErrorMessage(session.last_error, copy)}</p>}
          <div className="flex flex-wrap gap-3"><Button asChild size="lg"><Link href={`/evidence?session=${encodeURIComponent(session.id)}&purpose=all`}>{copy("Revisar esta sesión", "Review this session")}</Link></Button>
            <Button asChild variant="outline"><Link href={withExecutionPurpose("/openmatb/setup", session.execution_purpose)}>{copy("Preparar una sesión nueva", "Prepare a new session")}</Link></Button></div></>}
      </CardContent>
    </Card>
    {!terminal && <BlockProgress session={session} receipt={receipt} />}
    {terminal && <>
      {!receipt && !receiptPoll.pollingError && <p role="status">{copy("Consultando qué se guardó…", "Checking what was saved…")}</p>}
      {receipt && <SessionReceipt receipt={receipt} onRetry={lease ? blockId => void retry(blockId) : undefined} retrying={retrying} />}
    </>}
    <div className="flex flex-wrap gap-3">
      {session.lifecycle === "BETWEEN_BLOCKS" && session.current_block_index === 1 && <Button variant="outline" disabled={busy || !lease} onClick={() => void action("repeat-practice")}>{copy("Repetir práctica", "Repeat practice")}</Button>}
      {!terminal && <Button variant="destructive" disabled={busy || !lease} onClick={() => void abort()}><StopCircle className="mr-2 h-4 w-4" />{copy("Abortar sesión", "Abort session")}</Button>}
      <Button variant="outline" onClick={refresh}><RefreshCw className="mr-2 h-4 w-4" />{copy("Actualizar", "Refresh")}</Button>
    </div>
    <details className="rounded border p-4 text-sm"><summary className="cursor-pointer font-semibold">{copy("Diagnósticos y procedencia", "Diagnostics and provenance")}</summary>
      <dl className="mt-3 grid gap-3 break-all font-mono text-xs sm:grid-cols-2">{Object.entries({ session: session.id, lifecycle: session.lifecycle, pid: session.active_pid,
        display: session.display_index + 1, display_index: session.display_index, block_order: session.block_order.join(" → "), preset: `${session.preset_id}@${session.preset_version}`, preset_sha256: session.preset_sha256,
        instruction_protocol: `${session.instruction_protocol.protocol_id}@${session.instruction_protocol.version}`, instruction_protocol_sha256: session.instruction_protocol.sha256, visual_profile: session.visual_profile_id ?? session.visual_theme,
        visual_profile_version: session.visual_profile_version, visual_profile_sha256: session.visual_profile_sha256, last_error: session.last_error }).map(([label, value]) => <div key={label}><dt className="text-muted-foreground">{label}</dt><dd>{value ?? "—"}</dd></div>)}</dl>
    </details>
  </div>;
}

export default function OpenMatbSessionPage() { return <Suspense><Content /></Suspense>; }
