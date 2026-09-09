"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { EvidenceInspector } from "@/components/evidence/EvidenceInspector";
import { useAppLocale } from "@/lib/i18n";
import { evidenceRequest, type EvidenceCapture, type EvidencePage } from "@/lib/evidence";

export default function EvidencePageView() {
  const { copy } = useAppLocale();
  const [purpose, setPurpose] = useState("study");
  const [offset, setOffset] = useState(0);
  const [captures, setCaptures] = useState<EvidencePage<EvidenceCapture> | null>(null);
  const [captureId, setCaptureId] = useState<string | null>(null);
  const [capture, setCapture] = useState<EvidenceCapture | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    const controller = new AbortController(); setCaptures(null); setError("");
    void evidenceRequest<EvidencePage<EvidenceCapture>>(`/evidence/captures?purpose=${purpose}&offset=${offset}`, { signal: controller.signal })
      .then(setCaptures).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [purpose, offset]);
  useEffect(() => {
    if (!captureId) { setCapture(null); return; }
    const controller = new AbortController(); setCapture(null); setError("");
    void evidenceRequest<EvidenceCapture>(`/evidence/captures/${captureId}`, { signal: controller.signal })
      .then(setCapture).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [captureId]);
  return <div className="space-y-6">
    <PageHeader kicker={copy("Investigación", "Research")} title={copy("Evidencia científica", "Scientific evidence")}
      description={copy("Eventos, observaciones temporales y resultados con procedencia verificable.", "Events, timing observations and results with verifiable provenance.")} />
    <Link href="/upload" className="text-info underline">{copy("Importar una captura", "Import a capture")}</Link>
    <label className="block">{copy("Finalidad", "Purpose")} <select className="native-select" value={purpose} onChange={e => { setPurpose(e.target.value); setOffset(0); setCaptureId(null); }}>
      <option value="study">{copy("Estudio", "Study")}</option><option value="practice">{copy("Práctica", "Practice")}</option><option value="exploration">{copy("Exploración", "Exploration")}</option>
    </select></label>
    {error && <p role="alert" className="text-danger">{error}</p>}
    <div className="flex flex-wrap gap-3">{captures?.items.map(item => <Button key={item.id} variant="outline" onClick={() => setCaptureId(item.id)}>{item.participant_id ?? "—"} · {item.condition} · {item.block_instance_id.slice(0, 8)}</Button>)}</div>
    {captures?.total === 0 && <p>{copy("No hay capturas para esta finalidad.", "No captures for this purpose.")}</p>}
    {captures && captures.total > 25 && <div className="flex gap-3"><Button disabled={!offset} onClick={() => setOffset(offset - 25)}>{copy("Anterior", "Previous")}</Button><Button disabled={offset + 25 >= captures.total} onClick={() => setOffset(offset + 25)}>{copy("Siguiente", "Next")}</Button></div>}
    {capture && <EvidenceInspector key={capture.id} capture={capture} />}
  </div>;
}
