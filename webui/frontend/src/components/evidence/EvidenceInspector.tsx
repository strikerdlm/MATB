"use client";
import { useEffect, useState } from "react";
import { EventReview } from "./EventReview";
import { SemanticReviewPanel } from "./SemanticReviewPanel";
import { metricDisplay, exclusionText } from "@/lib/evidence-display";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { downloadEvidence, evidenceRequest, type EvidenceCapture, type EvidencePage, type EvidenceRecord } from "@/lib/evidence";

function EventSources({ captureId, metricId }: { captureId: string; metricId: string }) {
  const { copy } = useAppLocale();
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<EvidencePage<EvidenceRecord> | null>(null);
  const [selected, setSelected] = useState<EvidenceRecord | null>(null);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ metric_id: metricId, offset: String(offset), limit: "25" });
    if (filter) params.set("event_id", filter);
    setPage(null); setSelected(null); setError("");
    void evidenceRequest<EvidencePage<EvidenceRecord>>(`/evidence/captures/${captureId}/records?${params}`, { signal: controller.signal })
      .then(result => setPage({ ...result, items: result.items.map((item, i) => ({ ...item, raw_json: result.raw_items?.[i] })) }))
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [captureId, metricId, offset, filter]);
  return <div className="space-y-4">
    <label className="block text-sm">{copy("Filtrar por ID de evento", "Filter by event ID")}
      <input className="native-select mt-1 w-full" value={filter} onChange={e => { setOffset(0); setFilter(e.target.value.trim()); }} />
    </label>
    {error && <p role="alert" className="text-danger">{error}</p>}
    {!page && !error && <p role="status">{copy("Cargando eventos…", "Loading events…")}</p>}
    {page && <>
      <p className="text-sm">{page.total} {copy("eventos de origen", "source events")}</p>
      <div className="max-h-72 overflow-auto"><table className="w-full text-left text-sm">
        <thead><tr><th>{copy("Orden", "Order")}</th><th>{copy("Tiempo del escenario (s)", "Scenario time (s)")}</th><th>{copy("Evento", "Event")}</th></tr></thead>
        <tbody>{page.items.map((event, index) => <tr key={`${event.event_id}-${index}`} className={`border-t border-white/10 ${selected?.event_id === event.event_id ? "bg-info/10" : ""}`}>
          <td>{event.sequence}</td><td>{((event.scenario_time_ns ?? 0) / 1e9).toFixed(6)}</td>
          <td><button type="button" className="py-2 text-info underline" aria-pressed={selected?.event_id === event.event_id} onClick={() => setSelected(event)}>{event.event_type} · {event.payload?.address || event.sequence}</button></td>
        </tr>)}</tbody>
      </table></div>
      <div className="flex gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>{copy("Anterior", "Previous")}</Button>
        <Button variant="outline" disabled={offset + 25 >= page.total} onClick={() => setOffset(offset + 25)}>{copy("Siguiente", "Next")}</Button></div>
    </>}
    {selected && <EventReview key={selected.event_id} captureId={captureId} eventId={selected.event_id} rawJson={selected.raw_json} />}

  </div>;
}

