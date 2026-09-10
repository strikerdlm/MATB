"use client";
import { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Button } from "@/components/ui/button";
import {
  getSourceAttempt,
  listAttempts,
  repeatAttempt,
  type Attempt,
} from "@/lib/assessments";
import { useAppLocale } from "@/lib/i18n";
import {
  WorkloadQuestionnaire,
  type WorkloadQuestionnaireProps,
} from "./WorkloadQuestionnaire";

/** Select a questionnaire identity; the server checks its exact native target. */
export function AssignedWorkloadQuestionnaire(
  props: WorkloadQuestionnaireProps,
) {
  const { copy } = useAppLocale();
  const requested = useSearchParams().get("questionnaire");
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setSelected("");
    setAttempts([]);
    setError("");
    if (props.blockInstanceId)
      void getSourceAttempt(
        "openmatb_block_attempt",
        props.blockInstanceId,
        "ratings",
      )
        .then(async (original) =>
          (await listAttempts(original.occasion_id)).filter(
            (row) => row.target_attempt_id === original.target_attempt_id,
          ),
        )
        .then((rows) => {
          if (active) {
            setAttempts(rows);
            if (requested) {
              if (rows.some((row) => row.id === requested))
                setSelected(requested);
              else
                setError(
                  copy(
                    "El cuestionario solicitado no pertenece a esta tarea exacta.",
                    "The requested questionnaire does not belong to this exact task.",
                  ),
                );
            }
          }
        })
        .catch((e) => {
          if (active) setError(String(e));
        });
    return () => {
      active = false;
    };
  }, [props.blockInstanceId, requested, copy]);
  const attempt = attempts.find((row) => row.id === selected);
  const pending =
    attempt && ["created", "started"].includes(attempt.acquisition_state);
  return (
    <section className="space-y-4">
      <label>
        {copy(
          "Intento de cuestionario para esta tarea",
          "Questionnaire attempt for this task",
        )}
        <select
          className="native-select block w-full"
          value={selected}
          disabled={busy}
          onChange={(e) => {
            setSelected(e.target.value);
            setError("");
          }}
        >
          <option value="">
            {copy("Seleccione el intento exacto", "Select the exact attempt")}
          </option>
          {attempts.map((row) => (
            <option key={row.id} value={row.id}>
              {row.ordinal} · {row.id} · {row.acquisition_state}
            </option>
          ))}
        </select>
      </label>
      <p>
        {copy(
          "La tarea destinataria exacta se conserva como requisito previo cuando está prescrita. Los intentos interrumpidos y las respuestas anteriores no se sustituyen.",
          "The exact target task is retained as a prerequisite when prescribed. Interrupted attempts and earlier answers are never replaced.",
        )}
      </p>
      {attempt && !pending && (
        <div className="space-y-2">
          <label>
            {copy(
              "Motivo de repetición del cuestionario",
              "Questionnaire repeat reason",
            )}
            <input
              className="native-input block"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <Button
            disabled={busy || !reason.trim()}
            onClick={() =>
              void (async () => {
                setBusy(true);
                setError("");
                try {
                  const next = await repeatAttempt(
                    attempt.id,
                    "study",
                    reason,
                    attempt.target_attempt_id ?? undefined,
                  );
                  setAttempts(
                    await listAttempts(attempt.occasion_id).then((rows) =>
                      rows.filter(
                        (row) =>
                          row.target_attempt_id === attempt.target_attempt_id,
                      ),
                    ),
                  );
                  setSelected(next.id);
                  setReason("");
                } catch (e) {
                  setError(String(e));
                } finally {
                  setBusy(false);
                }
              })()
            }
          >
            {copy("Crear repetición explícita", "Create explicit repeat")}
          </Button>
        </div>
      )}
      {pending && (
        <WorkloadQuestionnaire
          key={attempt.id}
          {...props}
          questionnaireAttemptId={attempt.id}
          onAccepted={(session, outcome) => {
            setAttempts((rows) =>
              rows.map((row) =>
                row.id === attempt.id
                  ? { ...row, acquisition_state: "finished" }
                  : row,
              ),
            );
            props.onAccepted(session, outcome);
          }}
        />
      )}
      {error && <p role="alert">{error}</p>}
    </section>
  );
}
