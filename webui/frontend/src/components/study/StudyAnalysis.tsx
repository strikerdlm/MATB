"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { studyCall, studyVersions, type StudyVersion } from "@/lib/study";
import { getApiBase } from "@/lib/runtime-config";

type Criterion = {
  passed: boolean;
  required: boolean;
  reason: string;
  evidence?: unknown;
};
type Row = {
  occasion_id: string;
  occasion_key: string;
  participant_id: string;
  instrument: string;
  attempt_id: string | null;
  attempts: { id: string; ordinal: number; acquisition_state: string }[];
  denominator: boolean;
  eligible: boolean;
  criteria: Record<string, Criterion>;
  source_error?: string;
  values?: Record<string, number>;
};
type Snapshot = {
  rows: Row[];
  comparisons: unknown;
  plan: { eligibility_policy: { repeat_selection: string } };
};
type Result = {
  id: string;
  data_sha256: string;
  plan_sha256: string;
  snapshot: Snapshot;
  result: unknown;
  current_applicability: { changed: boolean };
};
export function StudyAnalysis() {
  const { copy } = useAppLocale();
  const [versions, setVersions] = useState<StudyVersion[]>([]),
    [version, setVersion] = useState("");
  const [actor, setActor] = useState(""),
    [reason, setReason] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [attempts, setAttempts] = useState<Record<string, string>>({}),
    [nativeIds, setNativeIds] = useState<Record<string, string>>({}),
    [hcfAttempts, setHcfAttempts] = useState<Record<string, string>>({});
  const [qualification, setQualification] = useState<
    Record<string, Record<string, string>>
  >({});
  const [preview, setPreview] = useState<Snapshot | null>(null),
    [result, setResult] = useState<Result | null>(null),
    [comparison, setComparison] = useState<Result | null>(null);
  const [executions, setExecutions] = useState<
      { id: string; version_id: string }[]
    >([]),
    [hcf, setHcf] = useState<{ id: string; snapshot: unknown }[]>([]),
    [selectedHcf, setSelectedHcf] = useState(""),
    [otherHcf, setOtherHcf] = useState("");
  const [reopen, setReopen] = useState(""),
    [compareId, setCompareId] = useState(""),
    [api, setApi] = useState("");
  const epoch = useRef(0);
  useEffect(() => {
    let active = true;
    const query = new URL(window.location.href).searchParams;
    const identity = query.get("execution");
    if (identity)
      void studyCall<Result>(`/analyses/${encodeURIComponent(identity)}`)
        .then((value) => {
          if (active) {
            setResult(value);
            setPreview(value.snapshot);
            setReopen(value.id);
          }
        })
        .catch((e) => {
          if (active) setError(String(e));
        });
    const other = query.get("compare");
    if (other)
      void studyCall<Result>(`/analyses/${encodeURIComponent(other)}`)
        .then((value) => {
          if (active) {
            setComparison(value);
            setCompareId(value.id);
          }
        })
        .catch((e) => {
          if (active) setError(String(e));
        });
    void Promise.all([
      studyVersions(),
      studyCall<typeof executions>("/analyses"),
      studyCall<typeof hcf>("/analyses/hcf"),
      getApiBase(),
    ])
      .then(([v, e, h, a]) => {
        if (active) {
          setVersions(v.versions);
          setExecutions(e);
          setHcf(h);
          setApi(a);
        }
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, []);
  function updateUrl(identity?: string, other?: string) {
    const url = new URL(window.location.href);
    if (identity) url.searchParams.set("execution", identity);
    else url.searchParams.delete("execution");
    if (other) url.searchParams.set("compare", other);
    else url.searchParams.delete("compare");
    window.history.replaceState(null, "", url);
  }
  function request() {
    return {
      version_id: version,
      actor,
      reason,
      attempts,
      native_metric_ids: Object.fromEntries(
        Object.entries(nativeIds).map(([k, v]) => [
          k,
          v
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        ]),
      ),
      hcf_attempts: hcfAttempts,
      qualification_ids: qualification,
    };
  }
  async function run(action: "preview" | "execute" | "open" | "compare") {
    const generation = epoch.current;
    setBusy(true);
    setError("");
    try {
      if (action === "preview") {
        const value = await studyCall<Snapshot>("/analyses/preview", request());
        if (generation === epoch.current) setPreview(value);
      } else {
        const value =
          action === "execute"
            ? await studyCall<Result>("/analyses", request())
            : await studyCall<Result>(
                `/analyses/${encodeURIComponent(action === "open" ? reopen : compareId)}`,
              );
        if (generation === epoch.current) {
          if (action === "compare") {
            setComparison(value);
            updateUrl(result?.id, value.id);
          } else {
            setResult(value);
            setPreview(value.snapshot);
            setReopen(value.id);
            updateUrl(value.id, comparison?.id);
          }
          if (action === "execute") {
            setExecutions(await studyCall("/analyses"));
            setHcf(await studyCall("/analyses/hcf"));
          }
        }
      }
    } catch (e) {
      if (generation === epoch.current) setError(String(e));
    } finally {
      if (generation === epoch.current) setBusy(false);
    }
  }
  return (
    <div className="mx-auto max-w-6xl space-y-5 p-6">
      <h1 className="text-2xl font-semibold">
        {copy("Análisis descriptivo del plan", "Plan descriptive analysis")}
      </h1>
      <p>
        {copy(
          "Seleccione un plan congelado. Se muestran observaciones o agregaciones por unidad y diferencias emparejadas; no se calcula una media de cohorte. Cada ejecución conserva datos, criterios y denominadores.",
          "Select a frozen plan. Results are observations or aggregates within each declared unit, and paired differences; no cohort mean is computed. Each execution preserves its data, criteria and denominators.",
        )}
      </p>
      <p>
        {copy(
          "Los ajustes inferenciales y la cuadrícula histórica de visitas son herramientas separadas.",
          "Inferential fits and the legacy visit grid are separate tools.",
        )}
      </p>
      <Link href="/study">
        {copy("Editar y congelar planes", "Author and freeze plans")}
      </Link>
      <label className="block">
        {copy("Plan congelado", "Frozen plan")}
        <select
          aria-label={copy("Plan congelado", "Frozen plan")}
          className="native-select block"
          value={version}
          disabled={busy}
          onChange={(e) => {
            epoch.current++;
            setVersion(e.target.value);
            updateUrl();
            setPreview(null);
            setResult(null);
            setAttempts({});
            setNativeIds({});
            setHcfAttempts({});
            setQualification({});
          }}
        >
          <option value="">—</option>
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {v.study.title}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        {copy("Investigador", "Researcher")}
        <input
          className="native-input block"
          value={actor}
          onChange={(e) => setActor(e.target.value)}
        />
      </label>
      <label className="block">
        {copy("Motivo", "Reason")}
        <input
          className="native-input block w-full"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      <Button
        disabled={busy || !version || !actor.trim() || !reason.trim()}
        onClick={() => void run("preview")}
      >
        {copy("Inspeccionar elegibilidad", "Inspect eligibility")}
      </Button>
      {error && <p role="alert">{error}</p>}
      {preview && (
        <section className="space-y-4">
          <h2>
            {copy("Ocasiones y denominadores", "Occasions and denominators")}
          </h2>
          {preview.rows.map((row) => (
            <article className="rounded border p-3" key={row.occasion_id}>
              <h3>
                {row.participant_id} · {row.occasion_key}
              </h3>
              <p>
                {row.denominator
                  ? copy("Incluido en denominador", "Included in denominator")
                  : copy(
                      "Fuera del denominador declarado",
                      "Outside declared denominator",
                    )}{" "}
                ·{" "}
                {row.eligible
                  ? copy(
                      "Criterios requeridos satisfechos",
                      "Required criteria satisfied",
                    )
                  : copy("Excluido o pendiente", "Excluded or unresolved")}
              </p>
              {preview.plan.eligibility_policy.repeat_selection ===
                "explicit" && (
                <label>
                  {copy("Intento exacto", "Exact attempt")}
                  <select
                    className="native-select block"
                    value={attempts[row.occasion_id] ?? row.attempt_id ?? ""}
                    onChange={(e) => {
                      setAttempts({
                        ...attempts,
                        [row.occasion_id]: e.target.value,
                      });
                      setResult(null);
                    }}
                  >
                    <option value="">—</option>
                    {row.attempts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.ordinal} · {a.acquisition_state} · {a.id}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {row.instrument === "screen" && (
                <label className="block">
                  {copy(
                    "Intento HCF explícito para participante",
                    "Explicit participant HCF attempt",
                  )}
                  <select
                    className="native-select block"
                    value={hcfAttempts[row.participant_id] ?? ""}
                    onChange={(e) =>
                      setHcfAttempts({
                        ...hcfAttempts,
                        [row.participant_id]: e.target.value,
                      })
                    }
                  >
                    <option value="">—</option>
                    {row.attempts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.id}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {row.instrument === "openmatb" && row.attempt_id && (
                <>
                  <label>
                    {copy(
                      "IDs exactos de métricas nativas (separados por coma)",
                      "Exact native metric IDs (comma separated)",
                    )}
                    <input
                      className="native-input block w-full"
                      value={nativeIds[row.attempt_id] ?? ""}
                      onChange={(e) =>
                        setNativeIds({
                          ...nativeIds,
                          [row.attempt_id!]: e.target.value,
                        })
                      }
                    />
                  </label>
                  {["physical_timing", "human_calibration"].map((kind) => (
                    <label className="block" key={kind}>
                      {kind}
                      <input
                        aria-label={kind}
                        className="native-input block"
                        value={qualification[row.attempt_id!]?.[kind] ?? ""}
                        onChange={(e) =>
                          setQualification({
                            ...qualification,
                            [row.attempt_id!]: {
                              ...qualification[row.attempt_id!],
                              [kind]: e.target.value,
                            },
                          })
                        }
                      />
                    </label>
                  ))}
                </>
              )}
              <p>
                {copy("Resultados incluidos", "Included outcomes")}:{" "}
                {Object.keys(row.values ?? {}).join(", ") ||
                  copy("Ninguno", "None")}
              </p>
              {row.source_error && <p>{row.source_error}</p>}
              {Object.entries(row.criteria).map(([key, c]) => (
                <details key={key}>
                  <summary>
                    {key} · {c.passed ? "✓" : "—"} ·{" "}
                    {c.required
                      ? copy("requerido", "required")
                      : copy("informado", "reported")}
                  </summary>
                  <p>{c.reason}</p>
                  <a
                    href={`${api}/assessments/attempts/${row.attempt_id ?? ""}/raw`}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {copy("Evidencia original", "Original evidence")}
                  </a>
                  <pre className="overflow-auto whitespace-pre-wrap text-xs">
                    {JSON.stringify(c.evidence, null, 2)}
                  </pre>
                </details>
              ))}
            </article>
          ))}
          <details>
            <summary>
              {copy(
                "Comparación de configuraciones",
                "Configuration comparison",
              )}
            </summary>
            <pre className="overflow-auto whitespace-pre-wrap text-xs">
              {JSON.stringify(preview.comparisons, null, 2)}
            </pre>
          </details>
          <Button
            disabled={busy || !version || !actor.trim() || !reason.trim()}
            onClick={() => void run("execute")}
          >
            {copy(
              "Ejecutar y congelar descripción",
              "Execute and freeze description",
            )}
          </Button>
        </section>
      )}
      <section className="space-y-2">
        <h2>{copy("Reabrir por ID", "Reopen by ID")}</h2>
        <input
          aria-label={copy("ID de ejecución", "Execution ID")}
          className="native-input"
          list="analysis-executions"
          value={reopen}
          onChange={(e) => setReopen(e.target.value)}
        />
        <datalist id="analysis-executions">
          {executions.map((e) => (
            <option key={e.id} value={e.id} />
          ))}
        </datalist>
        <Button disabled={busy || !reopen} onClick={() => void run("open")}>
          {copy("Reabrir", "Reopen")}
        </Button>
        <input
          aria-label={copy("ID para comparar", "Comparison execution ID")}
          className="native-input"
          list="analysis-executions"
          value={compareId}
          onChange={(e) => setCompareId(e.target.value)}
        />
        <Button
          disabled={busy || !compareId}
          onClick={() => void run("compare")}
        >
          {copy("Comparar", "Compare")}
        </Button>
      </section>
      {[result, comparison]
        .filter((r): r is Result => r !== null)
        .map((r) => (
          <section key={r.id} className="rounded border p-3">
            <h2>{r.id}</h2>
            <p>
              {r.current_applicability.changed
                ? copy(
                    "La aplicabilidad actual cambió; el resultado congelado se conserva.",
                    "Current applicability changed; the frozen result is preserved.",
                  )
                : copy(
                    "Sin cambios de aplicabilidad detectados.",
                    "No applicability changes detected.",
                  )}
            </p>
            <p className="break-all">
              {r.data_sha256} · {r.plan_sha256}
            </p>
            <a href={`${api}/study/analyses/${r.id}/export`}>
              {copy(
                "Exportar datos, código y reproducción sin conexión",
                "Export data, code and offline replay",
              )}
            </a>
            <pre className="overflow-auto whitespace-pre-wrap text-xs">
              {JSON.stringify(r.result, null, 2)}
            </pre>
          </section>
        ))}
      <section>
        <h2>{copy("Comparar derivaciones HCF", "Compare HCF derivations")}</h2>
        {[
          [selectedHcf, setSelectedHcf],
          [otherHcf, setOtherHcf],
        ].map(([value, setter], i) => (
          <select
            aria-label={`HCF ${i + 1}`}
            className="native-select"
            key={i}
            value={value as string}
            onChange={(e) =>
              (setter as (value: string) => void)(e.target.value)
            }
          >
            <option value="">—</option>
            {hcf.map((h) => (
              <option key={h.id} value={h.id}>
                {h.id}
              </option>
            ))}
          </select>
        ))}
        {hcf
          .filter((h) => h.id === selectedHcf || h.id === otherHcf)
          .map((h) => (
            <pre
              className="overflow-auto whitespace-pre-wrap text-xs"
              key={h.id}
            >
              {JSON.stringify(h, null, 2)}
            </pre>
          ))}
      </section>
    </div>
  );
}