export function EvidenceInspector({ capture }: { capture: EvidenceCapture }) {
  const { copy } = useAppLocale();
  const es = copy("es", "en") === "es";
  const [panel, setPanel] = useState<"results" | "evidence">("results");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = capture.metrics.find(m => m.id === selectedId);
  const [error, setError] = useState("");
  const [selection, setSelection] = useState<string[]>([]);
  const [inputId, setInputId] = useState<string | null>(null);
  async function freezeInput() {
    setError("");
    try {
      const result = await evidenceRequest<{ id: string; rows: unknown[] }>("/evidence/analysis-inputs", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ metric_ids: selection }),
      });
      setInputId(result.id);
      const url = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
      const a = document.createElement("a"); a.href = url; a.download = `analysis-input-${result.id}.json`; a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }
  const status = capture.capture_status ?? (capture.runs[0]?.status === "failed" ? "processing_failed" : "reconciled");
  const statusLabel = status === "reconciled" ? copy("Conciliada", "Reconciled") : status === "partially_excluded" ? copy("Con exclusiones", "Partially excluded") : status === "pending" ? copy("Pendiente", "Pending") : copy("Procesamiento fallido", "Processing failed");
  const execution = capture.reconciliation?.analysis_execution;
  const eligible = capture.metrics.filter(m => m.confirmatory_eligible).length;
  return <section className="space-y-4" aria-label={copy("Inspector de evidencia", "Evidence inspector")}>
    <div className="control-surface space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-3"><div>
        <p className="page-kicker">{copy("Revisión de evidencia", "Evidence review")}</p>
        <h2 className="text-xl font-semibold">{capture.participant_id ?? "—"} · {capture.condition}</h2>
        <p className="text-sm">{statusLabel} · {eligible}/{capture.metrics.length} {copy("resultados elegibles según contrato", "contract eligible results")}</p>
      </div><Button variant="outline" onClick={() => { void downloadEvidence(capture.id).catch(e => setError(e.message)); }}>{copy("Exportar evidencia verificable", "Export verifiable evidence")}</Button></div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-white/10 pt-2 text-xs">
        <span>{copy("Tiempo físico", "Physical timing")}: {capture.qualification?.physical_timing === "linked_evidence" ? copy("ver informe vinculado", "see linked report") : copy("sin cualificar", "not qualified")}</span>
        <span>{copy("Calibración humana", "Human calibration")}: {capture.qualification?.human_calibration === "linked_evidence" ? copy("ver informe vinculado", "see linked report") : copy("sin cualificar", "not qualified")}</span>
        <span>{copy("Elegibilidad del protocolo: evaluación independiente pendiente", "Protocol eligibility: separate review pending")}</span>
      </div>
      <details><summary className="cursor-pointer text-sm">{copy("Procedencia de adquisición, análisis y cualificación", "Acquisition, analysis and qualification provenance")}</summary>
        <dl className="mt-3 grid gap-2 break-all text-xs md:grid-cols-2"><div><dt>{copy("Captura / instancia de bloque", "Capture / block instance")}</dt><dd>{capture.id}<br/>{capture.block_instance_id}</dd></div>
          <div><dt>Manifest SHA-256</dt><dd>{capture.manifest_sha256}</dd></div>
          <div><dt>{copy("Commit de adquisición", "Acquisition commit")}</dt><dd>{capture.manifest.source_commit}</dd></div>
          <div><dt>{copy("Commit de análisis", "Analysis commit")}</dt><dd>{execution?.source_commit ?? copy("No registrado", "Not recorded")}{execution?.source_dirty ? " (modified)" : ""}</dd></div>
          <div><dt>{copy("Implementación de análisis SHA-256", "Analysis implementation SHA-256")}</dt><dd>{execution?.implementation_sha256 ?? "—"}</dd></div>
          <div><dt>{copy("Dependencias fijadas SHA-256", "Dependency lock SHA-256")}</dt><dd>{execution?.dependency_lock_sha256 ?? "—"}</dd></div>
        </dl>
        {execution && <pre className="mt-2 overflow-auto whitespace-pre-wrap text-xs">{JSON.stringify({ configuration: execution.analysis_configuration, environment: execution.environment }, null, 2)}</pre>}
        {capture.runs.map(run => <p key={run.id} className="mt-2 text-xs">{run.version} · {run.status} {run.reason ?? ""}</p>)}
        {capture.qualification?.items.map(item => <div key={item.id} className="mt-3 break-all border-t border-white/10 pt-2 text-xs"><p>{item.record.kind} · {item.result} · {item.status}</p><p>{copy("Informe", "Report")}: {item.record.id}</p><p>{copy("Contexto", "Context")}: {item.record.context_sha256}</p><p>{copy("Revisor", "Reviewer")}: {item.record.reviewer}</p><details><summary>{copy("Contexto, evaluación y condiciones de invalidación", "Context, assessment and invalidation conditions")}</summary><pre className="max-h-64 overflow-auto whitespace-pre-wrap break-all">{JSON.stringify(item, null, 2)}</pre></details></div>)}
      </details>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {Boolean(capture.reconciliation?.issues.length) && <details><summary>{copy("Incidencias de conciliación", "Reconciliation findings")} ({capture.reconciliation?.issues.length})</summary>
        <ul className="mt-2 max-h-48 space-y-2 overflow-auto text-xs">{capture.reconciliation?.issues.map((issue, index) => <li key={index}>{exclusionText(issue.code, es)} <code>{issue.task ?? "capture"}: {issue.code}</code> {issue.detail}</li>)}</ul>
      </details>}
    </div>
    <div className="flex gap-2 lg:hidden" role="tablist" aria-label={copy("Panel de revisión", "Review panel")}>
      {(["results", "evidence"] as const).map(value => <button key={value} role="tab" aria-selected={panel === value} className="rounded border border-white/20 px-4 py-2" onClick={() => setPanel(value)}>{value === "results" ? copy("Resultados", "Results") : copy("Evidencia", "Evidence")}</button>)}
    </div>
    <div className="grid items-start gap-4 lg:grid-cols-[minmax(240px,0.7fr)_minmax(0,1.7fr)]">
      <div className={`control-surface min-w-0 ${panel === "results" ? "" : "hidden lg:block"}`}>
        <h3 className="mb-3 font-semibold">{copy("Resultados por tarea", "Results by task")}</h3>
        <div className="max-h-[650px] space-y-1 overflow-auto">
          {capture.metrics.map((metric, index) => { const display = metricDisplay(metric, es);
            const group = index === 0 || metricDisplay(capture.metrics[index-1], es).task !== display.task;
            return <div key={metric.id}>{group && <p className="mt-4 border-b border-white/10 pb-1 font-mono text-xs text-muted-foreground">{display.task}</p>}
              <div className={`flex items-start gap-2 rounded p-2 ${selectedId === metric.id ? "bg-info/10 ring-1 ring-info/40" : ""}`}>
                <input className="mt-1" type="checkbox" aria-label={`${copy("Incluir", "Include")} ${metric.metric}`} disabled={!metric.confirmatory_eligible} checked={selection.includes(metric.id)}
                  onChange={e => { setSelection(values => e.target.checked ? [...values, metric.id] : values.filter(v => v !== metric.id)); setInputId(null); }} />
                <button data-metric={metric.metric} type="button" aria-pressed={selectedId === metric.id} className="min-w-0 flex-1 text-left text-sm" onClick={() => { setSelectedId(metric.id); setPanel("evidence"); }}>
                  <span className="block">{display.name}</span><span className="font-mono text-lg">{display.value}</span> <span className="text-xs text-muted-foreground">{display.unit}</span>
                  <span className="block text-xs text-muted-foreground">{metric.confirmatory_eligible ? copy("Elegible según contrato", "Contract eligible") : metric.status === "not_applicable" ? copy("No administrada", "Not administered") : copy("Excluida del análisis confirmatorio", "Excluded from confirmatory analysis")}</span>
                </button>
              </div>
            </div>;
          })}
        </div>
        <Button variant="outline" className="mt-4 h-auto whitespace-normal" disabled={!selection.length} onClick={() => void freezeInput()}>{copy("Fijar y exportar selección para análisis", "Freeze and export analysis selection")}</Button>
        {inputId && <p className="mt-2 break-all text-xs" role="status">{copy("Selección guardada", "Saved selection")}: {inputId}</p>}
      </div>
      <div className={`control-surface min-w-0 space-y-4 ${panel === "evidence" ? "" : "hidden lg:block"}`}>
        {!selected ? <p className="py-12 text-sm text-muted-foreground">{copy("Seleccione un resultado para explorar qué ocurrió y qué evidencia lo respalda.", "Select a result to explore what occurred and which evidence supports it.")}</p> : <>
          <section className="space-y-3" aria-label={copy("Detalle de métrica", "Metric details")}>
            <h3 className="text-lg font-semibold">{metricDisplay(selected, es).name}</h3>
            <p className="break-all font-mono text-xs text-muted-foreground">{selected.metric} · v{selected.metric_version}</p>
            {selected.exclusion_reasons.length > 0 && <ul className="space-y-2 rounded border border-warning/30 p-3 text-sm">{selected.exclusion_reasons.map(reason => <li key={reason}>{exclusionText(reason, es)}<code className="block break-all text-xs text-muted-foreground">{reason}</code></li>)}</ul>}
            <details><summary className="cursor-pointer text-sm">{copy("Definición y valor exacto", "Definition and exact value")}</summary>
              <p className="mt-2 text-sm">{selected.definition.equation} ({selected.definition.unit})</p>
              <p className="font-mono text-xs">{selected.value === null ? "null" : String(selected.value)}</p>
              <p className="text-xs">{copy("Datos necesarios", "Required inputs")}: {selected.definition.required_inputs.join(", ")}</p><p className="text-xs">{selected.definition.missing_policy}</p>
              {selected.descriptive_value !== selected.value && <p className="text-xs">{copy("Valor descriptivo excluido", "Excluded descriptive value")}: {selected.descriptive_value ?? "—"}</p>}
            </details>
          </section>
          <EventSources key={`${capture.id}-${selected.id}`} captureId={capture.id} metricId={selected.id} />
        </>}
      </div>
    </div>
    <SemanticReviewPanel capture={capture} />
  </section>;
}
