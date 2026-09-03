"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";
import { AlertTriangle, Loader2 } from "lucide-react";
import { MissionMap } from "@/components/mission/map/MissionMap";
import { AlertQueue } from "@/components/mission/AlertQueue";
import { ContactQueue } from "@/components/mission/ContactQueue";
import { CommandBar } from "@/components/mission/CommandBar";
import { FleetPanel } from "@/components/mission/FleetPanel";
import { MissionTopBar } from "@/components/mission/MissionTopBar";
import { ProbeOverlay } from "@/components/mission/probes/ProbeOverlay";
import type { PostBlockScaleValues } from "@/components/mission/probes/PostBlockScales";
import { t } from "@/lib/simulation/i18n";
import { getSimulationSession, getSimulationState, transitionSession } from "@/lib/simulation/api";
import { useSimulationStore } from "@/lib/simulation/store";
import type { AircraftSnapshot, CommandKind, ContactSnapshot, JsonValue, Locale, ProtocolCommandKind, SessionView, WorldSnapshot } from "@/types/simulation";

export interface MissionConsoleProps {
  initialSession: SessionView;
  initialSnapshot?: WorldSnapshot | null;
  readOnly?: boolean;
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

export function MissionConsole({ initialSession, initialSnapshot = null, readOnly = false, onFinished }: MissionConsoleProps) {
  const initialized = useRef(false);
  const cleanupTimer = useRef<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [detailView, setDetailView] = useState<"alerts" | "contacts">("alerts");
  const session = useSimulationStore((state) => state.session);
  const snapshot = useSimulationStore((state) => state.snapshot);
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
    setBusy(true); setMessage(null);
    try {
      const updated = await transitionSession(
        currentSession.id,
        action,
        lease!,
        action === "finish"
          ? { disposition: body.disposition === "abort" ? "abort" : "complete" }
          : body,
      );
      useSimulationStore.setState({ session: updated });
      setMessage(t(locale, `lifecycle.${updated.lifecycle.toLowerCase()}` as never));
      if (updated.lifecycle === "FINISHED") onFinished?.(updated);
      if (action === "start") {
        const state = await getSimulationState(currentSession.id);
        useSimulationStore.getState().replaceAuthoritativeState(state);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : t(locale, "error.unknown_error"));
    } finally { setBusy(false); }
  }

  async function issueCommand(kind: CommandKind | ProtocolCommandKind, payload: Record<string, unknown>): Promise<boolean> {
    if (!currentSnapshot || !canControl) return false;
    setMessage(null);
    try {
      await submitCommand({ command_id: commandId(), expected_state_version: currentSnapshot.state_version, kind, payload: payload as Record<string, JsonValue> });
      setMessage(t(locale, "command.accepted"));
      return true;
    } catch (error) { setMessage(error instanceof Error ? error.message : t(locale, "error.unknown_error")); return false; }
  }

  function acknowledgeAlert(alertId: string) { void issueCommand("ACKNOWLEDGE_ALERT", { alert_id: alertId }); }

