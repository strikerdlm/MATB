"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams, useRouter } from "next/navigation";
import Link from "next/link";
import { AstraVisitHeader, AstraRecovery } from "./AstraVisitSupport";
import { Button } from "@/components/ui/button";
import { FixedLocaleProvider, useAppLocale } from "@/lib/i18n";
import {
  assignmentDetail,
  studyCall,
  type AssignmentDetail,
} from "@/lib/study";
import { createAttempt, getAttempt, type Attempt } from "@/lib/assessments";
import {
  getOpenMatbSession,
  createOpenMatbSession,
  controllerAction,
  storeOpenMatbCredentials,
  readOpenMatbController,
  abortOpenMatbSession,
} from "@/lib/openmatb/api";

interface Preparation {
  id: string;
  occasion_key: string;
  instrument: string;
  next_action: string;
  presentation: {
    locale: "en" | "es-419";
    resolved_task_instructions?: Record<string, string>;
    items: { id: string; task: string; text: string; question: string }[];
  };
  practice_attempt_ids: string[];
  events: {
    stage: string;
    passed: boolean | null;
    attempt_id?: string;
    native_attempt_id?: string;
    session_id?: string;
  }[];
}
interface Readiness {
  requirements: Record<
    string,
    {
      occasion_key: string;
      state: string;
      preparation_id?: string;
      reason?: unknown;
    }[]
  >;
  preparations: Preparation[];
}
const routes: Record<string, string> = {
  pvt: "/pvt",
  screen: "/screen",
  openmatb: "/openmatb/setup",
  liftoff: "/liftoff/setup",
  suas: "/mission/setup",
  physiology: "/physiology/polar-h10",
};

export function StudyParticipant() {
  const params = useSearchParams();
  const identity = params.get("assignment");
  const [detail, setDetail] = useState<AssignmentDetail | null>(null);
  const [error, setError] = useState("");
  const { copy } = useAppLocale();
  useEffect(() => {
    let active = true;
    setError("");
    if (identity)
      void assignmentDetail(identity)
        .then((value) => {
          if (active) setDetail(value);
        })
        .catch((e) => {
          if (active) setError(String(e));
        });
    return () => {
      active = false;
    };
  }, [identity]);
  if (!identity)
    return (
      <Link href="/study/assignments">
        {copy("Seleccionar visita asignada", "Select assigned visit")}
      </Link>
    );
  if (error) return <p role="alert">{error}</p>;
  if (!detail || detail.assignment.id !== identity)
    return <p>{copy("Cargando visita…", "Loading visit…")}</p>;
  const locale =
    detail.version.study.occasions.find((o) => detail.occasions[o.key])
      ?.locale ?? "es-419";
  return (
    <FixedLocaleProvider locale={locale}>
      <ParticipantVisit key={identity} initial={detail} />
    </FixedLocaleProvider>
  );
}

