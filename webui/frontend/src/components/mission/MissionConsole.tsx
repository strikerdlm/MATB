"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { MissionPresentation, preflightSnapshot } from "./presentation/MissionPresentation";
import { MissionDetailTabs } from "./MissionDetailTabs";
import { MissionNotices, connectionNotice, type MissionNotice } from "./MissionNotices";
import { consoleProfileStatus } from "@/lib/simulation/console-profile";
import { AlertQueue } from "@/components/mission/AlertQueue";
import { ContactQueue } from "@/components/mission/ContactQueue";
import { CommandBar } from "@/components/mission/CommandBar";
import { SwarmPanel } from "./SwarmPanel";
import { FleetPanel } from "@/components/mission/FleetPanel";
import { MissionTopBar } from "@/components/mission/MissionTopBar";
import { MissionInstructionPanel } from "@/components/mission/MissionInstructionPanel";
import { MissionJourneyRail } from "@/components/mission/MissionJourneyRail";
import { ProbeOverlay } from "@/components/mission/probes/ProbeOverlay";
import type { PostBlockScaleValues } from "@/components/mission/probes/PostBlockScales";
import { t } from "@/lib/simulation/i18n";
import { getSimulationSession, getSimulationState, transitionSession } from "@/lib/simulation/api";
import { flushPresentation } from "@/lib/simulation/presentation/queue";
import { getParticipantJourney } from "@/lib/api";
import { useSimulationStore } from "@/lib/simulation/store";
import { reconcileProbeRefresh, sameProbe } from "@/lib/simulation/probe-refresh";
import type { AircraftSnapshot, CommandKind, ContactSnapshot, JsonValue, Locale, ProtocolCommandKind, SessionView, WorldSnapshot } from "@/types/simulation";
import type { ParticipantJourneyStep } from "@/types";

export interface MissionConsoleProps {
  initialSession: SessionView;
  initialSnapshot?: WorldSnapshot | null;
  readOnly?: boolean;
  autoStart?: boolean;
  onFinished?: (session: SessionView) => void;
}

function controllerLease(sessionId: string): string | null {
  if (typeof window === "undefined") return null;
  try { return window.sessionStorage.getItem(`matb.simulation.${sessionId}.lease`); } catch { return null; }
}

