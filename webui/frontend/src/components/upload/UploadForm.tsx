"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { ingestCsv, IngestError } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { Participant } from "@/types";
import { useAppLocale } from "@/lib/i18n";

const LEVELS = ["LOW", "MEDIUM", "HIGH"] as const;
type Result = { kind: "ok"; msg: string } | { kind: "err"; msg: string } | null;

export function UploadForm({ participants, onIngested }: { participants: Participant[]; onIngested: () => void }) {
  const { copy } = useAppLocale();
  const [file, setFile] = useState<File | null>(null);
  const [manifest, setManifest] = useState<File | null>(null);
  const [pid, setPid] = useState("");
  const [ordinal, setOrdinal] = useState(1);
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("LOW");
  const [overwrite, setOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<Result>(null);

  async function submit() {
    if (!file || !pid) return;
    setBusy(true); setResult(null);
    try {
      const r = await ingestCsv(file, {
        participant_id: pid,
        visit_ordinal: ordinal,
        workload_level: level,
        overwrite,
        manifest,
      });
      const validation = r.validation
        ? ` ${copy("Validación", "Validation")}: ${r.validation.status}${r.validation.issue_count ? ` (${r.validation.issue_count} ${copy("incidencias", r.validation.issue_count === 1 ? "issue" : "issues")})` : ""}.`
        : "";
      setResult({ kind: "ok", msg: `${copy("Bloque incorporado", "Ingested block")} #${r.id} (${r.workload_level}).${validation}` });
      setFile(null);
      setManifest(null);
      onIngested();
    } catch (e) {
      const msg = e instanceof IngestError ? `${copy("Rechazado", "Rejected")} (${e.status}): ${e.message}` : (e as Error).message;
      setResult({ kind: "err", msg });
    } finally { setBusy(false); }
  }

  return (
    <div className="control-surface max-w-3xl space-y-5">
      <div className="grid gap-1 border-b border-white/10 pb-4">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{copy("Paquete de sesión", "Session package")}</p>
        <p className="text-sm text-muted-foreground">{copy("Vincule el contenido CSV con una celda planificada.", "Bind the CSV payload to one planned cell.")}</p>
      </div>
      <div>
        <Label htmlFor="csv">{copy("CSV de sesión", "Session CSV")}</Label>
        <Input id="csv" type="file" accept=".csv" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
      </div>
      <div>
        <Label htmlFor="manifest">{copy("Manifiesto del escenario (opcional)", "Scenario manifest (optional)")}</Label>
        <Input
          id="manifest"
          type="file"
          accept=".json,.manifest.json,application/json"
          onChange={(e) => setManifest(e.target.files?.[0] ?? null)}
        />
      </div>
      <div>
        <Label htmlFor="up-pid">{copy("Participante", "Participant")}</Label>
        <select id="up-pid" value={pid} onChange={(e) => setPid(e.target.value)}
                className="native-select w-full">
          <option value="">{copy("Seleccionar…", "Select...")}</option>
          {participants.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
        </select>
      </div>
      <div className="flex gap-3">
        <div className="flex-1">
          <Label htmlFor="up-visit">{copy("Visita", "Visit")}</Label>
          <select id="up-visit" value={ordinal} onChange={(e) => setOrdinal(Number(e.target.value))}
                  className="native-select w-full">
            {[1, 2, 3, 4, 5, 6].map((n) => <option key={n} value={n}>{copy("Visita", "Visit")} {n}</option>)}
          </select>
        </div>
        <div className="flex-1">
          <Label htmlFor="up-level">{copy("Nivel", "Level")}</Label>
          <select id="up-level" value={level} onChange={(e) => setLevel(e.target.value as (typeof LEVELS)[number])}
                  className="native-select w-full">
            {LEVELS.map((l) => <option key={l} value={l}>{l}</option>)}
          </select>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Switch id="ow" checked={overwrite} onCheckedChange={setOverwrite} />
        <Label htmlFor="ow">{copy("Sobrescribir si la celda ya está completa", "Overwrite if cell already filled")}</Label>
      </div>
      {result && (
        <p className={cn(
          "rounded-[4px] border px-3 py-2 text-sm",
          result.kind === "ok"
            ? "border-success/40 bg-success/10 text-success"
            : "border-danger/40 bg-danger/10 text-danger",
        )}>{result.msg}</p>
      )}
      <Button onClick={submit} disabled={busy || !file || !pid} className="w-full">
        {busy ? copy("Cargando…", "Uploading...") : copy("Incorporar sesión", "Ingest session")}
      </Button>
    </div>
  );
}
