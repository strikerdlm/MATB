"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { AlertTriangle, CheckCircle2, Loader2, MonitorUp, Play } from "lucide-react";

import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { useExecutionPurpose } from "@/lib/execution-purpose";
import { GuidedSteps, type GuidedStepState } from "@/components/layout/GuidedSteps";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { listParticipants, listVisits } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";
import {
  createOpenMatbSession,
  getOpenMatbReadiness,
  listOpenMatbInstructions,
  listOpenMatbPresets,
  listOpenMatbVisualProfiles,
  storeOpenMatbCredentials,
} from "@/lib/openmatb/api";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import { isParticipantId } from "@/lib/participant-id";
import type { Participant, Visit } from "@/types";
import type {
  OpenMatbInstructionProtocol,
  OpenMatbPresetSet,
  OpenMatbReadiness,
  OpenMatbVisualProfile,
} from "@/types/openmatb";

const CHECK_LABELS: Record<string, [string, string]> = {
  python: ["Python compatible", "Compatible Python"],
  runtime_dependencies: ["Dependencias nativas", "Native dependencies"],
  openmatb: ["Aplicación OpenMATB", "OpenMATB application"],
  questionnaires_es: ["Cuestionarios en español", "Spanish questionnaires"],
  graphical_display: ["Pantalla gráfica", "Graphical display"],
};

function stepState(complete: boolean, current: boolean): GuidedStepState {
  return complete ? "complete" : current ? "current" : "upcoming";
}