function commandId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") return crypto.randomUUID();
  return `cmd-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function MissionConsole({ initialSession, initialSnapshot = null, readOnly = false, autoStart = false, onFinished }: MissionConsoleProps) {
  const initialized = useRef(false);
  const autoStarted = useRef(false);
  const cleanupTimer = useRef<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<MissionNotice | null>(null);
  const [waypointMode, setWaypointMode] = useState(false);
  const [journeySteps, setJourneySteps] = useState<ParticipantJourneyStep[] | null>(null);
  const session = useSimulationStore((state) => state.session);
  const snapshot = useSimulationStore((state) => state.snapshot);
  const previousSnapshot = useSimulationStore((state) => state.previousSnapshot);
  const connection = useSimulationStore((state) => state.connection);
  const locale = useSimulationStore((state) => state.locale) as Locale;
  const selectedAircraftId = useSimulationStore((state) => state.selectedAircraftId);
  const selectedContactId = useSimulationStore((state) => state.selectedContactId);
  const pendingCommandIds = useSimulationStore((state) => state.pendingCommandIds);
  const transportError = useSimulationStore((state) => state.transportError);
  const activeProbe = useSimulationStore((state) => state.activeProbe);
  const concealOperationalState = useSimulationStore((state) => state.concealOperationalState);
  const initialize = useSimulationStore((state) => state.initialize);
  const connect = useSimulationStore((state) => state.connect);
  const disconnect = useSimulationStore((state) => state.disconnect);
  const reset = useSimulationStore((state) => state.reset);
  const selectAircraft = useSimulationStore((state) => state.selectAircraft);
  const selectContact = useSimulationStore((state) => state.selectContact);
  const submitCommand = useSimulationStore((state) => state.submitCommand);
  const currentSession = session ?? initialSession;
  const currentSnapshot = snapshot ?? initialSnapshot;
  const profileStatus = consoleProfileStatus(currentSession.console_profile);
  const modern = profileStatus === "supported";
  const transportNotice = connectionNotice(connection, transportError, locale);
  const notices = [transportNotice, notice].filter((item): item is MissionNotice => item !== null);
  const lease = controllerLease(currentSession.id);
  const canControl = !readOnly && Boolean(lease);
  const nextStep = currentSession.lifecycle === "PREPARED"
    ? (locale === "es-CO" ? `Paso siguiente: pulse INICIAR para comenzar ${currentSession.next_block_id ?? "PRÁCTICA"}.` : `Next step: press START to begin ${currentSession.next_block_id ?? "PRACTICE"}.`)
    : currentSession.lifecycle === "RUNNING"
      ? (locale === "es-CO" ? "Paso actual: complete el bloque y responda los instrumentos cuando aparezcan." : "Current step: complete the block and answer instruments when they appear.")
      : currentSession.lifecycle === "PAUSED" && currentSession.protocol_phase === "READY_FOR_BLOCK"
        ? (locale === "es-CO" ? `Paso siguiente: pulse INICIAR para continuar con ${currentSession.next_block_id ?? "el siguiente bloque"}.` : `Next step: press START to continue with ${currentSession.next_block_id ?? "the next block"}.`)
        : currentSession.lifecycle === "PAUSED"
          ? (locale === "es-CO" ? "Paso actual: complete el instrumento mostrado o reanude cuando esté listo." : "Current step: complete the displayed instrument or resume when ready.")
          : (locale === "es-CO" ? "Siga la acción resaltada en la barra superior." : "Follow the highlighted action in the top bar.");


  useEffect(() => {
    if (!currentSession.participant_id || !currentSession.visit_ordinal) return;
    let active = true;
    void getParticipantJourney(currentSession.participant_id, currentSession.visit_ordinal)
      .then((journey) => { if (active) setJourneySteps(journey.steps); })
      .catch(() => { if (active) setJourneySteps(null); });
    return () => { active = false; };
  }, [currentSession.active_block_id, currentSession.lifecycle, currentSession.participant_id, currentSession.protocol_phase, currentSession.visit_ordinal]);

  useEffect(() => {
    if (cleanupTimer.current !== null) {
      window.clearTimeout(cleanupTimer.current);
      cleanupTimer.current = null;
    }
    if (!initialized.current) {
      initialized.current = true;
      initialize({ session: initialSession, snapshot: initialSnapshot ?? undefined, locale: initialSession.locale });
      void connect({ role: lease ? "controller" : "observer", lease });
    }
    return () => {
      // React StrictMode performs an immediate setup → cleanup → setup probe
      // in development. Defer teardown by one turn so that probe does not
      // create overlapping controller sockets or pause a live session.
      cleanupTimer.current = window.setTimeout(() => {
        cleanupTimer.current = null;
        disconnect();
        reset();
        initialized.current = false;
      }, 0);
    };
  // The session is immutable for the lifetime of a console route.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSession.id]);

  const selectedAircraft = useMemo<AircraftSnapshot | null>(() => selectedAircraftId && currentSnapshot?.aircraft[selectedAircraftId] ? currentSnapshot.aircraft[selectedAircraftId] : null, [currentSnapshot, selectedAircraftId]);
  const selectedContact = useMemo<ContactSnapshot | null>(() => selectedContactId && currentSnapshot?.contacts[selectedContactId] ? currentSnapshot.contacts[selectedContactId] : null, [currentSnapshot, selectedContactId]);
  const alerts = Object.values(currentSnapshot?.alerts ?? {});
  const contacts = Object.values(currentSnapshot?.contacts ?? {});

  async function lifecycle(action: "start" | "pause" | "resume" | "finish", body: Record<string, string> = {}) {
    if (!canControl) return;
    setBusy(true); setNotice(null);
    try {
      if (action === "finish" && body.disposition !== "abort") {
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
        await flushPresentation(currentSession.id);
      }
      const updated = await transitionSession(
        currentSession.id,
        action,
        lease!,
        action === "finish"
          ? { disposition: body.disposition === "abort" ? "abort" : "complete" }
          : body,
      );
      useSimulationStore.setState({ session: updated });
      setNotice({ severity: "success", source: "lifecycle", message: t(locale, `lifecycle.${updated.lifecycle.toLowerCase()}` as never), action: null, resolution: "resolved" });
      if (updated.lifecycle === "FINISHED") onFinished?.(updated);
      if (action === "start") {
        const state = await getSimulationState(currentSession.id);
        useSimulationStore.getState().replaceAuthoritativeState(state);
      }
    } catch (error) {
      setNotice({ severity: "error", source: "lifecycle", message: error instanceof Error ? error.message : t(locale, "error.unknown_error"), action: locale === "es-CO" ? "Revise el estado de la sesión antes de reintentar." : "Check the session state before trying again.", resolution: "pending" });
    } finally { setBusy(false); }
  }

  useEffect(() => {
    if (!autoStart || autoStarted.current || !canControl || connection !== "live" || currentSession.lifecycle !== "PREPARED") return;
    autoStarted.current = true;
    void lifecycle("start", { block_id: currentSession.next_block_id ?? "PRACTICE" });
    // One explicit selector action starts once after controller ownership is established.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [autoStart, canControl, connection, currentSession.lifecycle, currentSession.next_block_id]);

  async function issueCommand(kind: CommandKind | ProtocolCommandKind, payload: Record<string, unknown>): Promise<boolean> {
    if (!currentSnapshot || !canControl) return false;
    setNotice(null);
    try {
      const result = await submitCommand({ command_id: commandId(), expected_state_version: currentSnapshot.state_version, kind, payload: payload as Record<string, JsonValue> });
      if (result.status === "rejected") throw new Error(result.message ?? result.code ?? t(locale, "error.unknown_error"));
      setNotice({ severity: "info", source: "command", message: t(locale, "command.accepted"), action: modern ? (locale === "es-CO" ? "Confirma la recepción; no evalúa el desempeño." : "Acknowledges receipt; it does not evaluate performance.") : null, resolution: "acknowledged" });
      return true;
    } catch (error) { setNotice({ severity: "error", source: "command", message: error instanceof Error ? error.message : t(locale, "error.unknown_error"), action: locale === "es-CO" ? "Revise la selección y el estado antes de reintentar." : "Check the selection and state before trying again.", resolution: "pending" }); return false; }
  }

  function acknowledgeAlert(alertId: string) { void issueCommand("ACKNOWLEDGE_ALERT", { alert_id: alertId }); }

  const probeSubmit = async (kind: ProtocolCommandKind, payload: Record<string, unknown>) => {
    const answeredProbe = activeProbe;
    if (kind === "SUBMIT_POST_BLOCK_SCALE") {
      const values = payload as { nasa_tlx?: Record<string, number>; bedford?: number | null };
      const tlxOk = await issueCommand(kind, { scale_id: "NASA_TLX", answers: values.nasa_tlx ?? {} });
      const bedfordOk = tlxOk && typeof values.bedford === "number"
        ? await issueCommand(kind, { scale_id: "BEDFORD", answers: { value: values.bedford } })
        : false;
      if (!tlxOk || !bedfordOk) return;
    } else if (!await issueCommand(kind, payload)) {
      return;
    }
    // Protocol command results carry an authoritative state version but not
    // the full protocol phase. Refresh the public session view so the next
    // block button appears immediately after the final post-block scale.
    try {
      const refreshed = await getSimulationSession(currentSession.id);
      useSimulationStore.setState((state) => reconcileProbeRefresh(state.activeProbe, answeredProbe, refreshed));
    } catch {
      useSimulationStore.setState((state) => sameProbe(state.activeProbe, answeredProbe)
        ? { activeProbe: null, concealOperationalState: false }
        : {});
    }
  };

  const probeOverlay = activeProbe ? <ProbeOverlay locale={locale} probe={activeProbe} pending={pendingCommandIds.length > 0} onIsa={(rating) => void probeSubmit("SUBMIT_ISA", { probe_id: activeProbe.kind === "ISA" ? activeProbe.probe_id : "", rating })} onSagat={(answer) => void probeSubmit("SUBMIT_SAGAT", { probe_id: activeProbe.kind === "SAGAT" ? activeProbe.probe_id : "", answer })} onPostBlock={(values: PostBlockScaleValues) => void probeSubmit("SUBMIT_POST_BLOCK_SCALE", { ...values })} /> : null;

  return (
    <div className="simulation-console relative flex min-h-screen flex-col bg-background text-foreground" aria-busy={busy} data-console-profile={profileStatus}>
      {!modern && <div className="signal-sweep pointer-events-none absolute inset-x-0 top-0 z-20 h-px bg-white/10" aria-hidden="true" />}
      <MissionTopBar session={currentSession} locale={locale} connection={connection} canControl={canControl} busy={busy} onStart={() => void lifecycle("start", { block_id: currentSession.next_block_id ?? currentSession.active_block_id ?? "PRACTICE" })} onPause={() => void lifecycle("pause", { reason: "operator_pause" })} onResume={() => void lifecycle("resume")} onFinish={() => void lifecycle("finish", { disposition: currentSession.lifecycle === "PREPARED" ? "abort" : "complete" })} />
      <div role="note" className="border-b border-info/30 bg-info/5 px-4 py-2 text-sm text-info lg:px-6">{modern ? nextStep.replace("INICIAR", "Iniciar").replace("START", "Start") : nextStep}</div>
      {profileStatus === "unsupported" && <div role="alert" className="border-b border-warning/30 px-4 py-2 text-sm text-warning">{locale === "es-CO" ? "Perfil de consola desconocido o incompatible. Se muestra la apariencia histórica; no se puede verificar la apariencia registrada." : "Unknown or mismatched console profile. Historical appearance is displayed; recorded appearance cannot be verified."}</div>}
      <MissionNotices modern={modern} notices={notices} legacyMessage={transportError ?? notice?.message} />
      {busy && <div className="sr-only" role="status">{t(locale, "mission.working")}</div>}
      {concealOperationalState ? probeOverlay : !currentSnapshot?.aircraft ? (
        <main className="grid flex-1 place-items-center p-8">{currentSession.presentation?.blocks[(currentSession.next_block_id ?? "PRACTICE") as "PRACTICE" | "LOW" | "MEDIUM" | "HIGH"] === "3d" ? <MissionPresentation session={currentSession} lease={canControl ? lease : null} readOnly snapshot={preflightSnapshot(currentSession.next_block_id ?? "PRACTICE")} locale={locale}/> : <div className="mission-panel max-w-lg p-8 text-center"><Loader2 className="mx-auto h-8 w-8 animate-spin text-info" aria-hidden="true" /><h1 className={`mt-4 font-display text-2xl ${modern ? "" : "uppercase"}`}>{t(locale, "mission.telemetry_standing_by")}</h1><p className="mt-2 text-sm text-muted-foreground">{t(locale, "mission.start_for_telemetry")}</p></div>}</main>
      ) : <main className="grid min-h-0 flex-1 gap-3 p-3 xl:h-[max(48rem,calc(100dvh-14rem))] xl:flex-none xl:grid-cols-[14rem_minmax(32rem,1fr)_21rem] xl:grid-rows-[minmax(0,1fr)] xl:p-4" aria-label={t(locale, "mission.operations")}>
        <div className="flex min-h-0 min-w-0 flex-col xl:col-start-2 xl:row-start-1">
        <MissionPresentation session={currentSession} lease={canControl ? lease : null} readOnly={!canControl} frozen={busy || concealOperationalState || currentSession.lifecycle === "PAUSED" && currentSession.protocol_phase !== "READY_FOR_BLOCK" || currentSession.lifecycle === "RUNNING" && connection !== "live"} snapshot={currentSnapshot} previousSnapshot={previousSnapshot} interpolate={currentSession.lifecycle === "RUNNING" && connection === "live" && !concealOperationalState} locale={locale} selectedAircraftId={selectedAircraftId} selectedContactId={selectedContactId} onSelectAircraft={(aircraftId) => { setWaypointMode(false); selectAircraft(aircraftId); }} onSelectContact={(contactId) => { setWaypointMode(false); selectContact(contactId); }} waypointAircraftId={waypointMode ? selectedAircraftId : null} onSetWaypoint={(aircraftId, waypoint) => { setWaypointMode(false); void issueCommand("SET_WAYPOINT", { aircraft_id: aircraftId, waypoint }); }} />
        </div>
        <div className={currentSnapshot.swarms ? "flex min-h-0 flex-col gap-3 xl:col-start-1 xl:row-start-1 xl:overflow-y-auto [&>*]:shrink-0" : "grid min-h-0 gap-3 md:grid-cols-2 xl:col-start-1 xl:row-start-1 xl:grid-cols-1 xl:grid-rows-[auto_minmax(15rem,1fr)]"}>
          {currentSnapshot.swarms ? <details className="mission-panel p-2"><summary className="cursor-pointer text-xs">{locale === "en" ? "Visit sequence" : "Secuencia de visita"}</summary><MissionJourneyRail session={currentSession} locale={locale} steps={journeySteps} /></details> : <MissionJourneyRail session={currentSession} locale={locale} steps={journeySteps} />}
          {currentSnapshot.swarms && <SwarmPanel snapshot={currentSnapshot} locale={locale} disabled={!canControl || busy || pendingCommandIds.length > 0} onCommand={(kind,payload)=>{void issueCommand(kind,payload);}} />}
          <FleetPanel snapshot={currentSnapshot} locale={locale} selectedAircraftId={selectedAircraftId} onSelect={selectAircraft} />
        </div>
        <aside className="flex min-h-0 flex-col gap-3 xl:col-start-3 xl:row-start-1" aria-label={t(locale, "mission.detail_panel")} data-testid="mission-detail-panel" tabIndex={-1}>
          <MissionInstructionPanel session={currentSession} locale={locale} selectedAircraft={selectedAircraft} selectedContact={selectedContact} />
          <MissionDetailTabs locale={locale} modern={modern}
            alerts={<AlertQueue alerts={alerts} locale={locale} readOnly={!canControl} onAcknowledge={(alert) => acknowledgeAlert(alert.alert_id)} />}
            contacts={<ContactQueue contacts={contacts} locale={locale} selectedContactId={selectedContactId} readOnly={!canControl} onSelect={selectContact} onInspect={(contact) => void issueCommand("INSPECT_CONTACT", { contact_id: contact.contact_id })} />} />
        </aside>
      </main>}
      {activeProbe && !concealOperationalState && probeOverlay}
      {!concealOperationalState && <CommandBar snapshot={currentSnapshot} selectedAircraft={selectedAircraft} selectedContact={selectedContact} locale={locale} readOnly={!canControl} pending={pendingCommandIds.length > 0} waypointMode={waypointMode} onWaypointMode={() => setWaypointMode((value) => !value)} onCommand={(kind, payload) => { setWaypointMode(false); void issueCommand(kind, payload); }} />}
    </div>
  );
}
