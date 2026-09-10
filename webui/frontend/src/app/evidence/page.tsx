"use client";
import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EvidenceInspector } from "@/components/evidence/EvidenceInspector";
import { useAppLocale } from "@/lib/i18n";
import { evidenceRequest, type EvidenceCapture, type EvidenceCaptureSummary, type EvidencePage } from "@/lib/evidence";
import { evidenceStateLabel } from "@/lib/evidence-state";

function useEvidenceResource<T>(path: string | null, revision: number) {
  const [state, setState] = useState<{ path: string | null; data: T | null; error: string }>({ path: null, data: null, error: "" });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState({ path, data: null, error: "" });
    void evidenceRequest<T>(path, { signal: controller.signal }).then(data => {
      if (!controller.signal.aborted) setState({ path, data, error: "" });
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) setState({ path, data: null, error: error instanceof Error ? error.message : "Request failed" });
    });
    return () => controller.abort();
  }, [path, revision]);
  return state.path === path ? state : { path, data: null, error: "" };
}

function EvidenceWorkspace() {
  const { copy, locale } = useAppLocale();
  const search = useSearchParams();
  const router = useRouter();
  const purpose = ["study", "practice", "exploration", "all"].includes(search.get("purpose") ?? "") ? search.get("purpose")! : "study";
  const query = (search.get("q") ?? "").slice(0, 200);
  const sessionId = search.get("session") ?? "";
  const captureId = search.get("capture");
  const rawOffset = Number(search.get("offset") ?? 0);
  const offset = Number.isSafeInteger(rawOffset) && rawOffset >= 0 ? rawOffset : 0;
  const [revision, setRevision] = useState(0);
  const params = new URLSearchParams({ purpose, offset: String(offset), limit: "25" });
  if (sessionId) params.set("session", sessionId);
  if (query) params.set("q", query);
  const list = useEvidenceResource<EvidencePage<EvidenceCaptureSummary>>(`/evidence/captures?${params}`, revision);
  const selected = useEvidenceResource<EvidenceCapture>(captureId ? `/evidence/captures/${encodeURIComponent(captureId)}` : null, revision);
  function href(changes: Record<string, string | null>) {
    const next = new URLSearchParams(search.toString());
    for (const [key, value] of Object.entries(changes)) {
      if (value) next.set(key, value); else next.delete(key);
    }
    return `/evidence?${next}`;
  }
  const navigate = (changes: Record<string, string | null>) => router.push(href(changes), { scroll: false });
  const listLoading = !list.data && !list.error;
  const selectedLoading = Boolean(captureId && !selected.data && !selected.error);
  return <div className="min-w-0 space-y-6 text-base">
    <PageHeader kicker={copy("Investigación", "Research")} title={copy("Evidencia científica", "Scientific evidence")}
      description={copy("Localice una sesión y revise los registros que respaldan sus resultados.", "Find a session and review the records supporting its results.")} />
    <div className="flex flex-wrap items-center justify-between gap-3">
      <Link href="/upload" className="text-sm text-info underline">{copy("Importar una captura", "Import a capture")}</Link>
      <Button variant="outline" className="text-sm normal-case tracking-normal" onClick={() => setRevision(value => value + 1)}>{copy("Actualizar resultados", "Refresh results")}</Button>
    </div>
    <form role="search" className="flex flex-wrap items-end gap-3" onSubmit={event => {
      event.preventDefault();
      navigate({ q: String(new FormData(event.currentTarget).get("q") ?? "").trim(), offset: null });
    }}>
      <label className="min-w-0 flex-1 text-sm">{copy("Buscar participante, bloque o captura", "Search participant, block or capture")}
        <Input key={query} name="q" type="search" maxLength={200} defaultValue={query} className="mt-1 text-base" />
      </label>
      <Button className="text-sm normal-case tracking-normal" type="submit">{copy("Buscar", "Search")}</Button>
      <label className="text-sm">{copy("Finalidad", "Purpose")}
        <select className="native-select mt-1 block" value={purpose} onChange={event => navigate({ purpose: event.target.value, offset: null })}>
          <option value="all">{copy("Todas", "All purposes")}</option><option value="study">{copy("Estudio", "Study")}</option>
          <option value="practice">{copy("Práctica", "Practice")}</option><option value="exploration">{copy("Exploración", "Exploration")}</option>
        </select>
      </label>
    </form>
    {sessionId && <div className="flex flex-wrap gap-3 text-sm"><span>{copy("Resultados de la sesión seleccionada", "Results for the selected session")}</span>
      <Link href={href({ session: null, offset: null })} className="text-info underline">{copy("Ver todas las sesiones", "View all sessions")}</Link></div>}
    <section aria-label={copy("Lista de capturas", "Capture list")} aria-busy={listLoading} className="space-y-3">
      {listLoading && <p role="status">{copy("Cargando capturas…", "Loading captures…")}</p>}
      {list.error && <p role="alert" className="text-danger">{list.error}</p>}
      {list.data && <>
        <p className="text-sm text-muted-foreground">{list.data.total} {copy("capturas. El registro de datos y su cualificación se muestran por separado.", "captures. Data registration and qualification are shown separately.")}</p>
        {list.data.items.length ? <div className="overflow-x-auto rounded border">
          <table className="w-full text-left text-sm">
            <caption className="sr-only">{copy("Capturas disponibles; la fecha indica cuándo se registraron en la consola.", "Available captures; the date indicates when they were registered in the console.")}</caption>
            <thead className="border-b bg-muted/30"><tr>
              {[copy("Participante", "Participant"), copy("Visita / bloque", "Visit / block"), copy("Registro", "Registered"), copy("Finalidad", "Purpose"), copy("Revisión", "Review"), copy("Abrir", "Open")].map(label => <th key={label} scope="col" className="p-3 font-semibold">{label}</th>)}
            </tr></thead>
            <tbody>{list.data.items.map(item => <tr key={item.id} data-selected={item.id === captureId} className={item.id === captureId ? "border-b border-info/40 bg-info/15" : "border-b border-border"}>
              <th scope="row" className="p-3 font-mono font-medium">{item.participant_id ?? "—"}</th>
              <td className="p-3"><div className="whitespace-nowrap">{item.visit_ordinal ?? "—"} · {item.condition}</div><span className="font-mono text-muted-foreground" title={item.block_instance_id}>{item.block_instance_id.slice(0, 8)}</span></td>
              <td className="p-3 tabular-nums"><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleString(locale)}</time></td>
              <td className="p-3">{evidenceStateLabel(item.execution_purpose, copy)}</td>
              <td className="min-w-56 space-y-1 p-3"><p className="font-medium">{evidenceStateLabel(item.capture_status, copy)}</p>
                <p>{copy("Tiempo físico: ", "Timing: ")}{evidenceStateLabel(item.qualification.physical_timing, copy)}</p>
                <p>{copy("Calibración humana: ", "Human calibration: ")}{evidenceStateLabel(item.qualification.human_calibration, copy)}</p>
                <p>{copy("Protocolo: ", "Protocol: ")}{evidenceStateLabel(item.qualification.protocol_eligibility.status, copy)}</p>
              </td>
              <td className="p-3"><Link scroll={false} href={href({ capture: item.id })} aria-current={item.id === captureId ? "true" : undefined}
                aria-label={`${copy("Revisar", "Review")} ${item.participant_id ?? "—"} · ${item.condition} · ${item.block_instance_id.slice(0, 8)}`}
                className="inline-block rounded border border-info/40 px-3 py-2 font-semibold text-info underline underline-offset-4">{item.id === captureId ? copy("Seleccionada", "Selected") : copy("Revisar", "Review")}</Link></td>
            </tr>)}</tbody>
          </table>
        </div> : <p>{copy("No hay capturas que coincidan. Ajuste la búsqueda o los filtros.", "No matching captures. Adjust the search or filters.")}</p>}
        <nav aria-label={copy("Páginas de capturas", "Capture pages")} className="flex flex-wrap gap-4 text-sm">
          {offset > 0 && <Link scroll={false} className="text-info underline" href={href({ offset: String(Math.max(0, offset - 25)) })}>{copy("Anterior", "Previous")}</Link>}
          {offset + 25 < list.data.total && <Link scroll={false} className="text-info underline" href={href({ offset: String(offset + 25) })}>{copy("Siguiente", "Next")}</Link>}
        </nav>
      </>}
    </section>
    <section aria-label={copy("Captura seleccionada", "Selected capture")} aria-busy={selectedLoading}>
      {selectedLoading && <p role="status">{copy("Cargando captura seleccionada…", "Loading selected capture…")}</p>}
      {selected.error && <p role="alert" className="text-danger">{selected.error}</p>}
      {selected.data && <EvidenceInspector key={selected.data.id} capture={selected.data} />}
    </section>
  </div>;
}

export default function EvidencePageView() {
  return <Suspense><EvidenceWorkspace /></Suspense>;
}
