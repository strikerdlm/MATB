"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Play, UserPlus, RotateCcw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ActiveSessionNotice } from "@/components/openmatb/ActiveSessionNotice";
import { astraCall, type AstraRoster, type AstraProtocol } from "@/lib/astra";
import { createOpenMatbSession, getOpenMatbDisplays, getOpenMatbReadiness, storeOpenMatbCredentials } from "@/lib/openmatb/api";
import { saveParticipantWindowState } from "@/lib/openmatb/participant-window";
import { useAppLocale } from "@/lib/i18n";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import type { OpenMatbDisplay } from "@/types/openmatb";

export default function AstraPage() {
  const router = useRouter();
  const { copy } = useAppLocale();
  const [roster, setRoster] = useState<AstraRoster | null>(null);
  const [protocol, setProtocol] = useState<AstraProtocol | null>(null);
  const [mission, setMission] = useState<"ASTRA-1" | "ASTRA-2">("ASTRA-1");
  const [selected, setSelected] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState(1);
  const [displays, setDisplays] = useState<OpenMatbDisplay[]>([]);
  const [display, setDisplay] = useState(0);
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [actor, setActor] = useState("");
  const [includePolar, setIncludePolar] = useState(true);
  const [baselineMinutes, setBaselineMinutes] = useState(5);
  const [callsign, setCallsign] = useState("");
  const [revision, setRevision] = useState(0);
  const [checked, setChecked] = useState(false);
  const [activeSession, setActiveSession] = useState(true);
  const refresh = useCallback(async () => {
    const [people, plan, screens, station] = await Promise.all([
      astraCall<AstraRoster>("/astra/roster?include_archived=true"), astraCall<AstraProtocol>("/astra/protocol"),
      getOpenMatbDisplays(), getOpenMatbReadiness(),
    ]);
    setRoster(people); setProtocol(plan); setDisplays(screens); setReady(station.ready);
    setDisplay(value => screens.some(screen => screen.index === value) ? value : screens[0]?.index ?? 0);
  }, []);
  useEffect(() => { void refresh().catch(reason => setError(openMatbErrorMessage(reason, copy))); }, [refresh, copy]);
  const people = roster?.participants.filter(p => p.mission === mission && !p.archived) ?? [];
  const person = people.find(p => p.id === selected);
  const visit = person?.visits.find(v => v.visit_ordinal === visitOrdinal);
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await action(); await refresh(); }
    catch (reason) { setError(openMatbErrorMessage(reason, copy)); }
    finally { setBusy(false); setRevision(value => value + 1); }
  }
  async function practice() {
    if (!person || !visit || !ready || !checked || busy || activeSession) return;
    const participantWindow = displays.length === 1 ? null : window.open("about:blank", "matb-fac-participant");
    await run(async () => {
      try {
        sessionStorage.setItem("openmatb.storage-check", "ok");
        sessionStorage.removeItem("openmatb.storage-check");
        const prepared = await createOpenMatbSession({ participant_id: person.id, visit_ordinal: visit.visit_ordinal,
          execution_purpose: "practice", preset_id: "astra-matb-field", preset_version: "1.0.0",
          instruction_protocol_id: "matb-fac-es-419", instruction_version: "1.0.0",
          visual_profile_id: "matb-daylight-avionics", visual_profile_version: "1.0.0", display_index: display });
        storeOpenMatbCredentials(prepared);
        if (displays.length === 1) {
          router.push(`/openmatb/participant?session=${encodeURIComponent(prepared.session.id)}`);
          return;
        }
        const windowState = participantWindow ? "opened" : "blocked";
        saveParticipantWindowState(prepared.session.id, windowState);
        if (participantWindow) participantWindow.location.href = `/openmatb/participant?session=${encodeURIComponent(prepared.session.id)}#token=${encodeURIComponent(prepared.participant_token)}`;
        router.push(`/openmatb/session?session=${encodeURIComponent(prepared.session.id)}&participant_window=${windowState}`);
      } catch (reason) { participantWindow?.close(); throw reason; }
    });
  }
  return <div className="mx-auto max-w-6xl space-y-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><p className="text-sm text-muted-foreground">ASTRA · MATB-FAC</p><h1 className="mt-1 text-3xl font-semibold">{copy("Aplicar MATB", "Run MATB")}</h1><p className="mt-2 text-muted-foreground">{copy("Seleccione misión, tripulante y visita.", "Select mission, crew member and visit.")}</p></div>
      <Button variant="outline" disabled={busy} onClick={() => void run(refresh)}><RotateCcw className="mr-2 h-4 w-4" />{copy("Actualizar", "Refresh")}</Button>
    </header>
    <ActiveSessionNotice revision={revision} onActiveChange={setActiveSession} />
    {error && <p role="alert" className="rounded border border-danger/40 bg-danger/10 p-4 text-danger">{error}</p>}
    {!roster && !error && <p role="status">{copy("Cargando tripulantes…", "Loading crew…")}</p>}
    {roster && !roster.participants.length && <Button disabled={busy} onClick={() => void run(async () => { await astraCall("/astra/initialize", {}); })}>{copy("Cargar ASTRA-1 (5) y ASTRA-2 (7)", "Load ASTRA-1 (5) and ASTRA-2 (7)")}</Button>}
    <div className="flex gap-3" aria-label={copy("Misión", "Mission")}>{(["ASTRA-1", "ASTRA-2"] as const).map(group => <Button key={group} variant={mission === group ? "default" : "outline"} aria-pressed={mission === group} onClick={() => { setMission(group); setSelected(""); setChecked(false); }}>{group} <span className="ml-2 opacity-70">{roster?.participants.filter(p => p.mission === group && !p.archived).length ?? 0}</span></Button>)}</div>
    <div className="grid gap-6 lg:grid-cols-[minmax(240px,1fr)_2fr]">
      <section aria-label={copy("Tripulantes", "Crew")} className="space-y-2">{people.map(p => <button key={p.id} disabled={busy} aria-pressed={p.id === selected} onClick={() => { setSelected(p.id); setChecked(false); }} className={`flex w-full items-center justify-between gap-3 rounded-lg border p-4 text-left ${p.id === selected ? "border-info bg-info/10" : "border-white/15 bg-card hover:border-white/40"}`}>
        <span><span className="block text-lg font-semibold">{p.callsign}</span><span className="text-xs text-muted-foreground">{p.id} · {p.time_slot ?? copy("Turno por asignar", "Time pending")}</span></span><span className="text-sm text-muted-foreground">{p.visits.filter(v => v.status === "complete").length}/8</span>
      </button>)}</section>
      <section className="rounded-xl border border-white/15 bg-card p-5 sm:p-6">
        {!person ? <p className="py-12 text-center text-muted-foreground">{copy("Seleccione un tripulante para preparar su prueba.", "Select a crew member to prepare their test.")}</p> : <div className="space-y-5">
          <div><h2 className="text-2xl font-semibold">{person.callsign}</h2><p className="mt-1 text-sm text-muted-foreground">{person.mission} · {person.id} · {copy("Puesto", "Station")} {person.station}{person.unit ? ` · ${person.unit}` : ""}</p></div>
          <label className="block text-sm font-medium">{copy("Visita", "Visit")}<select aria-label={copy("Visita", "Visit")} className="native-select mt-2 w-full" value={visitOrdinal} disabled={busy} onChange={event => { setVisitOrdinal(Number(event.target.value)); setChecked(false); }}>{person.visits.map(v => <option key={v.id} value={v.visit_ordinal}>{v.code} · {v.visit_ordinal === 1 ? "PRE" : v.visit_ordinal === 8 ? "POST / D+1" : `DM${v.scheduled_day}`} · {v.planned_date} · {v.completed_blocks}/3</option>)}</select></label>
          <p className="text-sm">{copy("90 min reservados · 3 bloques de 15 min", "90 min reserved · 3 blocks of 15 min")}<br /><span className="text-muted-foreground">{person.block_order.join(" → ")} · {person.time_slot ?? copy("Asigne un turno", "Assign a time")}</span></p>
          <label className="block text-sm font-medium">{copy("Pantalla de la prueba", "Test display")}<select aria-label={copy("Pantalla de la prueba", "Test display")} className="native-select mt-2 w-full" value={display} onChange={event => setDisplay(Number(event.target.value))}>{displays.map(screen => <option key={screen.index} value={screen.index}>{screen.label} · {screen.width} × {screen.height}</option>)}</select></label>
          {!ready && <p className="text-warning">{copy("La estación necesita revisión.", "The station needs attention.")} <Link href="/openmatb/setup?purpose=practice" className="underline">{copy("Ver requisitos", "View requirements")}</Link></p>}
          <label className="flex gap-3 rounded border border-white/15 p-3 text-sm"><input type="checkbox" checked={checked} disabled={busy} onChange={event => setChecked(event.target.checked)} /><span>{copy("Identidad, audio, controles y pantalla comprobados.", "Identity, audio, controls and display checked.")}</span></label>
          <div className="flex flex-wrap gap-3">
            <Button size="lg" disabled={busy || activeSession || !checked || !ready || !protocol?.active || !visit} onClick={() => void run(async () => { const next = await astraCall<{ url: string }>("/astra/visits/prepare", { participant_id: person.id, visit_ordinal: visitOrdinal }); router.push(`${next.url}&display=${display}&return=astra`); })}><Play className="mr-2 h-4 w-4" />{copy("Aplicar visita", "Run visit")} {visit?.code}</Button>
            {visitOrdinal === 1 && <Button variant="outline" disabled={busy || activeSession || !checked || !ready} onClick={() => void practice()}>{copy("Familiarización · 5 min", "Familiarization · 5 min")}</Button>}
          </div>
          {!protocol?.active && <p className="text-sm text-warning">{copy("Active el protocolo debajo una sola vez para habilitar las visitas de estudio. La familiarización ya está disponible.", "Activate the protocol below once to enable study visits. Familiarization is already available.")}</p>}
          <details className="text-sm"><summary className="cursor-pointer text-muted-foreground">{copy("Recordatorio del procedimiento", "Procedure reminder")}</summary><p className="mt-3">{copy("Conserve el basal real y su orden. Registre por separado 5 min de reposo pre-tarea y KSS antes de cada bloque. V0 incluye familiarización; V1–V7, recordatorio. Las escalas se completan tras cada bloque y las pausas son de 3 min. Fechas y turnos son planificados; no acreditan adquisición fisiológica.", "Preserve the actual baseline and block order. Record 5 min of pre-task rest separately and KSS before each block. V0 includes familiarization; V1–V7 use a reminder. Complete ratings after each block, with 3 min breaks. Dates and times are planned; they do not establish physiological acquisition.")}</p></details>
          <p className="text-sm">{copy("Polar H10: un sensor por estación. Basal PRE abreviado: ≥5 min de adaptación y 5 min de RR, más preparación y revisión. Los 5 min previos a MATB se guardan como referencia de la tarea. La duración elegida queda en el protocolo.", "Polar H10: one sensor per station. Abbreviated PRE baseline: ≥5 min adaptation and 5 min RR, plus preparation and review. The 5 min before MATB are saved as the task reference. The selected duration is retained in the protocol.")}</p>
          {protocol?.active && !protocol.includes_polar && <p className="text-sm">{copy("El protocolo activo no incluye Polar. Para capturarlo como estudio, cree una revisión del protocolo con fisiología antes de asignar nuevas visitas.", "The active protocol does not include Polar. To record it as study data, create a protocol revision with physiology before assigning new visits.")}</p>}
        </div>}
      </section>
    </div>
    {!protocol?.active && roster && <section className="rounded-lg border border-white/15 p-5 space-y-3">
      <h2 className="text-lg font-semibold">{copy("Activar protocolo de estudio · una vez", "Activate study protocol · once")}</h2>
      <p className="text-sm text-muted-foreground">{copy("V0–V7, tres bloques de 900 s, orden fijo por participante, NASA-TLX/Bedford y pausas de 180 s. No cambia las sesiones ya guardadas.", "V0–V7, three 900 s blocks, a fixed participant order, NASA-TLX/Bedford and 180 s breaks. Existing sessions remain recorded.")}</p>
      <details className="text-sm"><summary className="cursor-pointer">{copy("Revisar políticas de registro", "Review recording policies")}</summary><p className="mt-2">{copy("Se conservan interrupciones y originales; hasta 3 intentos por fallas técnicas, con selección explícita. Resúmenes individuales de vigilancia, seguimiento y carga percibida; sin imputación, HCF ni agrupación automática entre configuraciones. La preparación confirma reconocimiento de controles; no se aplica un umbral de rendimiento inventado. Consentimiento, reposo y KSS se documentan en la hoja de campo.", "Retain interruptions and originals; up to 3 attempts for technical failures, selected explicitly. Individual monitoring, tracking and workload summaries; no imputation, HCF or automatic pooling across configurations. Preparation confirms control recognition without an invented performance threshold. Document consent, rest and KSS in the field sheet.")}</p></details>
      <label className="block text-sm">{copy("Investigador responsable", "Responsible researcher")}<Input className=" mt-1 block w-full max-w-md" value={actor} onChange={event => setActor(event.target.value)} /></label>
      <label className="flex gap-2 text-sm"><input type="checkbox" checked={includePolar} onChange={event => setIncludePolar(event.target.checked)} />{copy("Incluir Polar H10: basal PRE en V0 y captura vinculada a cada bloque MATB", "Include Polar H10: PRE baseline in V0 and recording linked to each MATB block")}</label>
      {includePolar && <label className="block text-sm">{copy('Duración del registro basal PRE', 'PRE baseline recording duration')}<select className="native-select ml-2" value={baselineMinutes} onChange={event => setBaselineMinutes(Number(event.target.value))}><option value={5}>{copy('5 min · modalidad abreviada', '5 min · abbreviated protocol')}</option><option value={10}>{copy('10 min · manual ASTRA, dos segmentos de 5 min', '10 min · ASTRA manual, two 5 min segments')}</option></select><span className="mt-2 block text-muted-foreground">{copy('Ambas opciones requieren ≥5 min de adaptación sentado. La opción abreviada omite el segundo segmento de respaldo del manual v2.8.', 'Both options require ≥5 min of seated adaptation. The abbreviated option omits the second backup segment in manual v2.8.')}</span></label>}
      <Button disabled={busy || actor.trim().length < 3 || !!protocol?.version_id} onClick={() => void run(async () => { await astraCall("/astra/protocol/activate", { actor: actor.trim(), include_polar: includePolar, baseline_minutes: baselineMinutes }); })}>{busy ? copy("Preparando…", "Preparing…") : copy("Activar este protocolo", "Activate this protocol")}</Button>
      {protocol?.version_id && <p className="text-warning">{copy("Ya hay otro estudio activo en esta base. Revíselo en la configuración del estudio.", "Another study is active in this database. Review its study settings.")}</p>}
    </section>}
    <details className="rounded-lg border border-white/15 p-5"><summary className="cursor-pointer font-semibold">{copy("Gestionar participantes", "Manage participants")}</summary>
      <form className="mt-4 flex flex-wrap items-end gap-3" onSubmit={event => { event.preventDefault(); void run(async () => { await astraCall("/astra/participants", { callsign: callsign.trim(), mission }); setCallsign(""); }); }}>
        <label className="text-sm">{copy("Nuevo indicativo", "New callsign")}<Input className=" mt-1 block" value={callsign} onChange={event => setCallsign(event.target.value)} maxLength={60} required /></label>
        <Button disabled={busy || !callsign.trim()}><UserPlus className="mr-2 h-4 w-4" />{copy("Agregar a", "Add to")} {mission}</Button>
      </form>
      <p className="mt-4 text-sm text-muted-foreground">{copy("Retirar oculta al participante de la aplicación de pruebas y conserva sus resultados. Puede restaurarlo aquí.", "Removing hides a participant from test launch and retains their results. Restore them here.")}</p>
      <ul className="mt-3 divide-y divide-white/10">{roster?.participants.filter(p => p.mission === mission).map(p => <li key={p.id} className="flex items-center justify-between gap-3 py-3"><span>{p.callsign} <span className="text-sm text-muted-foreground">· {p.id}{p.archived ? ` · ${copy("Retirado", "Removed")}` : ""}</span></span><Button variant="ghost" disabled={busy} aria-label={`${p.archived ? copy("Restaurar", "Restore") : copy("Retirar", "Remove")} ${p.callsign}`} onClick={() => void run(async () => { await astraCall(`/participants/${encodeURIComponent(p.id)}${p.archived ? "/restore" : ""}`, p.archived ? {} : undefined, p.archived ? "POST" : "DELETE"); if (p.id === selected) setSelected(""); })}>{p.archived ? <RotateCcw className="h-4 w-4" /> : <Trash2 className="h-4 w-4" />}</Button></li>)}</ul>
    </details>
  </div>;
}
