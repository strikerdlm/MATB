"use client";
import { useEffect, useState } from "react";
import { evidenceRequest, type EvidenceRecord } from "@/lib/evidence";
import { useAppLocale } from "@/lib/i18n";

interface Context {
  task: string | null;
  events: { record: EvidenceRecord; raw_json: string; scenario_time_ns_text: string }[];
  task_fields: { kind: string; address: string; value: unknown; event_id: string; scenario_time_ns_text: string }[];
  timing: { record: EvidenceRecord; value_text: string }[];
  truncated: Record<string, boolean>;
}
export function EventReview({ captureId, eventId, rawJson }: { captureId: string; eventId: string; rawJson?: string }) {
  const { copy } = useAppLocale();
  const [context, setContext] = useState<Context | null>(null), [selected, setSelected] = useState(eventId), [error, setError] = useState("");
  useEffect(() => {
    const abort = new AbortController(); setContext(null); setError("");
    void evidenceRequest<Context>(`/evidence/captures/${captureId}/events/${selected}/context`, { signal: abort.signal })
      .then(result => { if (!abort.signal.aborted) setContext(result); })
      .catch(reason => { if (!abort.signal.aborted) setError(reason.message); });
    return () => abort.abort();
  }, [captureId, selected]);
  if (error) return <div><p role="alert">{error}</p>{rawJson && <details open><summary>{copy("Registro original seleccionado", "Selected original record")}</summary><pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{rawJson}</pre></details>}</div>;
  if (!context) return <p role="status">{copy("Cargando contexto…", "Loading context…")}</p>;
  const event = context.events.find(e => e.record.event_id === selected) ?? context.events[0];
  return <section className="space-y-4" aria-label={copy("Revisión de evento", "Event review")}>
    <div><h4 className="font-semibold">{copy("Secuencia de la oportunidad", "Opportunity sequence")}</h4>
      <p className="text-xs text-muted-foreground">{copy("Tiempo del escenario; contexto de tarea registrado. La exposición visual original no está disponible.", "Scenario time; recorded task context. Original visual exposure is unavailable.")}</p></div>
    <div className="flex gap-2 overflow-x-auto border-b border-white/20 pb-3" aria-label={copy("Línea temporal", "Timeline")}>
      {context.events.map((item, i) => <button key={`${item.record.event_id}-${i}`} type="button" aria-pressed={item.record.event_id === selected}
        className={`min-w-32 rounded border px-3 py-2 text-left text-xs ${item.record.event_id === selected ? "border-info bg-info/10" : "border-white/15"}`}
        onClick={() => setSelected(item.record.event_id)}><span className="block font-mono">{(Number(BigInt(item.scenario_time_ns_text) / BigInt(1000000))/1000).toFixed(3)} s</span>{item.record.event_type}</button>)}
    </div>
    {Object.values(context.truncated).some(Boolean) && <p className="text-sm text-warning">{copy("La ventana de contexto está limitada; consulte los archivos originales para la secuencia completa.", "This context window is bounded; consult the original artifacts for the complete sequence.")}</p>}
    <div className="grid gap-4 xl:grid-cols-2">
      <div className="min-w-0"><h4 className="text-sm font-semibold">{copy("Registro original del evento", "Original event record")}</h4>
        <pre className="mt-2 max-h-64 overflow-auto whitespace-pre-wrap break-all text-xs">{event?.raw_json}</pre>
        <details className="mt-3"><summary>{copy("Contexto previo de la tarea", "Preceding task context")}</summary>
          <p className="text-xs text-muted-foreground">{copy("Hasta 32 registros anteriores al evento seleccionado.", "Up to 32 records preceding the selected event.")}</p>
          {context.task_fields.map(field => <div key={`${field.kind}:${field.address}`} className="my-2 break-all text-xs"><strong>{field.address || field.kind}</strong>: {JSON.stringify(field.value)}<p className="text-muted-foreground">{field.event_id}</p></div>)}
        </details>
      </div>
      <div><h4 className="text-sm font-semibold">{copy("Observaciones temporales vinculadas", "Linked timing observations")}</h4>
        <p className="my-2 text-xs text-muted-foreground">{copy("Cada valor conserva su dominio de reloj. No se calcula latencia entre relojes ni se sincroniza fisiología sin cualificación.", "Each value retains its clock domain. Cross-clock latency and physiology alignment require qualification.")}</p>
        {context.timing.filter(t => t.record.event_id === event?.record.event_id).map(t => <div key={t.record.observation_id} className="break-all border-t border-white/10 py-2 text-xs"><p>{t.record.kind} · {t.record.evidence_source} · {t.record.clock_id}</p><p className="font-mono">{t.value_text} {t.record.unit}</p><p>{t.record.observation_id}</p></div>)}
        <p className="mt-3 text-xs text-muted-foreground">{copy("Inicio físico, mirada y fisiología sincronizada: no disponibles en esta captura.", "Physical onset, gaze and synchronized physiology: unavailable in this capture.")}</p>
      </div>
    </div>
  </section>;
}
