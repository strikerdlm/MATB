"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, AlertCircle } from "lucide-react";
import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useExecutionPurpose } from "@/lib/execution-purpose";
import { useReportExperimentFlow } from "@/lib/experiment-flow";
import { listParticipants, listVisits } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";
import {useAssignedAttempt} from '@/lib/assigned-attempt';
import {useAssessmentAdmission} from '@/lib/assessment-admission';
import { createOpenMatbSession, getOpenMatbReadiness, getOpenMatbDisplays, listOpenMatbInstructions,
  listOpenMatbPresets, listOpenMatbVisualProfiles, storeOpenMatbCredentials } from "@/lib/openmatb/api";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import { saveParticipantWindowState } from "@/lib/openmatb/participant-window";
import { isParticipantId } from "@/lib/participant-id";
import type { Participant, Visit } from "@/types";
import type { OpenMatbDisplay, OpenMatbInstructionProtocol, OpenMatbPresetSet, OpenMatbReadiness, OpenMatbVisualProfile } from "@/types/openmatb";

const CHECKS: Record<string, [string, string, string, string]> = {
  python: ["Python compatible", "Compatible Python", "Ejecute el preparador de la estación para configurar Python.", "Run the station preparation launcher to configure Python."],
  runtime_dependencies: ["Dependencias nativas", "Native dependencies", "Ejecute el preparador de la estación para instalar las dependencias.", "Run the station preparation launcher to install the dependencies."],
  openmatb: ["Aplicación OpenMATB", "OpenMATB application", "Restaure OpenMATB con el preparador de la estación.", "Restore OpenMATB with the station preparation launcher."],
  questionnaires_es: ["Cuestionarios en español", "Spanish questionnaires", "Restaure los cuestionarios con el preparador de la estación.", "Restore the questionnaires with the station preparation launcher."],
  graphical_display: ["Escritorio gráfico", "Graphical desktop", "Conecte una pantalla y abra una sesión de escritorio en la estación.", "Connect a display and open a desktop session on the station."],
  native_process_clear: ["Tarea anterior cerrada", "Previous task closed", "Cierre la ventana nativa de la conexión anterior.", "Close the native task window from the previous connection."],
};

