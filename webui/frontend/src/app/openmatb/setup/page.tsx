"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { AlertTriangle, CheckCircle2, MonitorUp, Play } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Input } from "@/components/ui/input";
import { listParticipants, listVisits } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";
import { createOpenMatbSession, getOpenMatbReadiness, listOpenMatbInstructions, listOpenMatbPresets, storeOpenMatbCredentials } from "@/lib/openmatb/api";
import type { Participant, Visit } from "@/types";
import type { OpenMatbInstructionProtocol, OpenMatbPresetSet, OpenMatbReadiness } from "@/types/openmatb";

export default function OpenMatbSetupPage() {
  const router = useRouter();
  const { copy } = useAppLocale();
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [presets, setPresets] = useState<OpenMatbPresetSet[]>([]);
  const [instructions, setInstructions] = useState<OpenMatbInstructionProtocol[]>([]);
  const [readiness, setReadiness] = useState<OpenMatbReadiness | null>(null);
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [presetKey, setPresetKey] = useState("");
  const [instructionKey, setInstructionKey] = useState("");
  const [displayIndex, setDisplayIndex] = useState(1);
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([listParticipants(), listOpenMatbPresets(), listOpenMatbInstructions(), getOpenMatbReadiness()])
      .then(([people, presetRows, instructionRows, ready]) => {
        if (!active) return;
        const publishedPresets = presetRows.filter((row) => row.status === "published");
        const publishedInstructions = instructionRows.filter((row) => row.status === "published");
        setParticipants(people); setPresets(publishedPresets); setInstructions(publishedInstructions); setReadiness(ready);
        if (publishedPresets[0]) setPresetKey(`${publishedPresets[0].preset_id}@${publishedPresets[0].version}`);
        if (publishedInstructions[0]) setInstructionKey(`${publishedInstructions[0].protocol_id}@${publishedInstructions[0].version}`);
        setDisplayIndex(ready.display_index_default);
      })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : copy("No se pudo preparar OpenMATB.", "OpenMATB setup could not be loaded.")); });
    return () => { active = false; };
  }, [copy]);

  useEffect(() => {
    if (!participantId) { setVisits([]); setVisitOrdinal(""); return; }
    void listVisits(participantId).then((rows) => { setVisits(rows); setVisitOrdinal(rows[0] ? String(rows[0].visit_ordinal) : ""); }).catch((reason: unknown) => setError(reason instanceof Error ? reason.message : copy("No se pudieron cargar las visitas.", "Visits could not be loaded.")));
  }, [copy, participantId]);

  const preset = useMemo(() => presets.find((row) => `${row.preset_id}@${row.version}` === presetKey), [presetKey, presets]);
  const protocol = useMemo(() => instructions.find((row) => `${row.protocol_id}@${row.version}` === instructionKey), [instructionKey, instructions]);
  const canPrepare = Boolean(readiness?.ready && participantId && visitOrdinal && preset && protocol && acknowledged && !busy);

  async function prepare() {
    if (!canPrepare || !preset || !protocol) return;
    const participantWindow = window.open("about:blank", "matb-fac-participant");
    setBusy(true); setError(null);
    try {
      const prepared = await createOpenMatbSession({
        participant_id: participantId, visit_ordinal: Number(visitOrdinal),
        preset_id: preset.preset_id, preset_version: preset.version,
        instruction_protocol_id: protocol.protocol_id, instruction_version: protocol.version,
        display_index: displayIndex,
      });
      storeOpenMatbCredentials(prepared);
      const participantUrl = `/openmatb/participant?session=${encodeURIComponent(prepared.session.id)}#token=${encodeURIComponent(prepared.participant_token)}`;
      if (participantWindow) participantWindow.location.href = participantUrl;
      router.push(`/openmatb/session?session=${encodeURIComponent(prepared.session.id)}`);
    } catch (reason: unknown) {
      participantWindow?.close();
      setError(reason instanceof Error ? reason.message : copy("No se pudo preparar la suite.", "The suite could not be prepared."));
    } finally { setBusy(false); }
  }

  return <div className="space-y-6">
    <PageHeader
      kicker={copy("Control nativo", "Native control")}
      title={copy("Suite OpenMATB clásica", "Classic OpenMATB suite")}
      description={copy("Prepare una visita completa con práctica, bloques contrabalanceados e instrucciones para el participante.", "Prepare a complete visit with practice, counterbalanced blocks, and participant instructions.")}
      actions={<Button asChild variant="outline"><Link href="/openmatb/settings">{copy("Configurar presets e instrucciones", "Configure presets and instructions")}</Link></Button>}
      stats={[
        { label: copy("Sistema", "System"), value: readiness?.platform ?? "—" },
        { label: copy("Perfiles", "Profiles"), value: "04" },
        { label: copy("Estado", "Status"), value: readiness?.ready ? copy("Listo", "Ready") : copy("Revisar", "Check") },
      ]}
    />

    {error && <p role="alert" className="border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>}
    {readiness && !readiness.ready && <div role="alert" className="flex gap-3 border border-warning/40 bg-warning/5 p-4 text-sm text-warning"><AlertTriangle className="h-5 w-5 shrink-0" /><div><strong>{copy("La estación no está lista.", "The station is not ready.")}</strong><ul className="mt-2 list-disc pl-5">{Object.entries(readiness.checks).filter(([, ok]) => !ok).map(([name]) => <li key={name}>{name}</li>)}</ul></div></div>}

    <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_23rem]">
      <Card>
        <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Preparar visita", "Prepare visit")}</CardTitle><CardDescription>{copy("La configuración queda bloqueada al crear la sesión.", "Configuration is locked when the session is created.")}</CardDescription></CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2"><Label htmlFor="om-participant">{copy("Participante", "Participant")}</Label><select id="om-participant" className="native-select w-full" value={participantId} onChange={(event) => setParticipantId(event.target.value)}><option value="">—</option>{participants.map((row) => <option key={row.id} value={row.id}>{row.id}</option>)}</select></div>
          <div className="space-y-2"><Label htmlFor="om-visit">{copy("Visita", "Visit")}</Label><select id="om-visit" className="native-select w-full" value={visitOrdinal} onChange={(event) => setVisitOrdinal(event.target.value)} disabled={!participantId}><option value="">—</option>{visits.map((row) => <option key={row.id} value={row.visit_ordinal}>{copy("Día", "Day")} {row.scheduled_day} · V{row.visit_ordinal}</option>)}</select></div>
          <div className="space-y-2"><Label htmlFor="om-preset">{copy("Preset publicado", "Published preset")}</Label><select id="om-preset" className="native-select w-full" value={presetKey} onChange={(event) => setPresetKey(event.target.value)}>{presets.map((row) => <option key={`${row.preset_id}@${row.version}`} value={`${row.preset_id}@${row.version}`}>{row.label_es} · v{row.version}</option>)}</select></div>
          <div className="space-y-2"><Label htmlFor="om-protocol">{copy("Instrucciones", "Instructions")}</Label><select id="om-protocol" className="native-select w-full" value={instructionKey} onChange={(event) => setInstructionKey(event.target.value)}>{instructions.map((row) => <option key={`${row.protocol_id}@${row.version}`} value={`${row.protocol_id}@${row.version}`}>{row.title} · v{row.version}</option>)}</select></div>
          <div className="space-y-2"><Label htmlFor="om-display">{copy("Pantalla del participante", "Participant display")}</Label><Input id="om-display" type="number" min={0} max={15} value={displayIndex} onChange={(event) => setDisplayIndex(Number(event.target.value))} /><p className="text-xs text-muted-foreground">{copy("Use 1 para la segunda pantalla; use 0 si sólo hay una.", "Use 1 for the second display; use 0 for a single display.")}</p></div>
          <label className="flex items-start gap-3 border border-white/10 bg-white/[0.02] p-3 text-sm text-muted-foreground sm:col-span-2"><input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} className="mt-1" /><span>{copy("Confirmo que esta estación se utilizará como instrumento de investigación y que verificaré físicamente el audio y los controles antes de la sesión.", "I confirm this station is used as a research instrument and I will physically verify audio and controls before the session.")}</span></label>
          <Button className="sm:col-span-2" disabled={!canPrepare} onClick={() => void prepare()}><Play className="mr-2 h-4 w-4" />{busy ? copy("Preparando…", "Preparing…") : copy("Preparar y abrir pantalla del participante", "Prepare and open participant display")}</Button>
        </CardContent>
      </Card>

      <Card><CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Comprobaciones", "Checks")}</CardTitle></CardHeader><CardContent className="space-y-3">{readiness ? Object.entries(readiness.checks).map(([name, ok]) => <div key={name} className="flex items-center justify-between border-b border-white/10 pb-2 text-sm"><span className="font-mono text-xs uppercase">{name.replaceAll("_", " ")}</span><CheckCircle2 className={`h-4 w-4 ${ok ? "text-success" : "text-danger"}`} /></div>) : <p>{copy("Consultando…", "Checking…")}</p>}<div className="mt-5 flex gap-3 border border-info/30 bg-info/5 p-3 text-xs text-muted-foreground"><MonitorUp className="h-4 w-4 shrink-0 text-info" /><span>{copy("El panel del investigador permanece en la primera pantalla. OpenMATB se abrirá en el índice seleccionado.", "The researcher console stays on the first display. OpenMATB opens on the selected display index.")}</span></div></CardContent></Card>
    </div>

    {preset && <Card><CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Parámetros de carga", "Workload parameters")}</CardTitle><CardDescription>{copy("Preset de ingeniería versionado; no equivale a calibración humana independiente.", "Versioned engineering preset; it is not independent human calibration.")}</CardDescription></CardHeader><CardContent className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><tr><th className="pb-3">{copy("Perfil", "Profile")}</th><th>{copy("Duración", "Duration")}</th><th>{copy("Dificultad", "Difficulty")}</th><th>TRACK</th><th>RESMAN</th><th>ISA</th></tr></thead><tbody>{Object.entries(preset.profiles).map(([name, value]) => <tr key={name} className="border-t border-white/10"><td className="py-3 font-semibold">{name}</td><td>{value.duration_seconds}s</td><td>{value.difficulty.toFixed(2)}</td><td>{value.track_target_proportion.toFixed(2)}</td><td>{value.resman_loss_per_min} L/min</td><td>{value.isa_probe_interval_sec}s</td></tr>)}</tbody></table></CardContent></Card>}
  </div>;
}
