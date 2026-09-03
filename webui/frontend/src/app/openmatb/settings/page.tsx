"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Copy, Save, Send } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useAppLocale } from "@/lib/i18n";
import {
  cloneOpenMatbInstructions,
  cloneOpenMatbPreset,
  listOpenMatbInstructions,
  listOpenMatbPresets,
  publishOpenMatbInstructions,
  publishOpenMatbPreset,
  updateOpenMatbInstructions,
  updateOpenMatbPreset,
} from "@/lib/openmatb/api";
import type { OpenMatbInstructionProtocol, OpenMatbPresetSet, OpenMatbProfile, OpenMatbProfileSettings } from "@/types/openmatb";

const profiles: OpenMatbProfile[] = ["PRACTICE", "LOW", "MEDIUM", "HIGH"];
const taskNames = ["TRACK", "COMM", "SYSMON", "RESMAN"];

function nextVersion(version: string): string {
  const parts = version.split(".").map(Number);
  return parts.length === 3 && parts.every(Number.isFinite) ? `${parts[0]}.${parts[1]}.${parts[2] + 1}` : "1.0.1";
}

export default function OpenMatbSettingsPage() {
  const { copy } = useAppLocale();
  const [presets, setPresets] = useState<OpenMatbPresetSet[]>([]);
  const [instructions, setInstructions] = useState<OpenMatbInstructionProtocol[]>([]);
  const [preset, setPreset] = useState<OpenMatbPresetSet | null>(null);
  const [protocol, setProtocol] = useState<OpenMatbInstructionProtocol | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    const [presetRows, instructionRows] = await Promise.all([listOpenMatbPresets(), listOpenMatbInstructions()]);
    setPresets(presetRows); setInstructions(instructionRows);
    setPreset((current) => presetRows.find((row) => row.preset_id === current?.preset_id && row.version === current.version) ?? presetRows.at(-1) ?? null);
    setProtocol((current) => instructionRows.find((row) => row.protocol_id === current?.protocol_id && row.version === current.version) ?? instructionRows.at(-1) ?? null);
  }, []);

  useEffect(() => { void reload().catch((reason: unknown) => setError(reason instanceof Error ? reason.message : copy("No se pudo cargar la configuración.", "Configuration could not be loaded."))); }, [copy, reload]);

  async function run(action: () => Promise<unknown>, success: string) {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); await reload(); setNotice(success); }
    catch (reason: unknown) { setError(reason instanceof Error ? reason.message : copy("La operación no se pudo completar.", "The operation could not be completed.")); }
    finally { setBusy(false); }
  }

  function changeProfile(name: OpenMatbProfile, key: keyof OpenMatbProfileSettings, value: number) {
    setPreset((current) => current ? { ...current, profiles: { ...current.profiles, [name]: { ...current.profiles[name], [key]: value } } } : current);
  }

  return <div className="space-y-6">
    <PageHeader
      kicker={copy("Configuración versionada", "Versioned configuration")}
      title={copy("Presets e instrucciones OpenMATB", "OpenMATB presets and instructions")}
      description={copy("Clone una versión publicada, modifique el borrador y publíquelo cuando esté listo. Las sesiones creadas conservan una copia inmutable.", "Clone a published version, edit the draft, and publish it when ready. Created sessions retain an immutable copy.")}
      actions={<Button asChild variant="outline"><Link href="/openmatb/setup">{copy("Volver a preparar visita", "Back to visit setup")}</Link></Button>}
    />
    {error && <p role="alert" className="border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>}
    {notice && <p role="status" className="border border-success/40 bg-success/10 px-4 py-3 text-sm text-success">{notice}</p>}

    <Card>
      <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Carga de trabajo", "Workload")}</CardTitle><CardDescription>{copy("Parámetros de ingeniería para práctica y bloques bajo, medio y alto.", "Engineering parameters for practice and low, medium, and high blocks.")}</CardDescription></CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 md:grid-cols-[1fr_auto]">
          <div className="space-y-2"><Label htmlFor="preset-select">{copy("Versión", "Version")}</Label><select id="preset-select" className="native-select w-full" value={preset ? `${preset.preset_id}@${preset.version}` : ""} onChange={(event) => setPreset(presets.find((row) => `${row.preset_id}@${row.version}` === event.target.value) ?? null)}>{presets.map((row) => <option key={`${row.preset_id}@${row.version}`} value={`${row.preset_id}@${row.version}`}>{row.label_es} · v{row.version} · {row.status}</option>)}</select></div>
          <div className="flex items-end"><Button variant="outline" disabled={!preset || busy} onClick={() => preset && void run(() => cloneOpenMatbPreset(preset, { preset_id: preset.preset_id, version: nextVersion(preset.version), label_es: `${preset.label_es} — borrador` }), copy("Borrador clonado.", "Draft cloned."))}><Copy className="mr-2 h-4 w-4" />{copy("Clonar borrador", "Clone draft")}</Button></div>
        </div>
        {preset && <>
          <div className="overflow-x-auto"><table className="w-full min-w-[920px] text-left text-sm"><thead className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><tr><th className="pb-3">{copy("Perfil", "Profile")}</th><th>{copy("Duración (s)", "Duration (s)")}</th><th>{copy("Dificultad", "Difficulty")}</th><th>{copy("Objetivo TRACK", "TRACK target")}</th><th>{copy("Pérdida RESMAN", "RESMAN loss")}</th><th>{copy("Intervalo ISA", "ISA interval")}</th></tr></thead><tbody>{profiles.map((name) => <tr key={name} className="border-t border-white/10"><td className="py-3 font-semibold">{name}</td>{(["duration_seconds", "difficulty", "track_target_proportion", "resman_loss_per_min", "isa_probe_interval_sec"] as (keyof OpenMatbProfileSettings)[]).map((key) => <td key={key} className="pr-3"><Input aria-label={`${name} ${key}`} type="number" step={key === "difficulty" || key === "track_target_proportion" ? "0.05" : "1"} value={preset.profiles[name][key]} disabled={preset.status !== "draft"} onChange={(event) => changeProfile(name, key, Number(event.target.value))} /></td>)}</tr>)}</tbody></table></div>
          <p className="text-xs text-muted-foreground">{copy("ISA usa la escala instantánea 1–5 en español. NASA-TLX (0–100, pasos de 5) y Bedford (1–10) se responden al final de cada bloque. Bedford se identifica como traducción exploratoria.", "ISA uses the Spanish 1–5 instantaneous scale. NASA-TLX (0–100 in steps of 5) and Bedford (1–10) are completed after each block. Bedford is identified as an exploratory translation.")}</p>
          <div className="flex flex-wrap gap-3"><Button disabled={preset.status !== "draft" || busy} onClick={() => void run(() => updateOpenMatbPreset(preset), copy("Preset guardado.", "Preset saved."))}><Save className="mr-2 h-4 w-4" />{copy("Guardar borrador", "Save draft")}</Button><Button variant="secondary" disabled={preset.status !== "draft" || busy} onClick={() => void run(() => publishOpenMatbPreset(preset), copy("Preset publicado.", "Preset published."))}><Send className="mr-2 h-4 w-4" />{copy("Publicar", "Publish")}</Button><span className="self-center font-mono text-[10px] text-muted-foreground">SHA-256 {preset.sha256.slice(0, 16)}…</span></div>
        </>}
      </CardContent>
    </Card>

    <Card>
      <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Instrucciones del participante", "Participant instructions")}</CardTitle><CardDescription>{copy("Texto español por visita y por tarea. No incluya identificadores personales.", "Spanish text by visit and task. Do not include personal identifiers.")}</CardDescription></CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 md:grid-cols-[1fr_auto]">
          <div className="space-y-2"><Label htmlFor="instruction-select">{copy("Versión", "Version")}</Label><select id="instruction-select" className="native-select w-full" value={protocol ? `${protocol.protocol_id}@${protocol.version}` : ""} onChange={(event) => setProtocol(instructions.find((row) => `${row.protocol_id}@${row.version}` === event.target.value) ?? null)}>{instructions.map((row) => <option key={`${row.protocol_id}@${row.version}`} value={`${row.protocol_id}@${row.version}`}>{row.title} · v{row.version} · {row.status}</option>)}</select></div>
          <div className="flex items-end"><Button variant="outline" disabled={!protocol || busy} onClick={() => protocol && void run(() => cloneOpenMatbInstructions(protocol, { protocol_id: protocol.protocol_id, version: nextVersion(protocol.version) }), copy("Borrador clonado.", "Draft cloned."))}><Copy className="mr-2 h-4 w-4" />{copy("Clonar borrador", "Clone draft")}</Button></div>
        </div>
        {protocol && <>
          <div className="space-y-2"><Label htmlFor="instruction-title">{copy("Título", "Title")}</Label><Input id="instruction-title" value={protocol.title} disabled={protocol.status !== "draft"} onChange={(event) => setProtocol({ ...protocol, title: event.target.value })} /></div>
          <div className="space-y-2"><Label htmlFor="instruction-steps">{copy("Pasos, uno por línea", "Steps, one per line")}</Label><Textarea id="instruction-steps" rows={8} value={protocol.steps.join("\n")} disabled={protocol.status !== "draft"} onChange={(event) => setProtocol({ ...protocol, steps: event.target.value.split("\n") })} /></div>
          <div className="grid gap-4 md:grid-cols-3">{["T0", "DM8", "DM15"].map((code) => <div key={code} className="space-y-2"><Label htmlFor={`visit-${code}`}>{code}</Label><Textarea id={`visit-${code}`} rows={5} value={protocol.visit_instructions[code] ?? protocol.visit_instructions.DEFAULT ?? ""} disabled={protocol.status !== "draft"} onChange={(event) => setProtocol({ ...protocol, visit_instructions: { ...protocol.visit_instructions, [code]: event.target.value } })} /></div>)}</div>
          <div className="grid gap-4 md:grid-cols-2">{taskNames.map((name) => <div key={name} className="space-y-2"><Label htmlFor={`instruction-${name}`}>{name}</Label><Textarea id={`instruction-${name}`} rows={4} value={protocol.task_instructions[name] ?? ""} disabled={protocol.status !== "draft"} onChange={(event) => setProtocol({ ...protocol, task_instructions: { ...protocol.task_instructions, [name]: event.target.value } })} /></div>)}</div>
          <div className="flex flex-wrap gap-3"><Button disabled={protocol.status !== "draft" || busy} onClick={() => void run(() => updateOpenMatbInstructions(protocol), copy("Instrucciones guardadas.", "Instructions saved."))}><Save className="mr-2 h-4 w-4" />{copy("Guardar borrador", "Save draft")}</Button><Button variant="secondary" disabled={protocol.status !== "draft" || busy} onClick={() => void run(() => publishOpenMatbInstructions(protocol), copy("Instrucciones publicadas.", "Instructions published."))}><Send className="mr-2 h-4 w-4" />{copy("Publicar", "Publish")}</Button><span className="self-center font-mono text-[10px] text-muted-foreground">SHA-256 {protocol.sha256.slice(0, 16)}…</span></div>
        </>}
      </CardContent>
    </Card>
  </div>;
}