function ParticipantVisit({ initial }: { initial: AssignmentDetail }) {
  const query = useSearchParams();
  const astra = initial.version.study.study_id === "astra-matb-field-2026";
  const [displayIndex, setDisplayIndex] = useState(0);
  const displayQuery = query.get("display");
  useEffect(() => {
    const key = `astra.display.${initial.assignment.id}`;
    let saved: string | null = null;
    try { saved = sessionStorage.getItem(key); } catch { /* Use the primary display. */ }
    const requested = Number(displayQuery ?? saved ?? "0");
    const index = Number.isInteger(requested) && requested >= 0 && requested <= 15 ? requested : 0;
    setDisplayIndex(index);
    if (astra) { try { sessionStorage.setItem(key, String(index)); } catch { /* The URL still selects this visit's display. */ } }
  }, [astra, displayQuery, initial.assignment.id]);
  const preferred = useAppLocale();
  const router = useRouter();
  const [detail, setDetail] = useState(initial);
  const [readiness, setReadiness] = useState<Readiness | null>(null);
  const [run, setRun] = useState<Preparation | null>(null);
  const [responses, setResponses] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [help, setHelp] = useState(false);
  const [stopped, setStopped] = useState(false);
  const [stopSelection, setStopSelection] = useState("");
  const mounted = useRef(true);
  const refreshEpoch = useRef(0);
  const nativeRequests = useRef(
    new Map<string, { attemptId: string; sessionId: string }>(),
  );
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const id = initial.assignment.id;
  const refresh = useCallback(async () => {
    const epoch = ++refreshEpoch.current;
    const [next, prepared] = await Promise.all([
      assignmentDetail(id),
      studyCall<Readiness>(`/assignments/${id}/preparation`),
    ]);
    if (!mounted.current || epoch !== refreshEpoch.current) return;
    if (next.assignment.id !== id)
      throw new Error("Assignment response identity changed.");
    setDetail(next);
    setReadiness(prepared);
    setRun((current) =>
      current
        ? (prepared.preparations.find((item) => item.id === current.id) ?? null)
        : null,
    );
  }, [id]);
  useEffect(() => {
    void refresh().catch((e) => setError(String(e)));
  }, [refresh]);
  async function act(action: () => Promise<void>) {
    setBusy(true);
    setError("");
    try {
      await action();
      if (mounted.current) await refresh();
    } catch (e) {
      if (mounted.current) setError(String(e));
    } finally {
      if (mounted.current) setBusy(false);
    }
  }
  const occasions = detail.version.study.occasions
    .filter((o) => detail.occasions[o.key])
    .toSorted((a, b) => a.order - b.order);
  const next = occasions.find(
    (o) =>
      !detail.attempts[o.key]?.some((a) => a.acquisition_state === "finished"),
  );
  const locale =
    (run && run.next_action !== "ready"
      ? run.presentation.locale
      : next?.locale) ?? preferred.locale;
  const copy = (es: string, en: string) => (locale === "en" ? en : es);
  const occasionLabel = (key: string) => {
    if (!astra) return key;
    const occasion = occasions.find(item => item.key === key);
    if (!occasion) return key;
    const level = occasion.condition_by_arm[detail.assignment.arm];
    const workload = ({ LOW: copy("baja", "low"), MEDIUM: copy("media", "medium"), HIGH: copy("alta", "high") })[level] ?? level;
    return `${copy("Bloque", "Block")} ${Math.ceil(occasion.order / 2)}/3 · ${copy("carga", "workload")} ${workload}`;
  };
  const missing = next
    ? readiness?.requirements[next.key]?.find((r) => r.state !== "prepared")
    : null;
  const stopCandidates =
    readiness?.preparations.filter(
      (preparation) =>
        preparation.next_action !== "stopped" &&
        !detail.attempts[preparation.occasion_key]?.some((attempt) =>
          ["started", "finished"].includes(attempt.acquisition_state),
        ),
    ) ?? [];
  const stopTarget =
    stopCandidates.find((item) => item.id === run?.id) ??
    stopCandidates.find((item) => item.id === stopSelection) ??
    (stopCandidates.length === 1 ? stopCandidates[0] : null);
  const recovery = detail.version.study.recovery_intervals?.find(
    (interval) =>
      interval.before_key === next?.key &&
      !detail.recovery_intervals?.some(
        (record) => record.interval_key === interval.key && record.ended_at,
      ),
  );
  const stageLabel = (stage: string) =>
    ({
      demonstration: copy("Preparar: demostración", "Prepare: demonstration"),
      acknowledgement: copy(
        "Entender: confirmar lectura",
        "Understand: acknowledge reading",
      ),
      comprehension: copy("Entender: responder", "Understand: answer"),
      practice: copy("Practicar", "Practice"),
      resolve_mapping: copy(
        "Preparar indicativo y control reales",
        "Prepare actual callsign and controls",
      ),
      ready: copy("Listo", "Ready"),
      stopped: copy("Preparación detenida", "Preparation stopped"),
    })[stage] ?? stage;
  async function stopNativePreparation(target: Preparation, latest: Readiness) {
    if (
      occasions.find((o) => o.key === target.occasion_key)?.instrument ===
      "openmatb"
    ) {
      const unresolved = () =>
        new Error(
          copy(
            "No se pudo confirmar el proceso nativo exacto. El investigador debe resolver su propiedad antes de detener la preparación.",
            "The exact native process could not be confirmed. The researcher must resolve ownership before stopping preparation.",
          ),
        );
      const fresh = await assignmentDetail(id);
      const occasionId = fresh.occasions[target.occasion_key];
      if (
        fresh.assignment.id !== id ||
        fresh.assignment.participant_id !== detail.assignment.participant_id ||
        !occasionId ||
        occasionId !== detail.occasions[target.occasion_key]
      )
        throw unresolved();
      const associations = new Map<string, string>();
      for (const attempt of fresh.attempts[target.occasion_key] ?? []) {
        if (
          attempt.occasion_id !== occasionId ||
          attempt.acquisition_state === "started"
        )
          throw unresolved();
        for (const source of attempt.sources) {
          if (source.source_table !== "openmatb_suite_session") continue;
          if (
            associations.has(source.source_id) &&
            associations.get(source.source_id) !== attempt.id
          )
            throw unresolved();
          associations.set(source.source_id, attempt.id);
        }
      }
      const requested = nativeRequests.current.get(target.id);
      const presented = target.events
        .toReversed()
        .find((event) => event.session_id);
      if (
        requested &&
        associations.get(requested.sessionId) !== requested.attemptId
      )
        throw unresolved();
      if (
        presented?.session_id &&
        (!associations.has(presented.session_id) ||
          (presented.native_attempt_id &&
            associations.get(presented.session_id) !==
              presented.native_attempt_id))
      )
        throw unresolved();
      if (
        requested &&
        presented?.session_id &&
        requested.sessionId !== presented.session_id
      )
        throw unresolved();
      const retainedId = requested?.sessionId ?? presented?.session_id;
      const sessions = await Promise.all(
        [...associations.keys()].map(async (sessionId) => {
          const session = await getOpenMatbSession(sessionId);
          if (
            session.id !== sessionId ||
            session.participant_id !== fresh.assignment.participant_id ||
            session.study_assignment_id !== id
          )
            throw unresolved();
          return session;
        }),
      );
      const active = sessions.filter(
        (session) => !["COMPLETE", "ABORTED"].includes(session.lifecycle),
      );
      if (
        active.length > 1 ||
        (retainedId && active.some((session) => session.id !== retainedId))
      )
        throw unresolved();
      if (
        !retainedId &&
        active.length &&
        latest.preparations.filter(
          (item) =>
            item.occasion_key === target.occasion_key &&
            item.next_action !== "stopped",
        ).length !== 1
      )
        throw unresolved();
      const native = active[0];
      if (native) {
        const lease = readOpenMatbController(native.id);
        if (!lease)
          throw new Error(
            copy(
              "El investigador debe detener el proceso nativo.",
              "The researcher must stop the native process.",
            ),
          );
        const aborted = await abortOpenMatbSession(native.id, lease);
        if (aborted.id !== native.id || aborted.lifecycle !== "ABORTED")
          throw new Error(
            copy(
              "La detención nativa no está confirmada.",
              "Native stop is not confirmed.",
            ),
          );
      }
    }
  }
  function launch(attempt: Attempt, instrument: string) {
    router.push(
      `${routes[instrument]}?purpose=${attempt.execution_purpose}&attempt=${encodeURIComponent(attempt.id)}&participant=${encodeURIComponent(detail.assignment.participant_id)}&visit=${detail.assignment.visit_id}`,
    );
  }
  return (
    <section className="mx-auto max-w-3xl space-y-5">
      {astra ? <AstraVisitHeader detail={detail} /> : <>
      <h1 className="text-2xl font-semibold">
        {copy("Visita del participante", "Participant visit")}:{" "}
        {detail.assignment.participant_id}
      </h1>
      <p>
        {copy("Visita", "Visit")} {detail.assignment.visit_id} ·{" "}
        {detail.version.study.title}
      </p>
      <p className="break-all text-xs">{detail.assignment.version_id}</p>
      </>}
      <div className="flex gap-3">
        <Button variant="outline" onClick={() => setHelp(!help)}>
          {copy("Ayuda", "Help")}
        </Button>
        <Button
          variant="outline"
          disabled={busy || !stopTarget}
          onClick={() =>
            void act(async () => {
              if (!stopTarget) return;
              const latest = await studyCall<Readiness>(
                `/assignments/${id}/preparation`,
              );
              const target = latest.preparations.find(
                (item) =>
                  item.id === stopTarget.id && item.next_action !== "stopped",
              );
              if (!target)
                throw new Error(
                  copy(
                    "Seleccione una preparación activa exacta.",
                    "Select an exact active preparation.",
                  ),
                );
              await stopNativePreparation(target, latest);
              const saved = await studyCall<Preparation>(
                `/preparation/${target.id}/stop`,
                {},
              );
              if (saved.id !== target.id || saved.next_action !== "stopped")
                throw new Error(
                  copy(
                    "No se confirmó el registro de detención.",
                    "The stop evidence write was not confirmed.",
                  ),
                );
              if (mounted.current) {
                setRun(saved);
                setStopped(true);
              }
            })
          }
        >
          {copy("Detener preparación", "Stop preparation")}
        </Button>
      </div>
      {stopCandidates.length > 1 &&
        !stopCandidates.some((item) => item.id === run?.id) && (
          <label>
            {copy(
              "Preparación exacta para detener",
              "Exact preparation to stop",
            )}
            <select
              value={stopSelection}
              onChange={(event) => setStopSelection(event.target.value)}
            >
              <option value="">—</option>
              {stopCandidates.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.occasion_key} · {item.id}
                </option>
              ))}
            </select>
          </label>
        )}
      {help && (
        <p>
          {copy(
            "Pida ayuda al investigador. Durante una tarea use sus controles de ayuda y detención existentes. La preparación no califica el equipo físico.",
            "Ask the researcher for help. During a task use its existing help and stop controls. Preparation does not qualify physical equipment.",
          )}
        </p>
      )}
      {stopped ? (
        <p>
          {copy(
            "Preparación detenida. Los registros previos se conservaron; consulte al investigador.",
            "Preparation stopped. Prior records were retained; contact the researcher.",
          )}
        </p>
      ) : (
        <>
          {run && run.next_action !== "ready" ? (
            <fieldset disabled={busy} className="space-y-4 rounded border p-4">
              <h2>
                {stageLabel(run.next_action)} · {occasionLabel(run.occasion_key)}
              </h2>
              {Object.entries(
                run.presentation.resolved_task_instructions ?? {},
              ).map(([task, text]) => (
                <p key={task}>{text}</p>
              ))}
              {run.presentation.items.map((item) => (
                <div key={item.id}>
                  <p>{item.text}</p>
                  {run.next_action === "comprehension" && (
                    <label>
                      {item.question}
                      <input
                        className="native-input block"
                        value={responses[item.id] ?? ""}
                        onChange={(e) =>
                          setResponses({
                            ...responses,
                            [item.id]: e.target.value,
                          })
                        }
                      />
                    </label>
                  )}
                </div>
              ))}
              {["demonstration", "acknowledgement", "comprehension"].includes(
                run.next_action,
              ) && (
                <Button
                  onClick={() =>
                    void act(async () => {
                      setRun(
                        await studyCall<Preparation>(
                          `/preparation/${run.id}/stages`,
                          {
                            stage: run.next_action,
                            responses:
                              run.next_action === "comprehension"
                                ? responses
                                : {},
                          },
                        ),
                      );
                      setResponses({});
                    })
                  }
                >
                  {copy("Continuar", "Continue")}
                </Button>
              )}
              {run.next_action === "practice" && (
                <>
                  <Button
                    onClick={() =>
                      void act(async () => {
                        const attempt = await studyCall<Attempt>(
                          `/preparation/${run.id}/practice`,
                          {},
                        );
                        launch(attempt, run.instrument);
                      })
                    }
                  >
                    {copy("Realizar práctica", "Perform practice")}
                  </Button>
                  <PracticeReuse
                    key={run.id}
                    preparation={run}
                    onReused={async (updated) => {
                      if (mounted.current)
                        await act(async () => {
                          setRun(updated);
                        });
                    }}
                  />
                  {run.practice_attempt_ids.map((attempt) => (
                    <Button
                      key={attempt}
                      variant="outline"
                      onClick={() =>
                        void act(async () =>
                          setRun(
                            await studyCall<Preparation>(
                              `/preparation/${run.id}/grade`,
                              { attempt_id: attempt },
                            ),
                          ),
                        )
                      }
                    >
                      {copy("Evaluar observaciones", "Evaluate observations")} ·{" "}
                      {attempt.slice(0, 8)}
                    </Button>
                  ))}
                </>
              )}
              {run.next_action === "resolve_mapping" && (
                <Button
                  onClick={() =>
                    void act(async () => {
                      const spec = occasions.find(
                        (o) => o.key === run.occasion_key,
                      )!;
                      let attempt = detail.attempts[spec.key]?.find(
                        (a) => a.acquisition_state === "created",
                      );
                      if (!attempt)
                        attempt = await createAttempt(
                          detail.occasions[spec.key],
                          "study",
                        );
                      const native = spec.config as {
                        preset: { id: string; version: string };
                        instructions: { id: string; version: string };
                        visual: { id: string; version: string };
                      };
                      const prepared = await createOpenMatbSession({
                        attempt_id: attempt.id,
                        execution_purpose: "study",
                        preparation_only: true,
                        participant_id: detail.assignment.participant_id,
                        visit_ordinal: spec.visit_ordinal,
                        preset_id: native.preset.id,
                        preset_version: native.preset.version,
                        instruction_protocol_id: native.instructions.id,
                        instruction_version: native.instructions.version,
                        visual_profile_id: native.visual.id,
                        visual_profile_version: native.visual.version,
                        display_index: displayIndex,
                      });
                      storeOpenMatbCredentials(prepared);
                      nativeRequests.current.set(run.id, {
                        attemptId: attempt.id,
                        sessionId: prepared.session.id,
                      });
                      await controllerAction(
                        prepared.session.id,
                        "preflight",
                        prepared.controller_lease,
                      );
                      setRun(
                        await studyCall<Preparation>(
                          `/preparation/${run.id}/native-presentation`,
                          { session_id: prepared.session.id },
                        ),
                      );
                    })
                  }
                >
                  {copy(
                    "Resolver preparación nativa",
                    "Resolve native preparation",
                  )}
                </Button>
              )}
              <Button
                variant="outline"
                onClick={() =>
                  void act(async () => {
                    const latest = await studyCall<Readiness>(
                      `/assignments/${id}/preparation`,
                    );
                    const target = latest.preparations.find(
                      (item) => item.id === run.id,
                    );
                    if (!target)
                      throw new Error(
                        copy(
                          "No se encontró la preparación exacta.",
                          "The exact preparation was not found.",
                        ),
                      );
                    await stopNativePreparation(target, latest);
                    setRun(
                      await studyCall<Preparation>(
                        `/assignments/${id}/preparation/${run.occasion_key}`,
                        {},
                      ),
                    );
                    setResponses({});
                  })
                }
              >
                {copy(
                  "Reiniciar preparación explícitamente",
                  "Explicitly restart preparation",
                )}
              </Button>
              <details>
                <summary>
                  {copy(
                    "Respuestas y observaciones guardadas",
                    "Saved responses and observations",
                  )}
                </summary>
                <pre className="overflow-auto whitespace-pre-wrap text-xs">
                  {JSON.stringify(run.events, null, 2)}
                </pre>
              </details>
            </fieldset>
          ) : astra && recovery ? (
            <AstraRecovery key={recovery.key} detail={detail} interval={recovery} onComplete={refresh} />
          ) : missing ? (
            <Button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  const existing = readiness?.preparations
                    .toReversed()
                    .find(
                      (p) =>
                        p.occasion_key === missing.occasion_key &&
                        p.next_action !== "ready",
                    );
                  setRun(
                    existing ??
                      (await studyCall<Preparation>(
                        `/assignments/${id}/preparation/${missing.occasion_key}`,
                        {},
                      )),
                  );
                })
              }
            >
              {copy("Preparar", "Prepare")} · {occasionLabel(missing.occasion_key)}
            </Button>
          ) : recovery ? (
            <section className="space-y-3">
              <h2>
                {copy("Intervalo de recuperación", "Recovery interval")} ·{" "}
                {recovery.key}
              </h2>
              <p>
                {copy(
                  "Descanse según el protocolo. El investigador registra el inicio y el fin del intervalo.",
                  "Rest as prescribed. The researcher records the interval start and finish.",
                )}{" "}
                {recovery.duration_seconds}s
              </p>
              <Button disabled={busy} onClick={() => void act(refresh)}>
                {copy("Comprobar siguiente acción", "Check next action")}
              </Button>
            </section>
          ) : next ? (
            <>
              <h2>
                {next.instrument === "questionnaire"
                  ? copy("Valoraciones", "Ratings")
                  : copy("Listo para realizar", "Ready to perform")}{" "}
                · {occasionLabel(next.key)}
              </h2>
              {!astra && <p>
                {next.phase} · {next.instrument}
              </p>}
              <Button
                disabled={busy}
                onClick={() =>
                  void act(async () => {
                    const rows = detail.attempts[next.key] ?? [];
                    if (rows.length > 1)
                      throw new Error(
                        copy(
                          "El investigador debe seleccionar el intento exacto.",
                          "The researcher must select the exact attempt.",
                        ),
                      );
                    let attempt = rows[0];
                    if (!attempt) {
                      const targets = next.target_key
                        ? (detail.attempts[next.target_key]?.filter(
                            (row) => row.acquisition_state === "finished",
                          ) ?? [])
                        : [];
                      if (next.target_key && targets.length !== 1)
                        throw new Error(
                          copy(
                            "El investigador debe seleccionar la tarea destinataria exacta.",
                            "The researcher must select the exact target task.",
                          ),
                        );
                      attempt = await createAttempt(
                        detail.occasions[next.key],
                        "study",
                        targets[0]?.id,
                      );
                    }
                    if (next.instrument === "questionnaire") {
                      const target = occasions.find(
                        (o) => o.key === next.target_key,
                      )!;
                      const task = detail.attempts[target.key]?.find(
                        (a) => a.id === attempt.target_attempt_id,
                      );
                      const source = task?.sources.find(
                        (s) => s.source_table === "openmatb_suite_session",
                      );
                      if (!source)
                        throw new Error(
                          copy(
                            "Abra la pantalla nativa de la tarea exacta.",
                            "Open the native display for the exact task.",
                          ),
                        );
                      router.push(
                        `/openmatb/participant?session=${source.source_id}&questionnaire=${attempt.id}`,
                      );
                      return;
                    }
                    if (
                      next.prerequisite_keys.length &&
                      attempt.acquisition_state === "created"
                    ) {
                      const selected: Record<string, string> = {};
                      for (const key of next.prerequisite_keys) {
                        const candidates =
                          detail.attempts[key]?.filter(
                            (a) => a.acquisition_state === "finished",
                          ) ?? [];
                        if (candidates.length !== 1)
                          throw new Error(
                            copy(
                              "El investigador debe elegir el intento previo exacto.",
                              "The researcher must choose the exact prerequisite attempt.",
                            ),
                          );
                        selected[key] = candidates[0].id;
                      }
                      await studyCall(`/attempts/${attempt.id}/prerequisites`, {
                        selections: selected,
                      });
                    }
                    if (next.instrument === "openmatb") {
                      const fresh = await getAttempt(attempt.id);
                      const source = fresh.sources.find(
                        (s) => s.source_table === "openmatb_suite_session",
                      );
                      if (source) {
                        const lease = readOpenMatbController(source.source_id);
                        if (!lease)
                          throw new Error(
                            copy(
                              "Reabra el control nativo con el investigador.",
                              "Reopen native control with the researcher.",
                            ),
                          );
                        await controllerAction(
                          source.source_id,
                          "start",
                          lease,
                        );
                        router.push(
                          `/openmatb/participant?session=${source.source_id}`,
                        );
                        return;
                      }
                    }
                    launch(attempt, next.instrument);
                  })
                }
              >
                {next.instrument === "questionnaire"
                  ? copy("Responder valoraciones", "Answer ratings")
                  : copy("Realizar evaluación", "Perform assessment")}
              </Button>
            </>
          ) : (
            <p>
              {copy(
                "Evaluaciones realizadas. El investigador debe revisar los registros y cerrar la recolección de la visita.",
                "Assessments performed. The researcher must review the records and close visit collection.",
              )}
            </p>
          )}
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <Link href={astra || query.get("return") === "astra" ? "/astra" : "/study/assignments"} className="block underline">
        {astra ? copy("Volver a tripulantes ASTRA", "Return to ASTRA crew") : copy("Volver al investigador", "Return to researcher")}
      </Link>
    </section>
  );
}

