"use client";
import { PresentationSetup } from "../presentation/PresentationSetup";
import type { PresentationConfig } from "@/lib/simulation/presentation/contracts";

import React, { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, ChevronRight, Loader2, Radio, ShieldCheck } from "lucide-react";
import { listVisits } from "@/lib/api";
import {useAssignedAttempt} from '@/lib/assigned-attempt';
import {useAssessmentAdmission} from '@/lib/assessment-admission';
import { createSimulationSession, SimulationApiError } from "@/lib/simulation/api";
import { storePreparedSessionLease } from "@/lib/simulation/lease";
import { STRINGS, t, type TranslationKey } from "@/lib/simulation/i18n";
import { useAppLocale } from "@/lib/i18n";
import type { Participant, Visit } from "@/types";
import type { Locale, PreparedSession, ScenarioSummary } from "@/types/simulation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";
import { GuidedSteps, type GuidedStepState } from "@/components/layout/GuidedSteps";
import { InstructionAudio } from "@/components/instructions/InstructionAudio";
import { isParticipantId } from "@/lib/participant-id";

const EMPTY_VISITS: Visit[] = [];
const PROFILE_ORDER = ["PRACTICE", "LOW", "MEDIUM", "HIGH"] as const;

export interface MissionSetupFormProps {
  participants: Participant[];
  scenarios: ScenarioSummary[];
  /** Parent page data-loading state.  The form remains renderable for tests. */
  loading?: boolean;
  loadError?: string | null;
  /** Useful for embedding and component tests that already fetched visits. */
  initialVisits?: Visit[];
  visitsLoader?: (participantId: string) => Promise<Visit[]>;
  preparationEnabled?: boolean;
}

function errorMessage(reason: unknown, locale: Locale): string {
  if (reason instanceof SimulationApiError) {
    const fields = reason.context?.fields;
    if (reason.code === "invalid_request" && Array.isArray(fields) && fields.includes("body.participant_id")) {
      return locale === "es-CO"
        ? "El código del participante no es compatible. Use P seguido de 2 a 6 dígitos, por ejemplo P01."
        : "The participant code is not compatible. Use P followed by 2 to 6 digits, for example P01.";
    }
    const candidate = `error.${reason.code}` as TranslationKey;
    if (Object.prototype.hasOwnProperty.call(STRINGS.en, candidate)) return t(locale, candidate);
    return reason.message;
  }
  if (reason instanceof Error) return reason.message;
  return t(locale, "setup.prepare_error");
}

function scenarioFleet(): string {
  // The installed protocol supports a bounded 2–8 synthetic fleet.  The
  // scenario's exact count is authoritative in the live snapshot, while the
  // setup summary communicates the safe operating range.
  return "2–8 sUAS";
}

function manifestHash(scenario: ScenarioSummary): string {
  if (!scenario.scenario_sha256) return "—";
  return `${scenario.scenario_sha256.slice(0, 12)}…`;
}

