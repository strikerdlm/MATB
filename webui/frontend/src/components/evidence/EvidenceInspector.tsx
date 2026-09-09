"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { downloadEvidence, evidenceRequest, type EvidenceCapture, type EvidencePage, type EvidenceRecord } from "@/lib/evidence";

function EventSources({ captureId, metricId }: { captureId: string; metricId: string }) {
  const { copy } = useAppLocale();
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<EvidencePage<EvidenceRecord> | null>(null);
  const [selected, setSelected] = useState<EvidenceRecord | null>(null);
  const [timing, setTiming] = useState<EvidenceRecord[]>([]);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ metric_id: metricId, offset: String(offset), limit: "25" });
    if (filter) params.set("event_id", filter);
    setPage(null); setSelected(null); setTiming([]); setError("");
    void evidenceRequest<EvidencePage<EvidenceRecord>>(`/evidence/captures/${captureId}/records?${params}`, { signal: controller.signal })
      .then(result => setPage({ ...result, items: result.items.map((item, i) => ({ ...item, raw_json: result.raw_items?.[i] })) }))
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [captureId, metricId, offset, filter]);
  useEffect(() => {
    if (!selected) return;
    const controller = new AbortController(); setTiming([]);
    void evidenceRequest<EvidencePage<EvidenceRecord>>(`/evidence/captures/${captureId}/records?stream=timing&event_id=${selected.event_id}`, { signal: controller.signal })
      .then(result => setTiming(result.items.map((item, i) => ({ ...item, value_text: result.value_texts?.[i] }))))
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [captureId, selected]);
  return <div className="space-y-4">
    <label className="block text-sm">{copy("Filtrar por ID de evento", "Filter by event ID")}
      <input className="native-select mt-1 w-full" value={filter} onChange={e => { setOffset(0); setFilter(e.target.value.trim()); }} />
    </label>
    {error && <p role="alert" className="text-danger">{error}</p>}
    {!page && !error && <p role="status">{copy("Cargando eventos…", "Loading events…")}</p>}
    {page && <>
      <p className="text-sm">{page.total} {copy("eventos de origen", "source events")}</p>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead><tr><th>{copy("Orden", "Order")}</th><th>{copy("Tiempo del escenario (s)", "Scenario time (s)")}</th><th>{copy("Evento", "Event")}</th></tr></thead>
        <tbody>{page.items.map((event, index) => <tr key={`${event.event_id}-${index}`} className="border-t border-white/10">
          <td>{event.sequence}</td><td>{((event.scenario_time_ns ?? 0) / 1e9).toFixed(6)}</td>
          <td><button type="button" className="py-2 text-info underline" onClick={() => setSelected(event)}>{event.event_type} · {event.payload?.address || event.sequence}</button></td>
        </tr>)}</tbody>
      </table></div>
      <div className="flex gap-3"><Button variant="outline" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 25))}>{copy("Anterior", "Previous")}</Button>
        <Button variant="outline" disabled={offset + 25 >= page.total} onClick={() => setOffset(offset + 25)}>{copy("Siguiente", "Next")}</Button></div>
    </>}
    {selected && <section className="space-y-3 rounded border border-info/30 p-4" aria-label={copy("Evento seleccionado", "Selected event")}>
      <h4 className="font-semibold">{copy("Registro original del evento", "Original event record")}</h4>
      <p className="break-all font-mono text-xs">{selected.event_id}</p>
      <pre className="max-h-64 overflow-auto whitespace-pre-wrap text-xs">{selected.raw_json ?? JSON.stringify(selected, null, 2)}</pre>
      <h4 className="font-semibold">{copy("Observaciones temporales vinculadas", "Linked timing observations")}</h4>
      <p className="text-sm text-muted-foreground">{copy("Los valores pertenecen a dominios de reloj distintos; no se calcula latencia entre ellos.", "Values belong to named clock domains; no latency is calculated between clocks.")}</p>
      {timing.length ? timing.map(observation => <div key={observation.observation_id} className="break-all border-t border-white/10 pt-2 text-sm">
        <p>{observation.kind} · {observation.evidence_source} · {observation.clock_id}</p>
        <p className="font-mono">{observation.value_text ?? observation.value} {observation.unit}</p>
        <p className="font-mono text-xs text-muted-foreground">{observation.observation_id}</p>
      </div>) : <p>{copy("Observaciones no disponibles.", "Observations unavailable.")}</p>}
    </section>}
  </div>;
}

