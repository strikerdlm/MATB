"use client";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { evidenceStateLabel } from "@/lib/evidence-state";
import type { OpenMatbReceipt } from "@/types/openmatb";

const STATES: Record<string, [string, string]> = {
  starting: ["Abriendo tarea", "Opening task"], running: ["En ejecución", "Running"], completed: ["Completada", "Completed"],
  failed: ["Error", "Failed"], aborted: ["Abortada", "Aborted"], interrupted: ["Interrumpida", "Interrupted"],
  saved: ["Guardado", "Saved"], missing: ["Faltante", "Missing"], partial: ["Incompleto", "Incomplete"], invalid: ["No válido", "Invalid"],
  unknown: ["Sin confirmar", "Unconfirmed"], pending: ["Pendiente", "Pending"], not_required: ["No se requiere", "Not required"],
  awaiting_completion: ["Esperando el cierre del bloque", "Waiting for block completion"], queued: ["En cola", "Queued"],
  processing: ["Procesando", "Processing"], processed: ["Procesado", "Processed"], unavailable: ["No disponible", "Unavailable"],
};

export function SessionReceipt({ receipt, onRetry, retrying }: {
  receipt: OpenMatbReceipt; onRetry?: (blockId: string) => void; retrying?: string | null;
}) {
  const { copy } = useAppLocale();
  const state = (value: string) => STATES[value] ? copy(...STATES[value]) : copy("Sin confirmar", "Unconfirmed");
  return <section className="space-y-4" aria-label={copy("Comprobante de la sesión", "Session receipt")}>
    <h2 className="text-xl font-semibold">{copy("Qué se guardó", "What was saved")} · {receipt.participant_id} · V{receipt.visit_ordinal}</h2>
    {receipt.historical && <p className="text-sm text-warning">{copy("Los estados detallados de guardado no se registraron para esta sesión anterior. Revise los archivos disponibles.", "Detailed save states were not recorded for this older session. Review the available files.")}</p>}
    {!receipt.attempts.length && !receipt.historical && <p>{copy("No se registró ningún inicio de bloque.", "No block launch was recorded.")}</p>}
    {receipt.attempts.length > 0 && <p className="text-sm text-muted-foreground">{receipt.attempts.filter(attempt => attempt.task_status === "completed").length} {copy("intentos de bloque completados. Guardar archivos no cualifica las mediciones.", "completed block attempts. Saved files do not establish measurement qualification.")}</p>}
    <div className="grid gap-4 xl:grid-cols-2">{receipt.attempts.map(attempt => <article key={attempt.block_instance_id} className="min-w-0 rounded border p-4">
      <h3 className="font-semibold">{attempt.profile}</h3>
      <dl className="mt-3 space-y-2 text-sm">{[
        [copy("Tarea", "Task"), state(attempt.task_status)], [copy("Archivos nativos", "Native files"), state(attempt.artifact_status)],
        [copy("Escalas", "Ratings"), state(attempt.ratings_status)], [copy("Importación al estudio", "Study import"), state(attempt.legacy_import_status)],
        [copy("Procesamiento de evidencia", "Evidence processing"), state(attempt.evidence_status)],
        ...(attempt.capture_status ? [[copy("Resultados de origen", "Source results"), evidenceStateLabel(attempt.capture_status, copy)]] : []),
        [copy("Tiempo físico", "Physical timing"), evidenceStateLabel(attempt.qualification?.physical_timing ?? "not_assessed", copy)],
        [copy("Calibración humana", "Human calibration"), evidenceStateLabel(attempt.qualification?.human_calibration ?? "not_assessed", copy)],
        [copy("Elegibilidad del protocolo", "Protocol eligibility"), evidenceStateLabel(attempt.qualification?.protocol_eligibility.status ?? "not_assessed", copy)],
      ].map(([label, value]) => <div key={label} className="flex flex-wrap justify-between gap-x-4 gap-y-1 border-b border-border/50 pb-1"><dt className="text-muted-foreground">{label}</dt><dd className="font-medium">{value}</dd></div>)}</dl>
      {attempt.evidence_status === "queued" && <p className="mt-3 text-sm">{copy("Se procesará al terminar la sesión, cuando no haya una tarea nativa activa.", "Processing will run after the session ends, when no native task is active.")}</p>}
      {attempt.evidence_status === "unavailable" && <p className="mt-3 text-sm text-warning">{copy("Faltan archivos nativos completos. Revise los archivos de esta sesión antes de reintentar.", "Complete native files are unavailable. Review this session’s files before retrying.")}</p>}
      <div className="mt-3 flex flex-wrap gap-3">
        {attempt.capture_id && <Link className="text-sm text-info underline" href={`/evidence?session=${encodeURIComponent(receipt.session_id)}&purpose=all&capture=${encodeURIComponent(attempt.capture_id)}`}>{copy("Revisar resultados y evidencia", "Review results and evidence")}</Link>}
        {onRetry && ["failed", "unavailable"].includes(attempt.evidence_status) && <Button variant="outline" className="text-sm normal-case tracking-normal" disabled={Boolean(retrying)} onClick={() => onRetry(attempt.block_instance_id)}>{retrying === attempt.block_instance_id ? copy("Reintentando…", "Retrying…") : copy("Reintentar procesamiento", "Retry processing")}</Button>}
      </div>
      <details className="mt-3 text-sm text-muted-foreground"><summary className="cursor-pointer">{copy("Identificadores y diagnósticos", "Identifiers and diagnostics")}</summary><dl className="mt-2 space-y-2 break-all font-mono text-xs"><div><dt>{copy("Intento", "Attempt")}</dt><dd>{attempt.block_instance_id}</dd></div>{[attempt.artifact_error, attempt.legacy_import_error, attempt.evidence_error].filter(Boolean).map((error, index) => <div key={index}><dt>{copy("Detalle", "Detail")}</dt><dd>{error}</dd></div>)}</dl></details>
    </article>)}</div>
  </section>;
}
