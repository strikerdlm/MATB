"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";
import { CrewFrame } from "./CrewFrame";
import { CrewDaySummary } from "./CrewDaySummary";
import { PvtRunner } from "@/components/pvt/PvtRunner";
import { InstructionAudio } from "@/components/instructions/InstructionAudio";
import { useAssignedAttempt } from "@/lib/assigned-attempt";
import { useAssessmentAdmission } from "@/lib/assessment-admission";
import { getCrewProgress, crewActivity, crewHref, type CrewProgress } from "@/lib/crew-workflow";
import { postPvt, postScreen } from "@/lib/api";
import { FixedLocaleProvider, useAppLocale } from "@/lib/i18n";
import { PVT_PROTOCOL_DURATION_MS, type PvtRunResult } from "@/lib/pvt";
import type { ScreenPayload } from "@/lib/screen";

const TaskRunner = dynamic(() => import("@/components/screen/TaskRunner").then(m => m.TaskRunner), { ssr: false });
const KSS = [
  ["Extremadamente despierto", "Extremely alert"], ["Muy despierto", "Very alert"],
  ["Despierto", "Alert"], ["Más o menos despierto", "Rather alert"],
  ["Ni despierto, ni somnoliento", "Neither alert nor sleepy"],
  ["Algunos signos de somnolencia", "Some signs of sleepiness"],
  ["Somnoliento, pero sin esfuerzo de mantenerse despierto", "Sleepy, but no effort to keep awake"],
  ["Somnoliento, algún esfuerzo para mantenerse despierto", "Sleepy, but some effort to keep awake"],
  ["Muy somnoliento, gran esfuerzo para mantenerse despierto, luchando contra el sueño", "Very sleepy, great effort to keep awake, fighting sleep"],
] as const;

