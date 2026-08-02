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
import { getSimulationState, transitionSession } from "@/lib/simulation/api";
import { useSimulationStore } from "@/lib/simulation/store";
import type { ActiveProbePayload, AircraftSnapshot, CommandKind, ContactSnapshot, JsonValue, Locale, ProtocolCommandKind, SessionView, WorldSnapshot } from "@/types/simulation";

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
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
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

  useEffect(() => {
    if (initialized.current) return;
    initialized.current = true;
    initialize({ session: initialSession, snapshot: initialSnapshot ?? undefined, locale: initialSession.locale });
    void connect({ role: lease ? "controller" : "observer", lease });
    return () => { disconnect(); reset(); initialized.current = false; };
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
      const updated = await transitionSession(currentSession.id, action, lease!, action === "finish" ? { disposition: "complete" } : body);
      useSimulationStore.setState({ session: updated });
      setMessage(`lifecycle.${updated.lifecycle.toLowerCase()}`);
      if (updated.lifecycle === "FINISHED") onFinished?.(updated);
      if (action === "start") {
        const state = await getSimulationState(currentSession.id);
        useSimulationStore.getState().replaceAuthoritativeState(state);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "lifecycle request failed");
    } finally { setBusy(false); }
  }

  async function issueCommand(kind: CommandKind | ProtocolCommandKind, payload: Record<string, unknown>) {
    if (!currentSnapshot || !canControl) return;
    setMessage(null);
    try {
      await submitCommand({ command_id: commandId(), expected_state_version: currentSnapshot.state_version, kind, payload: payload as Record<string, JsonValue> });
      setMessage("command.accepted");
    } catch (error) { setMessage(error instanceof Error ? error.message : "command failed"); }
  }

  function acknowledgeAlert(alertId: string) { void issueCommand("ACKNOWLEDGE_ALERT", { alert_id: alertId }); }

  const probeSubmit = async (kind: ProtocolCommandKind, payload: Record<string, unknown>) => {
    await issueCommand(kind, payload);
    useSimulationStore.setState({ activeProbe: null, concealOperationalState: false });
  };

  const probeOverlay = activeProbe ? <ProbeOverlay locale={locale} probe={activeProbe} pending={pendingCommandIds.length > 0} onIsa={(rating) => void probeSubmit("SUBMIT_ISA", { probe_id: activeProbe.kind === "ISA" ? activeProbe.probe_id : "", rating })} onSagat={(answer) => void probeSubmit("SUBMIT_SAGAT", { probe_id: activeProbe.kind === "SAGAT" ? activeProbe.probe_id : "", answer })} onPostBlock={(values: PostBlockScaleValues) => void probeSubmit("SUBMIT_POST_BLOCK_SCALE", { scale_id: "NASA_TLX", answers: values.nasa_tlx })} /> : null;

  return (
    <div className="simulation-console flex min-h-screen flex-col bg-background text-foreground" aria-busy={busy}>
      <MissionTopBar session={currentSession} locale={locale} connection={connection} canControl={canControl} busy={busy} onStart={() => void lifecycle("start", { block_id: currentSession.active_block_id ?? "PRACTICE" })} onPause={() => void lifecycle("pause", { reason: "operator_pause" })} onResume={() => void lifecycle("resume")} onFinish={() => void lifecycle("finish")} />
      {(transportError || message) && <div role="status" aria-live="polite" className="flex items-center gap-2 border-b border-warning/30 bg-warning/5 px-4 py-2 font-mono text-xs text-warning"><AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />{transportError ?? message}</div>}
      {busy && <div className="sr-only" role="status">Working…</div>}
      {concealOperationalState && probeOverlay ? probeOverlay : !currentSnapshot?.aircraft ? (
        <main className="grid flex-1 place-items-center p-8"><div className="mission-panel max-w-lg p-8 text-center"><Loader2 className="mx-auto h-8 w-8 animate-spin text-info" aria-hidden="true" /><h1 className="mt-4 font-display text-2xl uppercase">Telemetry standing by</h1><p className="mt-2 text-sm text-muted-foreground">Start the next protocol block to receive the authoritative synthetic fleet snapshot.</p></div></main>
      ) : <main className="grid min-h-0 flex-1 gap-3 p-3 lg:grid-cols-[18rem_minmax(0,1fr)_22rem] lg:p-4"><FleetPanel snapshot={currentSnapshot} locale={locale} selectedAircraftId={selectedAircraftId} onSelect={selectAircraft} /><MissionMap snapshot={currentSnapshot} locale={locale} selectedAircraftId={selectedAircraftId} selectedContactId={selectedContactId} onSelectAircraft={selectAircraft} onSelectContact={selectContact} /><aside className="mission-panel flex min-h-0 flex-col"><div className="grid grid-cols-2 border-b border-white/10"><button type="button" className="border-b-2 border-white px-3 py-3 font-mono text-[10px] uppercase tracking-wider">Alerts</button><button type="button" className="border-b-2 border-transparent px-3 py-3 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">Contacts</button></div><div className="min-h-0 flex-1"><AlertQueue alerts={alerts} locale={locale} readOnly={!canControl} onAcknowledge={(alert) => acknowledgeAlert(alert.alert_id)} /><ContactQueue contacts={contacts} locale={locale} readOnly={!canControl} onAction={(kind, contact) => void issueCommand(kind, { contact_id: contact.contact_id, ...(kind === "CLASSIFY_CONTACT" ? { classification: "uncertain" } : kind === "SET_CONTACT_PRIORITY" ? { priority: "MEDIUM" } : kind === "REPORT_CONTACT" ? { note_code: "GENERAL" } : {}) })} /></div></aside></main>}
      {activeProbe && !concealOperationalState && probeOverlay}
      <CommandBar snapshot={currentSnapshot} selectedAircraft={selectedAircraft} selectedContact={selectedContact} locale={locale} readOnly={!canControl} pending={pendingCommandIds.length > 0} onCommand={issueCommand} />
    </div>
  );
}
