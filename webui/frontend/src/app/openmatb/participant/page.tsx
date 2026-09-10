"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Check, Monitor } from "lucide-react";

import { ExecutionPurposeBadge } from "@/components/experiments/ExperimentGuide";
import { WorkloadQuestionnaire } from "@/components/openmatb/WorkloadQuestionnaire";
import { Button } from "@/components/ui/button";
import { useReportExperimentFlow } from "@/lib/experiment-flow";
import { withExecutionPurpose } from "@/lib/execution-purpose";
import { useAppLocale } from "@/lib/i18n";
import {
  acknowledgeOpenMatbInstructions,
  getOpenMatbSession,
  readOpenMatbParticipant,
  submitOpenMatbScales,
} from "@/lib/openmatb/api";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import { openMatbStage } from "@/lib/openmatb/progress";
import { useSerializedPolling } from "@/lib/serialized-polling";
import type { OpenMatbSession, WorkloadScaleSubmission } from "@/types/openmatb";

function ParticipantContent() {
  const params = useSearchParams();
  const { copy, setLocale } = useAppLocale();
  const id = params.get("session");
  const [token, setToken] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [draftClearFailureSessionId, setDraftClearFailureSessionId] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    try {
      const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
      const supplied = fragment.get("token") ?? readOpenMatbParticipant(id);
      if (supplied) {
        window.sessionStorage.setItem(`openmatb.participant.${id}`, supplied);
        setToken(supplied);
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
      }
    } catch {
      setActionError(copy(
        "Esta pestaña no pudo conservar la credencial del participante. Pida al investigador que vuelva a abrir esta pantalla.",
        "This tab could not retain the participant credential. Ask the researcher to reopen this display.",
      ));
    }
  }, [copy, id]);

  const pollSession = useCallback(() => {
    if (!id) return Promise.reject(new Error(copy("Falta el identificador de la sesión.", "Session identifier is missing.")));
    return getOpenMatbSession(id);
  }, [copy, id]);

  const { value: polledSession, pollingError, acceptActionValue } = useSerializedPolling({
    enabled: Boolean(id),
    poll: pollSession,
    intervalMs: 1_000,
    resetKey: id,
    errorMessage: (reason) => openMatbErrorMessage(reason, copy, ["No se pudo consultar la sesión.", "Session could not be loaded."]),
  });
  const session = polledSession?.id === id ? polledSession : null;

  useReportExperimentFlow("openmatb", openMatbStage(session?.lifecycle), session?.execution_purpose);

  useEffect(() => {
    if (session?.locale) setLocale(session.locale);
  }, [session?.locale, setLocale]);

  async function acknowledge() {
    if (!id || !token) return;
    setBusy(true);
    setActionError(null);
    try {
      acceptActionValue(await acknowledgeOpenMatbInstructions(id, token));
    } catch (reason: unknown) {
      setActionError(openMatbErrorMessage(reason, copy, ["No se pudo confirmar.", "Acknowledgement failed."]));
    } finally {
      setBusy(false);
    }
  }

  function submit(submission: WorkloadScaleSubmission): Promise<OpenMatbSession> {
    if (!id || !token) return Promise.reject(new Error(copy("Falta la credencial del participante.", "Participant credential is missing.")));
    return submitOpenMatbScales(id, token, submission);
  }

  function acceptWorkload(nextSession: OpenMatbSession, outcome: { draftClearFailed: boolean }) {
    setDraftClearFailureSessionId(outcome.draftClearFailed ? nextSession.id : null);
    acceptActionValue(nextSession);
  }

  if (!session) {
    return <main className="grid min-h-screen place-items-center bg-background p-8 text-muted-foreground">
      {pollingError ?? copy("Cargando…", "Loading…")}
    </main>;
  }

  const title = session.lifecycle === "INSTRUCTIONS"
    ? session.instruction_protocol.title
    : session.lifecycle === "AWAITING_SCALE"
      ? copy("Carga de trabajo percibida", "Perceived workload")
      : copy("Sesión MATB - FAC", "MATB - FAC session");

  return <main className="min-h-screen bg-background p-5 sm:p-8">
    <div className="mx-auto max-w-5xl space-y-6">
      <header className="space-y-4 border-b border-white/15 pb-5">
        <div className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">MATB - FAC · {session.visit_code} · {session.participant_id}</div>
        <ExecutionPurposeBadge purpose={session.execution_purpose} />
        <h1 className="font-display text-3xl font-semibold uppercase tracking-wide">{title}</h1>
      </header>

      {pollingError && <p role="alert" className="border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{pollingError}</p>}
      {actionError && <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{actionError}</p>}
      {draftClearFailureSessionId === session.id && <p role="alert" className="border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{copy("Las respuestas se guardaron, pero no se pudo eliminar el borrador de esta pestaña.", "Ratings were saved, but the draft could not be removed from this tab.")}</p>}

      {session.lifecycle === "INSTRUCTIONS" && <section className="space-y-6">
        <div className="border border-info/40 bg-info/5 p-4">
          <div className="font-mono text-xs uppercase text-info">{session.visit_code} · {copy("Día", "Day")} {session.scheduled_day}</div>
          <p className="mt-2 text-lg leading-7">{session.visit_instruction}</p>
        </div>
        <ol className="space-y-3">
          {session.instruction_protocol.steps.map((step, index) => <li key={`${index}-${step}`} className="flex gap-4 border-b border-white/10 pb-3">
            <span className="font-mono text-sm text-info">{String(index + 1).padStart(2, "0")}</span>
            <span className="text-lg leading-7">{step}</span>
          </li>)}
        </ol>
        <div className="grid gap-3 sm:grid-cols-2">
          {Object.entries(session.instruction_protocol.task_instructions).map(([task, text]) => <div key={task} className="mission-panel p-4">
            <h2 className="font-display text-xl font-semibold">{task}</h2>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p>
          </div>)}
        </div>
        <Button className="h-auto min-h-11 max-w-full whitespace-normal px-5 py-3 text-sm normal-case tracking-normal" size="lg" disabled={!token || busy} onClick={() => void acknowledge()}>
          <Check className="mr-2 h-4 w-4" />
          {busy ? copy("Confirmando…", "Acknowledging…") : copy("He leído y comprendido las instrucciones", "I have read and understood the instructions")}
        </Button>
      </section>}

      {(session.lifecycle === "READY" || session.lifecycle === "BETWEEN_BLOCKS") && <section className="grid min-h-[45vh] place-items-center text-center">
        <div>
          <Monitor className="mx-auto h-12 w-12 text-info" />
          <h2 className="mt-5 font-display text-3xl uppercase">{copy("Listo para continuar", "Ready to continue")}</h2>
          <p className="mt-3 text-muted-foreground">{copy("Espere la indicación del investigador. El siguiente bloque se abrirá en esta pantalla.", "Wait for the researcher. The next block will open on this display.")}</p>
        </div>
      </section>}

      {session.lifecycle === "STARTING" && <section className="grid min-h-[45vh] place-items-center text-center">
        <div>
          <Monitor className="mx-auto h-12 w-12 text-info" />
          <h2 className="mt-5 font-display text-3xl uppercase">{copy("Abriendo la ventana de la tarea nativa", "Opening the native task window")}</h2>
          <p className="mt-3 text-muted-foreground">{copy("Espere mientras aparece la ventana de la tarea en la pantalla seleccionada.", "Wait while the task window appears on the selected display.")}</p>
        </div>
      </section>}

      {session.lifecycle === "RUNNING" && <section className="grid min-h-[45vh] place-items-center text-center">
        <div>
          <Monitor className="mx-auto h-12 w-12 text-success" />
          <h2 className="mt-5 font-display text-3xl uppercase">{copy("OpenMATB en ejecución", "OpenMATB running")}</h2>
          <p className="mt-3 text-muted-foreground">{copy("Utilice los controles de la tarea. Esta pantalla volverá al terminar el bloque.", "Use the task controls. This display will return when the block ends.")}</p>
        </div>
      </section>}

      {session.lifecycle === "PAUSED" && <section className="grid min-h-[45vh] place-items-center text-center">
        <div>
          <Monitor className="mx-auto h-12 w-12 text-warning" />
          <h2 className="mt-5 font-display text-3xl uppercase">{copy("OpenMATB en pausa", "OpenMATB paused")}</h2>
          <p className="mt-3 text-muted-foreground">{copy("La tarea está en pausa. Espere al investigador antes de continuar.", "The task is paused. Wait for the researcher before continuing.")}</p>
        </div>
      </section>}

      {session.lifecycle === "AWAITING_SCALE" && session.active_block === "PRACTICE" && <section className="grid min-h-[35vh] place-items-center text-center">
        <p className="text-muted-foreground">{copy("Los bloques de práctica no recopilan calificaciones de carga de trabajo. Espere mientras avanza la sesión.", "Practice blocks do not collect workload ratings. Wait while the session advances.")}</p>
      </section>}

      {session.lifecycle === "AWAITING_SCALE" && session.active_block && session.active_block !== "PRACTICE" && <WorkloadQuestionnaire
        sessionId={session.id}
        blockInstanceId={session.active_block_instance_id}
        profile={session.active_block}
        tokenAvailable={Boolean(token)}
        onSubmit={submit}
        onAccepted={acceptWorkload}
      />}

      {session.lifecycle === "AWAITING_SCALE" && !session.active_block && <p role="alert" className="border border-warning/40 bg-warning/10 p-4 text-sm text-warning">
        {copy("No se puede identificar el bloque activo. Actualice esta página y avise al investigador si el mensaje continúa.", "The active block cannot be identified. Refresh this page and tell the researcher if the message remains.")}
      </p>}

      {session.lifecycle === "COMPLETE" && <section className="grid min-h-[45vh] place-items-center text-center">
        <div>
          <Check className="mx-auto h-14 w-14 text-success" />
          <h2 className="mt-5 font-display text-4xl uppercase">{session.execution_purpose === "practice" ? copy("Práctica completada", "Practice completed") : copy("Sesión completada", "Session completed")}</h2>
          <p className="mt-3 text-muted-foreground">{copy("Los datos de la sesión quedaron guardados.", "Session data has been saved.")}</p>
          <Link href={withExecutionPurpose("/start", session.execution_purpose)} className="mt-4 inline-block underline">{copy("Volver a los experimentos", "Back to experiments")}</Link>
        </div>
      </section>}

      {(session.lifecycle === "ABORTED" || session.lifecycle === "FAILED" || session.lifecycle === "INTERRUPTED") && <section className="grid min-h-[45vh] place-items-center text-center">
        <div>
          <h2 className="font-display text-3xl uppercase text-warning">{copy("Sesión detenida", "Session stopped")}</h2>
          <p className="mt-3 text-muted-foreground">{copy("Avise al investigador y conserve esta ventana para revisar el estado.", "Tell the researcher and keep this window open to review the status.")}</p>
        </div>
      </section>}
    </div>
  </main>;
}

export default function OpenMatbParticipantPage() {
  return <Suspense><ParticipantContent /></Suspense>;
}
