"use client";

import { useEffect, useState } from "react";
import { Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import type { OpenMatbProfile, OpenMatbSession, WorkloadScaleSubmission } from "@/types/openmatb";

const INSTRUMENT_VERSION = "openmatb-workload-v1";

const TLX_ES = [
  ["mental_demand", "Demanda mental", "Baja", "Alta"],
  ["physical_demand", "Demanda física", "Baja", "Alta"],
  ["temporal_demand", "Demanda temporal", "Baja", "Alta"],
  ["performance", "Rendimiento", "Bueno", "Deficiente"],
  ["effort", "Esfuerzo", "Bajo", "Alto"],
  ["frustration", "Frustración", "Baja", "Alta"],
] as const;

const BEDFORD_ES = [
  "Carga insignificante.",
  "Carga baja.",
  "Capacidad sobrante suficiente para todas las tareas adicionales deseables.",
  "Capacidad sobrante insuficiente para atender fácilmente tareas adicionales.",
  "Capacidad sobrante reducida; las tareas adicionales no reciben la atención deseada.",
  "Poca capacidad sobrante; el esfuerzo permite poca atención a tareas adicionales.",
  "Muy poca capacidad sobrante, pero se puede mantener el esfuerzo en las tareas principales.",
  "Carga muy alta, casi sin capacidad sobrante; es difícil mantener el esfuerzo.",
  "Carga extremadamente alta, sin capacidad sobrante; existen dudas serias sobre mantener el esfuerzo.",
  "Tareas abandonadas; no fue posible aplicar esfuerzo suficiente.",
];

const TLX_EN = [
  ["mental_demand", "Mental demand", "Low", "High"],
  ["physical_demand", "Physical demand", "Low", "High"],
  ["temporal_demand", "Temporal demand", "Low", "High"],
  ["performance", "Performance", "Good", "Poor"],
  ["effort", "Effort", "Low", "High"],
  ["frustration", "Frustration", "Low", "High"],
] as const;

const BEDFORD_EN = [
  "Insignificant workload.",
  "Low workload.",
  "Enough spare capacity for all desirable additional tasks.",
  "Not enough spare capacity to easily attend to additional tasks.",
  "Reduced spare capacity; additional tasks do not receive the desired attention.",
  "Little spare capacity; effort permits little attention to additional tasks.",
  "Very little spare capacity, but effort on the primary tasks can be maintained.",
  "Very high workload, almost no spare capacity; effort is difficult to maintain.",
  "Extremely high workload, no spare capacity; serious doubts about maintaining effort.",
  "Tasks abandoned; sufficient effort could not be applied.",
];

type TlxKey = WorkloadScaleSubmission["nasa_tlx"] extends Record<infer Key, number> ? Key : never;
type TlxDraft = Partial<Record<TlxKey, number>>;

interface WorkloadDraft {
  instrument_version: typeof INSTRUMENT_VERSION;
  session_id: string;
  block_instance_id: string;
  nasa_tlx: TlxDraft;
  bedford: number | null;
}

type DraftNotice = "restored" | "invalid" | "unavailable" | "clear_failed";

interface BoundDraftState {
  identity: string | null;
  ready: boolean;
  tlx: TlxDraft;
  bedford: number | null;
}

export interface WorkloadQuestionnaireProps {
  sessionId: string;
  blockInstanceId: string | null;
  profile: Exclude<OpenMatbProfile, "PRACTICE">;
  tokenAvailable: boolean;
  onSubmit: (submission: WorkloadScaleSubmission) => Promise<OpenMatbSession>;
  onAccepted: (session: OpenMatbSession, outcome: { draftClearFailed: boolean }) => void;
}

export function workloadDraftKey(sessionId: string, blockInstanceId: string): string {
  return `openmatb.workload-draft.${INSTRUMENT_VERSION}.${sessionId}.${blockInstanceId}`;
}

function isScaleValue(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0 && value <= 100 && value % 5 === 0;
}

function parseDraft(raw: string, sessionId: string, blockInstanceId: string): WorkloadDraft | null {
  const value: unknown = JSON.parse(raw);
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Partial<WorkloadDraft>;
  if (
    candidate.instrument_version !== INSTRUMENT_VERSION
    || candidate.session_id !== sessionId
    || candidate.block_instance_id !== blockInstanceId
    || !candidate.nasa_tlx
    || typeof candidate.nasa_tlx !== "object"
    || Array.isArray(candidate.nasa_tlx)
  ) return null;
  for (const [key, answer] of Object.entries(candidate.nasa_tlx)) {
    if (!TLX_EN.some(([known]) => known === key) || !isScaleValue(answer)) return null;
  }
  if (candidate.bedford !== null && !(Number.isInteger(candidate.bedford) && Number(candidate.bedford) >= 1 && Number(candidate.bedford) <= 10)) return null;
  return candidate as WorkloadDraft;
}

function confirmsSavedBlock(session: OpenMatbSession, _profile: OpenMatbProfile, blockInstanceId: string): boolean {
  return Object.values(session.scores).some(score => score.block_instance_id === blockInstanceId);
}

export function WorkloadQuestionnaire({
  sessionId,
  blockInstanceId,
  profile,
  tokenAvailable,
  onSubmit,
  onAccepted,
}: WorkloadQuestionnaireProps) {
  const { copy, locale } = useAppLocale();
  const tlxScales = locale === "en" ? TLX_EN : TLX_ES;
  const bedfordChoices = locale === "en" ? BEDFORD_EN : BEDFORD_ES;
  const draftIdentity = blockInstanceId ? workloadDraftKey(sessionId, blockInstanceId) : null;
  const [draftState, setDraftState] = useState<BoundDraftState>({ identity: null, ready: false, tlx: {}, bedford: null });
  const [draftNotice, setDraftNotice] = useState<DraftNotice | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const identityMatches = draftState.identity === draftIdentity;
  const tlx = identityMatches ? draftState.tlx : {};
  const bedford = identityMatches ? draftState.bedford : null;

  useEffect(() => {
    setDraftNotice(null);
    setSubmitError(null);
    if (!blockInstanceId || !draftIdentity) {
      setDraftState({ identity: null, ready: false, tlx: {}, bedford: null });
      return;
    }
    let nextTlx: TlxDraft = {};
    let nextBedford: number | null = null;
    try {
      const raw = window.sessionStorage.getItem(draftIdentity);
      if (raw) {
        let draft: WorkloadDraft | null = null;
        try {
          draft = parseDraft(raw, sessionId, blockInstanceId);
        } catch {
          draft = null;
        }
        if (draft) {
          nextTlx = draft.nasa_tlx;
          nextBedford = draft.bedford;
          setDraftNotice("restored");
        } else {
          window.sessionStorage.removeItem(draftIdentity);
          setDraftNotice("invalid");
        }
      }
    } catch {
      setDraftNotice("unavailable");
    } finally {
      setDraftState({ identity: draftIdentity, ready: true, tlx: nextTlx, bedford: nextBedford });
    }
  }, [blockInstanceId, draftIdentity, sessionId]);

  useEffect(() => {
    if (!blockInstanceId || !draftIdentity || !draftState.ready || draftState.identity !== draftIdentity || (Object.keys(draftState.tlx).length === 0 && draftState.bedford === null)) return;
    const draft: WorkloadDraft = {
      instrument_version: INSTRUMENT_VERSION,
      session_id: sessionId,
      block_instance_id: blockInstanceId,
      nasa_tlx: draftState.tlx,
      bedford: draftState.bedford,
    };
    try {
      window.sessionStorage.setItem(draftIdentity, JSON.stringify(draft));
    } catch {
      setDraftNotice("unavailable");
    }
  }, [blockInstanceId, draftIdentity, draftState, sessionId]);

  const missing: string[] = tlxScales.filter(([key]) => !isScaleValue(tlx[key])).map(([, label]) => label);
  if (bedford === null) missing.push("Bedford");

  if (!blockInstanceId) {
    return <section aria-label={copy("Cuestionario de carga de trabajo", "Workload questionnaire")}>
      <p role="alert" className="border border-warning/40 bg-warning/10 p-4 text-sm text-warning">
        {copy(
          "No se puede identificar este bloque. Actualice esta página. Si el mensaje continúa, pida al investigador que vuelva a abrir la pantalla del participante.",
          "This block cannot be identified. Refresh this page. If the message remains, ask the researcher to reopen the participant display.",
        )}
      </p>
    </section>;
  }

  const durableBlockInstanceId = blockInstanceId;
  const complete = missing.length === 0;

  async function submit() {
    if (!complete || submitting || !tokenAvailable) return;
    setSubmitting(true);
    setSubmitError(null);
    const submission: WorkloadScaleSubmission = {
      block_instance_id: durableBlockInstanceId,
      nasa_tlx: tlx as WorkloadScaleSubmission["nasa_tlx"],
      bedford: bedford as number,
    };
    try {
      const response = await onSubmit(submission);
      if (!confirmsSavedBlock(response, profile, durableBlockInstanceId)) {
        setSubmitError(copy(
          "El servidor no confirmó las respuestas de este bloque. Se conservó el borrador; inténtelo de nuevo.",
          "The server did not confirm ratings for this block. Your draft was kept; try again.",
        ));
        return;
      }
      let draftClearFailed = false;
      try {
        window.sessionStorage.removeItem(workloadDraftKey(sessionId, durableBlockInstanceId));
      } catch {
        draftClearFailed = true;
        setDraftNotice("clear_failed");
      }
      onAccepted(response, { draftClearFailed });
    } catch (reason: unknown) {
      setSubmitError(openMatbErrorMessage(reason, copy, ["No se pudieron guardar las escalas.", "Ratings could not be saved."]));
    } finally {
      setSubmitting(false);
    }
  }

  return <section className="space-y-8" aria-label={copy("Cuestionario de carga de trabajo", "Workload questionnaire")}>
    <div>
      <h2 className="font-display text-2xl uppercase">{copy("Índice de carga de tareas (RTLX sin ponderar)", "Task Load Index (unweighted RTLX)")}</h2>
      <p className="mt-2 text-sm text-muted-foreground">{copy("Califique las seis dimensiones de 0 a 100. El resultado es su promedio, sin ponderación.", "Rate all six dimensions from 0 to 100. The result is their unweighted mean.")}</p>
      <p role="status" className={`mt-3 text-sm ${complete ? "text-success" : "text-warning"}`}>
        {complete
          ? copy("Todas las respuestas están completas.", "All responses are answered.")
          : copy(`${missing.length} sin responder: ${missing.join(", ")}.`, `${missing.length} unanswered: ${missing.join(", ")}.`)}
      </p>
    </div>

    {draftNotice && <p role={draftNotice === "restored" ? "status" : "alert"} className={`border p-3 text-sm ${draftNotice === "restored" ? "border-info/30 bg-info/5 text-info" : "border-warning/40 bg-warning/10 text-warning"}`}>
      {draftNotice === "restored" && copy("Se restauró el borrador de este bloque.", "Draft restored for this block.")}
      {draftNotice === "invalid" && copy("El borrador guardado no era válido y no se restauró.", "Saved draft was invalid and was not restored.")}
      {draftNotice === "unavailable" && copy("El almacenamiento de borradores no está disponible en esta pestaña. Mantenga esta página abierta hasta guardar las respuestas.", "Draft storage is unavailable in this tab. Keep this page open until ratings are saved.")}
      {draftNotice === "clear_failed" && copy("Las respuestas se guardaron, pero no se pudo eliminar el borrador de esta pestaña.", "Ratings were saved, but the draft could not be removed from this tab.")}
    </p>}
    {submitError && <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{submitError}</p>}

    <div className="grid gap-5 sm:grid-cols-2">
      {tlxScales.map(([key, label, low, high]) => <div key={key} className="mission-panel block p-4" data-testid={`${key}-scale`}>
        <label htmlFor={`openmatb-${key}`} className="font-semibold">{label}</label>
        <input
          id={`openmatb-${key}`}
          aria-valuetext={isScaleValue(tlx[key]) ? String(tlx[key]) : copy("Sin responder", "Not answered")}
          className="mt-4 w-full accent-white"
          type="range"
          min={0}
          max={100}
          step={5}
          value={tlx[key] ?? 50}
          onChange={(event) => setDraftState((current) => current.identity === draftIdentity
            ? { ...current, tlx: { ...current.tlx, [key]: Number(event.target.value) } }
            : current)}
        />
        <span className="mt-2 flex items-center justify-between gap-3 font-mono text-xs text-muted-foreground">
          <span>{low}</span>
          <strong className="text-lg text-foreground" data-testid={`${key}-value`}>{isScaleValue(tlx[key]) ? tlx[key] : copy("Sin responder", "Not answered")}</strong>
          <span>{high}</span>
        </span>
        {!isScaleValue(tlx[key]) && <Button className="mt-3 h-auto min-h-10 max-w-full whitespace-normal px-3 py-2 text-sm normal-case tracking-normal" size="sm" variant="outline" onClick={() => setDraftState((current) => current.identity === draftIdentity
          ? { ...current, tlx: { ...current.tlx, [key]: 50 } }
          : current)}>
          {copy(`Usar 50 para ${label}`, `Use 50 for ${label}`)}
        </Button>}
      </div>)}
    </div>

    <fieldset>
      <legend className="font-display text-2xl uppercase">Bedford</legend>
      <p className="mt-2 text-sm text-warning">{copy("Medida secundaria exploratoria; traducción no validada localmente.", "Exploratory secondary measure; local validation has not been established.")}</p>
      <div className="mt-4 grid gap-2">
        {bedfordChoices.map((text, index) => {
          const value = index + 1;
          return <label key={value} className="flex cursor-pointer gap-3 border border-white/10 p-3 hover:border-white/40">
            <input type="radio" name="bedford" value={value} checked={bedford === value} onChange={() => setDraftState((current) => current.identity === draftIdentity ? { ...current, bedford: value } : current)} />
            <strong className="w-6 font-mono">{value}</strong>
            <span>{text}</span>
          </label>;
        })}
      </div>
    </fieldset>

    {!tokenAvailable && <p role="alert" className="text-sm text-warning">{copy("Esta pestaña no conserva la credencial del participante. Pida al investigador que vuelva a abrir esta pantalla.", "This tab does not hold the participant credential. Ask the researcher to reopen this display.")}</p>}
    <Button className="h-auto min-h-11 max-w-full whitespace-normal px-5 py-3 text-sm normal-case tracking-normal" size="lg" disabled={!tokenAvailable || submitting || !complete} onClick={() => void submit()}>
      <Send className="mr-2 h-4 w-4" />
      {submitting ? copy("Guardando…", "Saving…") : copy("Guardar escalas y continuar", "Save ratings and continue")}
    </Button>
  </section>;
}