  const probeSubmit = async (kind: ProtocolCommandKind, payload: Record<string, unknown>) => {
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
      useSimulationStore.setState({ session: refreshed, activeProbe: null, concealOperationalState: false });
    } catch {
      useSimulationStore.setState({ activeProbe: null, concealOperationalState: false });
    }
  };

  const probeOverlay = activeProbe ? <ProbeOverlay locale={locale} probe={activeProbe} pending={pendingCommandIds.length > 0} onIsa={(rating) => void probeSubmit("SUBMIT_ISA", { probe_id: activeProbe.kind === "ISA" ? activeProbe.probe_id : "", rating })} onSagat={(answer) => void probeSubmit("SUBMIT_SAGAT", { probe_id: activeProbe.kind === "SAGAT" ? activeProbe.probe_id : "", answer })} onPostBlock={(values: PostBlockScaleValues) => void probeSubmit("SUBMIT_POST_BLOCK_SCALE", { ...values })} /> : null;

  return (
    <div className="simulation-console relative flex min-h-screen flex-col bg-background text-foreground" aria-busy={busy}>
      <div className="signal-sweep pointer-events-none absolute inset-x-0 top-0 z-20 h-px bg-white/10" aria-hidden="true" />
      <MissionTopBar session={currentSession} locale={locale} connection={connection} canControl={canControl} busy={busy} onStart={() => void lifecycle("start", { block_id: currentSession.next_block_id ?? currentSession.active_block_id ?? "PRACTICE" })} onPause={() => void lifecycle("pause", { reason: "operator_pause" })} onResume={() => void lifecycle("resume")} onFinish={() => void lifecycle("finish", { disposition: currentSession.lifecycle === "PREPARED" ? "abort" : "complete" })} />
      <div role="note" className="border-b border-info/30 bg-info/5 px-4 py-2 text-sm text-info lg:px-6">{nextStep}</div>
      {(transportError || message) && <div role="status" aria-live="polite" className="flex items-center gap-2 border-b border-warning/30 bg-warning/5 px-4 py-2 font-mono text-xs text-warning"><AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />{transportError ?? message}</div>}
      {busy && <div className="sr-only" role="status">{t(locale, "mission.working")}</div>}
      {concealOperationalState && probeOverlay ? probeOverlay : !currentSnapshot?.aircraft ? (
        <main className="grid flex-1 place-items-center p-8"><div className="mission-panel max-w-lg p-8 text-center"><Loader2 className="mx-auto h-8 w-8 animate-spin text-info" aria-hidden="true" /><h1 className="mt-4 font-display text-2xl uppercase">{t(locale, "mission.telemetry_standing_by")}</h1><p className="mt-2 text-sm text-muted-foreground">{t(locale, "mission.start_for_telemetry")}</p></div></main>
      ) : <main className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[16rem_minmax(0,1fr)_20rem] lg:p-4" aria-label={t(locale, "mission.operations")}><FleetPanel snapshot={currentSnapshot} locale={locale} selectedAircraftId={selectedAircraftId} onSelect={selectAircraft} /><MissionMap snapshot={currentSnapshot} locale={locale} selectedAircraftId={selectedAircraftId} selectedContactId={selectedContactId} onSelectAircraft={selectAircraft} onSelectContact={selectContact} /><aside className="mission-panel flex min-h-0 flex-col" aria-label={t(locale, "mission.detail_panel")} data-testid="mission-detail-panel" tabIndex={-1}><div className="grid grid-cols-2 border-b border-white/10" role="tablist" aria-label={t(locale, "mission.detail_views")}><button type="button" role="tab" id="mission-alerts-tab" aria-selected={detailView === "alerts"} aria-controls="mission-detail-panel-content" tabIndex={detailView === "alerts" ? 0 : -1} onClick={() => setDetailView("alerts")} className={`border-b-2 px-3 py-3 font-mono text-[10px] uppercase tracking-wider ${detailView === "alerts" ? "border-white" : "border-transparent text-muted-foreground"}`}>{t(locale, "mission.alerts")}</button><button type="button" role="tab" id="mission-contacts-tab" aria-selected={detailView === "contacts"} aria-controls="mission-detail-panel-content" tabIndex={detailView === "contacts" ? 0 : -1} onClick={() => setDetailView("contacts")} className={`border-b-2 px-3 py-3 font-mono text-[10px] uppercase tracking-wider ${detailView === "contacts" ? "border-white" : "border-transparent text-muted-foreground"}`}>{t(locale, "mission.contacts")}</button></div><div className="min-h-0 flex-1" id="mission-detail-panel-content" role="tabpanel" tabIndex={0} aria-labelledby={detailView === "alerts" ? "mission-alerts-tab" : "mission-contacts-tab"}>{detailView === "alerts" ? <AlertQueue alerts={alerts} locale={locale} readOnly={!canControl} onAcknowledge={(alert) => acknowledgeAlert(alert.alert_id)} /> : <ContactQueue contacts={contacts} locale={locale} readOnly={!canControl} onAction={(kind, contact) => void issueCommand(kind, { contact_id: contact.contact_id, ...(kind === "CLASSIFY_CONTACT" ? { classification: "uncertain" } : kind === "SET_CONTACT_PRIORITY" ? { priority: "MEDIUM" } : kind === "REPORT_CONTACT" ? { note_code: "GENERAL" } : {}) })} />}</div></aside></main>}
      {activeProbe && !concealOperationalState && probeOverlay}
      <CommandBar snapshot={currentSnapshot} selectedAircraft={selectedAircraft} selectedContact={selectedContact} locale={locale} readOnly={!canControl} pending={pendingCommandIds.length > 0} onCommand={(kind, payload) => { void issueCommand(kind, payload); }} />
    </div>
  );
}