export function CrewBrowserRunner() {
  const query = useSearchParams();
  const requestedReturn = crewActivity(query.get("return"));
  const assigned = useAssignedAttempt();
  const context = assigned.context;
  const preferred = useAppLocale();
  const locale = context?.locale ?? preferred.locale;
  const copy = (es: string, en: string) => locale === "en" ? en : es;
  const [callsign, setCallsign] = useState("");
  const [progress, setProgress] = useState<CrewProgress | null>(null);
  const [verified, setVerified] = useState(false);
  const [stage, setStage] = useState<"loading" | "kss" | "pvt" | "screen" | "saving" | "saved" | "save_error">("loading");
  const [error, setError] = useState("");
  const [kss, setKss] = useState<number | null>(null);
  const [pending, setPending] = useState<PvtRunResult | ScreenPayload | null>(null);
  const initiated = useRef<string | null>(null);
  const admission = useAssessmentAdmission(assigned.attempt && context && verified ? {
    attemptId: assigned.attempt.id, participantId: context.participant_id, visitId: context.visit_id,
    visitOrdinal: context.assigned_visit.ordinal, purpose: "study" as const, locale,
  } : null);
  useEffect(() => {
    let active = true;
    setVerified(false);
    if (!context || !["pvt", "screen"].includes(context.instrument) || assigned.attempt?.execution_purpose !== "study") return;
    void getCrewProgress(context.instrument as "pvt" | "screen").then(result => {
      const person = result.participants.find(row => row.participant_id === context.participant_id);
      if (!person) throw new Error("El intento no corresponde a un tripulante activo.");
      if (active) { setCallsign(person.callsign); setVerified(true); setProgress(person); }
    }).catch(reason => { if (active) setError(reason instanceof Error ? reason.message : String(reason)); });
    return () => { active = false; };
  }, [context, assigned.attempt?.execution_purpose]);
  useEffect(() => {
    if (!verified || !context || !assigned.attempt || initiated.current === assigned.attempt.id) return;
    if (assigned.attempt.acquisition_state !== "created") {
      setError("Esta prueba ya comenzó. Vuelve a la selección para continuar con su estado guardado.");
      return;
    }
    initiated.current = assigned.attempt.id;
    void admission.admit().then(value => {
      if (value) setStage(context.instrument === "pvt" ? "kss" : "screen");
    }).catch(reason => { setError(reason instanceof Error ? reason.message : String(reason)); });
    // The ref prevents repeated starts; admission owns immutable context and pagehide interruption.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [verified, assigned.attempt, context]);

  async function save(raw: PvtRunResult | ScreenPayload) {
    const acquired = admission.admitted;
    if (!acquired || !context) return;
    setPending(raw); setStage("saving"); setError("");
    try {
      if (context.instrument === "pvt") {
        if (kss === null) throw new Error("Falta la respuesta de somnolencia.");
        const run = raw as PvtRunResult;
        await postPvt({ attempt_id: acquired.attemptId, participant_id: acquired.participantId,
          visit_ordinal: acquired.visitOrdinal, kss_score: kss, administered_at: run.administeredAt,
          duration_ms: run.durationMs, execution_purpose: "study", locale: acquired.locale,
          timing_version: 2, interruption_count: run.interruptionCount, max_frame_gap_ms: run.maxFrameGapMs,
          terminal_phase: run.terminalPhase, terminal_stimulus_at_ms: run.terminalStimulusAtMs,
          fast_mode: false, trials: run.trials });
      } else {
        await postScreen(acquired.participantId, raw as ScreenPayload, false, "study", acquired.attemptId);
      }
      setStage("saved");
      // Saving has succeeded even if the schedule refresh temporarily fails.
      void getCrewProgress(requestedReturn).then(result => {
        setProgress(result.participants.find(row => row.participant_id === context.participant_id) ?? null);
      }).catch(() => setProgress(null));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason)); setStage("save_error");
    }
  }
  const returnHref = crewHref(requestedReturn, callsign || undefined);
  return <FixedLocaleProvider locale={locale}><CrewFrame step={3}>
    <div className="crew-heading"><h1>{context?.instrument === "screen" ? copy("Pruebas", "Tests") : "KSS + PVT"}</h1><p>{callsign}{context ? ` · ${context.assigned_visit.code}` : ""}</p></div>
    {(error || assigned.error) && <div role="alert" className="crew-error">{error || assigned.error}</div>}
    {stage === "loading" && !error && <p role="status">{copy("Abriendo tu prueba…", "Opening your test…")}</p>}
    {stage === "kss" && <section className="mx-auto max-w-3xl space-y-6">
      <h2 className="text-2xl font-semibold">{copy("¿Qué tan somnoliento te sientes ahora?", "How sleepy do you feel right now?")}</h2>
      <fieldset className="space-y-2"><legend className="mb-4 text-muted-foreground">{copy("Escala de Somnolencia de Karolinska · elige una respuesta", "Karolinska Sleepiness Scale · choose one response")}</legend>
        {KSS.map((labels, index) => <label key={index} className={`flex cursor-pointer gap-4 rounded-md border p-4 ${kss === index + 1 ? "border-info bg-info/10" : "border-white/20"}`}><input type="radio" name="crew-kss" value={index + 1} checked={kss === index + 1} onChange={() => setKss(index + 1)} /><span>{index + 1}. {copy(labels[0], labels[1])}</span></label>)}
      </fieldset>
      <button type="button" className="crew-primary" disabled={kss === null} onClick={() => setStage("pvt")}>{copy("Continuar a PVT", "Continue to PVT")}</button>
    </section>}
    {stage === "pvt" && <section className="space-y-5"><p className="text-muted-foreground">{copy("Responde con la barra espaciadora cuando aparezca el contador. Duración: 10 minutos.", "Press the space bar when the counter appears. Duration: 10 minutes.")}</p><InstructionAudio src={`/audio/instructions/pvt-${locale === "en" ? "en" : "es"}.mp3`} label={copy("Escuchar instrucciones", "Listen to instructions")} unavailableLabel={copy("Audio no disponible. Lee las instrucciones en pantalla.", "Audio unavailable. Read the instructions on screen.")} /><PvtRunner durationMs={PVT_PROTOCOL_DURATION_MS} onComplete={run => void save(run)} /></section>}
    {stage === "screen" && <TaskRunner fast={false} onComplete={raw => void save(raw)} />}
    {stage === "saving" && <p role="status">{copy("Guardando la prueba…", "Saving the test…")}</p>}
    {stage === "save_error" && pending && <div className="space-y-4"><p>{copy("Conservamos los datos en esta pestaña. Vuelve a intentar el guardado.", "The data remains in this tab. Retry saving.")}</p><button className="crew-primary" onClick={() => void save(pending)}>{copy("Reintentar guardado", "Retry saving")}</button></div>}
    {stage === "saved" && <div className="mx-auto max-w-2xl space-y-6 text-center"><h2 className="text-3xl font-semibold">{copy("Prueba guardada", "Test saved")}</h2><p className="text-muted-foreground">{copy("Tu registro quedó guardado. La aplicación continuará con lo que sigue pendiente.", "Your record was saved. The app will continue with the next pending activity.")}</p><Link className="crew-primary" href={returnHref}>{requestedReturn === "suas" ? copy("Continuar a la misión", "Continue to the mission") : copy("Volver a mi sesión", "Back to my session")}</Link></div>}
    {stage === "saved" && progress?.schedule && <div className="mx-auto max-w-2xl"><CrewDaySummary person={progress} /></div>}
    {stage === "loading" && error && <Link className="underline text-info" href={returnHref}>{copy("Volver a mi sesión", "Back to my session")}</Link>}
  </CrewFrame></FixedLocaleProvider>;
}
