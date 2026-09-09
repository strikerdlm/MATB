"use client";
import { useState } from "react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { evidenceRequest, type EvidenceCapture } from "@/lib/evidence";
import { EvidenceInspector } from "./EvidenceInspector";

export function EvidenceUpload() {
  const { copy } = useAppLocale();
  const [files, setFiles] = useState<Record<string, File | undefined>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [capture, setCapture] = useState<EvidenceCapture | null>(null);
  const fields = [
    ["capture_manifest", copy("Manifiesto de captura", "Capture manifest"), ".json"],
    ["scenario_manifest", copy("Manifiesto del escenario", "Scenario manifest"), ".json"],
    ["events", copy("Eventos científicos v3", "Scientific events v3"), ".jsonl"],
    ["timing", copy("Observaciones de tiempo v1", "Timing observations v1"), ".jsonl"],
    ["legacy_csv", copy("CSV de contraste (opcional)", "Companion CSV (optional)"), ".csv"],
  ];
  async function submit() {
    setBusy(true); setError(""); setCapture(null);
    try {
      const form = new FormData();
      for (const [key, file] of Object.entries(files)) if (file) form.append(key, file);
      setCapture(await evidenceRequest<EvidenceCapture>("/ingest/evidence", { method: "POST", body: form }));
    } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
    finally { setBusy(false); }
  }
  return <section className="space-y-5" aria-label={copy("Evidencia científica", "Scientific evidence")}>
    <div className="control-surface max-w-3xl space-y-4">
      <h2 className="text-lg font-semibold">{copy("Captura científica", "Scientific capture")}</h2>
      <p className="text-sm text-muted-foreground">{copy("La identidad y las tareas proceden del manifiesto. La importación conserva los archivos originales y presenta las exclusiones por métrica.", "Identity and administered tasks come from the manifest. Import preserves original files and reports exclusions for each metric.")}</p>
      {fields.map(([key, label, accept]) => <div key={key}>
        <Label htmlFor={`evidence-${key}`}>{label}</Label>
        <Input id={`evidence-${key}`} type="file" accept={accept} disabled={busy}
          onChange={e => setFiles(previous => ({ ...previous, [key]: e.target.files?.[0] }))} />
      </div>)}
      <Button onClick={() => void submit()} disabled={busy || fields.slice(0, 4).some(([key]) => !files[key])}>
        {busy ? copy("Conciliando evidencia…", "Reconciling evidence…") : copy("Importar evidencia", "Import evidence")}
      </Button>
      {error && <p role="alert" className="text-danger">{error}</p>}
    </div>
    {capture && <EvidenceInspector capture={capture} />}
  </section>;
}
