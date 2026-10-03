"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Activity, Download, Play, Square } from "lucide-react";

import {useAssignedAttempt} from '@/lib/assigned-attempt';
import {useAssessmentAdmission} from '@/lib/assessment-admission';
import {assignmentDetail} from '@/lib/study';
import { experimentErrorMessage } from "@/lib/experiment-errors";
import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { useExecutionPurpose, withExecutionPurpose } from "@/lib/execution-purpose";
import { useReportExperimentFlow } from "@/lib/experiment-flow";
import { PageHeader } from "@/components/layout/PageHeader";
import { InstructionAudio } from "@/components/instructions/InstructionAudio";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppLocale } from "@/lib/i18n";
import { listParticipants } from "@/lib/api";
import type { Participant } from "@/types";
import { PolarDevicePanel } from "@/components/physiology/PolarDevicePanel";
import { PolarCaptureReview } from "@/components/physiology/PolarCaptureReview";
import {
  addPolarMarker,
  connectPolar,
  createPolarCapture,
  disconnectPolar,
  downloadPolarBundle,
  getPolarConnection,
  getActivePolarCapture,
  getPolarCapture,
  validatePolarControl,
  getPolarAnalysis,
  openPolarStream,
  scanPolar,
  startPolarCapture,
  stopPolarCapture,
} from "@/lib/physiology/api";
import type { PolarAnalysis, PolarCapture, PolarConnection, PolarDevice, PolarEvent } from "@/types/physiology";


type AccRate = 25 | 50 | 100 | 200;
type AccRange = 2 | 4 | 8;
type EnvelopePoint = { minimum: number; maximum: number };

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function Envelope({ points }: { points: EnvelopePoint[] }) {
  const { copy } = useAppLocale();
  if (!points.length) return <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">{copy("Esperando electrocardiograma (ECG)…", "Waiting for electrocardiogram (ECG)…")}</div>;
  const maximum = Math.max(1, ...points.flatMap((point) => [Math.abs(point.minimum), Math.abs(point.maximum)]));
  return <svg viewBox={`0 0 ${points.length * 4} 100`} className="h-24 w-full" role="img" aria-label={copy("Envolvente ECG decimada", "Downsampled ECG envelope")}>
    <line x1="0" x2={points.length * 4} y1="50" y2="50" stroke="currentColor" opacity="0.15" />
    {points.map((point, index) => <line
      key={index}
      x1={index * 4 + 2}
      x2={index * 4 + 2}
      y1={50 - (point.maximum / maximum) * 45}
      y2={50 - (point.minimum / maximum) * 45}
      stroke="currentColor"
      strokeWidth="2"
    />)}
  </svg>;
}

function AccTrace({ values }: { values: number[] }) {
  const { copy } = useAppLocale();
  if (!values.length) return <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">{copy("Esperando acelerometría…", "Waiting for acceleration…")}</div>;
  const low = Math.min(...values);
  const span = Math.max(1, Math.max(...values) - low);
  const points = values.map((value, index) => `${index * 4},${94 - ((value - low) / span) * 88}`).join(" ");
  return <svg viewBox={`0 0 ${Math.max(4, values.length * 4)} 100`} className="h-24 w-full" role="img" aria-label={copy("Magnitud vectorial de aceleración decimada", "Downsampled acceleration magnitude")}>
    <polyline points={points} fill="none" stroke="currentColor" strokeWidth="2" />
  </svg>;
}