function PracticeReuse({
  preparation,
  onReused,
}: {
  preparation: Preparation;
  onReused: (run: Preparation) => Promise<void>;
}) {
  const copy = (es: string, en: string) =>
    preparation.presentation.locale === "en" ? en : es;
  const [candidates, setCandidates] = useState<
    { event_id: string; attempt_id: string }[]
  >([]);
  const [selected, setSelected] = useState("");
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void studyCall<{ event_id: string; attempt_id: string }[]>(
      `/preparation/${preparation.id}/reusable-practice`,
    )
      .then((rows) => {
        if (active) setCandidates(rows);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [preparation.id]);
  if (!candidates.length) return error ? <p role="alert">{error}</p> : null;
  return (
    <details className="space-y-2">
      <summary>
        {copy(
          "Investigador: seleccionar competencia previa compatible",
          "Researcher: select compatible prior competence",
        )}
      </summary>
      <label>
        {copy("Observaciones previas exactas", "Exact prior observations")}
        <select
          className="native-select block"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">—</option>
          {candidates.map((item) => (
            <option key={item.event_id} value={item.event_id}>
              {item.attempt_id} · {item.event_id}
            </option>
          ))}
        </select>
      </label>
      <label>
        {copy("Investigador", "Researcher")}
        <input
          className="native-input block"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        />
      </label>
      <label>
        {copy("Motivo de reutilización", "Reuse reason")}
        <input
          className="native-input block"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <Button
        disabled={!selected || !actor.trim() || !reason.trim()}
        onClick={() =>
          void studyCall<Preparation>(
            `/preparation/${preparation.id}/reuse-practice`,
            { event_id: selected, actor, reason },
          )
            .then(onReused)
            .catch((e) => setError(String(e)))
        }
      >
        {copy(
          "Usar estas observaciones previas",
          "Use these prior observations",
        )}
      </Button>
      {error && <p role="alert">{error}</p>}
    </details>
  );
}