export function EvidenceInspector({ capture }: { capture: EvidenceCapture }) {
  const { copy } = useAppLocale();
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
  return <section className="space-y-5" aria-label={copy("Inspector de evidencia", "Evidence inspector")}>
    <div className="control-surface space-y-3">
      <h2 className="text-xl font-semibold">{capture.participant_id ?? "—"} · {capture.condition}</h2>
      <p>{capture.execution_purpose} · {capture.completion} · {capture.runs[0]?.status ?? "pending"}</p>
      <p className="text-sm text-muted-foreground">{copy("La conciliación de fuentes, la cualificación temporal física y la calibración humana son resultados independientes.", "Source reconciliation, physical timing qualification and human calibration are separate outcomes.")}</p>
      <details><summary className="cursor-pointer">{copy("Procedencia y procesamiento", "Provenance and processing")}</summary>
        <dl className="space-y-2 break-all text-xs"><dt>Capture</dt><dd>{capture.id}</dd><dt>Block instance</dt><dd>{capture.block_instance_id}</dd>
          <dt>Manifest SHA-256</dt><dd>{capture.manifest_sha256}</dd><dt>Source commit</dt><dd>{capture.manifest.source_commit}</dd>
          <dt>Scenario SHA-256</dt><dd>{capture.manifest.scenario_sha256}</dd></dl>
        {capture.runs.map(run => <p key={run.id} className="mt-2 text-sm">{run.version} · {run.status} {run.reason ?? ""}</p>)}
      </details>
      <Button variant="outline" onClick={() => { void downloadEvidence(capture.id).catch(e => setError(e.message)); }}>{copy("Exportar evidencia verificable", "Export verifiable evidence")}</Button>
      {error && <p role="alert" className="text-danger">{error}</p>}
      {Boolean(capture.reconciliation?.issues.length) && <details open><summary>{copy("Incidencias de conciliación", "Reconciliation findings")} ({capture.reconciliation?.issues.length})</summary>
        <ul className="mt-2 max-h-48 list-inside list-disc overflow-auto text-sm">{capture.reconciliation?.issues.map((issue, index) => <li key={index}>{issue.task ?? "capture"}: {issue.code} {issue.detail}</li>)}</ul>
      </details>}
    </div>
    <div className="control-surface overflow-x-auto"><table className="w-full text-left text-sm">
      <caption className="pb-3 text-left">{copy("Seleccione una métrica para revisar sus fuentes y exclusiones.", "Select a metric to review its sources and exclusions.")}</caption>
      <thead><tr><th>{copy("Análisis", "Analysis")}</th><th>{copy("Métrica", "Metric")}</th><th>{copy("Valor", "Value")}</th><th>{copy("Estado", "Status")}</th><th>{copy("Elegibilidad", "Eligibility")}</th></tr></thead>
      <tbody>{capture.metrics.map(metric => <tr key={metric.id} className="border-t border-white/10">
        <td><input type="checkbox" aria-label={`${copy("Incluir", "Include")} ${metric.metric}`} disabled={!metric.confirmatory_eligible}
          checked={selection.includes(metric.id)} onChange={e => { setSelection(values => e.target.checked ? [...values, metric.id] : values.filter(v => v !== metric.id)); setInputId(null); }} /></td>
        <td><button className="py-3 pr-3 text-left text-info underline" onClick={() => setSelectedId(metric.id)}>{metric.metric}</button></td>
        <td>{metric.value ?? "—"}</td><td>{metric.status}</td>
        <td>{metric.confirmatory_eligible ? copy("Elegible según contrato", "Contract eligible") : copy("Excluida", "Excluded")}</td>
      </tr>)}</tbody>
    </table>
      <Button variant="outline" className="mt-4" disabled={!selection.length} onClick={() => void freezeInput()}>{copy("Fijar y exportar selección para análisis", "Freeze and export analysis selection")}</Button>
      {inputId && <p className="mt-2 break-all text-xs" role="status">{copy("Selección guardada", "Saved selection")}: {inputId}</p>}
    </div>
    {selected && <section className="control-surface space-y-4" aria-label={copy("Detalle de métrica", "Metric details")}>
      <h3 className="font-semibold">{selected.metric} · v{selected.metric_version}</h3>
      <p>{selected.definition.equation} ({selected.definition.unit})</p>
      <p className="text-sm">{copy("Datos necesarios", "Required inputs")}: {selected.definition.required_inputs.join(", ")}</p>
      <p className="text-sm">{selected.definition.missing_policy}</p>
      {selected.descriptive_value !== selected.value && <p>{copy("Valor descriptivo excluido", "Excluded descriptive value")}: {selected.descriptive_value ?? "—"}</p>}
      <p>{copy("Cualificación temporal física", "Physical timing qualification")}: {selected.physical_timing_qualification}</p>
      <p>{copy("Calibración humana", "Human calibration")}: {selected.human_calibration}</p>
      {selected.exclusion_reasons.length > 0 && <ul className="list-inside list-disc">{selected.exclusion_reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>}
      <EventSources key={`${capture.id}-${selected.id}`} captureId={capture.id} metricId={selected.id} />
    </section>}
  </section>;
}