function SetupContent() {
  const router = useRouter();
  const preferred = useAppLocale();
  const assigned = useAssignedAttempt();
  const locale = assigned.context?.locale ?? preferred.locale;
  const copy = useCallback((es:string,en:string) => locale === 'en' ? en : es, [locale]);
  const purpose = useExecutionPurpose();
  useReportExperimentFlow("openmatb", "prepare");
  const copyRef = useRef(copy); copyRef.current = copy;
  const stationRequest = useRef(0);
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [presets, setPresets] = useState<OpenMatbPresetSet[]>([]);
  const [instructions, setInstructions] = useState<OpenMatbInstructionProtocol[]>([]);
  const [visualProfiles, setVisualProfiles] = useState<OpenMatbVisualProfile[]>([]);
  const [readiness, setReadiness] = useState<OpenMatbReadiness | null>(null);
  const [displays, setDisplays] = useState<OpenMatbDisplay[]>([]);
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [presetKey, setPresetKey] = useState("");
  const [instructionKey, setInstructionKey] = useState("");
  const [visualProfileKey, setVisualProfileKey] = useState("");
  const [displayIndex, setDisplayIndex] = useState<number | null>(null);
  const [acknowledged, setAcknowledged] = useState(false);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stationError, setStationError] = useState<string | null>(null);

  useEffect(() => {if(assigned.context) setParticipantId(assigned.context.participant_id);}, [assigned.context]);
  const admission = useAssessmentAdmission(assigned.attempt && assigned.context ? {attemptId:assigned.attempt.id, participantId:assigned.context.participant_id, visitId:assigned.context.visit_id, purpose:assigned.attempt.execution_purpose, locale:assigned.context.locale} : null, {runtime:true});
  const frozen = assigned.context?.config as {preset?:{id:string;version:string};instructions?:{id:string;version:string};visual?:{id:string;version:string}} | undefined;
  const checkStation = useCallback(async () => {
    const revision = ++stationRequest.current;
    setChecking(true);
    const [readyResult, displayResult] = await Promise.allSettled([getOpenMatbReadiness(), getOpenMatbDisplays()]);
    if (revision !== stationRequest.current) return null;
    const ready = readyResult.status === "fulfilled" ? readyResult.value : null;
    const screens = displayResult.status === "fulfilled" ? displayResult.value : [];
    setReadiness(ready); setDisplays(screens);
    setDisplayIndex(current => current ?? (screens.length === 1 ? screens[0].index : screens[1]?.index ?? null));
    const failure = readyResult.status === "rejected" ? readyResult.reason : displayResult.status === "rejected" ? displayResult.reason : null;
    setStationError(failure ? openMatbErrorMessage(failure, copyRef.current) : null);
    setChecking(false);
    return { ready, screens };
  }, []);

  useEffect(() => {
    let active = true;
    void checkStation();
    void Promise.all([listParticipants(), listOpenMatbPresets(), listOpenMatbInstructions(), listOpenMatbVisualProfiles()])
      .then(([people, presetRows, instructionRows, visualRows]) => {
        if (!active) return;
        const approvedPresets = presetRows.filter(row => row.status === "published");
        const approvedVisuals = visualRows.filter(row => row.status === "published");
        setParticipants(people); setPresets(approvedPresets);
        setInstructions(instructionRows.filter(row => row.status === "published")); setVisualProfiles(approvedVisuals);
        if (approvedPresets[0]) setPresetKey(`${approvedPresets[0].preset_id}@${approvedPresets[0].version}`);
        const preferred = approvedVisuals.find(row => row.profile_id === "matb-fac-modern" && row.version === "1.0.0") ?? approvedVisuals[0];
        if (preferred) setVisualProfileKey(`${preferred.profile_id}@${preferred.version}`);
      }).catch(reason => { if (active) setError(openMatbErrorMessage(reason, copyRef.current)); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; stationRequest.current += 1; };
  }, [checkStation]);

  useEffect(() => {
    let active = true;
    setVisits([]); setVisitOrdinal("");
    if (participantId) void listVisits(participantId).then(rows => {
      if (active) { setVisits(rows); setVisitOrdinal(String((rows.find(v=>v.id===assigned.context?.visit_id)??rows[0])?.visit_ordinal??'')); }
    }).catch(reason => { if (active) setError(openMatbErrorMessage(reason, copyRef.current)); });
    return () => { active = false; };
  }, [participantId, assigned.context?.visit_id]);

  useEffect(() => {
    const matching = instructions.filter(row => row.locale === locale);
    setInstructionKey(current => matching.some(row => `${row.protocol_id}@${row.version}` === current)
      ? current : matching[0] ? `${matching[0].protocol_id}@${matching[0].version}` : "");
  }, [instructions, locale]);

  const preset = presets.find(row => `${row.preset_id}@${row.version}` === (frozen?.preset ? `${frozen.preset.id}@${frozen.preset.version}` : presetKey));
  const protocol = instructions.find(row => `${row.protocol_id}@${row.version}` === (frozen?.instructions ? `${frozen.instructions.id}@${frozen.instructions.version}` : instructionKey));
  const visual = visualProfiles.find(row => `${row.profile_id}@${row.version}` === (frozen?.visual ? `${frozen.visual.id}@${frozen.visual.version}` : visualProfileKey));
  const selectedDisplay = displays.find(row => row.index === displayIndex);
  const stationReady = Boolean(readiness?.ready && displays.length && !stationError);
  const missing: Array<{ target: string; label: string }> = [];
  if (purpose === "study" && !assigned.context) missing.push({target:"om-purpose",label:copy("Seleccione una evaluación asignada en /study/assignments", "Select an assigned assessment at /study/assignments")});
  if (!purpose) missing.push({ target: "om-purpose", label: copy("Elija práctica o estudio", "Choose practice or study") });
  if (!stationReady) missing.push({ target: "om-station", label: copy("Resuelva los requisitos de la estación", "Resolve the station requirements") });
  if (!participantId || !isParticipantId(participantId)) missing.push({ target: "om-participant", label: copy("Seleccione un participante", "Select a participant") });
  if (!visits.some(row => String(row.visit_ordinal) === visitOrdinal)) missing.push({ target: "om-visit", label: copy("Seleccione la visita asignada", "Select the assigned visit") });
  if (!preset || !protocol || !visual) missing.push({ target: !preset ? "om-preset" : !protocol ? "om-protocol" : "om-theme", label: copy("Seleccione una configuración publicada", "Select a published configuration") });
  if (!selectedDisplay) missing.push({ target: "om-display", label: copy("Seleccione una pantalla conectada", "Select a connected display") });
  if (!acknowledged) missing.push({ target: "om-equipment", label: copy("Confirme la comprobación del equipo", "Confirm the equipment check") });
  const pendingReason = loading ? copy("Cargando participantes y configuración…", "Loading participants and configuration…")
    : checking ? copy("Comprobando los requisitos de la estación…", "Checking the station requirements…")
    : busy ? copy("Creando sesión…", "Creating session…") : null;
  const canPrepare = !missing.length && !pendingReason;

  function focusRequirement(target: string) {
    const element = document.getElementById(target);
    const details = element?.closest("details");
    if (details) details.open = true;
    element?.focus();
  }
  async function prepare() {
    if (!canPrepare || !purpose || !preset || !protocol || !visual || displayIndex === null) return;
    const participantWindow = window.open("about:blank", "matb-fac-participant");
    setBusy(true); setError(null);
    try {
      // Credentials must survive this route change and a reload in this tab.
      sessionStorage.setItem("openmatb.storage-check", "ok"); sessionStorage.removeItem("openmatb.storage-check");
      const current = await checkStation();
      if (!current?.ready?.ready) throw new Error(copy("Resuelva los requisitos de la estación y vuelva a comprobar.", "Resolve the station requirements and check again."));
      if (!current.screens.some(row => row.index === displayIndex)) throw new Error(copy("La pantalla seleccionada se desconectó. Seleccione una pantalla conectada.", "The selected display disconnected. Select a connected display."));
      const admitted = assigned.attempt ? await admission.admit() : null;
      if(purpose === 'study' && !admitted) throw new Error('Select an assigned assessment');
      const prepared = await createOpenMatbSession({ attempt_id: admitted?.attemptId, execution_purpose: purpose, participant_id: participantId, visit_ordinal: Number(visitOrdinal),
        preset_id: preset.preset_id, preset_version: preset.version, instruction_protocol_id: protocol.protocol_id,
        instruction_version: protocol.version, visual_profile_id: visual.profile_id, visual_profile_version: visual.version, display_index: displayIndex });
      storeOpenMatbCredentials(prepared);
      const windowState = participantWindow ? "opened" : "blocked";
      saveParticipantWindowState(prepared.session.id, windowState);
      if (participantWindow) participantWindow.location.href = `/openmatb/participant?session=${encodeURIComponent(prepared.session.id)}#token=${encodeURIComponent(prepared.participant_token)}`;
      router.push(`/openmatb/session?session=${encodeURIComponent(prepared.session.id)}&participant_window=${windowState}`);
    } catch (reason) {
      participantWindow?.close();
      setError(openMatbErrorMessage(reason, copyRef.current));
    } finally { setBusy(false); }
  }

  return <div className="min-w-0 space-y-6 text-base [&_button]:text-sm [&_button]:normal-case [&_button]:tracking-normal">
    <div id="om-purpose" tabIndex={-1}><Link className="underline" href="/study/assignments">{copy("Evaluaciones asignadas", "Assigned assessments")}</Link>
      <ExperimentGuide id="openmatb" /></div>
    <PageHeader kicker={copy("Preparación", "Preparation")} title={copy("Suite OpenMATB", "OpenMATB suite")}
      description={copy("Compruebe la estación, confirme la visita y abra las instrucciones. La tarea se inicia después desde el panel del investigador.", "Check the station, confirm the visit, and open the instructions. The researcher starts the task afterward from the controller.")} />
    {error && <div role="alert" className="rounded border border-danger/40 p-3 text-danger"><p>{error}</p><Button variant="link" onClick={() => location.reload()}>{copy("Volver a cargar la preparación", "Reload preparation")}</Button></div>}
    <Card id="om-station" tabIndex={-1}>
      <CardHeader><CardTitle className="text-xl">{copy("1. ¿Está lista la estación?", "1. Is the station ready?")}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        {stationError && <p role="alert" className="text-danger">{stationError}</p>}
        <ul className="grid gap-3 md:grid-cols-2">{Object.entries(readiness?.checks ?? {}).map(([key, ready]) => {
          const text = CHECKS[key];
          return <li key={key} className="rounded border p-3 text-sm"><div className="flex items-center gap-2">
            {ready ? <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" /> : <AlertCircle className="h-4 w-4 text-warning" aria-hidden="true" />}
            <span className="font-medium">{text ? copy(text[0], text[1]) : copy("Requisito de la estación", "Station requirement")}</span>
            <span className="ml-auto">{ready ? copy("Correcto", "Ready") : copy("Revisar", "Needs attention")}</span></div>
            {!ready && <div className="mt-2"><p>{text ? copy(text[2], text[3]) : copy("Consulte los diagnósticos y vuelva a comprobar.", "Review diagnostics and check again.")}</p>
              <Button variant="link" disabled={checking || busy} onClick={() => void checkStation()}>{copy("Comprobar este requisito", "Recheck this requirement")}</Button></div>}
          </li>;
        })}</ul>
        <Button variant="outline" disabled={checking || busy} onClick={() => void checkStation()}>{checking ? copy("Comprobando…", "Checking…") : copy("Comprobar de nuevo", "Check again")}</Button>
        <div className="max-w-xl space-y-2"><label htmlFor="om-display" className="text-sm font-medium">{copy("Pantalla del participante", "Participant display")}</label>
          <select id="om-display" className="native-select w-full" value={displayIndex ?? ""} disabled={busy || checking} onChange={event => setDisplayIndex(event.target.value === "" ? null : Number(event.target.value))}>
            <option value="">{copy("Seleccione una pantalla", "Select a display")}</option>
            {displayIndex !== null && !selectedDisplay && <option value={displayIndex}>{copy("Desconectada", "Disconnected")} · {copy("Pantalla", "Display")} {displayIndex + 1}</option>}
            {displays.map(display => <option key={display.index} value={display.index}>{copy("Pantalla", "Display")} {display.index + 1} · {display.width} × {display.height}{display.index === 0 && displays.length > 1 ? copy(" · primera pantalla", " · first display") : ""}</option>)}
          </select><p className="text-sm text-muted-foreground">{copy("La aplicación nativa usará esta pantalla. Las instrucciones se abren en una ventana del navegador independiente.", "The native task uses this display. Instructions open in a separate browser window.")}</p>
        </div>
        <label className="flex items-start gap-3 rounded border p-3 text-sm"><input id="om-equipment" type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} disabled={busy || admission.pending} className="mt-1" />
          <span>{copy("Confirmo que verificaré físicamente audio, mouse, teclado o joystick antes de recolectar datos.", "I confirm that I will physically verify audio, mouse, keyboard, or joystick before collecting data.")}</span></label>
      </CardContent>
    </Card>
    <Card><CardHeader><CardTitle className="text-xl">{copy("2. ¿Quién participa?", "2. Who is participating?")}</CardTitle></CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2"><label htmlFor="om-participant" className="text-sm font-medium">{copy("Participante", "Participant")}</label>
          <select id="om-participant" className="native-select w-full" value={participantId} disabled={loading || busy} onChange={event => setParticipantId(event.target.value)}><option value="">—</option>{participants.map(person => <option key={person.id}>{person.id}</option>)}</select>
          {!loading && !participants.length && <Link href="/participants" className="text-sm text-info underline">{copy("Registrar participante", "Register participant")}</Link>}
        </div>
        <div className="space-y-2"><label htmlFor="om-visit" className="text-sm font-medium">{copy("Visita asignada", "Assigned visit")}</label>
          <select id="om-visit" className="native-select w-full" value={visitOrdinal} disabled={!participantId || busy} onChange={event => setVisitOrdinal(event.target.value)}><option value="">—</option>{visits.map(visit => <option key={visit.id} value={visit.visit_ordinal}>V{visit.visit_ordinal} · {copy("Día", "Day")} {visit.scheduled_day}</option>)}</select>
        </div>
        {participantId && visitOrdinal && <p className="text-sm sm:col-span-2">{copy("Seleccionado", "Selected")}: <strong className="font-mono">{participantId}</strong> · V{visitOrdinal}</p>}
      </CardContent>
    </Card>
    <Card><CardHeader><CardTitle className="text-xl">{copy("3. ¿Qué se ejecutará?", "3. What will run?")}</CardTitle></CardHeader>
      <CardContent className="space-y-4">
        <p className="font-medium">{protocol?.title ?? copy("Seleccione un protocolo publicado", "Select a published protocol")}</p>
        <p className="text-sm">{preset?.label_es} · {visual?.label}</p>
        <p className="text-sm text-muted-foreground">{purpose === "practice" ? copy("Un bloque de práctica, sin cuestionario ni cierre de visita de estudio.", "One practice block, with no questionnaire or completion of a study visit.") : purpose === "study" ? copy("Una condición asignada, con escalas inmediatamente después. La preparación prescrita se realiza antes de esta ejecución.", "One assigned condition, with ratings immediately afterward. Prescribed preparation happens before this run.") : copy("Elija la finalidad para ver la secuencia.", "Choose a purpose to see the sequence.")}</p>
        <details className="rounded border p-3"><summary className="cursor-pointer text-sm font-semibold">{copy("Ver configuración", "View configuration")}</summary>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <label className="space-y-2 text-sm" htmlFor="om-preset">{copy("Preset publicado", "Published preset")}<select id="om-preset" className="native-select w-full" value={frozen?.preset ? `${frozen.preset.id}@${frozen.preset.version}` : presetKey} disabled={busy || admission.pending || !!assigned.context} onChange={event => setPresetKey(event.target.value)}>{presets.map(row => <option key={`${row.preset_id}@${row.version}`} value={`${row.preset_id}@${row.version}`}>{row.label_es} · v{row.version}</option>)}</select></label>
            <label className="space-y-2 text-sm" htmlFor="om-protocol">{copy("Protocolo de instrucciones", "Instruction protocol")}<select id="om-protocol" className="native-select w-full" value={frozen?.instructions ? `${frozen.instructions.id}@${frozen.instructions.version}` : instructionKey} disabled={busy || admission.pending || !!assigned.context} onChange={event => setInstructionKey(event.target.value)}>{instructions.filter(row => row.locale === locale).map(row => <option key={`${row.protocol_id}@${row.version}`} value={`${row.protocol_id}@${row.version}`}>{row.title} · v{row.version}</option>)}</select></label>
            <label className="space-y-2 text-sm" htmlFor="om-theme">{copy("Perfil visual publicado", "Published visual profile")}<select id="om-theme" className="native-select w-full" value={frozen?.visual ? `${frozen.visual.id}@${frozen.visual.version}` : visualProfileKey} disabled={busy || admission.pending || !!assigned.context} onChange={event => setVisualProfileKey(event.target.value)}>{visualProfiles.map(row => <option key={`${row.profile_id}@${row.version}`} value={`${row.profile_id}@${row.version}`}>{row.label} · v{row.version}</option>)}</select></label>
            <p className="text-sm text-muted-foreground">{copy("Los perfiles y sus huellas quedan congelados con la sesión.", "Profiles and their hashes are frozen with the session.")}</p>
          </div>
          {preset && <div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr>{[copy("Bloque", "Block"), copy("Duración", "Duration"), copy("Dificultad", "Difficulty"), "TRACK", "RESMAN", "ISA"].map(label => <th key={label} className="p-2">{label}</th>)}</tr></thead><tbody>{Object.entries(preset.profiles).map(([name, value]) => <tr key={name} className="border-t"><td className="p-2">{name}</td><td>{value.duration_seconds}s</td><td>{value.difficulty}</td><td>{value.track_target_proportion}</td><td>{value.resman_loss_per_min} L/min</td><td>{value.isa_probe_interval_sec}s</td></tr>)}</tbody></table></div>}
          <div className="mt-4 flex flex-wrap gap-4 text-sm"><Link href="/openmatb/settings" className="text-info underline">{copy("Configuración avanzada", "Advanced settings")}</Link><Link href="/openmatb/appearance" className="text-info underline">{copy("Apariencia", "Appearance")}</Link></div>
          <details className="mt-4 text-sm"><summary className="cursor-pointer">{copy("Diagnósticos y procedencia", "Diagnostics and provenance")}</summary><pre className="mt-2 overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ display_index: displayIndex, preset_id: preset?.preset_id, preset_version: preset?.version, preset_sha256: preset?.sha256, instruction_protocol_id: protocol?.protocol_id, instruction_protocol_version: protocol?.version, instruction_protocol_sha256: protocol?.sha256, visual_profile_id: visual?.profile_id, visual_profile_version: visual?.version, visual_profile_sha256: visual?.sha256, readiness }, null, 2)}</pre></details>
        </details>
        <div aria-live="polite" className="text-sm">{missing.length > 0 && <><p>{copy("Para continuar:", "To continue:")}</p><ul className="mt-1 space-y-1">{missing.map(item => <li key={item.target}><button className="text-left text-info underline" onClick={() => focusRequirement(item.target)}>{item.label}</button></li>)}</ul></>}</div>
        {pendingReason && <p role="status" className="text-sm">{pendingReason}</p>}
        <Button size="lg" className="h-auto min-h-11 max-w-full whitespace-normal" disabled={!canPrepare} onClick={() => void prepare()}>{busy ? copy("Creando sesión…", "Creating session…") : copy("Crear sesión y abrir instrucciones", "Create session and open instructions")}</Button>
      </CardContent>
    </Card>
  </div>;
}

export default function OpenMatbSetupPage() { return <Suspense><SetupContent /></Suspense>; }
