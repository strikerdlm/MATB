"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowRight, CheckCircle2, Clock3, MoonStar } from "lucide-react";

import { InstructionAudio } from "@/components/instructions/InstructionAudio";
import { PageHeader } from "@/components/layout/PageHeader";
import { PvtRunner } from "@/components/pvt/PvtRunner";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { getPvtSummary, listParticipants, listVisits, postPvt } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";
import { PVT_PROTOCOL_DURATION_MS, type PvtTrial } from "@/lib/pvt";
import type { Participant, PvtAssessment, PvtSummary, Visit } from "@/types";

const KSS_EN = [
  "Extremely alert",
  "Very alert",
  "Alert",
  "Rather alert",
  "Neither alert nor sleepy",
  "Some signs of sleepiness",
  "Sleepy, but no effort to keep awake",
  "Sleepy, but some effort to keep awake",
  "Very sleepy, great effort to keep awake, fighting sleep",
] as const;

const KSS_ES = [
  "Extremadamente despierto",
  "Muy despierto",
  "Despierto",
  "Más o menos despierto",
  "Ni despierto, ni somnoliento",
  "Algunos signos de somnolencia",
  "Somnoliento, pero sin esfuerzo de mantenerse despierto",
  "Somnoliento, algún esfuerzo para mantenerse despierto",
  "Muy somnoliento, gran esfuerzo para mantenerse despierto, luchando contra el sueño",
] as const;

type Stage = "select" | "kss" | "instructions" | "pvt" | "saving" | "complete";