export default function OpenMatbSetupPage() {
  const router = useRouter();
  const { copy, locale } = useAppLocale();
  const purpose = useExecutionPurpose();
  const copyRef = useRef(copy);
  copyRef.current = copy;
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [visits, setVisits] = useState<Visit[]>([]);
  const [presets, setPresets] = useState<OpenMatbPresetSet[]>([]);
  const [instructions, setInstructions] = useState<OpenMatbInstructionProtocol[]>([]);
  const [visualProfiles, setVisualProfiles] = useState<OpenMatbVisualProfile[]>([]);
  const [readiness, setReadiness] = useState<OpenMatbReadiness | null>(null);
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [presetKey, setPresetKey] = useState("");
  const [instructionKey, setInstructionKey] = useState("");
  const [visualProfileKey, setVisualProfileKey] = useState("");
  const [displayIndex, setDisplayIndex] = useState(1);
  const [acknowledged, setAcknowledged] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    void Promise.all([
      listParticipants(),
      listOpenMatbPresets(),
      listOpenMatbInstructions(),
      listOpenMatbVisualProfiles(),
      getOpenMatbReadiness(),
    ])
      .then(([people, presetRows, instructionRows, visualProfileRows, ready]) => {
        if (!active) return;
        const publishedPresets = presetRows.filter((row) => row.status === "published");
        const publishedInstructions = instructionRows.filter((row) => row.status === "published");
        const publishedVisualProfiles = visualProfileRows.filter((row) => row.status === "published");
        setParticipants(people);
        setPresets(publishedPresets);
        setInstructions(publishedInstructions);
        setVisualProfiles(publishedVisualProfiles);
        setReadiness(ready);
        if (publishedPresets[0]) setPresetKey(`${publishedPresets[0].preset_id}@${publishedPresets[0].version}`);
        const preferredVisualProfile = publishedVisualProfiles.find(
          (row) => row.profile_id === "matb-fac-modern" && row.version === "1.0.0",
        ) ?? publishedVisualProfiles[0];
        if (preferredVisualProfile) {
          setVisualProfileKey(`${preferredVisualProfile.profile_id}@${preferredVisualProfile.version}`);
        }
        setDisplayIndex(ready.display_index_default);
      })
      .catch((reason: unknown) => {
        if (active) setError(openMatbErrorMessage(reason, copyRef.current, ["No se pudo preparar OpenMATB.", "OpenMATB setup could not be loaded."]));
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (!participantId) {
      setVisits([]);
      setVisitOrdinal("");
      return () => { active = false; };
    }
    setVisitOrdinal("");
    void listVisits(participantId)
      .then((rows) => {
        if (!active) return;
        setVisits(rows);
        setVisitOrdinal(rows[0] ? String(rows[0].visit_ordinal) : "");
      })
      .catch((reason: unknown) => {
        if (active) setError(openMatbErrorMessage(reason, copyRef.current, ["No se pudieron cargar las visitas.", "Visits could not be loaded."]));
      });
    return () => { active = false; };
  }, [participantId]);

  useEffect(() => {
    const matching = instructions.filter((row) => row.locale === locale);
    setInstructionKey((current) => matching.some((row) => `${row.protocol_id}@${row.version}` === current)
      ? current : matching[0] ? `${matching[0].protocol_id}@${matching[0].version}` : "");
  }, [instructions, locale]);

  const preset = useMemo(
    () => presets.find((row) => `${row.preset_id}@${row.version}` === presetKey),
    [presetKey, presets],
  );
  const protocol = useMemo(
    () => instructions.find((row) => `${row.protocol_id}@${row.version}` === instructionKey),
    [instructionKey, instructions],
  );
  const visualProfile = useMemo(
    () => visualProfiles.find((row) => `${row.profile_id}@${row.version}` === visualProfileKey),
    [visualProfileKey, visualProfiles],
  );
  const participantIsValid = !participantId || isParticipantId(participantId);
  const stationReady = Boolean(readiness?.ready);
  const identityReady = Boolean(participantId && participantIsValid && visitOrdinal);
  const configurationReady = Boolean(
    identityReady && preset && protocol && visualProfile && Number.isInteger(displayIndex),
  );
  const canPrepare = Boolean(stationReady && configurationReady && acknowledged && !busy && !loading);

  async function prepare() {
    if (!canPrepare || !preset || !protocol || !visualProfile) return;
    const participantWindow = window.open("about:blank", "matb-fac-participant");
    setBusy(true);
    setError(null);
    try {
      const ready = await getOpenMatbReadiness();
      setReadiness(ready);
      if (!ready.ready) throw new Error(copy("Revise los requisitos de la estación e intente de nuevo.", "Check station requirements and try again."));
      const prepared = await createOpenMatbSession({
        execution_purpose: purpose,
        participant_id: participantId,
        visit_ordinal: Number(visitOrdinal),
        preset_id: preset.preset_id,
        preset_version: preset.version,
        instruction_protocol_id: protocol.protocol_id,
        instruction_version: protocol.version,
        visual_profile_id: visualProfile.profile_id,
        visual_profile_version: visualProfile.version,
        display_index: displayIndex,
      });
      storeOpenMatbCredentials(prepared);
      const participantUrl = `/openmatb/participant?session=${encodeURIComponent(prepared.session.id)}#token=${encodeURIComponent(prepared.participant_token)}`;
      if (participantWindow) participantWindow.location.href = participantUrl;
      router.push(`/openmatb/session?session=${encodeURIComponent(prepared.session.id)}`);
    } catch (reason: unknown) {
      participantWindow?.close();
      setError(openMatbErrorMessage(reason, copyRef.current, ["No se pudo crear la sesión.", "The session could not be created."]));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <ExperimentGuide id="openmatb" />
      <PageHeader
        kicker={copy("Control nativo", "Native control")}
        title={copy("Suite OpenMATB", "OpenMATB suite")}
        description={copy(
          "Primero se crean las instrucciones del participante; la ventana nativa se abre en el paso siguiente.",
          "Participant instructions are created first; the native window opens in the next step.",
        )}
        actions={<div className="flex flex-wrap gap-2"><Button asChild variant="outline"><Link href="/openmatb/appearance">{copy("Apariencia", "Appearance")}</Link></Button><Button asChild variant="outline"><Link href="/openmatb/settings">{copy("Configuración avanzada", "Advanced settings")}</Link></Button></div>}
        stats={[
          { label: copy("Sistema", "System"), value: readiness?.platform ?? "—" },
          { label: copy("Bloques", "Blocks"), value: purpose === "practice" ? "01" : "04" },
          { label: copy("Estación", "Station"), value: stationReady ? copy("Lista", "Ready") : copy("Revisar", "Check") },
        ]}
      />

      <GuidedSteps
        label={copy("Pasos para abrir OpenMATB", "Steps to open OpenMATB")}
        steps={[
          { title: copy("Estación", "Station"), description: copy("Compruebe Python, OpenMATB y la pantalla.", "Check Python, OpenMATB, and the display."), state: stepState(stationReady, true) },
          { title: copy("Participante", "Participant"), description: copy("Seleccione el código y la visita.", "Select the code and visit."), state: stepState(identityReady, stationReady) },
          { title: copy("Configuración", "Configuration"), description: copy("Confirme preset, instrucciones y pantalla.", "Confirm preset, instructions, and display."), state: stepState(configurationReady && acknowledged, identityReady) },
          { title: copy("Instrucciones", "Instructions"), description: copy("Cree la sesión y abra la pantalla del participante.", "Create the session and open the participant display."), state: stepState(false, canPrepare) },
        ]}
      />

      {error && <p role="alert" className="border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{error}</p>}
      {readiness && !readiness.ready && (
        <div role="alert" className="flex gap-3 border border-warning/40 bg-warning/5 p-4 text-sm text-warning">
          <AlertTriangle className="h-5 w-5 shrink-0" aria-hidden="true" />
          <div>
            <strong>{copy("La estación aún no está lista.", "The station is not ready yet.")}</strong>
            <p className="mt-1 text-xs">{copy("Cierre la consola y vuelva a abrir “01 - Abrir consola UAS” para reparar dependencias o compilación.", "Close the console and reopen “01 - Open UAS console” to repair dependencies or the build.")}</p>
          </div>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_23rem]">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Paso 2 · Preparar visita", "Step 2 · Prepare visit")}</CardTitle>
            <CardDescription>{copy("Complete los campos de arriba hacia abajo.", "Complete the fields from top to bottom.")}</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="om-participant">{copy("1. Participante", "1. Participant")}</Label>
              <select id="om-participant" className="native-select w-full" value={participantId} onChange={(event) => setParticipantId(event.target.value)} disabled={loading || busy}>
                <option value="">{loading ? copy("Cargando…", "Loading…") : "—"}</option>
                {participants.map((row) => <option key={row.id} value={row.id}>{row.id}</option>)}
              </select>
              {!loading && participants.length === 0 && <p className="text-xs text-muted-foreground"><Link href="/participants" className="text-info underline underline-offset-2">{copy("Cree primero un participante P01.", "Create a P01 participant first.")}</Link></p>}
              {participantId && !participantIsValid && <p role="alert" className="text-xs text-danger">{copy("Este registro antiguo no es compatible. Cree un código como P01.", "This older record is not compatible. Create a code such as P01.")}</p>}
            </div>
            <div className="space-y-2">
              <Label htmlFor="om-visit">{copy("2. Visita", "2. Visit")}</Label>
              <select id="om-visit" className="native-select w-full" value={visitOrdinal} onChange={(event) => setVisitOrdinal(event.target.value)} disabled={!participantId || busy}>
                <option value="">—</option>
                {visits.map((row) => <option key={row.id} value={row.visit_ordinal}>{copy("Día", "Day")} {row.scheduled_day} · V{row.visit_ordinal}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="om-preset">{copy("3. Preset publicado", "3. Published preset")}</Label>
              <select id="om-preset" className="native-select w-full" value={presetKey} onChange={(event) => setPresetKey(event.target.value)} disabled={busy}>
                {presets.map((row) => <option key={`${row.preset_id}@${row.version}`} value={`${row.preset_id}@${row.version}`}>{row.label_es} · v{row.version}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="om-protocol">{copy("4. Instrucciones", "4. Instructions")}</Label>
              <select id="om-protocol" className="native-select w-full" value={instructionKey} onChange={(event) => setInstructionKey(event.target.value)} disabled={busy}>
                {instructions.filter((row) => row.locale === locale).map((row) => <option key={`${row.protocol_id}@${row.version}`} value={`${row.protocol_id}@${row.version}`}>{row.title} · v{row.version}</option>)}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="om-theme">{copy("5. Presentación visual", "5. Visual presentation")}</Label>
              <select id="om-theme" className="native-select w-full" value={visualProfileKey} onChange={(event) => setVisualProfileKey(event.target.value)} disabled={busy}>
                {visualProfiles.map((row) => <option key={`${row.profile_id}@${row.version}`} value={`${row.profile_id}@${row.version}`}>{row.label} · v{row.version}</option>)}
              </select>
              <p className="text-xs text-muted-foreground">{copy("El perfil publicado y su SHA-256 quedan congelados con la sesión. No combine condiciones sin validar equivalencia.", "The published profile and its SHA-256 are frozen with the session. Do not pool conditions without validating equivalence.")}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="om-display">{copy("6. Pantalla donde se abrirá OpenMATB", "6. Display where OpenMATB will open")}</Label>
              <Input id="om-display" type="number" min={0} max={15} value={displayIndex} onChange={(event) => setDisplayIndex(Number(event.target.value))} disabled={busy} />
              <p className="text-xs text-muted-foreground">{copy("Use 1 para la segunda pantalla; use 0 si sólo hay una.", "Use 1 for the second display; use 0 for a single display.")}</p>
            </div>
            <label className="flex items-start gap-3 border border-white/10 bg-white/[0.02] p-3 text-sm text-muted-foreground sm:col-span-2">
              <input type="checkbox" checked={acknowledged} onChange={(event) => setAcknowledged(event.target.checked)} disabled={busy} className="mt-1" />
              <span>{copy("Confirmo que verificaré físicamente audio, mouse, teclado o joystick antes de recolectar datos.", "I confirm that I will physically verify audio, mouse, keyboard, or joystick before collecting data.")}</span>
            </label>
            <Button className="sm:col-span-2" size="lg" disabled={!canPrepare} onClick={() => void prepare()}>
              {busy ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="mr-2 h-4 w-4" aria-hidden="true" />}
              {busy ? copy("Creando sesión…", "Creating session…") : copy("Crear sesión y abrir instrucciones", "Create session and open instructions")}
            </Button>
            <p className="text-center text-xs text-muted-foreground sm:col-span-2">{copy("Este botón todavía no inicia OpenMATB. Después de confirmar las instrucciones, el panel mostrará “Abrir OpenMATB”.", "This button does not start OpenMATB yet. After instructions are confirmed, the console will show “Open OpenMATB”.")}</p>
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Paso 1 · Comprobaciones", "Step 1 · Checks")}</CardTitle></CardHeader>
          <CardContent className="space-y-3">
            {readiness ? Object.entries(readiness.checks).map(([name, ok]) => {
              const label = CHECK_LABELS[name];
              return <div key={name} className="flex items-center justify-between border-b border-white/10 pb-2 text-sm"><span>{label ? copy(label[0], label[1]) : name.replaceAll("_", " ")}</span><CheckCircle2 className={`h-4 w-4 ${ok ? "text-success" : "text-danger"}`} aria-label={ok ? copy("Correcto", "Ready") : copy("Falta", "Missing")} /></div>;
            }) : <p className="text-sm text-muted-foreground">{copy("Consultando…", "Checking…")}</p>}
            {readiness?.warnings.map((warning) => <p key={warning} className="text-xs text-warning">{warning}</p>)}
            <div className="mt-5 flex gap-3 border border-info/30 bg-info/5 p-3 text-xs text-muted-foreground">
              <MonitorUp className="h-4 w-4 shrink-0 text-info" aria-hidden="true" />
              <span>{copy("El panel del investigador queda en esta pantalla. La aplicación nativa usará el índice seleccionado.", "The researcher console stays on this display. The native application uses the selected index.")}</span>
            </div>
          </CardContent>
        </Card>
      </div>

      {preset && (
        <Card>
          <CardHeader><CardTitle className="font-display text-xl uppercase tracking-wide">{copy("Parámetros de carga", "Workload parameters")}</CardTitle><CardDescription>{copy("Preset de ingeniería versionado; no equivale a calibración humana independiente.", "Versioned engineering preset; it is not independent human calibration.")}</CardDescription></CardHeader>
          <CardContent className="overflow-x-auto"><table className="w-full min-w-[760px] text-left text-sm"><thead className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground"><tr><th className="pb-3">{copy("Perfil", "Profile")}</th><th>{copy("Duración", "Duration")}</th><th>{copy("Dificultad", "Difficulty")}</th><th>TRACK</th><th>RESMAN</th><th>ISA</th></tr></thead><tbody>{Object.entries(preset.profiles).map(([name, value]) => <tr key={name} className="border-t border-white/10"><td className="py-3 font-semibold">{name}</td><td>{value.duration_seconds}s</td><td>{value.difficulty.toFixed(2)}</td><td>{value.track_target_proportion.toFixed(2)}</td><td>{value.resman_loss_per_min} L/min</td><td>{value.isa_probe_interval_sec}s</td></tr>)}</tbody></table></CardContent>
        </Card>
      )}
    </div>
  );
}
