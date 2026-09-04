"use client";

import React, { useState } from "react";

import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { sealLiftoffSession, submitLiftoffQuestionnaires, submitLiftoffResults } from "@/lib/liftoff/api";
import type { LiftoffDebriefView, LiftoffQuestionnaires } from "@/types/liftoff";
import { useAppLocale } from "@/lib/i18n";

export function LiftoffDebrief({ sessionId }: { sessionId: string }) {
  const { copy } = useAppLocale();
  const [ratings, setRatings] = useState<Record<string, string>>({});
  const [resultsSaved, setResultsSaved] = useState(false);
  const [ratingsSaved, setRatingsSaved] = useState(false);
  const dimensions = [
    ["mental_demand", copy("Demanda mental", "Mental demand")], ["physical_demand", copy("Demanda física", "Physical demand")],
    ["temporal_demand", copy("Demanda temporal", "Temporal demand")], ["performance", copy("Rendimiento", "Performance")],
    ["effort", copy("Esfuerzo", "Effort")], ["frustration", copy("Frustración", "Frustration")],
  ];
  const complete = dimensions.every(([key]) => ratings[key] !== undefined && ratings[key] !== "" && Number.isFinite(Number(ratings[key])) && Number(ratings[key]) >= 0 && Number(ratings[key]) <= 100)
    && !!ratings.kss && Number.isInteger(Number(ratings.kss)) && Number(ratings.kss) >= 1 && Number(ratings.kss) <= 9;
  const [lapTimes, setLapTimes] = useState("");
  const [invalidLaps, setInvalidLaps] = useState("0");
  const [restarts, setRestarts] = useState("0");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debrief, setDebrief] = useState<LiftoffDebriefView | null>(null);

  async function seal(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const lease = sessionStorage.getItem(`matb.liftoff.${sessionId}.lease`);
    if (!lease || !screenshot || !complete) { setError(copy("Se requieren la autorización de control y la captura del resultado.", "Controller lease and result screenshot are required.")); return; }
    const validLapTimes = lapTimes.trim() ? lapTimes.split(",").map((value) => value.trim() ? Number(value.trim()) : NaN) : [];
    if (validLapTimes.some((value) => !Number.isFinite(value) || value <= 0)) {
      setError(copy("Revise los tiempos: use segundos positivos separados por comas; no deje entradas vacías.", "Check lap times: use positive seconds separated by commas; do not leave empty entries.")); return;
    }
    setBusy(true);
    setError(null);
    try {
      if (!resultsSaved) await submitLiftoffResults(sessionId, lease, {
        valid_lap_times_s: validLapTimes,
        invalid_laps: Number(invalidLaps),
        observer_restart_count: Number(restarts),
      }, screenshot);
      setResultsSaved(true);
      if (!ratingsSaved) await submitLiftoffQuestionnaires(sessionId, lease,
        Object.fromEntries(Object.entries(ratings).map(([key, value]) => [key, Number(value)])) as unknown as LiftoffQuestionnaires);
      setRatingsSaved(true);
      setDebrief(await sealLiftoffSession(sessionId, lease));

    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : copy("Falló el sellado de la sesión.", "Session seal failed."));
    } finally {
      setBusy(false);
    }
  }

  if (debrief) {
    const primary = debrief.primary ?? {};
    const primaryLabels = [
      ["median_lap_time_s", copy("Mediana de vuelta (s)", "Median lap time (s)")],
      ["best_lap_time_s", copy("Mejor vuelta (s)", "Best lap time (s)")],
      ["valid_laps", copy("Vueltas válidas", "Valid laps")],
      ["invalid_laps", copy("Vueltas inválidas", "Invalid laps")],
      ["lap_completion_proportion", copy("Proporción de vueltas completadas (0–1)", "Lap completion proportion (0–1)")],
    ];
    const rtlx = dimensions.reduce((sum, [key]) => sum + Number(ratings[key]), 0) / 6;
    return <div className="mission-panel p-6"><p className="page-kicker">{copy("Evidencia sellada", "Sealed evidence")}</p><h1 className="page-title mt-2">{debrief.validity}</h1><p className="mt-3 text-sm text-muted-foreground">{copy("Calidad de telemetría", "Telemetry quality")}: {debrief.quality?.validity ?? copy("registrada", "recorded")}. {copy("Los resultados por componente permanecen separados.", "Component outcomes remain separate.")}</p><dl className="mt-4 grid gap-3 sm:grid-cols-2">{primaryLabels.map(([key, label]) => <div key={key} className="metric-tile"><dt>{label}</dt><dd>{typeof primary[key] === "number" ? (primary[key] as number).toFixed(2) : copy("Sin observación", "No observation")}</dd></div>)}</dl><p className="mt-4">{copy("RTLX sin ponderar (0–100)", "Unweighted RTLX (0–100)")}: {rtlx.toFixed(1)}</p><p role="status" className="mt-3">{copy("Resultados y respuestas guardados.", "Results and ratings saved.")}</p><details className="mt-4"><summary>{copy("Resultados detallados", "Detailed results")}</summary><pre className="mt-2 overflow-auto text-xs">{JSON.stringify(debrief, null, 2)}</pre></details><Link href="/start" className="mt-5 inline-block underline">{copy("Volver a los experimentos", "Back to experiments")}</Link></div>;
  }

  return (
    <form onSubmit={seal} className="mission-panel space-y-5 p-6">
      <div><p className="page-kicker">{copy("Verificación del resultado visible", "Visible-result verification")}</p><h1 className="page-title mt-2">{copy("Informe y sellado", "Debrief and seal")}</h1></div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-2 md:col-span-3"><Label htmlFor="lap-times">{copy("Tiempos de vuelta válidos (segundos, separados por comas)", "Valid lap times (seconds, comma-separated)")}</Label><Input disabled={resultsSaved} id="lap-times" aria-label={copy("Tiempos de vuelta válidos", "Valid lap times")} value={lapTimes} onChange={(event) => setLapTimes(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="invalid-laps">{copy("Vueltas inválidas", "Invalid laps")}</Label><Input disabled={resultsSaved} id="invalid-laps" type="number" min="0" value={invalidLaps} onChange={(event) => setInvalidLaps(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="restart-count">{copy("Reinicios del observador", "Observer restarts")}</Label><Input disabled={resultsSaved} id="restart-count" type="number" min="0" value={restarts} onChange={(event) => setRestarts(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="result-screen">{copy("Captura del resultado", "Result screenshot")}</Label><Input disabled={resultsSaved} id="result-screen" aria-label={copy("Captura del resultado", "Result screenshot")} type="file" accept="image/png,image/jpeg" onChange={(event) => setScreenshot(event.target.files?.[0] ?? null)} /></div>
      </div>
      <fieldset disabled={ratingsSaved} className="grid gap-4 border-t border-white/15 pt-5 sm:grid-cols-2">
        <legend className="font-semibold">{copy("Sus respuestas sobre este vuelo", "Your ratings for this flight")}</legend>
        <p className="text-sm text-muted-foreground sm:col-span-2">{copy("RTLX: índice de carga de tareas sin ponderar. Califique las seis dimensiones de 0 a 100; una puntuación mayor representa mayor demanda, esfuerzo, frustración o dificultad de rendimiento.", "RTLX: unweighted Task Load Index. Rate all six dimensions from 0 to 100; higher ratings represent greater demand, effort, frustration, or performance difficulty.")}</p>
        {dimensions.map(([key, label]) => <div key={key} className="space-y-2"><Label htmlFor={"liftoff-" + key}>{label}</Label><Input id={"liftoff-" + key} type="number" min={0} max={100} step={5} required value={ratings[key] ?? ""} onChange={(event) => setRatings((current) => ({ ...current, [key]: event.target.value }))} /></div>)}
        <div className="space-y-2 sm:col-span-2"><Label htmlFor="liftoff-kss">{copy("Somnolencia de Karolinska (1–9)", "Karolinska sleepiness (1–9)")}</Label><Input id="liftoff-kss" type="number" min={1} max={9} required value={ratings.kss ?? ""} onChange={(event) => setRatings((current) => ({ ...current, kss: event.target.value }))} /><p className="text-xs text-muted-foreground">{copy("1 = extremadamente despierto; 5 = ni despierto ni somnoliento; 9 = muy somnoliento, luchando contra el sueño.", "1 = extremely alert; 5 = neither alert nor sleepy; 9 = very sleepy, fighting sleep.")}</p></div>
      </fieldset>
      {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
      <Button disabled={busy || !screenshot || !complete}>{busy ? copy("Sellando evidencia…", "Sealing evidence…") : copy("Sellar sesión", "Seal session")}</Button>
    </form>
  );
}