export default function PolarH10Page() {
  const preferred = useAppLocale();
  const assigned = useAssignedAttempt();
  const locale = assigned.context?.locale ?? preferred.locale;
  const copy = useCallback((es:string,en:string) => locale === 'en' ? en : es, [locale]);
  const [companionSources,setCompanionSources]=useState<{table:string;id:string}[]>([]);
  const purpose = useExecutionPurpose();
  const [connection, setConnection] = useState<PolarConnection>({ connected: false, device_alias: null, capabilities: null });
  const [devices, setDevices] = useState<PolarDevice[]>([]);
  const [connectionStep, setConnectionStep] = useState<"searching" | "connecting" | "switching" | null>(null);
  const [previousCapture, setPreviousCapture] = useState<{ capture: PolarCapture; lease: string } | null>(null);
  const [capture, setCapture] = useState<PolarCapture | null>(null);
  const [lease, setLease] = useState("");
  const [participant, setParticipant] = useState("");
  const [participants, setParticipants] = useState<Participant[] | null>(null);
  const [participantLoadFailed, setParticipantLoadFailed] = useState(false);
  const [participantReload, setParticipantReload] = useState(0);
  const [restoring, setRestoring] = useState(true);
  const [statusKnown, setStatusKnown] = useState(false);
  const [ownershipNotice, setOwnershipNotice] = useState<string | null>(null);
  const restoreGeneration = useRef(0);
  const actionPending = useRef(false);
  const [sessionKind, setSessionKind] = useState<PolarCapture["matb_session_kind"]>("generic");
  const [sessionId, setSessionId] = useState("");
  const [accRate, setAccRate] = useState<AccRate>(50);
  const [accRange, setAccRange] = useState<AccRange>(2);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [heartRate, setHeartRate] = useState<number | null>(null);
  const [rr, setRr] = useState<number | null>(null);
  const [quality, setQuality] = useState<Record<string, unknown>>({});
  const [ecg, setEcg] = useState<EnvelopePoint[]>([]);
  const [acc, setAcc] = useState<number[]>([]);
  const [gaps, setGaps] = useState(0);
  const [lastMarker, setLastMarker] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [restContext, setRestContext] = useState<'TASK_PRE' | 'PRE_REST_SEATED' | 'PRE_REST_SEATED_5MIN'>('TASK_PRE');
  const admission = useAssessmentAdmission(assigned.attempt && assigned.context ? {attemptId:assigned.attempt.id, participantId:assigned.context.participant_id, visitId:assigned.context.visit_id, purpose:'study', locale:assigned.context.locale} : null, {runtime:true});
  useEffect(()=>{if(capture) return; let active=true; const bound=assigned.context;if(bound){setParticipant(bound.participant_id);const settings=bound.config.settings as {acc_sample_rate_hz:AccRate;acc_range_g:AccRange};setAccRate(settings.acc_sample_rate_hz);setAccRange(settings.acc_range_g);if(!bound.accompanying_key){setSessionKind('generic');setSessionId(bound.occasion_id);}else void assignmentDetail(bound.assignment_id).then(detail=>{if(active)setCompanionSources((detail.attempts[bound.accompanying_key!]??[]).flatMap(a=>a.sources.filter(s=>['openmatb_suite_session','liftoff_session','simulation_session'].includes(s.source_table)).map(s=>({table:s.source_table,id:s.source_id}))));});}return()=>{active=false;};},[assigned.context, capture]);
  const [analysis, setAnalysis] = useState<PolarAnalysis | null>(null);
  const lastSequence = useRef(0);
  const captureId = capture?.capture_id;
  useReportExperimentFlow("physiology", capture?.lifecycle === "capturing" ? "perform" : capture?.lifecycle === "complete" ? "complete" : capture ? "instructions" : "prepare");

  useEffect(() => {
    let active = true;
    setParticipantLoadFailed(false);
    void listParticipants().then((people) => {
      if (active) setParticipants(people.filter((person) => !person.archived));
    }).catch(() => {
      if (active) setParticipantLoadFailed(true);
    });
    return () => { active = false; };
  }, [participantReload]);

  useEffect(() => {
    if (capture?.lifecycle !== 'capturing') return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [capture?.lifecycle]);

  useEffect(() => {
    if (assigned.context) return;
    const query = new URLSearchParams(window.location.search);
    const selectedParticipant = query.get("participant");
    const selectedVisit = query.get("visit");
    if (selectedParticipant && /^P\d{2,6}$/.test(selectedParticipant)) {
      setParticipant(selectedParticipant);
      if (selectedVisit && /^\d+$/.test(selectedVisit)) {
        setSessionKind("generic");
        setSessionId(`baseline:${selectedParticipant}:V${selectedVisit}`);
      }
    }
  }, [assigned.context]);

  const refreshCapture = useCallback(async () => {
    if (actionPending.current) return;
    const generation = ++restoreGeneration.current;
    try {
      const [active, currentConnection] = await Promise.all([getActivePolarCapture(), getPolarConnection()]);
      const saved = sessionStorage.getItem("polar.selected");
      const legacy = Object.keys(sessionStorage).filter(key => key.startsWith("polar.controller."));
      const assignedCapture = assigned.attempt?.sources?.find(source => source.source_table === 'polar_capture')?.source_id
        ?? (assigned.attempt ? sessionStorage.getItem(`polar.attempt.${assigned.attempt.id}`) : null);
      const selected = assigned.identity ? assignedCapture : saved ?? (legacy.length === 1 ? legacy[0].slice("polar.controller.".length) : null);
      const found = active ?? (selected ? await getPolarCapture(selected) : null);
      let restoredLease = found ? sessionStorage.getItem(`polar.controller.${found.capture_id}`) ?? "" : "";
      let verified = found;
      if (found && restoredLease) {
        try { verified = await validatePolarControl(found.capture_id, restoredLease); }
        catch { restoredLease = ""; }
      }
      if (generation !== restoreGeneration.current) return;
      setConnection(currentConnection);
      setStatusKnown(true);
      setCapture(verified);
      setLease(restoredLease);
      setOwnershipNotice(found && !restoredLease ? copy(
        "Captura sin autorización de control en esta pestaña. Vuelva a la pestaña que la inició; no se detendrá automáticamente. Revise Estación si requiere recuperación.",
        "This tab has no valid control lease. Return to the owning browser tab to stop this capture; it will not be stopped automatically. Check Station for recovery status.") : null);
      if (verified) {
        setParticipant(verified.participant_pseudonym);
        setSessionKind(verified.matb_session_kind);
        setSessionId(verified.matb_session_kind === "generic" ? "" : verified.matb_session_id);
        sessionStorage.setItem("polar.selected", verified.capture_id);
        const rest = sessionStorage.getItem(`polar.rest.${verified.capture_id}`);
        if (rest === 'TASK_PRE' || rest === 'PRE_REST_SEATED' || rest === 'PRE_REST_SEATED_5MIN') setRestContext(rest);
      }
    } catch {
      if (generation === restoreGeneration.current) {
        setStatusKnown(false);
        setError(copy("No se pudo comprobar la captura. Actualice el estado antes de preparar otra.", "Capture status could not be checked. Refresh status before preparing another recording."));
      }
    } finally {
      if (generation === restoreGeneration.current) setRestoring(false);
    }
  }, [copy, assigned.identity, assigned.attempt]);

  useEffect(() => {
    void refreshCapture();
    const timer = setInterval(() => { void refreshCapture(); }, 5000);
    return () => { clearInterval(timer); restoreGeneration.current += 1; };
  }, [refreshCapture]);

  const report = useCallback((event: PolarEvent) => {
    lastSequence.current = Math.max(lastSequence.current, event.sequence);
    if (event.event_type === "hr") {
      setHeartRate(numberValue(event.payload.heart_rate_bpm));
      const intervals = Array.isArray(event.payload.rr_ms) ? event.payload.rr_ms : [];
      setRr(numberValue(intervals.at(-1)));
    } else if (event.event_type === "quality") {
      setQuality(event.payload);
    } else if (event.event_type === "gap") {
      setGaps((value) => value + 1);
    } else if (event.event_type === "marker") {
      setLastMarker(typeof event.payload.label === "string" ? event.payload.label : null);
    } else if (event.event_type === "preview" && event.payload.stream === "ecg") {
      const minimum = numberValue(event.payload.minimum_uv);
      const maximum = numberValue(event.payload.maximum_uv);
      if (minimum !== null && maximum !== null) setEcg((value) => [...value.slice(-59), { minimum, maximum }]);
    } else if (event.event_type === "preview" && event.payload.stream === "acc") {
      const magnitude = numberValue(event.payload.mean_vector_magnitude_mg);
      if (magnitude !== null) setAcc((value) => [...value.slice(-59), magnitude]);
    }
  }, []);

  useEffect(() => {
    lastSequence.current = 0;
    setHeartRate(null); setRr(null); setEcg([]); setAcc([]); setQuality({}); setGaps(0); setLastMarker(null); setAnalysis(null);
  }, [captureId]);

  useEffect(() => {
    if (!captureId || !lease) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    void openPolarStream(captureId, lease, lastSequence.current, event => { if (!disposed && event.capture_id === captureId) report(event); }, value => { if (!disposed && value.capture_id === captureId) setCapture(value); })
      .then((value) => { if (disposed) value.close(); else socket = value; })
      .catch((reason: unknown) => { if (!disposed) setError(reason instanceof Error ? reason.message : "Monitor unavailable"); });
    return () => { disposed = true; socket?.close(); };
  }, [captureId, lease, report]);

  async function run(action: () => Promise<void>) {
    if (actionPending.current) return;
    actionPending.current = true; restoreGeneration.current += 1;
    setBusy(true); setError(null); setNotice(null);
    try { await action(); }
    catch (reason: unknown) { setError(experimentErrorMessage(reason, copy)); }
    finally { actionPending.current = false; setBusy(false); setConnectionStep(null); }
  }

  function clearFinishedCapture(clearParticipant = false) {
    restoreGeneration.current += 1;
    if (capture) setPreviousCapture({ capture, lease });
    sessionStorage.setItem("polar.selected", "");
    setCapture(null); setLease(""); setAnalysis(null); setOwnershipNotice(null);
    setSessionId(""); setSessionKind("generic");
    if (clearParticipant) setParticipant("");
  }

  async function connectDevice(device: PolarDevice) {
    setConnectionStep("connecting");
    setDevices([]); // A connection attempt consumes the discovery token.
    const capabilities = await connectPolar(device.device_token);
    setConnection({ connected: true, device_alias: capabilities.device_alias, capabilities });
    setNotice(copy("H10 conectado. Compruebe la persona seleccionada y pulse Preparar.", "H10 connected. Check the selected participant and press Prepare."));
  }

  async function findAndConnect() {
    if (!statusKnown || restoring || (capture && !["complete", "failed"].includes(capture.lifecycle))) return;
    await run(async () => {
      if (connection.connected) {
        setConnectionStep("switching");
        setConnection(await disconnectPolar());
        if (!assigned.context) setParticipant("");
      }
      if (capture && !assigned.context) clearFinishedCapture(true);
      setDevices([]);
      setConnectionStep("searching");
      const found = await scanPolar(8);
      setDevices(found);
      if (found.length === 1 && found[0].connectable !== false) {
        await connectDevice(found[0]);
      } else {
        setNotice(found.length
          ? copy("Se encontraron bandas. Elija la que ha identificado para esta persona; si no está seguro, deje activa solo esa banda y vuelva a buscar.", "Straps found. Choose the one identified for this participant; if unsure, leave only that strap active and search again.")
          : copy("No apareció ningún H10. Humedezca los electrodos, ajuste la banda al pecho y cierre otras apps que la usen. Acerque la banda y vuelva a buscar.", "No H10 appeared. Wet the electrodes, fit the chest strap and close other apps using it. Bring it closer and search again."));
      }
    });
  }

  async function connect(device: PolarDevice) {
    if (!statusKnown || restoring || connection.connected || (capture && !["complete", "failed"].includes(capture.lifecycle))) return;
    await run(() => connectDevice(device));
  }

  async function prepare() {
    if (!purpose || !participantAvailable) return;
    await run(async () => {
      const admitted = purpose === 'study' ? await admission.admit() : null;
      if(purpose === 'study' && !admitted) throw Object.assign(new Error('Assigned assessment required'), { code: 'study_assignment_required' });
      const prepared = await createPolarCapture({ attempt_id:admitted?.attemptId,
        execution_purpose: purpose,
        participant_pseudonym: participant,
        matb_session_kind: sessionKind,
        matb_session_id: sessionKind === "generic" ? undefined : sessionId,
        settings: { ecg_sample_rate_hz: 130, ecg_resolution_bits: 14, acc_sample_rate_hz: accRate, acc_resolution_bits: 16, acc_range_g: accRange },
      });
      setCapture(prepared.capture);
      setLease(prepared.controller_lease);
      setOwnershipNotice(null);
      sessionStorage.setItem("polar.selected", prepared.capture.capture_id);
      sessionStorage.setItem(`polar.controller.${prepared.capture.capture_id}`, prepared.controller_lease);
      if (assigned.attempt) sessionStorage.setItem(`polar.attempt.${assigned.attempt.id}`, prepared.capture.capture_id);
      sessionStorage.setItem(`polar.rest.${prepared.capture.capture_id}`, restContext);
      const url = new URL(window.location.href); url.searchParams.set('capture', prepared.capture.capture_id);
      window.history.replaceState({}, '', url);
      lastSequence.current = 0; setHeartRate(null); setRr(null); setQuality({}); setEcg([]); setAcc([]); setGaps(0); setAnalysis(null);
      setNotice(purpose === "practice" || sessionKind === "generic"
        ? copy("Registro preparado. Puede iniciarlo sin una prueba activa.", "Recording prepared. You can start it without an active test.")
        : copy("Captura preparada. Iníciela durante READY.", "Capture prepared. Start it while the task is READY."));
    });
  }

  async function start() {
    if (!capture) return;
    await run(async () => {
      setCapture(await startPolarCapture(capture.capture_id, lease));
      const label = preRest ? (baselineMinutes === 5 ? 'PRE_REST_SEATED_5MIN' : 'PRE_REST_SEATED') : assigned.context?.phase === 'TASK' ? 'TASK' : 'TASK_PRE';
      await addPolarMarker(capture.capture_id, lease, label);
      setLastMarker(label);
      setNow(Date.now());
      setNotice(preRest
        ? `${copy('Basal PRE iniciado tras ≥5 min de adaptación. Duración de registro:', 'PRE baseline started after ≥5 min adaptation. Recording duration:')} ${baselineMinutes} min.`
        : copy('Registro de tarea iniciado. Antes del primer bloque mantenga 5 minutos de reposo sentado.', 'Task recording started. Before the first block maintain 5 minutes of seated rest.'));
    });
  }

  async function stop() {
    if (!capture) return;
    await run(async () => {
      setCapture(await stopPolarCapture(capture.capture_id, lease));
      try { setAnalysis(await getPolarAnalysis(capture.capture_id, lease)); }
      catch { setAnalysis(null); }
      setNotice(copy("Captura finalizada. Revise brechas antes del análisis.", "Capture finalized. Review gaps before analysis."));
    });
  }

  const metrics = {
    rmssd: numberValue(quality.rmssd_ms),
    ln: numberValue(quality.ln_rmssd),
    pnn50: numberValue(quality.pnn50_percent),
    sqi: numberValue(quality.sqi),
  };
  const capturing = capture?.lifecycle === "capturing";
  const participantAvailable = Boolean(participants?.some((person) => person.id === participant));
  const activeCapture = !!capture && ["starting", "capturing", "stopping"].includes(capture.lifecycle);
  const settings = capture?.resolved_settings ?? capture?.requested_settings;
  const phaseResponses = analysis?.valid ? analysis.workload_responses.filter((response) => response.valid) : [];
  const preRest = assigned.context?.phase === 'PRE_REST_SEATED' || (!assigned.context && restContext.startsWith('PRE_REST_SEATED'));
  const baselineMinutes = (assigned.context ? assigned.context.condition_by_arm[assigned.context.arm]?.endsWith('_5MIN') : restContext.endsWith('_5MIN')) ? 5 : 10;
  const startedAt = capture?.started_at_utc;
  const elapsed = startedAt ? Math.max(0, Math.floor(((capture.ended_at_utc ? Date.parse(capture.ended_at_utc.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(capture.ended_at_utc) ? capture.ended_at_utc : `${capture.ended_at_utc}Z`) : now) - Date.parse(/[Zz]|[+-]\d{2}:\d{2}$/.test(startedAt) ? startedAt : `${startedAt}Z`)) / 1000)) : 0;

  return <div className="space-y-6">
    {purpose==='study'&&<Link className="underline" href="/study/assignments">{copy("Seleccionar evaluación asignada","Select assigned assessment")}</Link>}
    <ExperimentGuide id="physiology" />
    <PageHeader
      kicker={copy("Fisiología experimental", "Experimental physiology")}
      title="Polar H10 · ECG + ACC + HR/RR"
      description={copy(
        "Adquisición Bluetooth local para investigación. Los descriptores HRV son descriptivos y no generan clasificaciones de carga, aptitud ni alertas operacionales.",
        "Local Bluetooth research acquisition. HRV descriptors are descriptive and do not produce workload classes, fitness conclusions, or operational alerts.",
      )}
      stats={[
        { label: "HR", value: heartRate === null ? "—" : `${heartRate}` },
        { label: "RR ms", value: rr === null ? "—" : rr.toFixed(0) },
        { label: copy("Brechas", "Gaps"), value: capture?.gap_count ?? gaps },
      ]}
    />

    {error && <p role="alert" className="border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>}
    {ownershipNotice && <p role="alert" className="border border-warning p-3">{ownershipNotice} <Link href="/station">{copy("Abrir Estación", "Open Station")}</Link></p>}
    <div className="flex flex-wrap items-center gap-3"><Button variant="outline" disabled={busy || restoring} onClick={() => void refreshCapture()}>{copy("Actualizar estado", "Refresh status")}</Button><Link href="/station">{copy("Estado y recuperación de Estación", "Station status and recovery")}</Link><span>{copy("Propósito", "Purpose")}: {capture?.execution_purpose ?? purpose ?? copy("Seleccione práctica o estudio", "Select practice or study")}</span></div>
    <div className="flex flex-wrap items-center gap-3">
            {capture?.lifecycle === "created" && <Button disabled={busy || !lease} onClick={() => void start()}><Play className="mr-2 h-4 w-4" />{copy("Iniciar grabación", "Start recording")}</Button>}
            {activeCapture && <Button variant="destructive" disabled={busy || !lease || capture?.lifecycle === "stopping"} onClick={() => void stop()}><Square className="mr-2 h-4 w-4" />{copy("Detener y finalizar", "Stop and finalize")}</Button>}
          {capture && <div className="border border-white/10 p-3 font-mono text-xs text-muted-foreground"><p>{capture.capture_id}</p><p>{capture.participant_pseudonym} · {capture.execution_purpose} · {capture.matb_session_kind === "generic" ? copy("Independiente", "Standalone") : `${capture.matb_session_kind}: ${capture.matb_session_id}`}</p><p className="mt-1">{capture.lifecycle} · ECG {settings?.ecg_sample_rate_hz} Hz · ACC {settings?.acc_sample_rate_hz} Hz ±{settings?.acc_range_g}G</p></div>}
    </div>
    {notice && <p role="status" className="border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">{notice}</p>}
    {assigned.context && <Link className="block underline" href={`/study/participant?assignment=${assigned.context.assignment_id}`}>{copy('Volver a la visita MATB · la captura continúa hasta detenerla', 'Return to the MATB visit · capture continues until stopped')}</Link>}
    <p className="text-sm text-muted-foreground">{copy('Un H10 por estación. Compruebe la correspondencia persona–banda antes de cada registro; los alias de búsqueda no son identificadores permanentes.', 'One H10 per station. Check the person–strap pairing before every recording; scan aliases are not permanent identifiers.')}</p>

    <Card className="border-info/30 bg-info/5">
      <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Instrucciones para el participante", "Participant instructions")}</CardTitle><CardDescription>{copy("Para una línea basal de reposo, siga estas instrucciones. Para otras grabaciones, siga el protocolo asignado.", "For a resting baseline, follow these instructions. For other recordings, follow the assigned protocol.")}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <InstructionAudio src={`/audio/instructions/polar-${locale === "en" ? "en" : "es"}.mp3`} label={copy("Escuchar instrucciones Polar H10", "Listen to Polar H10 instructions")} unavailableLabel={copy("Audio no disponible", "Audio unavailable")} />
        <ol className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <li className="metric-tile"><strong className="text-info">1.</strong> {copy("Permita que el investigador coloque y compruebe el sensor.", "Allow the researcher to fit and check the sensor.")}</li>
          <li className="metric-tile"><strong className="text-info">2.</strong> {copy("Siéntese con espalda apoyada, pies en el suelo y manos quietas.", "Sit with back supported, feet on the floor, and hands still.")}</li>
          <li className="metric-tile"><strong className="text-info">3.</strong> {preRest ? `${copy('Tras ≥5 min de adaptación, registre en silencio y respirando espontáneamente:', 'After ≥5 min adaptation, record silently with spontaneous breathing:')} ${baselineMinutes} min.` : copy("Respire normalmente y evite hablar durante cinco minutos.", "Breathe normally and avoid speaking for five minutes.")}</li>
          <li className="metric-tile"><strong className="text-info">4.</strong> {copy("Avise si siente incomodidad. Espere la confirmación antes de moverse.", "Report discomfort. Wait for confirmation before moving.")}</li>
        </ol>
      </CardContent>
    </Card>

    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <PolarDevicePanel connection={connection} devices={devices} busy={busy} step={connectionStep}
        locked={restoring || !statusKnown || Boolean(capture && !["complete", "failed"].includes(capture.lifecycle))}
        copy={copy} onSearch={() => void findAndConnect()} onConnect={(device) => void connect(device)}
        onDisconnect={() => void run(async () => { setConnection(await disconnectPolar()); setDevices([]); })} />

      <Card>
        <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Preparar captura", "Prepare capture")}</CardTitle><CardDescription>{copy("La grabación independiente no requiere una prueba MATB. El modo estudio conserva la evaluación de fisiología asignada.", "Standalone recording needs no MATB test. Study mode retains the assigned physiology assessment.")}</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          {!capture && <p className="text-sm text-muted-foreground">{copy("Use su pseudónimo registrado.", "Use your registered pseudonym.")} <Link className="underline" href="/participants">{copy("Abrir Participantes", "Open Participants")}</Link></p>}
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="polar-participant">{copy("Pseudónimo", "Pseudonym")}</Label>
              <select id="polar-participant" className="native-select w-full" value={participantAvailable ? participant : ""} onChange={(event) => setParticipant(event.target.value)} disabled={Boolean(capture) || Boolean(assigned.context) || participants === null}>
                <option value="">{participants === null ? copy("Cargando participantes…", "Loading participants…") : copy("Seleccione un participante", "Select a participant")}</option>
                {participants?.map((person) => <option key={person.id} value={person.id}>{person.callsign ? `${person.id} · ${person.callsign}` : person.id}</option>)}
              </select>
              {participantLoadFailed && <p role="alert" className="text-sm text-danger">{copy("No se pudo cargar la lista de participantes. Vuelva a intentarlo.", "Could not load participants. Please try again.")}</p>}
              {participants?.length === 0 && <p className="text-sm text-muted-foreground">{copy("Registre un participante antes de preparar la captura.", "Register a participant before preparing the recording.")}</p>}
              {participants && participant && !participantAvailable && <p role="alert" className="text-sm text-danger">{copy("El participante seleccionado no está disponible. Seleccione un participante activo o revise su asignación.", "The selected participant is unavailable. Select an active participant or review the assignment.")}</p>}
              {(participantLoadFailed || participants?.length === 0 || (participants && participant && !participantAvailable)) && <div className="flex flex-wrap items-center gap-3 text-sm">
                <Link className="underline" href="/participants">{copy("Abrir participantes", "Open participants")}</Link>
                <Button variant="outline" size="sm" disabled={busy || Boolean(capture)} onClick={() => setParticipantReload((value) => value + 1)}>{copy("Recargar participantes", "Reload participants")}</Button>
              </div>}
            </div>
            <div className="space-y-2"><Label htmlFor="polar-session-kind">{copy("Asociación", "Association")}</Label><select id="polar-session-kind" className="native-select w-full" value={sessionKind} onChange={(event) => setSessionKind(event.target.value as PolarCapture["matb_session_kind"])} disabled={Boolean(capture) || Boolean(assigned.context)}><option value="openmatb">OpenMATB</option><option value="generic">{copy("Grabación independiente", "Standalone recording")}</option><option value="liftoff">Liftoff</option><option value="suas">sUAS</option></select></div>
            {sessionKind !== "generic" && <div className="space-y-2 sm:col-span-2"><Label htmlFor="polar-session-id">{copy("ID de sesión MATB", "MATB session ID")}</Label><Input id="polar-session-id" value={sessionId} onChange={(event) => setSessionId(event.target.value)} disabled={Boolean(capture) || Boolean(assigned.context)} placeholder={copy("ID exacto de sesión asociada", "Exact associated session ID")} /></div>}
            <div className="space-y-2"><Label htmlFor="polar-acc-rate">ACC Hz</Label><select id="polar-acc-rate" className="native-select w-full" value={accRate} onChange={(event) => setAccRate(Number(event.target.value) as AccRate)} disabled={Boolean(capture) || Boolean(assigned.context)}>{[25, 50, 100, 200].map((value) => <option key={value}>{value}</option>)}</select></div>
            <div className="space-y-2"><Label htmlFor="polar-acc-range">ACC ±G</Label><select id="polar-acc-range" className="native-select w-full" value={accRange} onChange={(event) => setAccRange(Number(event.target.value) as AccRange)} disabled={Boolean(capture) || Boolean(assigned.context)}>{[2, 4, 8].map((value) => <option key={value}>{value}</option>)}</select></div>
          </div>
          <div className="flex flex-wrap gap-2">
            {assigned.context?.accompanying_key && !capture && <label>{copy('Sesión acompañada exacta','Exact accompanying session')}<select className="native-select block" value={sessionId} onChange={e=>{const source=companionSources.find(s=>s.id===e.target.value);setSessionId(e.target.value);setSessionKind(source?.table==='openmatb_suite_session'?'openmatb':source?.table==='liftoff_session'?'liftoff':'suas');}}><option value="">—</option>{companionSources.map(s=><option key={s.id} value={s.id}>{s.table} · {s.id}</option>)}</select></label>}
            {!capture && <Button disabled={!purpose || busy || restoring || !statusKnown || !connection.connected || (sessionKind !== "generic" && !sessionId) || !participantAvailable || (purpose === "study" && !assigned.context)} onClick={() => void prepare()}>{copy("Preparar", "Prepare")}</Button>}
            {capture && capture.execution_purpose !== "practice" && ["finalized", "incomplete"].includes(capture.artifact_state) && <Button variant="outline" disabled={busy || !lease} onClick={() => void run(() => downloadPolarBundle(capture.capture_id, lease))}><Download className="mr-2 h-4 w-4" />{copy("Descargar paquete", "Download bundle")}</Button>}
            {capture?.artifact_state === "finalized" && capture.matb_session_kind !== "generic" && purpose && <Button asChild><Link href={withExecutionPurpose("/mission/setup#briefing", purpose)}>{copy("Continuar a instrucciones de misión", "Continue to mission briefing")}</Link></Button>}
          </div>
          {!assigned.context && capture && ["complete", "failed"].includes(capture.lifecycle) && <Button variant="outline" disabled={busy} onClick={() => clearFinishedCapture()}>{copy("Preparar otra grabación", "Prepare another recording")}</Button>}
          {!assigned.context && !capture && <label className="block text-sm">{copy('Condición de reposo', 'Rest condition')}<select className="native-select mt-2 block" value={restContext} onChange={event => setRestContext(event.target.value as typeof restContext)}><option value="TASK_PRE">{copy('Referencia pre-tarea · 5 min', 'Pre-task reference · 5 min')}</option><option value="PRE_REST_SEATED_5MIN">{copy('Basal PRE abreviado · 5 min tras ≥5 min de adaptación', 'Abbreviated PRE baseline · 5 min after ≥5 min adaptation')}</option><option value="PRE_REST_SEATED">{copy('Basal PRE sentado · 10 min tras ≥5 min de adaptación', 'Seated PRE baseline · 10 min after ≥5 min adaptation')}</option></select></label>}
          {capture && <div className="border border-white/10 p-3 text-sm">{startedAt && <p role="timer" className="mt-3 text-3xl tabular-nums">{Math.floor(elapsed / 60)}:{String(elapsed % 60).padStart(2, '0')}</p>}{preRest && <p>PRE: {baselineMinutes} min. {baselineMinutes === 5 ? copy('Modalidad abreviada; sin segundo segmento de respaldo.', 'Abbreviated protocol; no second backup segment.') : 'A = 0–5 min; B = 5–10 min.'} {copy('El reloj indica duración, no calidad de señal. Detenga el registro al terminar.', 'The timer indicates duration, not signal quality. Stop recording when finished.')}</p>}</div>}
        </CardContent>
      </Card>
    </div>

    <div className="grid gap-6 lg:grid-cols-2">
      <Card><CardHeader><CardTitle className="font-display text-lg uppercase tracking-wide">ECG · µV</CardTitle><CardDescription>{copy("Envolvente decimada para supervisión; los 130 Hz completos permanecen en Parquet.", "Decimated monitoring envelope; full 130 Hz data remains in Parquet.")}</CardDescription></CardHeader><CardContent className="text-info"><Envelope points={ecg} /></CardContent></Card>
      <Card><CardHeader><CardTitle className="font-display text-lg uppercase tracking-wide">ACC · mG</CardTitle><CardDescription>{copy("Magnitud vectorial por paquete; x/y/z completos permanecen en Parquet.", "Packet vector magnitude; full x/y/z data remains in Parquet.")}</CardDescription></CardHeader><CardContent className="text-warning"><AccTrace values={acc} /></CardContent></Card>
    </div>

    <Card>
      <CardHeader><CardTitle className="flex items-center gap-2 font-display text-xl uppercase tracking-wide"><Activity className="h-5 w-5" />HRV descriptiva en vivo</CardTitle><CardDescription>{copy("Ventana móvil de 60 s. SDNN se etiqueta como ultracorta y exploratoria; la comparación principal usa fases estandarizadas de cinco minutos.", "Rolling 60 s window. SDNN is ultra-short and exploratory; primary comparison uses standardized five-minute phases.")}</CardDescription></CardHeader>
      <CardContent className="space-y-5">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          {[{ label: "RMSSD ms", value: metrics.rmssd }, { label: "lnRMSSD", value: metrics.ln }, { label: "pNN50 %", value: metrics.pnn50 }, { label: "SQI", value: metrics.sqi }].map((item) => <div className="metric-tile" key={item.label}><p className="page-kicker">{item.label}</p><p className="mt-2 font-display text-2xl">{item.value === null ? "—" : item.value.toFixed(2)}</p></div>)}
        </div>
        <div className="flex flex-wrap gap-2">
          {(["BASELINE", "PRACTICE", "LOW", "MEDIUM", "HIGH", "RECOVERY"] as const).map((label) => <Button key={label} size="sm" variant={lastMarker === label ? "secondary" : "outline"} disabled={!capturing || busy || !lease} onClick={() => capture && void run(async () => { await addPolarMarker(capture.capture_id, lease, label); setLastMarker(label); })}>{label}</Button>)}
        </div>
        <p className="text-xs leading-5 text-muted-foreground">{copy("LOW, MEDIUM, HIGH y RECOVERY se insertan automáticamente desde el ciclo de vida OpenMATB cuando la captura está vinculada. Los botones permiten marcas supervisadas. Ninguna marca de software se presenta como inicio físico exacto del estímulo.", "LOW, MEDIUM, HIGH, and RECOVERY are inserted automatically from the OpenMATB lifecycle when the capture is linked. Buttons allow supervised markers. No software marker is presented as exact physical stimulus onset.")}</p>
      </CardContent>
    </Card>
    {!capture && previousCapture && <details className="rounded border border-white/10 p-4">
      <summary className="cursor-pointer">{copy("Última captura guardada", "Last saved recording")} · {previousCapture.capture.participant_pseudonym}</summary>
      <PolarCaptureReview capture={previousCapture.capture} lease={previousCapture.lease} copy={copy} />
    </details>}
    {capture && <PolarCaptureReview capture={capture} lease={lease} copy={copy} />}
    {phaseResponses.length > 0 && <Card>
      <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Respuesta por fase de cinco minutos", "Five-minute phase response")}</CardTitle><CardDescription>{copy("Comparación descriptiva contra línea base.", "Descriptive comparison with baseline.")}</CardDescription></CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {phaseResponses.map((response) => <div key={response.phase} className="metric-tile">
          <p className="page-kicker">{response.phase}</p>
          <p className="mt-2 text-sm">Î”lnRMSSD <strong>{response.delta_ln_rmssd === null ? "—" : response.delta_ln_rmssd.toFixed(3)}</strong></p>
          <p className="mt-1 text-sm">Î”HR <strong>{response.delta_mean_hr_bpm === null ? "—" : `${response.delta_mean_hr_bpm.toFixed(1)} bpm`}</strong></p>
          <p className="mt-2 font-mono text-[10px] text-muted-foreground">{copy("DESCRIPTIVO", "DESCRIPTIVE")}</p>
        </div>)}
      </CardContent>
    </Card>}
  </div>;
}
