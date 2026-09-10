"use client";
import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { studyCall } from "@/lib/study";
import { getApiBase } from "@/lib/runtime-config";
import type { Occasion } from "@/lib/assessments";

export function StudyHistory() {
  const participant = useSearchParams().get("participant");
  return (
    <ParticipantHistory key={participant ?? ""} participant={participant} />
  );
}

function ParticipantHistory({ participant }: { participant: string | null }) {
  const { copy } = useAppLocale();
  const [exposure, setExposure] = useState<Record<string, unknown>[]>([]);
  const [occasions, setOccasions] = useState<Occasion[]>([]);
  const [selected, setSelected] = useState("");
  const [history, setHistory] = useState<{
    identity: string;
    value: unknown;
  } | null>(null);
  const [error, setError] = useState("");
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [visit, setVisit] = useState("");
  const [phase, setPhase] = useState("");
  const [order, setOrder] = useState("");
  async function call(path: string, body?: unknown) {
    const response = await fetch(`${await getApiBase()}${path}`, {
      method: body ? "POST" : "GET",
      headers: { "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    const value = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(value.detail));
    return value;
  }
  useEffect(() => {
    let active = true;
    setSelected("");
    setExposure([]);
    setOccasions([]);
    setHistory(null);
    if (participant)
      void Promise.all([
        studyCall<Record<string, unknown>[]>(
          `/participants/${encodeURIComponent(participant)}/exposure`,
        ),
        call(
          `/assessments/occasions?participant_id=${encodeURIComponent(participant)}`,
        ),
      ])
        .then(([e, o]) => {
          if (active) {
            setExposure(e);
            setOccasions(o);
          }
        })
        .catch((e) => {
          if (active) setError(String(e));
        });
    return () => {
      active = false;
    };
  }, [participant]);
  useEffect(() => {
    let active = true;
    setHistory(null);
    if (selected)
      void call(`/assessments/occasions/${selected}/classifications`)
        .then((v) => {
          if (active) setHistory({ identity: selected, value: v });
        })
        .catch((e) => {
          if (active) setError(String(e));
        });
    return () => {
      active = false;
    };
  }, [selected]);
  return (
    <section className="space-y-5">
      <h1>
        {copy(
          "Exposición y clasificación histórica",
          "Exposure and historical classification",
        )}{" "}
        · {participant}
      </h1>
      <p>
        {copy(
          "Los tiempos y configuraciones históricos desconocidos permanecen desconocidos. Una clasificación no otorga permiso de inclusión en el análisis.",
          "Unknown historical times and configurations remain unknown. Classification does not grant analysis inclusion permission.",
        )}
      </p>
      <div className="overflow-auto">
        <table>
          <thead>
            <tr>
              {[
                "Instrument",
                "Attempt",
                "Purpose",
                "Duration (s)",
                "Outcome",
                "Competence",
              ].map((t) => (
                <th key={t} className="p-2">
                  {copy(
                    (
                      {
                        Instrument: "Instrumento",
                        Attempt: "Intento",
                        Purpose: "Finalidad",
                        "Duration (s)": "Duración (s)",
                        Outcome: "Resultado",
                        Competence: "Competencia",
                      } as Record<string, string>
                    )[t],
                    t,
                  )}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {exposure.map((e) => (
              <tr key={String(e.attempt_id)}>
                {[
                  "instrument",
                  "attempt_id",
                  "purpose",
                  "duration_seconds",
                  "outcome",
                  "competence",
                ].map((k) => (
                  <td key={k} className="p-2">
                    {e[k] === null || e[k] === undefined
                      ? copy("Desconocido", "Unknown")
                      : String(e[k])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <label>
        {copy("Ocasión histórica", "Historical occasion")}
        <select
          className="native-select block"
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
        >
          <option value="">—</option>
          {occasions
            .filter((o) => ["legacy", "legacy_compat"].includes(o.origin))
            .map((o) => (
              <option key={o.id} value={o.id}>
                {o.instrument} · {o.id}
              </option>
            ))}
        </select>
      </label>
      {selected && (
        <>
          <div className="grid gap-3 sm:grid-cols-2">
            {[
              [copy("Investigador", "Reviewer"), reviewer, setReviewer],
              [
                copy("Motivo y referencias", "Reason and references"),
                reason,
                setReason,
              ],
              [copy("Identidad de visita", "Visit ID"), visit, setVisit],
              [copy("Fase", "Phase"), phase, setPhase],
              [copy("Orden", "Order"), order, setOrder],
            ].map(([label, value, setter]) => (
              <label key={String(label)}>
                {String(label)}
                <input
                  className="native-input block"
                  value={String(value)}
                  onChange={(e) =>
                    (setter as (value: string) => void)(e.target.value)
                  }
                />
              </label>
            ))}
          </div>
          <Button
            disabled={!reviewer || !reason || !visit || !phase || !order}
            onClick={() =>
              void call(`/assessments/occasions/${selected}/classifications`, {
                reviewer,
                reason,
                visit_id: Number(visit),
                phase,
                order: Number(order),
                supporting_references: [],
              })
                .then((value) => setHistory({ identity: selected, value }))
                .catch((e) => setError(String(e)))
            }
          >
            {copy("Registrar clasificación", "Record classification")}
          </Button>
          <details open>
            <summary>
              {copy("Historial inmutable", "Immutable history")}
            </summary>
            <pre className="overflow-auto text-xs">
              {JSON.stringify(
                history?.identity === selected ? history.value : null,
                null,
                2,
              )}
            </pre>
          </details>
        </>
      )}
      {error && <p role="alert">{error}</p>}
      <PurposeReview
        key={participant ?? ""}
        participant={participant}
        exposure={exposure}
      />
      <Link className="block underline" href="/study/assignments">
        {copy("Asignaciones", "Assignments")}
      </Link>
    </section>
  );
}

function PurposeReview({
  exposure,
  participant,
}: {
  exposure: Record<string, unknown>[];
  participant: string | null;
}) {
  const { copy } = useAppLocale();
  const [identity, setIdentity] = useState("");
  const [record, setRecord] = useState<{
    identity: string;
    value: unknown;
  } | null>(null);
  const [purpose, setPurpose] = useState("practice");
  const [reviewer, setReviewer] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const eligible = exposure.filter(
    (item) =>
      item.participant_id === participant &&
      item.purpose_provenance_id &&
      item.purpose_origin !== "explicit",
  );
  const membership = eligible
    .map((item) => String(item.purpose_provenance_id))
    .toSorted()
    .join("|");
  const scope = useRef({ active: true, identity, ids: new Set<string>() });
  scope.current.identity = identity;
  scope.current.ids = new Set(
    eligible.map((item) => String(item.purpose_provenance_id)),
  );
  useEffect(() => {
    scope.current.active = true;
    return () => {
      scope.current.active = false;
    };
  }, []);
  const selected = scope.current.ids.has(identity);
  async function request(id: string, body?: unknown) {
    const base = await getApiBase();
    if (
      !scope.current.active ||
      scope.current.identity !== id ||
      !scope.current.ids.has(id)
    )
      throw new Error(
        "Purpose selection no longer belongs to this participant.",
      );
    const response = await fetch(
      `${base}/purpose-provenance/${encodeURIComponent(id)}${body ? "/classifications" : ""}`,
      {
        method: body ? "POST" : "GET",
        headers: { "Content-Type": "application/json" },
        ...(body ? { body: JSON.stringify(body) } : {}),
      },
    );
    const value = await response.json();
    if (!response.ok) throw new Error(JSON.stringify(value.detail));
    return value;
  }
  useEffect(() => {
    let active = true;
    setRecord(null);
    if (selected)
      void request(identity)
        .then((value) => {
          if (active) setRecord({ identity, value });
        })
        .catch((e) => {
          if (active) setError(String(e));
        });
    return () => {
      active = false;
    };
  }, [identity, membership, selected]);
  return (
    <section className="space-y-3 rounded border p-4">
      <h2>
        {copy("Revisión de finalidad histórica", "Historical purpose review")}
      </h2>
      <label>
        {copy("Registro de finalidad", "Purpose record")}
        <select
          className="native-select block"
          value={selected ? identity : ""}
          onChange={(e) => setIdentity(e.target.value)}
        >
          <option value="">—</option>
          {eligible.map((e) => (
            <option
              key={String(e.attempt_id)}
              value={String(e.purpose_provenance_id)}
            >
              {String(e.instrument)} · {String(e.attempt_id)} ·{" "}
              {String(e.purpose_origin)}
            </option>
          ))}
        </select>
      </label>
      {selected && (
        <>
          <label>
            {copy("Finalidad revisada", "Reviewed purpose")}
            <select
              className="native-select block"
              value={purpose}
              onChange={(e) => setPurpose(e.target.value)}
            >
              <option value="practice">{copy("Práctica", "Practice")}</option>
              <option value="study">{copy("Estudio", "Study")}</option>
              <option value="exploration">
                {copy("Exploración", "Exploration")}
              </option>
            </select>
          </label>
          <label>
            {copy("Revisor de finalidad", "Purpose reviewer")}
            <input
              className="native-input block"
              value={reviewer}
              onChange={(e) => setReviewer(e.target.value)}
            />
          </label>
          <label>
            {copy(
              "Motivo y referencias de finalidad",
              "Purpose reason and references",
            )}
            <textarea
              className="native-input block"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <Button
            disabled={!selected || !reviewer || !reason}
            onClick={() =>
              void request(identity, {
                purpose,
                reviewer,
                reason,
                supporting_references: [],
              })
                .then((value) => {
                  if (
                    scope.current.active &&
                    scope.current.identity === identity &&
                    scope.current.ids.has(identity)
                  )
                    setRecord({ identity, value });
                })
                .catch((e) => {
                  if (
                    scope.current.active &&
                    scope.current.identity === identity &&
                    scope.current.ids.has(identity)
                  )
                    setError(String(e));
                })
            }
          >
            {copy("Registrar revisión de finalidad", "Record purpose review")}
          </Button>
          <pre className="overflow-auto whitespace-pre-wrap text-xs">
            {JSON.stringify(
              record?.identity === identity ? record.value : null,
              null,
              2,
            )}
          </pre>
        </>
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
