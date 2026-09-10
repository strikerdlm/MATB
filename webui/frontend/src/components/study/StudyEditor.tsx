"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import {
  studyCall,
  studyVersions,
  type StudyPayload,
  type StudyDraft,
  type StudyVersion,
  type Binding,
  type StudyOccasion,
} from "@/lib/study";
import { policyChoice } from "./policy-labels";
import { PolicyEditor } from "./PolicyEditor";
import { OccasionEditor } from "./OccasionEditor";

export function StudyEditor() {
  const { copy } = useAppLocale();
  const [kind, setKind] = useState("pre-post-recovery");
  const [payload, setPayload] = useState<StudyPayload | null>(null);
  const [draft, setDraft] = useState<StudyDraft | null>(null);
  const [drafts, setDrafts] = useState<StudyDraft[]>([]);
  const [selectedDraft, setSelectedDraft] = useState("");
  const [history, setHistory] = useState<unknown>(null);
  const [rehearsal, setRehearsal] = useState<string | null>(null);
  const [versions, setVersions] = useState<StudyVersion[]>([]);
  const [bindings, setBindings] = useState<Record<string, unknown>>({});
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  useEffect(() => {
    void studyCall<StudyDraft[]>("/drafts")
      .then(setDrafts)
      .catch((e) => setNotice(String(e)));
    void studyVersions()
      .then((v) => setVersions(v.versions))
      .catch((e) => setNotice(String(e)));
    void studyCall<Record<string, unknown>>("/bindings")
      .then(setBindings)
      .catch((e) => setNotice(String(e)));
  }, []);
  const change = (next: StudyPayload) => {
    setPayload(next);
    setDirty(true);
    setRehearsal(null);
  };
  async function run(action: () => Promise<void>) {
    setBusy(true);
    setNotice("");
    try {
      await action();
    } catch (e) {
      setNotice(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    if (!payload) return null;
    const next = await studyCall<StudyDraft>(
      draft ? `/drafts/${draft.id}` : "/drafts",
      payload,
      draft ? "PUT" : "POST",
    );
    setDraft(next);
    setDrafts((rows) => [...rows.filter((row) => row.id !== next.id), next]);
    setSelectedDraft(next.id);
    setDirty(false);
    return next;
  }
  async function openDraft(identity: string) {
    const next = await studyCall<StudyDraft>(`/drafts/${identity}`);
    setDraft(next);
    setPayload(JSON.parse(next.payload_json));
    setSelectedDraft(next.id);
    setDirty(false);
    setRehearsal(null);
    setHistory(await studyCall(`/drafts/${identity}/history`));
  }
  const study = payload?.study,
    analysis = payload?.analysis;
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-semibold">
        {copy(
          "Protocolo y plan de análisis",
          "Study protocol and analysis plan",
        )}
      </h1>
      <p>
        {copy(
          "Las plantillas y ensayos son sintéticos. Escriba las reglas científicas antes de aprobar una versión.",
          "Templates and rehearsals are synthetic. Author the scientific rules before approving a version.",
        )}
      </p>
      <Link href="/study/assignments" className="underline">
        {copy("Asignaciones de participantes", "Participant assignments")}
      </Link>
      <fieldset disabled={busy} className="flex flex-wrap gap-3">
        <label>
          {copy("Borrador guardado", "Saved draft")}
          <select
            className="native-select block"
            value={selectedDraft}
            onChange={(e) => setSelectedDraft(e.target.value)}
          >
            <option value="">—</option>
            {drafts.map((row) => (
              <option key={row.id} value={row.id}>
                {JSON.parse(row.payload_json).study.title} · {row.id}
                {row.frozen_version_id ? copy(" · Congelado", " · Frozen") : ""}
              </option>
            ))}
          </select>
        </label>
        <Button
          disabled={!selectedDraft}
          onClick={() => void run(() => openDraft(selectedDraft))}
        >
          {copy("Abrir borrador", "Open saved draft")}
        </Button>
      </fieldset>
      {draft && (
        <p className="text-sm">
          {copy("Identidad del borrador", "Draft identity")}: {draft.id} ·{" "}
          {draft.sha256}
        </p>
      )}
      {draft && (
        <details>
          <summary>
            {copy(
              "Historial de validación, ensayo y aprobación",
              "Validation, rehearsal and approval history",
            )}
          </summary>
          <Button
            onClick={() =>
              void run(async () =>
                setHistory(await studyCall(`/drafts/${draft.id}/history`)),
              )
            }
          >
            {copy("Actualizar historial", "Refresh history")}
          </Button>
          <pre className="overflow-auto whitespace-pre-wrap text-xs">
            {JSON.stringify(history, null, 2)}
          </pre>
        </details>
      )}
      <fieldset disabled={busy} className="flex gap-3">
        <label>
          {copy("Plantilla", "Template")}
          <select
            className="native-select block"
            value={kind}
            onChange={(e) => setKind(e.target.value)}
          >
            <option value="longitudinal">
              {copy("Longitudinal", "Longitudinal")}
            </option>
            <option value="pre-post-recovery">
              {copy("Pre / post / recuperación", "Pre / post / recovery")}
            </option>
            <option value="repeated-block">
              {copy("Bloques repetidos", "Repeated blocks")}
            </option>
          </select>
        </label>
        <Button
          onClick={() =>
            void run(async () => {
              setPayload(await studyCall<StudyPayload>(`/templates/${kind}`));
              setDraft(null);
              setRehearsal(null);
              setDirty(true);
            })
          }
        >
          {copy("Cargar plantilla", "Load template")}
        </Button>
      </fieldset>
      {payload && study && analysis && (
        <fieldset
          disabled={busy || !!draft?.frozen_version_id}
          className="space-y-5"
        >
          <div className="grid gap-3 sm:grid-cols-2">
            <label>
              {copy("Identidad del estudio", "Study identity")}
              <input
                className="native-input block w-full"
                value={study.study_id}
                onChange={(e) =>
                  change({
                    ...payload,
                    study: { ...study, study_id: e.target.value },
                  })
                }
              />
            </label>
            <label>
              {copy("Título", "Title")}
              <input
                className="native-input block w-full"
                value={study.title}
                onChange={(e) =>
                  change({
                    ...payload,
                    study: { ...study, title: e.target.value },
                  })
                }
              />
            </label>
          </div>
          <label className="block">
            <input
              type="checkbox"
              checked={study.synthetic}
              onChange={(e) =>
                change({
                  ...payload,
                  study: { ...study, synthetic: e.target.checked },
                })
              }
            />{" "}
            {copy(
              "Este borrador es sintético (no se puede aprobar)",
              "This draft is synthetic (cannot be approved)",
            )}
          </label>
          <label className="block">
            {copy(
              "Brazos de asignación, separados por coma",
              "Assignment arms, comma separated",
            )}
            <input
              className="native-input block"
              value={study.arms.join(",")}
              onChange={(e) =>
                change({
                  ...payload,
                  study: {
                    ...study,
                    arms: e.target.value.split(",").map((s) => s.trim()),
                  },
                })
              }
            />
          </label>
          <h2 className="font-semibold">
            {copy("Visitas programadas", "Scheduled visits")}
          </h2>
          {study.visits.map((v, i) => (
            <div key={i} className="flex flex-wrap gap-2">
              {(["ordinal", "code", "scheduled_day"] as const).map((key) => (
                <label key={key}>
                  {key === "ordinal"
                    ? copy("Visita", "Visit")
                    : key === "code"
                      ? copy("Código", "Code")
                      : copy("Día", "Day")}
                  <input
                    className="native-input block w-28"
                    type={key === "code" ? "text" : "number"}
                    value={v[key]}
                    onChange={(e) =>
                      change({
                        ...payload,
                        study: {
                          ...study,
                          visits: study.visits.map((row, n) =>
                            n === i
                              ? {
                                  ...row,
                                  [key]:
                                    key === "code"
                                      ? e.target.value
                                      : Number(e.target.value),
                                }
                              : row,
                          ),
                        },
                      })
                    }
                  />
                </label>
              ))}
            </div>
          ))}
          <h2 className="font-semibold">
            {copy("Ocasiones e instrumentos", "Occasions and instruments")}
          </h2>
          {study.occasions.map((occasion, i) => (
            <OccasionEditor
              key={i}
              occasion={occasion}
              study={study}
              bindings={bindings}
              onChange={(next) => {
                const occasions = study.occasions.map((o, n) =>
                  n === i ? next : o,
                );
                change({
                  ...payload,
                  study: {
                    ...study,
                    occasions,
                    enabled_instruments: [
                      ...new Set(occasions.map((o) => o.instrument)),
                    ],
                  },
                });
              }}
              onRemove={() => {
                const occasions = study.occasions.filter((_, n) => n !== i);
                change({
                  ...payload,
                  study: {
                    ...study,
                    occasions,
                    enabled_instruments: [
                      ...new Set(occasions.map((o) => o.instrument)),
                    ],
                  },
                });
              }}
            />
          ))}
          <Button
            onClick={() => {
              const next: StudyOccasion = {
                key: `occasion${study.occasions.length + 1}`,
                visit_ordinal: study.visits[0].ordinal,
                instrument: "pvt",
                phase: "",
                order: study.occasions.length + 1,
                condition_by_arm: Object.fromEntries(
                  study.arms.map((a) => [a, ""]),
                ),
                locale: "es-419",
                config: (bindings.pvt as Binding[] | undefined)?.[0] ?? {},
                prerequisite_keys: [],
                target_key: null,
                collection_group: null,
                accompanying_key: null,
              };
              change({
                ...payload,
                study: {
                  ...study,
                  occasions: [...study.occasions, next],
                  enabled_instruments: [
                    ...new Set([...study.enabled_instruments, "pvt"]),
                  ],
                },
              });
            }}
          >
            {copy("Agregar ocasión", "Add occasion")}
          </Button>
          <h2 className="font-semibold">
            {copy("Intervalos de recuperación", "Recovery intervals")}
          </h2>
          <p>
            {copy(
              "La duración la define el investigador; el intervalo pertenece a la misma visita.",
              "The researcher defines the duration; the interval belongs to the same visit.",
            )}
          </p>
          {study.recovery_intervals.map((interval, i) => (
            <div key={i} className="flex flex-wrap gap-3">
              <label>
                {copy("Identidad del intervalo", "Interval key")}
                <input
                  className="native-input block"
                  value={interval.key}
                  onChange={(e) =>
                    change({
                      ...payload,
                      study: {
                        ...study,
                        recovery_intervals: study.recovery_intervals.map(
                          (r, n) =>
                            n === i ? { ...r, key: e.target.value } : r,
                        ),
                      },
                    })
                  }
                />
              </label>
              {(["anchor_key", "before_key"] as const).map((key) => (
                <label key={key}>
                  {key === "anchor_key"
                    ? copy("Después de", "After")
                    : copy("Antes de", "Before")}
                  <select
                    className="native-select block"
                    value={interval[key]}
                    onChange={(e) =>
                      change({
                        ...payload,
                        study: {
                          ...study,
                          recovery_intervals: study.recovery_intervals.map(
                            (r, n) =>
                              n === i ? { ...r, [key]: e.target.value } : r,
                          ),
                        },
                      })
                    }
                  >
                    <option value="">—</option>
                    {study.occasions.map((o) => (
                      <option key={o.key}>{o.key}</option>
                    ))}
                  </select>
                </label>
              ))}
              <label>
                {copy("Duración (segundos)", "Duration (seconds)")}
                <input
                  type="number"
                  min={1}
                  className="native-input block w-28"
                  value={interval.duration_seconds || ""}
                  onChange={(e) =>
                    change({
                      ...payload,
                      study: {
                        ...study,
                        recovery_intervals: study.recovery_intervals.map(
                          (r, n) =>
                            n === i
                              ? {
                                  ...r,
                                  duration_seconds: Number(e.target.value),
                                }
                              : r,
                        ),
                      },
                    })
                  }
                />
              </label>
            </div>
          ))}
          <Button
            onClick={() =>
              change({
                ...payload,
                study: {
                  ...study,
                  recovery_intervals: [
                    ...study.recovery_intervals,
                    {
                      key: `recovery${study.recovery_intervals.length + 1}`,
                      anchor_key: "",
                      before_key: "",
                      duration_seconds: 0,
                    },
                  ],
                },
              })
            }
          >
            {copy("Agregar intervalo", "Add interval")}
          </Button>
          <PolicyEditor payload={payload} onChange={change} />
          <h2 className="font-semibold">
            {copy(
              "Reglas obligatorias del investigador",
              "Required researcher rules",
            )}
          </h2>
          {(["preparation", "repeat", "interruption"] as const).map((key) => (
            <label key={key} className="block">
              {key === "preparation"
                ? copy("Regla de preparación", "Preparation rule")
                : key === "repeat"
                  ? copy("Regla de repetición", "Repeat rule")
                  : copy("Regla de interrupción", "Interruption rule")}
              <textarea
                className="native-input block w-full"
                value={study.rules[key]}
                onChange={(e) =>
                  change({
                    ...payload,
                    study: {
                      ...study,
                      rules: { ...study.rules, [key]: e.target.value },
                    },
                  })
                }
              />
            </label>
          ))}
          <p className="text-sm">
            {copy(
              "Defina criterios, evidencia requerida y decisiones. El ensayo no verifica competencia humana ni calificación física.",
              "Define criteria, required evidence and decisions. Rehearsal does not verify human competence or physical qualification.",
            )}
          </p>
          <label>
            {copy("Unidad de análisis", "Analysis unit")}
            <select
              className="native-select block"
              value={analysis.unit}
              onChange={(e) =>
                change({
                  ...payload,
                  analysis: {
                    ...analysis,
                    unit: e.target.value as typeof analysis.unit,
                  },
                })
              }
            >
              <option value="participant">
                {policyChoice("participant", copy)}
              </option>
              <option value="visit">{policyChoice("visit", copy)}</option>
              <option value="attempt">{policyChoice("attempt", copy)}</option>
            </select>
          </label>
          {analysis.outcomes.map((outcome, i) => (
            <div key={i} className="space-y-2 rounded border p-3">
              <label>
                {copy("Resultado", "Outcome key")}
                <input
                  className="native-input block"
                  value={outcome.key}
                  onChange={(e) =>
                    change({
                      ...payload,
                      analysis: {
                        ...analysis,
                        outcomes: analysis.outcomes.map((o, n) =>
                          n === i ? { ...o, key: e.target.value } : o,
                        ),
                      },
                    })
                  }
                />
              </label>
              <label>
                {copy("Métrica", "Metric")}
                <select
                  className="native-select block"
                  value={outcome.metric}
                  onChange={(e) =>
                    change({
                      ...payload,
                      analysis: {
                        ...analysis,
                        outcomes: analysis.outcomes.map((o, n) =>
                          n === i ? { ...o, metric: e.target.value } : o,
                        ),
                      },
                    })
                  }
                >
                  {[
                    "pvt.median_rt_ms",
                    "pvt.lapses",
                    "pvt.kss",
                    "screen.hcf",
                    "screen.simple_rt",
                    "openmatb.workload",
                    "openmatb.performance",
                    "physiology.raw",
                    "physiology.mean_hr_bpm",
                    "liftoff.performance",
                    "suas.performance",
                  ].map((m) => (
                    <option key={m} value={m}>
                      {policyChoice(m, copy)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                {copy("Resumen", "Summary")}
                <select
                  className="native-select block"
                  value={outcome.summary}
                  onChange={(e) =>
                    change({
                      ...payload,
                      analysis: {
                        ...analysis,
                        outcomes: analysis.outcomes.map((o, n) =>
                          n === i
                            ? {
                                ...o,
                                summary: e.target.value as typeof o.summary,
                              }
                            : o,
                        ),
                      },
                    })
                  }
                >
                  {["individual", "mean", "median"].map((m) => (
                    <option key={m} value={m}>
                      {policyChoice(m, copy)}
                    </option>
                  ))}
                </select>
              </label>
              <div>
                {study.occasions.map((o) => (
                  <label key={o.key} className="mr-4">
                    <input
                      type="checkbox"
                      checked={outcome.occasion_keys.includes(o.key)}
                      onChange={(e) =>
                        change({
                          ...payload,
                          analysis: {
                            ...analysis,
                            outcomes: analysis.outcomes.map((r, n) =>
                              n === i
                                ? {
                                    ...r,
                                    occasion_keys: e.target.checked
                                      ? [...r.occasion_keys, o.key]
                                      : r.occasion_keys.filter(
                                          (k) => k !== o.key,
                                        ),
                                  }
                                : r,
                            ),
                          },
                        })
                      }
                    />
                    {o.key}
                  </label>
                ))}
              </div>
            </div>
          ))}
          <Button
            onClick={() =>
              change({
                ...payload,
                analysis: {
                  ...analysis,
                  outcomes: [
                    ...analysis.outcomes,
                    {
                      key: `outcome${analysis.outcomes.length + 1}`,
                      metric: "pvt.median_rt_ms",
                      occasion_keys: [],
                      summary: "individual",
                    },
                  ],
                },
              })
            }
          >
            {copy("Agregar resultado", "Add outcome")}
          </Button>
          {analysis.contrasts.map((c, i) => (
            <div className="flex gap-3" key={i}>
              {(["left_outcome", "right_outcome"] as const).map((key) => (
                <label key={key}>
                  {key === "left_outcome"
                    ? copy("Resultado izquierdo", "Left outcome")
                    : copy("Resultado derecho", "Right outcome")}
                  <select
                    className="native-select block"
                    value={c[key]}
                    onChange={(e) =>
                      change({
                        ...payload,
                        analysis: {
                          ...analysis,
                          contrasts: analysis.contrasts.map((r, n) =>
                            n === i ? { ...r, [key]: e.target.value } : r,
                          ),
                        },
                      })
                    }
                  >
                    <option value="">—</option>
                    {analysis.outcomes.map((o) => (
                      <option key={o.key}>{o.key}</option>
                    ))}
                  </select>
                </label>
              ))}
            </div>
          ))}
          <Button
            onClick={() =>
              change({
                ...payload,
                analysis: {
                  ...analysis,
                  contrasts: [
                    ...analysis.contrasts,
                    {
                      key: `contrast${analysis.contrasts.length + 1}`,
                      left_outcome: "",
                      right_outcome: "",
                      operation: "difference",
                    },
                  ],
                },
              })
            }
          >
            {copy("Agregar contraste descriptivo", "Add descriptive contrast")}
          </Button>
          {(
            ["exclusions", "denominators", "qualification", "pooling"] as const
          ).map((key) => (
            <label key={key} className="block">
              {
                {
                  exclusions: copy("Exclusiones", "Exclusions"),
                  denominators: copy("Denominadores", "Denominators"),
                  qualification: copy(
                    "Calificación de evidencia",
                    "Evidence qualification",
                  ),
                  pooling: copy(
                    "Agrupación entre versiones",
                    "Pooling across versions",
                  ),
                }[key]
              }
              <textarea
                className="native-input block w-full"
                value={analysis.rules[key]}
                onChange={(e) =>
                  change({
                    ...payload,
                    analysis: {
                      ...analysis,
                      rules: { ...analysis.rules, [key]: e.target.value },
                    },
                  })
                }
              />
            </label>
          ))}
          <label>
            {copy("Datos históricos desconocidos", "Unknown historical data")}
            <select
              className="native-select block"
              value={analysis.rules.historical_unknowns}
              onChange={(e) =>
                change({
                  ...payload,
                  analysis: {
                    ...analysis,
                    rules: {
                      ...analysis.rules,
                      historical_unknowns: e.target
                        .value as typeof analysis.rules.historical_unknowns,
                    },
                  },
                })
              }
            >
              <option value="exclude">{copy("Excluir", "Exclude")}</option>
              <option value="reviewed_classification_required">
                {copy(
                  "Exigir clasificación revisada y permiso del plan",
                  "Require reviewed classification and plan permission",
                )}
              </option>
            </select>
          </label>
          <div className="flex gap-3">
            <Button
              onClick={() =>
                void run(async () => {
                  await save();
                  setNotice(copy("Borrador guardado", "Draft saved"));
                })
              }
            >
              {copy("Guardar borrador", "Save draft")}
            </Button>
            <Button
              onClick={() =>
                void run(async () => {
                  const saved = await save();
                  if (saved) {
                    const result = await studyCall<{
                      issues: { path: string; message: string }[];
                    }>(`/drafts/${saved.id}/validate`, {});
                    setNotice(
                      result.issues.length
                        ? result.issues
                            .map((i) => `${i.path}: ${i.message}`)
                            .join("\n")
                        : copy("Validación correcta", "Validation passed"),
                    );
                  }
                })
              }
            >
              {copy("Validar", "Validate")}
            </Button>
            <Button
              onClick={() =>
                void run(async () => {
                  const saved = await save();
                  if (saved) {
                    const result = await studyCall<{ id: string }>(
                      `/drafts/${saved.id}/rehearse`,
                      {},
                    );
                    setRehearsal(result.id);
                    setNotice(
                      copy(
                        "Ensayo sintético completado; no es una aprobación.",
                        "Synthetic rehearsal completed; this is not approval.",
                      ),
                    );
                  }
                })
              }
            >
              {copy("Ensayar", "Rehearse")}
            </Button>
          </div>
        </fieldset>
      )}
      <fieldset disabled={busy} className="space-y-3">
        <label className="block">
          {copy("Investigador responsable", "Named researcher")}
          <input
            className="native-input block"
            value={actor}
            onChange={(e) => setActor(e.target.value)}
          />
        </label>
        <label className="block">
          {copy(
            "Motivo y declaración de revisión",
            "Reason and review attestation",
          )}
          <textarea
            className="native-input block w-full"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
        </label>
        <Button
          disabled={
            !draft ||
            dirty ||
            !rehearsal ||
            !actor.trim() ||
            !reason.trim() ||
            !!payload?.study.synthetic ||
            !!draft.frozen_version_id
          }
          onClick={() =>
            void run(async () => {
              if (!draft) return;
              const frozen = await studyCall<StudyVersion>(`/drafts/${draft.id}/freeze`, {
                sha256: draft.sha256,
                rehearsal_id: rehearsal,
                actor,
                reason,
              });
              setVersions((await studyVersions()).versions);
              const saved = { ...draft, frozen_version_id: frozen.id };
              setDraft(saved);
              setDrafts(rows => rows.map(row => row.id === draft.id ? saved : row));
            })
          }
        >
          {copy("Congelar con aprobación", "Freeze with approval")}
        </Button>
      </fieldset>
      <h2 className="font-semibold">
        {copy("Historial de versiones inmutables", "Immutable version history")}
      </h2>
      {versions.map((v) => (
        <div
          key={v.id}
          id={`version-${v.id}`}
          className="space-y-2 rounded border p-3"
        >
          <Link className="underline" href={`/study#version-${v.id}`}>
            {v.study.title} · {v.id}
          </Link>
          <p className="break-all text-xs">
            StudySpec {v.study_sha256}
            <br />
            AnalysisPlan {v.analysis_plan_id} · {v.analysis_sha256}
          </p>
          <div className="flex gap-3">
            <Button
              disabled={busy || !actor || !reason}
              onClick={() =>
                void run(async () => {
                  await studyCall(`/versions/${v.id}/activate`, {
                    actor,
                    reason,
                  });
                  setNotice(
                    copy(
                      "Versión activada para nuevas asignaciones.",
                      "Version activated for new assignments.",
                    ),
                  );
                })
              }
            >
              {copy("Activar recolección", "Activate collection")}
            </Button>
            <Button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  const next = await studyCall<StudyDraft>(
                    `/versions/${v.id}/clone`,
                    {},
                  );
                  setDraft(next);
                  setPayload(JSON.parse(next.payload_json));
                  setRehearsal(null);
                  setDirty(false);
                })
              }
            >
              {copy("Crear enmienda", "Author amendment")}
            </Button>
          </div>
          <details>
            <summary>
              {copy("Ver versión exacta", "Inspect exact version")}
            </summary>
            <pre className="max-h-80 overflow-auto text-xs">
              {JSON.stringify(v, null, 2)}
            </pre>
          </details>
        </div>
      ))}
      {notice && (
        <p role="status" className="whitespace-pre-wrap">
          {notice}
        </p>
      )}
    </div>
  );
}