export function MissionSetupForm({
  participants,
  scenarios,
  loading = false,
  loadError = null,
  initialVisits = EMPTY_VISITS,
  visitsLoader = listVisits,
  preparationEnabled = true,
}: MissionSetupFormProps) {
  const router = useRouter();
  const [presentation,setPresentation] = useState<PresentationConfig>();
  const preferred=useAppLocale();
  const assigned=useAssignedAttempt();
  const locale=assigned.context ? (assigned.context.locale==='en'?'en':'es-CO') : preferred.simulationLocale;
  const copy=preferred.copy;
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [scenarioId, setScenarioId] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [visits, setVisits] = useState<Visit[]>(initialVisits);
  const [visitsLoading, setVisitsLoading] = useState(false);
  const [visitsError, setVisitsError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.scenario_id === scenarioId) ?? null,
    [scenarioId, scenarios],
  );
  const participantIsValid = !participantId || isParticipantId(participantId);
  const canSubmit = Boolean(
    preparationEnabled && participantId && participantIsValid && visitOrdinal && scenarioId && locale && acknowledged
      && !loading && !visitsLoading && !submitting,
  );

  const localeRef = useRef(locale);
  localeRef.current = locale;
  useEffect(() => {
    if (scenarios.length === 1) setScenarioId((current) => current || scenarios[0].scenario_id);
  }, [scenarios]);

  useEffect(() => {
    let mounted = true;
    setVisitOrdinal("");
    setVisitsError(null);
    if (!participantId) {
      setVisits(initialVisits);
      setVisitsLoading(false);
      return () => {
        mounted = false;
      };
    }

    const provided = initialVisits.filter((visit) => visit.participant_id === participantId);
    if (provided.length > 0) {
      setVisits(provided);
      setVisitOrdinal(String(provided[0].visit_ordinal));
      setVisitsLoading(false);
      return () => {
        mounted = false;
      };
    }

    setVisits([]);
    setVisitsLoading(true);
    void visitsLoader(participantId)
      .then((rows) => {
        if (mounted) {
          setVisits(rows);
          setVisitOrdinal(rows[0] ? String(rows[0].visit_ordinal) : "");
        }
      })
      .catch((reason: unknown) => {
        if (mounted) setVisitsError(reason instanceof Error ? reason.message : t(localeRef.current, "setup.load_error"));
      })
      .finally(() => {
        if (mounted) setVisitsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [initialVisits, participantId, visitsLoader]);

  const admission=useAssessmentAdmission(assigned.attempt&&assigned.context?{attemptId:assigned.attempt.id,participantId,visitId:assigned.context.visit_id,purpose:'study',locale:assigned.context.locale}:null, {runtime:true});
  useEffect(()=>{let active=true;const bound=assigned.context;if(bound){setParticipantId(bound.participant_id);setScenarioId((bound.config.scenario as {id:string}).id);setPresentation((bound.config.presentation??undefined) as PresentationConfig|undefined);void visitsLoader(bound.participant_id).then(rows=>{if(active)setVisitOrdinal(String(rows.find(v=>v.id===bound.visit_id)?.visit_ordinal??''));});}return()=>{active=false;};},[assigned.context,visitsLoader]);
  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      if (!acknowledged) setSubmitError(t(locale, "setup.acknowledgement_required"));
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      const admitted=await admission.admit();
      if(!admitted)throw new Error('Select an assigned assessment at /study/assignments');
      const prepared: PreparedSession = await createSimulationSession({ attempt_id:admitted.attemptId,
        execution_purpose: "study",
        participant_id: participantId,
        visit_ordinal: Number(visitOrdinal),
        scenario_id: scenarioId,
        ...(presentation ? {presentation}:{}),
        locale,
      });
      // Confirm old sessions before deleting their leases, and never put the
      // lease in the URL, page state, or any rendered diagnostic.
      await storePreparedSessionLease(prepared);
      router.push(`/mission?session=${encodeURIComponent(prepared.id)}`);
    } catch (reason: unknown) {
      setSubmitError(errorMessage(reason, locale));
    } finally {
      setSubmitting(false);
    }
  }

  const labels = STRINGS[locale];
  const state = (complete: boolean, current: boolean): GuidedStepState => complete ? "complete" : current ? "current" : "upcoming";
  const identityReady = Boolean(participantId && participantIsValid);
  const protocolReady = Boolean(identityReady && visitOrdinal && scenarioId);

  return (
    <div className="min-h-screen bg-background px-4 py-8 text-foreground sm:px-6 lg:px-10">
      <div className="mx-auto max-w-6xl space-y-7"><p className="text-sm text-muted-foreground">{locale === "en" ? "Before this study mission, complete KSS and a valid 10-minute PVT for the same visit." : "Antes de esta misión de estudio, complete KSS y una PVT válida de 10 minutos para la misma visita."} <Link href="/study/assignments" className="underline">{copy("Seleccionar evaluación asignada","Select assigned assessment")}</Link></p>
        {!preparationEnabled && <p role="status" className="border border-warning/40 bg-warning/10 px-4 py-3 text-sm text-warning">{copy("Elija sesión de estudio arriba para preparar una misión. Para familiarización, use la prueba técnica desde el catálogo.", "Choose study session above to prepare a mission. For familiarization, use the technical test from the catalog.")}</p>}
        <fieldset disabled={Boolean(assigned.context)}><PresentationSetup locale={locale} value={presentation} onChange={setPresentation}/></fieldset>
        <header className="flex flex-col justify-between gap-5 border-b border-white/10 pb-6 md:flex-row md:items-end">
          <div>
            <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.24em] text-muted-foreground">
              <Radio className="h-3.5 w-3.5 text-success" aria-hidden="true" />
              <span>{labels["app.name"]}</span>
            </div>
            <h1 className="font-display text-3xl font-semibold uppercase tracking-tight text-white sm:text-4xl">
              {labels["setup.title"]}
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{labels["setup.subtitle"]}</p>
          </div>
          <div className="flex items-center gap-2 border border-success/30 bg-success/5 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-success">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {labels["setup.offline"]}
          </div>
        </header>

        <div role="note" className="flex gap-3 border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{labels["app.research_only"]}</span>
        </div>

        <GuidedSteps
          label={copy("Pasos para crear una misión", "Steps to create a mission")}
          steps={[
            { title: copy("Participante", "Participant"), description: copy("Seleccione un código P01–P999999.", "Select a P01–P999999 code."), state: state(identityReady, true) },
            { title: copy("Visita y escenario", "Visit and scenario"), description: copy("Confirme la visita y el escenario instalado.", "Confirm the visit and installed scenario."), state: state(protocolReady, identityReady) },
            { title: copy("Confirmación", "Confirmation"), description: copy("Confirme el uso como instrumento de investigación.", "Confirm use as a research instrument."), state: state(acknowledged, protocolReady) },
            { title: copy("Continuar", "Continue"), description: copy("Cree la sesión y vaya al panel de misión.", "Create the session and continue to the mission console."), state: state(false, canSubmit) },
          ]}
        />

        <Card id="briefing" className="scroll-mt-6 border-info/30 bg-info/5">
          <CardHeader>
            <CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Instrucciones antes de la misión", "Instructions before the mission")}</CardTitle>
            <CardDescription>{copy("El participante debe escuchar o leer esta guía completa antes de iniciar PRÁCTICA.", "The participant must listen to or read this complete guide before starting PRACTICE.")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <InstructionAudio src={`/audio/instructions/mission-${locale === "es-CO" ? "es" : "en"}.mp3`} label={copy("Escuchar instrucciones de misión", "Listen to mission instructions")} unavailableLabel={copy("Audio no disponible", "Audio unavailable")} />
            <div className="grid gap-3 md:grid-cols-2">
              <div id="practice" className="scroll-mt-6 rounded border border-white/10 bg-black/20 p-4"><div className="page-kicker text-info">06 · {copy("Práctica", "Practice")}</div><p className="mt-2 text-sm text-muted-foreground">{copy("Seleccione aeronaves y contactos; pruebe los comandos inferiores; confirme alertas. Los errores de práctica sirven para aprender la interfaz.", "Select aircraft and contacts; try the bottom commands; acknowledge alerts. Practice errors are used to learn the interface.")}</p></div>
              <div id="blocks" className="scroll-mt-6 rounded border border-white/10 bg-black/20 p-4"><div className="page-kicker text-info">07 · {copy("Bloques", "Blocks")}</div><p className="mt-2 text-sm text-muted-foreground">{copy("Después de PRÁCTICA, siga el bloque que aparece en la barra superior. No cambie de pantalla ni cierre la ventana.", "After PRACTICE, follow the block shown in the top bar. Do not switch screens or close the window.")}</p></div>
              <div id="workload" className="scroll-mt-6 rounded border border-white/10 bg-black/20 p-4"><div className="page-kicker text-info">08 · {copy("Preguntas", "Questions")}</div><p className="mt-2 text-sm text-muted-foreground">{copy("Cuando aparezca una pregunta, la misión se detendrá. Responda con su percepción actual; no hay respuestas correctas en las escalas de carga.", "When a question appears, the mission will pause. Answer from your current perception; workload scales have no correct answers.")}</p></div>
              <div id="complete" className="scroll-mt-6 rounded border border-white/10 bg-black/20 p-4"><div className="page-kicker text-info">09 · {copy("Finalizar", "Finish")}</div><p className="mt-2 text-sm text-muted-foreground">{copy("Al terminar, espere la confirmación de guardado y avise al investigador antes de abandonar el puesto.", "At the end, wait for the saved confirmation and tell the researcher before leaving the station.")}</p></div>
            </div>
          </CardContent>
        </Card>

        {loadError && (
          <div role="alert" className="border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {loadError}
          </div>
        )}
        {loading && (
          <p role="status" aria-live="polite" className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
            {labels["a11y.loading"]}…
          </p>
        )}

        <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl uppercase tracking-wide">{labels["setup.title"]}</CardTitle>
              <CardDescription>{labels["setup.subtitle"]}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="mission-participant">{labels["setup.participant"]}</Label>
                  <select
                    id="mission-participant"
                    aria-label={labels["setup.participant"]}
                    value={participantId}
                    onChange={(event) => setParticipantId(event.target.value)}
                    disabled={Boolean(assigned.context) || loading || submitting}
                    className="h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 text-sm outline-none transition focus:border-white/60 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">—</option>
                    {participants.map((participant) => (
                      <option key={participant.id} value={participant.id}>{participant.id}</option>
                    ))}
                  </select>
                  {!loading && participants.length === 0 && (
                    <p className="text-xs text-muted-foreground">
                      {labels["setup.no_participants"]} <Link href="/participants" className="text-info underline underline-offset-2">{copy("Crear participante", "Create participant")}</Link>
                    </p>
                  )}
                  {participantId && !participantIsValid && (
                    <p role="alert" className="text-xs text-danger">{copy("Este registro antiguo no puede iniciar una misión. Cree un código como P01.", "This older record cannot start a mission. Create a code such as P01.")}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="mission-visit">{labels["setup.visit"]}</Label>
                  <select
                    id="mission-visit"
                    aria-label={labels["setup.visit"]}
                    value={visitOrdinal}
                    onChange={(event) => setVisitOrdinal(event.target.value)}
                    disabled={Boolean(assigned.context) || !participantId || visitsLoading || submitting}
                    className="h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 text-sm outline-none transition focus:border-white/60 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">{visitsLoading ? "…" : "—"}</option>
                    {visits
                      .slice()
                      .sort((left, right) => left.visit_ordinal - right.visit_ordinal)
                      .map((visit) => (
                        <option key={visit.id} value={String(visit.visit_ordinal)}>
                          {copy("Día", "Day")} {visit.scheduled_day} · V{visit.visit_ordinal}
                        </option>
                      ))}
                  </select>
                  {visitsError && <p role="alert" className="text-xs text-danger">{visitsError}</p>}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="mission-scenario">{labels["setup.scenario"]}</Label>
                  <select
                    id="mission-scenario"
                    aria-label={labels["setup.scenario"]}
                    value={scenarioId}
                    onChange={(event) => setScenarioId(event.target.value)}
                    disabled={Boolean(assigned.context) || loading || submitting}
                    className="h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 text-sm outline-none transition focus:border-white/60 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">—</option>
                    {scenarios.map((scenario) => (
                      <option key={scenario.scenario_id} value={scenario.scenario_id}>
                        {scenario.titles?.[locale] || scenario.title || scenario.scenario_id}
                      </option>
                    ))}
                  </select>
                  {!loading && scenarios.length === 0 && (
                    <p className="text-xs text-muted-foreground">{labels["setup.no_scenarios"]}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label>{labels["setup.language"]}</Label>
                  <div className="flex h-10 items-center rounded-[3px] border border-input bg-black/20 px-3 text-sm text-muted-foreground">
                    {locale === "es-CO" ? labels["setup.language_es_co"] : labels["setup.language_en"]}
                  </div>
                </div>
              </div>

              <label className="flex cursor-pointer items-start gap-3 border border-white/10 bg-white/[0.02] px-3 py-3 text-sm text-muted-foreground transition hover:border-white/25">
                <input
                  type="checkbox"
                  aria-label={`Research instrument — ${labels["setup.research_instrument"]}`}
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                  disabled={submitting}
                  className="mt-0.5 h-4 w-4 accent-white"
                />
                <span>{labels["setup.research_instrument"]}</span>
              </label>

              {submitError && (
                <p role="alert" className="border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                  {submitError}
                </p>
              )}

              <Button
                type="submit"
                aria-label={`Prepare session — ${labels["setup.prepare_session"]}`}
                disabled={!canSubmit}
                className="w-full sm:w-auto"
              >
                {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <ChevronRight className="mr-2 h-4 w-4" aria-hidden="true" />}
                {submitting ? labels["setup.preparing"] : copy("Crear sesión y continuar al panel", "Create session and continue to console")}
              </Button>
            </CardContent>
          </Card>

          <Card className={cn("h-fit", !selectedScenario && "opacity-80")}>
            <CardHeader>
              <CardTitle className="font-display text-lg uppercase tracking-wide">{labels["setup.manifest"]}</CardTitle>
              <CardDescription>{selectedScenario?.titles?.[locale] || selectedScenario?.title || "—"}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 font-mono text-xs">
              <dl className="space-y-3">
                <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-2">
                  <dt className="text-muted-foreground">{labels["setup.manifest_hash"]}</dt>
                  <dd className="text-right text-foreground">{selectedScenario ? manifestHash(selectedScenario) : "—"}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-2">
                  <dt className="text-muted-foreground">{labels["setup.fleet_range"]}</dt>
                  <dd className="text-right text-foreground">{selectedScenario ? scenarioFleet() : "2–8 sUAS"}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-2">
                  <dt className="text-muted-foreground">{labels["setup.profiles"]}</dt>
                  <dd className="text-right text-foreground">
                    {(selectedScenario?.block_order?.length === PROFILE_ORDER.length
                      ? selectedScenario.block_order
                      : PROFILE_ORDER).join(" · ")}
                  </dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-muted-foreground">{labels["setup.offline"]}</dt>
                  <dd className="inline-flex items-center gap-1.5 text-success"><Check className="h-3.5 w-3.5" aria-hidden="true" /> {locale === "es-CO" ? "ejecución local" : "local runtime"}</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </form>
      </div>
    </div>
  );
}