export default function PvtPage() {
  const { locale, copy } = useAppLocale();
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [summary, setSummary] = useState<PvtSummary | null>(null);
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [kssScore, setKssScore] = useState<number | null>(null);
  const [stage, setStage] = useState<Stage>("select");
  const [result, setResult] = useState<PvtAssessment | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [fastMode, setFastMode] = useState(false);

  useEffect(() => {
    setFastMode(new URLSearchParams(window.location.search).get("fast") === "1");
    Promise.all([listParticipants(), getPvtSummary()])
      .then(([participantRows, pvtRows]) => {
        setParticipants(participantRows);
        setSummary(pvtRows);
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, []);

  useEffect(() => {
    const nextHash = stage === "kss" || stage === "select" ? "#kss" : "#pvt";
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, "", nextHash);
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    }
  }, [stage]);

  useEffect(() => {
    setVisitOrdinal("");
    setVisits([]);
    if (!participantId) return;
    listVisits(participantId)
      .then((rows) => {
        setVisits(rows);
        const completedVisitIds = new Set(
          summary?.assessments.filter((row) => row.participant_id === participantId).map((row) => row.visit_id) ?? [],
        );
        const next = rows.find((visit) => !completedVisitIds.has(visit.id)) ?? rows[0];
        if (next) setVisitOrdinal(String(next.visit_ordinal));
      })
      .catch((reason) => setError(reason instanceof Error ? reason.message : String(reason)));
  }, [participantId, summary]);

  const visit = useMemo(
    () => visits.find((row) => row.visit_ordinal === Number(visitOrdinal)) ?? null,
    [visitOrdinal, visits],
  );
  const alreadyRecorded = Boolean(
    visit && summary?.assessments.some((row) => row.visit_id === visit.id),
  );
  const kssLabels = locale === "en" ? KSS_EN : KSS_ES;
  const durationMs = fastMode ? 12_000 : PVT_PROTOCOL_DURATION_MS;
  const audioLocale = locale === "en" ? "en" : "es";

  function beginKss() {
    if (!participantId || !visitOrdinal || alreadyRecorded) return;
    setError(null);
    setKssScore(null);
    setStage("kss");
  }

  async function completePvt({ trials, durationMs: completedDuration }: { trials: PvtTrial[]; durationMs: number }) {
    if (kssScore === null) return;
    setStage("saving");
    try {
      const saved = await postPvt({
        participant_id: participantId,
        visit_ordinal: Number(visitOrdinal),
        kss_score: kssScore,
        administered_at: new Date().toISOString(),
        duration_ms: completedDuration,
        fast_mode: fastMode,
        trials,
      });
      setResult(saved);
      setSummary(await getPvtSummary());
      setStage("complete");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
      setStage("instructions");
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Paso 2 y 3 de la visita", "Visit steps 2 and 3")}
        title={copy("KSS + Test de Vigilancia Psicomotora (PVT)", "KSS + Psychomotor Vigilance Test (PVT)")}
        description={copy(
          "Primero indique su somnolencia actual con la escala de Karolinska. Después complete la PVT estándar de 10 minutos.",
          "First rate your current sleepiness on the Karolinska scale. Then complete the standard 10-minute PVT.",
        )}
        stats={[
          { label: copy("Orden", "Order"), value: "KSS → PVT" },
          { label: copy("Duración PVT", "PVT duration"), value: "10 min" },
          { label: copy("Visitas", "Visits"), value: "T0 · DM8 · DM15" },
        ]}
      />

      {fastMode && (
        <div role="note" className="flex gap-3 rounded border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          {copy("Modo rápido de verificación: el resultado se guarda como no válido para el protocolo.", "Fast verification mode: the result is stored as not protocol-valid.")}
        </div>
      )}
      {error && <div role="alert" className="rounded border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</div>}

      {stage === "select" && (
        <Card>
          <CardHeader>
            <CardTitle>{copy("Identifique esta visita", "Identify this visit")}</CardTitle>
            <CardDescription>{copy("Use únicamente el código seudonimizado asignado.", "Use only the assigned pseudonymous code.")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-5 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="pvt-participant">{copy("Participante", "Participant")}</Label>
                <select id="pvt-participant" className="native-select w-full" value={participantId} onChange={(event) => setParticipantId(event.target.value)}>
                  <option value="">—</option>
                  {participants.map((participant) => <option key={participant.id} value={participant.id}>{participant.id}</option>)}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="pvt-visit">{copy("Visita", "Visit")}</Label>
                <select id="pvt-visit" className="native-select w-full" value={visitOrdinal} onChange={(event) => setVisitOrdinal(event.target.value)} disabled={!participantId}>
                  <option value="">—</option>
                  {visits.map((row) => <option key={row.id} value={row.visit_ordinal}>{copy("Día", "Day")} {row.scheduled_day} · V{row.visit_ordinal}</option>)}
                </select>
              </div>
            </div>
            {alreadyRecorded && <p className="text-sm text-warning">{copy("Esta visita ya tiene una PVT registrada.", "This visit already has a recorded PVT.")}</p>}
            <Button type="button" onClick={beginKss} disabled={!participantId || !visitOrdinal || alreadyRecorded}>
              {copy("Continuar a KSS", "Continue to KSS")}<ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      )}

      {stage === "kss" && (
        <Card className="border-info/30">
          <CardHeader>
            <div className="mb-2 flex items-center gap-2 text-info"><MoonStar className="h-5 w-5" /><span className="page-kicker text-info">{copy("Primero", "First")} · KSS</span></div>
            <CardTitle>{copy("Escala de Somnolencia de Karolinska", "Karolinska Sleepiness Scale")}</CardTitle>
            <CardDescription className="max-w-3xl text-base text-foreground">
              {copy(
                "Seleccione el número que represente el nivel de somnolencia durante los cinco minutos inmediatamente anteriores:",
                "Select the number that represents your level of sleepiness during the immediately preceding five minutes:",
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <InstructionAudio src={`/audio/instructions/kss-${audioLocale}.mp3`} label={copy("Escuchar instrucciones KSS", "Listen to KSS instructions")} unavailableLabel={copy("Audio no disponible", "Audio unavailable")} />
            <fieldset className="grid gap-2">
              <legend className="sr-only">Karolinska Sleepiness Scale</legend>
              {kssLabels.map((label, index) => {
                const value = index + 1;
                return (
                  <label key={value} className={`flex cursor-pointer items-start gap-4 rounded border px-4 py-3 transition ${kssScore === value ? "border-info bg-info/10" : "border-white/10 hover:border-white/30"}`}>
                    <input type="radio" name="kss" value={value} checked={kssScore === value} onChange={() => setKssScore(value)} className="mt-1 h-4 w-4 accent-cyan-400" />
                    <strong className="w-5 font-mono text-info">{value}</strong><span>{label}</span>
                  </label>
                );
              })}
            </fieldset>
            <Button type="button" onClick={() => setStage("instructions")} disabled={kssScore === null}>
              {copy("Guardar KSS y ver instrucciones PVT", "Save KSS and view PVT instructions")}<ArrowRight className="ml-2 h-4 w-4" />
            </Button>
          </CardContent>
        </Card>
      )}

      {stage === "instructions" && (
        <Card className="border-info/30">
          <CardHeader>
            <div className="mb-2 flex items-center gap-2 text-info"><Clock3 className="h-5 w-5" /><span className="page-kicker text-info">{copy("Después", "Next")} · PVT</span></div>
            <CardTitle>{copy("Instrucciones de la PVT", "PVT instructions")}</CardTitle>
            <CardDescription>{copy("Lea o escuche todo antes de iniciar. La prueba comienza solamente cuando pulse el botón.", "Read or listen to everything before starting. The test begins only when you press the button.")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <InstructionAudio src={`/audio/instructions/pvt-${audioLocale}.mp3`} label={copy("Escuchar instrucciones PVT", "Listen to PVT instructions")} unavailableLabel={copy("Audio no disponible", "Audio unavailable")} />
            <ol className="grid gap-3 text-sm sm:grid-cols-2">
              <li className="metric-tile"><strong>1.</strong> {copy("Apoye un dedo sobre la barra espaciadora o sobre el área negra de respuesta.", "Rest one finger on the space bar or the black response area.")}</li>
              <li className="metric-tile"><strong>2.</strong> {copy("Espere. El contador aparecerá después de un intervalo variable.", "Wait. The counter will appear after a variable interval.")}</li>
              <li className="metric-tile"><strong>3.</strong> {copy("Responda apenas aparezca el contador. La pantalla mostrará su tiempo en milisegundos.", "Respond as soon as the counter appears. The screen will show your time in milliseconds.")}</li>
              <li className="metric-tile"><strong>4.</strong> {copy("No se anticipe. Si responde antes, verá “Demasiado pronto”. Continúe hasta que termine el tiempo.", "Do not anticipate. If you respond early, you will see “Too soon.” Continue until time ends.")}</li>
            </ol>
            <div className="rounded border border-white/10 bg-black/25 p-4 text-sm text-muted-foreground">
              {copy("Duración: 10 minutos. Intervalo variable: 2 a 10 segundos. Responda siempre con la misma mano y mantenga la atención en el centro.", "Duration: 10 minutes. Variable interval: 2 to 10 seconds. Always respond with the same hand and keep your attention centered.")}
            </div>
            <Button type="button" size="lg" onClick={() => setStage("pvt")}>{copy("Estoy listo", "I am ready")}<ArrowRight className="ml-2 h-4 w-4" /></Button>
          </CardContent>
        </Card>
      )}

      {stage === "pvt" && <PvtRunner durationMs={durationMs} onComplete={(value) => void completePvt(value)} />}
      {stage === "saving" && <div role="status" className="grid min-h-[50vh] place-items-center text-center"><div><Clock3 className="mx-auto mb-4 h-10 w-10 animate-pulse text-info" /><p>{copy("Guardando la PVT…", "Saving PVT…")}</p></div></div>}
      {stage === "complete" && result && (
        <Card className="border-success/40 bg-success/5">
          <CardHeader>
            <CheckCircle2 className="mb-3 h-10 w-10 text-success" />
            <CardTitle>{copy("KSS y PVT completadas", "KSS and PVT complete")}</CardTitle>
            <CardDescription>{copy("Avise al investigador. El siguiente paso es la línea basal con Polar H10.", "Tell the researcher. The next step is the Polar H10 baseline.")}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 sm:grid-cols-4">
            <div className="metric-tile"><div className="page-kicker">KSS</div><div className="mt-1 text-2xl">{result.kss_score}</div></div>
            <div className="metric-tile"><div className="page-kicker">{copy("Mediana", "Median")}</div><div className="mt-1 text-2xl">{result.metrics.median_rt_ms?.toFixed(0) ?? "—"} ms</div></div>
            <div className="metric-tile"><div className="page-kicker">{copy("Lapsos", "Lapses")}</div><div className="mt-1 text-2xl">{result.metrics.lapses}</div></div>
            <div className="metric-tile"><div className="page-kicker">{copy("Anticipaciones", "False starts")}</div><div className="mt-1 text-2xl">{result.metrics.false_starts}</div></div>
            <div className="sm:col-span-4"><Button asChild><Link href={`/physiology/polar-h10?participant=${encodeURIComponent(result.participant_id)}&visit=${encodeURIComponent(visitOrdinal)}`}>{copy("Continuar a línea basal Polar H10", "Continue to Polar H10 baseline")}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button></div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
