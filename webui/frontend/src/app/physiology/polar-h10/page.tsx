"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Activity, Battery, Bluetooth, Download, Play, Radio, Square, WifiOff } from "lucide-react";

import {useAssignedAttempt} from '@/lib/assigned-attempt';
import {useAssessmentAdmission} from '@/lib/assessment-admission';
import {assignmentDetail} from '@/lib/study';
import { experimentErrorMessage } from "@/lib/experiment-errors";
import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { useExecutionPurpose, withExecutionPurpose } from "@/lib/execution-purpose";
import { useReportExperimentFlow } from "@/lib/experiment-flow";
import { PageHeader } from "@/components/layout/PageHeader";
import { InstructionAudio } from "@/components/instructions/InstructionAudio";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useAppLocale } from "@/lib/i18n";
import {
  addPolarMarker,
  connectPolar,
  createPolarCapture,
  disconnectPolar,
  downloadPolarBundle,
  getPolarConnection,
  getPolarAnalysis,
  listenPolarBroadcast,
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
  const [capture, setCapture] = useState<PolarCapture | null>(null);
  const [lease, setLease] = useState("");
  const [participant, setParticipant] = useState("P01");
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
  const admission = useAssessmentAdmission(assigned.attempt && assigned.context ? {attemptId:assigned.attempt.id, participantId:assigned.context.participant_id, visitId:assigned.context.visit_id, purpose:'study', locale:assigned.context.locale} : null, {runtime:true});
  useEffect(()=>{let active=true; const bound=assigned.context;if(bound){setParticipant(bound.participant_id);const settings=bound.config.settings as {acc_sample_rate_hz:AccRate;acc_range_g:AccRange};setAccRate(settings.acc_sample_rate_hz);setAccRange(settings.acc_range_g);if(!bound.accompanying_key){setSessionKind('generic');setSessionId(bound.occasion_id);}else void assignmentDetail(bound.assignment_id).then(detail=>{if(active)setCompanionSources((detail.attempts[bound.accompanying_key!]??[]).flatMap(a=>a.sources.filter(s=>['openmatb_suite_session','liftoff_session','simulation_session'].includes(s.source_table)).map(s=>({table:s.source_table,id:s.source_id}))));});}return()=>{active=false;};},[assigned.context]);
  const [analysis, setAnalysis] = useState<PolarAnalysis | null>(null);
  const lastSequence = useRef(0);
  const captureId = capture?.capture_id;
  useReportExperimentFlow("physiology", capture?.lifecycle === "capturing" ? "perform" : capture?.lifecycle === "complete" ? "complete" : capture ? "instructions" : "prepare");

  useEffect(() => {
    void getPolarConnection().then(setConnection).catch(() => undefined);
    const query = new URLSearchParams(window.location.search);
    const selectedParticipant = query.get("participant");
    const selectedVisit = query.get("visit");
    if (selectedParticipant && /^P\d{2,6}$/.test(selectedParticipant) && selectedVisit && /^\d+$/.test(selectedVisit)) {
      setParticipant(selectedParticipant);
      setSessionKind("generic");
      setSessionId(`baseline:${selectedParticipant}:V${selectedVisit}`);
    }
  }, []);

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
    if (!captureId || !lease) return;
    let disposed = false;
    let socket: WebSocket | null = null;
    void openPolarStream(captureId, lease, lastSequence.current, report, setCapture)
      .then((value) => { if (disposed) value.close(); else socket = value; })
      .catch((reason: unknown) => { if (!disposed) setError(reason instanceof Error ? reason.message : "Monitor unavailable"); });
    return () => { disposed = true; socket?.close(); };
  }, [captureId, lease, report]);

  async function run(action: () => Promise<void>) {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); }
    catch (reason: unknown) { setError(experimentErrorMessage(reason, copy)); }
    finally { setBusy(false); }
  }

  async function scan(broadcastOnly: boolean) {
    await run(async () => {
      const found = await (broadcastOnly ? listenPolarBroadcast(5) : scanPolar(5));
      setDevices(found);
      setNotice(found.length ? copy("Polar H10 encontrado.", "Polar H10 found.") : copy("No se encontró un H10 durante la búsqueda.", "No H10 was found during the scan."));
    });
  }

  async function connect(device: PolarDevice) {
    await run(async () => {
      const capabilities = await connectPolar(device.device_token);
      setConnection({ connected: true, device_alias: capabilities.device_alias, capabilities });
      setDevices([]);
    });
  }

  async function prepare() {
    if (!purpose) return;
    await run(async () => {
      const admitted = purpose === 'study' ? await admission.admit() : null;
      if(purpose === 'study' && !admitted) throw new Error('Select an assigned assessment at /study/assignments');
      const prepared = await createPolarCapture({ attempt_id:admitted?.attemptId,
        execution_purpose: purpose,
        participant_pseudonym: participant,
        matb_session_kind: purpose === "practice" ? "generic" : sessionKind,
        matb_session_id: purpose === "practice" ? `practice:${participant}` : sessionId || `baseline:${participant}`,
        settings: { ecg_sample_rate_hz: 130, ecg_resolution_bits: 14, acc_sample_rate_hz: accRate, acc_resolution_bits: 16, acc_range_g: accRange },
      });
      setCapture(prepared.capture);
      setLease(prepared.controller_lease);
      sessionStorage.setItem(`polar.controller.${prepared.capture.capture_id}`, prepared.controller_lease);
      setNotice(copy("Captura preparada. Iníciela durante READY.", "Capture prepared. Start it while the task is READY."));
    });
  }

  async function start() {
    if (!capture) return;
    await run(async () => {
      setCapture(await startPolarCapture(capture.capture_id, lease));
      await addPolarMarker(capture.capture_id, lease, "BASELINE");
      setLastMarker("BASELINE");
      setNotice(copy("Línea base iniciada; mantenga cinco minutos en reposo sentado.", "Baseline started; maintain five seated resting minutes."));
    });
  }

  async function stop() {
    if (!capture) return;
    await run(async () => {
      setCapture(await stopPolarCapture(capture.capture_id, lease));
      setAnalysis(await getPolarAnalysis(capture.capture_id, lease));
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
  const settings = capture?.resolved_settings ?? capture?.requested_settings;

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
    {notice && <p role="status" className="border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">{notice}</p>}

    <Card className="border-info/30 bg-info/5">
      <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Instrucciones para el participante", "Participant instructions")}</CardTitle><CardDescription>{copy("Esta línea basal ocurre después de KSS y PVT, antes de las instrucciones de misión.", "This baseline occurs after KSS and PVT, before the mission briefing.")}</CardDescription></CardHeader>
      <CardContent className="space-y-4">
        <InstructionAudio src={`/audio/instructions/polar-${locale === "en" ? "en" : "es"}.mp3`} label={copy("Escuchar instrucciones Polar H10", "Listen to Polar H10 instructions")} unavailableLabel={copy("Audio no disponible", "Audio unavailable")} />
        <ol className="grid gap-3 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <li className="metric-tile"><strong className="text-info">1.</strong> {copy("Permita que el investigador coloque y compruebe el sensor.", "Allow the researcher to fit and check the sensor.")}</li>
          <li className="metric-tile"><strong className="text-info">2.</strong> {copy("Siéntese con espalda apoyada, pies en el suelo y manos quietas.", "Sit with back supported, feet on the floor, and hands still.")}</li>
          <li className="metric-tile"><strong className="text-info">3.</strong> {copy("Respire normalmente y evite hablar durante cinco minutos.", "Breathe normally and avoid speaking for five minutes.")}</li>
          <li className="metric-tile"><strong className="text-info">4.</strong> {copy("Avise si siente incomodidad. Espere la confirmación antes de moverse.", "Report discomfort. Wait for confirmation before moving.")}</li>
        </ol>
      </CardContent>
    </Card>

    <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 font-display text-xl uppercase tracking-wide"><Bluetooth className="h-5 w-5" />{copy("Dispositivo", "Device")}</CardTitle>
          <CardDescription>{copy("La dirección Bluetooth nunca se muestra ni se guarda.", "The Bluetooth address is never shown or stored.")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <Button disabled={busy || connection.connected} onClick={() => void scan(false)}><Bluetooth className="mr-2 h-4 w-4" />{copy("Buscar H10", "Scan for H10")}</Button>
            <Button variant="outline" disabled={busy || connection.connected} onClick={() => void scan(true)}><Radio className="mr-2 h-4 w-4" />{copy("Escuchar HR emitida", "Listen for broadcast HR")}</Button>
            <Button variant="outline" disabled={busy || !connection.connected || capturing} onClick={() => void run(async () => { setConnection(await disconnectPolar()); setCapture(null); setLease(""); })}><WifiOff className="mr-2 h-4 w-4" />{copy("Desconectar", "Disconnect")}</Button>
          </div>
          {devices.map((device) => <button key={device.device_token} type="button" disabled={device.connectable === false || busy} onClick={() => void connect(device)} className="w-full border border-white/10 p-4 text-left transition hover:border-white/30 disabled:opacity-50">
            <div className="flex items-center justify-between gap-3"><span className="font-semibold">{device.alias}</span><Badge variant={device.connectable === false ? "danger" : "success"}>{device.connectable === false ? copy("No conectable", "Not connectable") : copy("Disponible", "Available")}</Badge></div>
            <div className="mt-2 flex gap-4 font-mono text-xs text-muted-foreground"><span>RSSI {device.rssi ?? "—"}</span><span>HR broadcast {device.broadcast_hr_bpm ?? "—"}</span></div>
          </button>)}
          {connection.capabilities && <div className="grid gap-3 border border-white/10 p-4 sm:grid-cols-2">
            <div><p className="page-kicker">{connection.device_alias}</p><p className="mt-2 text-sm">Firmware {connection.capabilities.firmware ?? "—"}</p></div>
            <div className="flex items-center gap-2"><Battery className="h-5 w-5" /><span className="font-display text-2xl">{connection.capabilities.battery_percent ?? "—"}%</span></div>
            <p className="text-xs text-muted-foreground">ECG {connection.capabilities.ecg_sample_rates_hz.join("/")} Hz · ACC {connection.capabilities.acc_sample_rates_hz.join("/")} Hz · ±{connection.capabilities.acc_ranges_g.join("/±")}G</p>
            <p className="text-xs text-warning">{copy("Memoria interna: pendiente de cualificación.", "Internal recording: qualification pending.")}</p>
          </div>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Preparar captura", "Prepare capture")}</CardTitle><CardDescription>{copy("Para OpenMATB, inicie la captura cuando la sesión esté en READY.", "For OpenMATB, start capture while the session is READY.")}</CardDescription></CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2"><Label htmlFor="polar-participant">{copy("Pseudónimo", "Pseudonym")}</Label><Input id="polar-participant" value={participant} onChange={(event) => setParticipant(event.target.value.toUpperCase())} disabled={Boolean(capture)} /></div>
            <div className="space-y-2"><Label htmlFor="polar-session-kind">{copy("Flujo MATB", "MATB workflow")}</Label><select id="polar-session-kind" className="native-select w-full" value={sessionKind} onChange={(event) => setSessionKind(event.target.value as PolarCapture["matb_session_kind"])} disabled={Boolean(capture)}><option value="openmatb">OpenMATB</option><option value="generic">Generic</option><option value="liftoff">Liftoff</option><option value="suas">sUAS</option></select></div>
            <div className="space-y-2 sm:col-span-2"><Label htmlFor="polar-session-id">ID de sesión</Label><Input id="polar-session-id" value={sessionId} onChange={(event) => setSessionId(event.target.value)} disabled={Boolean(capture)} placeholder="OpenMATB session UUID" /></div>
            <div className="space-y-2"><Label htmlFor="polar-acc-rate">ACC Hz</Label><select id="polar-acc-rate" className="native-select w-full" value={accRate} onChange={(event) => setAccRate(Number(event.target.value) as AccRate)} disabled={Boolean(capture)}>{[25, 50, 100, 200].map((value) => <option key={value}>{value}</option>)}</select></div>
            <div className="space-y-2"><Label htmlFor="polar-acc-range">ACC ±G</Label><select id="polar-acc-range" className="native-select w-full" value={accRange} onChange={(event) => setAccRange(Number(event.target.value) as AccRange)} disabled={Boolean(capture)}>{[2, 4, 8].map((value) => <option key={value}>{value}</option>)}</select></div>
          </div>
          <div className="flex flex-wrap gap-2">
            {assigned.context?.accompanying_key && !capture && <label>{copy('Sesión acompañada exacta','Exact accompanying session')}<select className="native-select block" value={sessionId} onChange={e=>{const source=companionSources.find(s=>s.id===e.target.value);setSessionId(e.target.value);setSessionKind(source?.table==='openmatb_suite_session'?'openmatb':source?.table==='liftoff_session'?'liftoff':'suas');}}><option value="">—</option>{companionSources.map(s=><option key={s.id} value={s.id}>{s.table} · {s.id}</option>)}</select></label>}
            {!capture && <Button disabled={!purpose || busy || !connection.connected || !sessionId || !participant} onClick={() => void prepare()}>{copy("Preparar", "Prepare")}</Button>}
            {capture?.lifecycle === "created" && <Button disabled={busy} onClick={() => void start()}><Play className="mr-2 h-4 w-4" />{copy("Iniciar línea base", "Start baseline")}</Button>}
            {capturing && <Button variant="destructive" disabled={busy} onClick={() => void stop()}><Square className="mr-2 h-4 w-4" />{copy("Detener y finalizar", "Stop and finalize")}</Button>}
            {capture && capture.execution_purpose !== "practice" && ["finalized", "incomplete"].includes(capture.artifact_state) && <Button variant="outline" disabled={busy} onClick={() => void run(() => downloadPolarBundle(capture.capture_id, lease))}><Download className="mr-2 h-4 w-4" />{copy("Descargar paquete", "Download bundle")}</Button>}
            {capture?.artifact_state === "finalized" && purpose && <Button asChild><Link href={withExecutionPurpose("/mission/setup#briefing", purpose)}>{copy("Continuar a instrucciones de misión", "Continue to mission briefing")}</Link></Button>}
          </div>
          {capture && <div className="border border-white/10 p-3 font-mono text-xs text-muted-foreground"><p>{capture.capture_id}</p><p className="mt-1">{capture.lifecycle} · ECG {settings?.ecg_sample_rate_hz} Hz · ACC {settings?.acc_sample_rate_hz} Hz ±{settings?.acc_range_g}G</p></div>}
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
          {(["BASELINE", "PRACTICE", "LOW", "MEDIUM", "HIGH", "RECOVERY"] as const).map((label) => <Button key={label} size="sm" variant={lastMarker === label ? "secondary" : "outline"} disabled={!capturing || busy} onClick={() => capture && void run(async () => { await addPolarMarker(capture.capture_id, lease, label); setLastMarker(label); })}>{label}</Button>)}
        </div>
        <p className="text-xs leading-5 text-muted-foreground">{copy("LOW, MEDIUM, HIGH y RECOVERY se insertan automáticamente desde el ciclo de vida OpenMATB cuando la captura está vinculada. Los botones permiten marcas supervisadas. Ninguna marca de software se presenta como inicio físico exacto del estímulo.", "LOW, MEDIUM, HIGH, and RECOVERY are inserted automatically from the OpenMATB lifecycle when the capture is linked. Buttons allow supervised markers. No software marker is presented as exact physical stimulus onset.")}</p>
      </CardContent>
    </Card>
    {analysis && <Card>
      <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Respuesta por fase de cinco minutos", "Five-minute phase response")}</CardTitle><CardDescription>{analysis.valid ? copy("Comparación descriptiva contra línea base.", "Descriptive comparison with baseline.") : `${copy("No estimable", "Not estimable")}: ${analysis.reason}`}</CardDescription></CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {analysis.workload_responses.map((response) => <div key={response.phase} className="metric-tile">
          <p className="page-kicker">{response.phase}</p>
          <p className="mt-2 text-sm">Î”lnRMSSD <strong>{response.delta_ln_rmssd === null ? "—" : response.delta_ln_rmssd.toFixed(3)}</strong></p>
          <p className="mt-1 text-sm">Î”HR <strong>{response.delta_mean_hr_bpm === null ? "—" : `${response.delta_mean_hr_bpm.toFixed(1)} bpm`}</strong></p>
          <p className="mt-2 font-mono text-[10px] text-muted-foreground">{response.valid ? copy("DESCRIPTIVO", "DESCRIPTIVE") : response.reason}</p>
        </div>)}
      </CardContent>
    </Card>}
  </div>;
}
