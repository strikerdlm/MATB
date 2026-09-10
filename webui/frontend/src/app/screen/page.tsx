"use client";
import Link from "next/link";
import dynamic from "next/dynamic";
import { useEffect, useState } from "react";
import { ExecutionPurposeBadge, ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { AssessmentPicker } from "@/components/assessments/AssessmentPicker";
import { type Attempt } from "@/lib/assessments";
import { useAssessmentAdmission } from "@/lib/assessment-admission";
import { listParticipants, listVisits, postScreen } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";
import { useExecutionPurpose } from "@/lib/execution-purpose";
import { flowStageForScreen, useReportExperimentFlow } from "@/lib/experiment-flow";
import type { Participant, Visit, ScreenIngestResult } from "@/types";
import type { ScreenPayload } from "@/lib/screen";

const TaskRunner = dynamic(() => import("@/components/screen/TaskRunner").then((module) => module.TaskRunner), { ssr: false });
export default function ScreenPage() {
  const { copy } = useAppLocale();
  const purpose = useExecutionPurpose();
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [participant, setParticipant] = useState("");
  const [visits, setVisits] = useState<Visit[]>([]);
  const [visitId, setVisitId] = useState<number | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<Attempt | null>(null);
  const [stage, setStage] = useState<"select" | "run" | "saving" | "review">("select");
  const [payload, setPayload] = useState<ScreenPayload | null>(null);
  const [result, setResult] = useState<ScreenIngestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [activityStarted, setActivityStarted] = useState(false);
  useEffect(() => {
    let active = true;
    void listParticipants().then((rows) => { if (active) setParticipants(rows); })
      .catch(() => { if (active) setError("connection"); });
    return () => { active = false; };
  }, []);
  useEffect(() => { let active = true; setVisits([]); setVisitId(null); if (participant) void listVisits(participant).then(rows => {if(active) {setVisits(rows); setVisitId(rows[0]?.id ?? null);}}).catch(e => {if(active) setError(String(e));}); return () => {active = false;}; }, [participant]);
  const admission = useAssessmentAdmission(selectedAttempt && participant && visitId && purpose
    ? {attemptId: selectedAttempt.id, participantId: participant, visitId, purpose} : null);
  async function begin() {if (!selectedAttempt) return; try {if (await admission.admit()) setStage("run");} catch(e) {setError(String(e));}}
  useReportExperimentFlow("screen", flowStageForScreen(stage, activityStarted, Boolean(result)));
  async function save(raw: ScreenPayload) {
    const acquired = admission.admitted;
    if (!acquired) return;
    setPayload(raw); setStage("saving"); setError(null);
    try { setResult(await postScreen(acquired.participantId, raw, false, acquired.purpose, acquired.attemptId)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "save"); }
    finally { setStage("review"); }
  }
  const fields = [
    ["simple_rt", copy("Reacción simple", "Simple reaction"), "median_ms", "ms"],
    ["choice_rt", copy("Elección de respuesta", "Response choice"), "median_ms", "ms"],
    ["nback", copy("Memoria de trabajo · 2-back", "Working memory · 2-back"), "d_prime", "d′"],
    ["tracking", copy("Seguimiento", "Tracking"), "rms_norm", copy("error normalizado", "normalized error")],
  ];
  return <div className="space-y-6">
    <PageHeader kicker={copy("Evaluación cognitiva", "Cognitive assessment")} title={copy("Batería cognitiva", "Cognitive battery")} description={copy("Cuatro pruebas breves, con instrucciones y práctica antes de cada una.", "Four short tests, with instructions and practice before each one.")} />
    {stage !== "select" && purpose && <ExecutionPurposeBadge purpose={purpose} />}
    {stage === "select" && <>
      <ExperimentGuide id="screen" />
      <div className="space-y-4 rounded-lg border border-white/15 p-5">
        <label htmlFor="screen-participant" className="block font-semibold">{copy("Su código de participante", "Your participant code")}</label>
        <select id="screen-participant" disabled={admission.pending} className="native-select w-full max-w-sm" value={participant} onChange={(event) => setParticipant(event.target.value)}>
          <option value="">{copy("Seleccione su código", "Select your code")}</option>
          {participants.map((row) => <option key={row.id} value={row.id}>{row.id}</option>)}
        </select>
        <p className="text-sm text-muted-foreground">{copy("Necesita teclado y mouse. Lea las instrucciones y responda cuando aparezca el estímulo.", "You need a keyboard and mouse. Read the instructions and respond when the stimulus appears.")}</p>
        <label className="block">{copy("Visita", "Visit")}<select disabled={admission.pending} className="native-select block" value={visitId ?? ''} onChange={e => setVisitId(Number(e.target.value))}>{visits.map(v => <option key={v.id} value={v.id}>V{v.visit_ordinal}</option>)}</select></label>
        <AssessmentPicker participantId={participant} visitId={visitId} instrument="screen" purpose={purpose} onSelect={setSelectedAttempt} disabled={admission.pending} />
        <Button disabled={admission.pending || !purpose || !participant || !selectedAttempt} onClick={() => void begin()}>{copy("Ver instrucciones y comenzar", "View instructions and begin")}</Button>
      </div>
    </>}
    {error && <div role="alert" className="rounded border border-danger/40 p-4">
      <p>{error === "connection" ? copy("No se pudieron cargar los códigos. Compruebe la conexión y vuelva a abrir esta actividad.", "Could not load participant codes. Check the connection and reopen this activity.") : copy("No se pudo guardar. Sus respuestas siguen disponibles en esta pantalla. Compruebe la conexión y vuelva a intentarlo.", "Could not save. Your responses remain available on this screen. Check the connection and try again.")}</p>
      {payload && <Button className="mt-3" onClick={() => void save(payload)}>{copy("Reintentar guardado", "Retry saving")}</Button>}
    </div>}
    {stage === "run" && <TaskRunner fast={admission.admitted?.purpose === "practice"} onStart={() => setActivityStarted(true)} onComplete={(raw) => void save(raw)} />}
    {stage === "saving" && <p role="status">{copy("Guardando respuestas…", "Saving responses…")}</p>}
    {stage === "review" && result && <section className="space-y-4">
      <h2 className="text-2xl font-semibold">{copy("Respuestas guardadas", "Responses saved")}</h2>
      <p>{purpose === "practice" ? copy("Práctica completada. Estos resultados no se incorporan al estudio.", "Practice completed. These results are not included in the study.") : copy("Batería completada. Revise las medidas de cada tarea.", "Battery completed. Review the measures for each task.")}</p>
      <div className="grid gap-3 sm:grid-cols-2">{fields.map(([key, label, field, unit]) => {
        const score = result.scores[key];
        const value = score?.[field];
        return <div key={key} className="rounded border border-white/15 p-5"><h3 className="font-semibold">{label}</h3>
          <p className="mt-2 text-2xl">{typeof value === "number" ? value.toFixed(2) : "—"} <span className="text-sm">{unit}</span></p>
          <p className="mt-2 text-sm text-muted-foreground">{score?.valid ? copy("Registro suficiente para esta medida.", "Sufficient recording for this measure.") : copy("Calidad o respuestas insuficientes para interpretar la medida.", "Insufficient quality or responses to interpret this measure.")}</p>
          {typeof score?.accuracy === "number" && <p className="mt-2 text-sm">{copy("Precisión", "Accuracy")}: {(score.accuracy * 100).toFixed(0)}%</p>}
        </div>;
      })}</div>
      <p className="text-sm text-muted-foreground">{copy("Las medidas describen su desempeño en estas tareas. No representan un diagnóstico ni una calificación global.", "These measures describe performance on these tasks. They do not represent a diagnosis or an overall grade.")}</p>
      <Button asChild><Link href={`/start?purpose=${purpose}`}>{copy("Volver a los experimentos", "Return to experiments")}</Link></Button>
    </section>}
  </div>;
}
