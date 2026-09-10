import type { TrafficFrame } from "@/lib/geography/types";
import { create } from "zustand";
import { getApiBase } from "@/lib/runtime-config";
import {
  SimulationApiError,
  getSimulationState,
  submitSimulationCommand,
} from "@/lib/simulation/api";
import {
  SimulationStream,
  type SimulationStreamOptions,
  type StreamStatus,
} from "@/lib/simulation/stream";
import type {
  AircraftSnapshot,
  AlertSnapshot,
  CommandKind,
  CommandRequest,
  CommandResultView,
  ConnectionMode,
  ContactSnapshot,
  ActiveProbePayload,
  Lifecycle,
  Locale,
  SessionView,
  StreamEnvelope,
  WorldSnapshot,
} from "@/types/simulation";

const LEASE_KEY_PREFIX = "matb.simulation.";
const LEASE_KEY_SUFFIX = ".lease";

export interface SimulationStoreState {
  traffic: TrafficFrame | null;
  session: SessionView | null;
  snapshot: WorldSnapshot | null;
  previousSnapshot: WorldSnapshot | null;
  lastSequence: number;
  connection: ConnectionMode;
  selectedAircraftId: string | null;
  selectedContactId: string | null;
  pendingCommandIds: string[];
  commandResults: Record<string, CommandResultView>;
  transportError: string | null;
  locale: Locale;
  activeProbe: ActiveProbePayload | null;
  concealOperationalState: boolean;
  initialize: {
    (session: SessionView, snapshot?: WorldSnapshot): void;
    (input: { session: SessionView; snapshot?: WorldSnapshot; locale?: Locale }): void;
  };
  applyEnvelope: (envelope: StreamEnvelope) => Promise<void>;
  replaceAuthoritativeState: (snapshot: WorldSnapshot) => void;
  selectAircraft: (aircraftId: string | null) => void;
  selectContact: (contactId: string | null) => void;
  submitCommand: (command: CommandRequest, lease?: string | null) => Promise<CommandResultView>;
  connect: (
    options?:
      | SimulationStream
      | (Partial<Omit<SimulationStreamOptions, "sessionId" | "onEnvelope" | "onStatus">> & {
          stream?: SimulationStream;
          role?: "controller" | "observer";
        }),
  ) => Promise<void>;
  disconnect: () => void;
  reset: () => void;
}

export type SimulationStore = ReturnType<typeof createSimulationStore>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function cloneSnapshot(snapshot: WorldSnapshot): WorldSnapshot {
  return JSON.parse(JSON.stringify(snapshot)) as WorldSnapshot;
}

function readLease(sessionId: string): string | null {
  if (typeof sessionStorage === "undefined") return null;
  try {
    return sessionStorage.getItem(`${LEASE_KEY_PREFIX}${sessionId}${LEASE_KEY_SUFFIX}`);
  } catch {
    return null;
  }
}

function snapshotPayload(envelope: StreamEnvelope): WorldSnapshot | null {
  if (!isRecord(envelope.payload)) return null;
  const raw = { ...envelope.payload };
  delete raw.resynchronizes_after_sequence;
  delete raw.authoritative_event_sequence;
  // A malformed snapshot is rejected by state application rather than
  // allowing partial payloads to overwrite authoritative data.
  if (!isRecord(raw.aircraft) || typeof raw.state_version !== "number") return null;
  return raw as unknown as WorldSnapshot;
}

function isPreStartSnapshot(envelope: StreamEnvelope): boolean {
  if (!isRecord(envelope.payload)) return false;
  return envelope.kind === "snapshot"
    && typeof envelope.payload.lifecycle === "string"
    && !isRecord(envelope.payload.aircraft);
}

function resynchronizesAfter(envelope: StreamEnvelope): number | undefined {
  if (typeof envelope.resynchronizes_after_sequence === "number") {
    return envelope.resynchronizes_after_sequence;
  }
  if (isRecord(envelope.payload) && typeof envelope.payload.resynchronizes_after_sequence === "number") {
    return envelope.payload.resynchronizes_after_sequence;
  }
  return undefined;
}

function lifecycleFromPayload(payload: unknown): Lifecycle | null {
  if (!isRecord(payload)) return null;
  const event = typeof payload.event === "string" ? payload.event : "";
  const map: Record<string, Lifecycle> = {
    block_started: "RUNNING",
    session_paused: "PAUSED",
    controller_disconnected: "PAUSED",
    session_resumed: "RUNNING",
    session_finished: "FINISHED",
    session_interrupted: "INTERRUPTED",
    process_shutdown: "INTERRUPTED",
    runtime_failure: "INTERRUPTED",
  };
  return map[event] ?? null;
}

function lifecycleValue(value: unknown): Lifecycle | null {
  return typeof value === "string" && ["PREPARED", "RUNNING", "PAUSED", "FINISHED", "ABORTED", "INTERRUPTED"].includes(value)
    ? value as Lifecycle
    : null;
}

function errorMessage(error: unknown): string {
  if (error instanceof SimulationApiError) return `${error.code}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return "simulation transport error";
}

function streamStatusToConnection(status: StreamStatus, session: SessionView | null): ConnectionMode {
  if (status === "live" && session?.lifecycle === "PAUSED") return "paused";
  return status;
}

function commandSubject(value: unknown): "aircraft" | "contact" | "alert" | null {
  if (!isRecord(value)) return null;
  if (typeof value.aircraft_id === "string") return "aircraft";
  if (typeof value.contact_id === "string") return "contact";
  if (typeof value.alert_id === "string") return "alert";
  return null;
}

/**
 * UI-side command affordances. The reducer remains authoritative: this list
 * only prevents obviously impossible buttons from being offered.
 */
export function validCommandsFor(
  subject: AircraftSnapshot | ContactSnapshot | AlertSnapshot | null | undefined,
): CommandKind[] {
  if (!subject) return [];
  const kind = commandSubject(subject);
  if (kind === "aircraft") {
    const aircraft = subject as AircraftSnapshot;
    if (
      aircraft.link === "LOST" ||
      aircraft.mode === "LOST_LINK_PROCEDURE" ||
      aircraft.mode === "RECOVERED" ||
      aircraft.mode === "MISSION_FAILED"
    ) return [];
    const commands: CommandKind[] = [
      "ASSIGN_SECTOR",
      "SET_WAYPOINT",
      "HOLD",
      "RETURN_TO_BASE",
    ];
    if (aircraft.mode === "HOLD" && aircraft.route.length > 0) {
      commands.splice(3, 0, "RESUME_MISSION");
    }
    return commands;
  }
  if (kind === "contact") {
    const contact = subject as ContactSnapshot;
    const commands: CommandKind[] = [];
    if (contact.evidence === "INSPECTABLE" && ["DETECTED", "INSPECTED"].includes(contact.workflow)) {
      commands.push("INSPECT_CONTACT");
    }
    if (["INSPECTED", "CLASSIFIED", "PRIORITIZED", "REPORTED"].includes(contact.workflow)) {
      commands.push("CLASSIFY_CONTACT");
    }
    if (["CLASSIFIED", "PRIORITIZED", "REPORTED"].includes(contact.workflow)) {
      commands.push("SET_CONTACT_PRIORITY");
    }
    if (
      ["PRIORITIZED", "REPORTED"].includes(contact.workflow) &&
      contact.classification !== null && contact.priority !== null
    ) {
      commands.push("REPORT_CONTACT");
    }
    return commands;
  }
  const alert = subject as AlertSnapshot;
  return !alert.acknowledged && alert.closed_sequence === null ? ["ACKNOWLEDGE_ALERT"] : [];
}

function isStream(value: unknown): value is SimulationStream {
  return Boolean(value) && typeof value === "object" && typeof (value as SimulationStream).connect === "function" && typeof (value as SimulationStream).close === "function";
}

function initialState(): Omit<SimulationStoreState, keyof {
  initialize: unknown;
  applyEnvelope: unknown;
  replaceAuthoritativeState: unknown;
  selectAircraft: unknown;
  selectContact: unknown;
  submitCommand: unknown;
  connect: unknown;
  disconnect: unknown;
  reset: unknown;
}> {
  return {
    session: null,
    traffic: null,
    snapshot: null,
    previousSnapshot: null,
    lastSequence: 0,
    connection: "disconnected",
    selectedAircraftId: null,
    selectedContactId: null,
    pendingCommandIds: [],
    commandResults: {},
    transportError: null,
    locale: "en",
    activeProbe: null,
    concealOperationalState: false,
  };
}

/** Create an isolated store for one mission; the exported hook is a default instance. */
export function createSimulationStore() {
  let activeStream: SimulationStream | null = null;
  let connectionGeneration = 0;

  return create<SimulationStoreState>((set, get) => {
    const replaceState = (snapshot: WorldSnapshot, sequence?: number) => {
      const current = get().snapshot;
      const currentSession = get().session;
      // The engine's state-version counter is scoped to a block.  A new
      // block therefore legitimately starts lower than the prior block's
      // final version; same-block snapshots must still be monotonic.
      if (current && snapshot.block_id === current.block_id && snapshot.state_version < current.state_version) return;
      set({
        previousSnapshot: current,
        snapshot: cloneSnapshot(snapshot),
        ...(sequence !== undefined ? { lastSequence: sequence } : {}),
        transportError: null,
        session: currentSession
          ? {
              ...currentSession,
              state_version: Math.max(currentSession.state_version, snapshot.state_version),
              simulation_time_ms: Math.max(currentSession.simulation_time_ms, snapshot.simulation_time_ms),
            }
          : currentSession,
      });
    };

    const apply = async (envelope: StreamEnvelope): Promise<void> => {
      const current = get();
      if (current.session && envelope.session_id !== current.session.id) return;
      if (envelope.sequence <= current.lastSequence) return;

      const isSnapshot = envelope.kind === "snapshot";
      const isResync = resynchronizesAfter(envelope) !== undefined;
      const hasInitialSnapshot = isSnapshot && current.snapshot === null;
      const expected = current.lastSequence + 1;
      if (!hasInitialSnapshot && !isResync && envelope.sequence > expected) {
        set({ connection: "reconnecting" });
        if (!current.session) {
          set({ transportError: "simulation session is not initialized" });
          return;
        }
        try {
          const authoritative = await getSimulationState(current.session.id);
          replaceState(authoritative);
          // A gap means the current socket can no longer prove contiguous
          // delivery. Re-open from the last known-good sequence so the server
          // sends a marked full snapshot and the next event starts a new chain.
          if (activeStream) {
            activeStream.close();
            activeStream.connect();
          }
        } catch (error) {
          set({ transportError: errorMessage(error), connection: "reconnecting" });
        }
        // Keep the last contiguous transport sequence. A subsequent fresh
        // snapshot from SimulationStream is the only safe gap boundary.
        return;
      }

      if (isSnapshot) {
        const snapshot = snapshotPayload(envelope);
        if (!snapshot) {
          if (isPreStartSnapshot(envelope)) {
            // A prepared session has no engine world yet. Preserve the
            // transport boundary so the first block lifecycle envelope is
            // contiguous; do not invent an empty authoritative fleet.
            set({ lastSequence: envelope.sequence, transportError: null });
            return;
          }
          set({ transportError: "invalid simulation snapshot payload" });
          return;
        }
        if (current.snapshot
          && snapshot.block_id === current.snapshot.block_id
          && snapshot.state_version < current.snapshot.state_version) {
          set({ lastSequence: envelope.sequence });
        } else {
          replaceState(snapshot, envelope.sequence);
        }
        const snapshotLifecycle = isRecord(envelope.payload) ? lifecycleValue(envelope.payload.lifecycle) : null;
        if (snapshotLifecycle && get().session) {
          set({
            session: { ...get().session!, lifecycle: snapshotLifecycle },
            connection: snapshotLifecycle === "PAUSED"
              ? "paused"
              : snapshotLifecycle === "RUNNING" && get().connection !== "reconnecting"
                ? "live"
                : get().connection,
          });
        }
        if (isResync) set({ connection: streamStatusToConnection("live", get().session) });
      } else {
        set({ lastSequence: envelope.sequence });
      }

      if(envelope.kind === "traffic") set({traffic: envelope.payload as unknown as TrafficFrame});
      const lifecycle = envelope.kind === "lifecycle" ? lifecycleFromPayload(envelope.payload) : null;
      if (lifecycle && get().session) {
        const session = { ...get().session!, lifecycle, state_version: Math.max(get().session!.state_version, envelope.state_version), simulation_time_ms: Math.max(get().session!.simulation_time_ms, envelope.simulation_time_ms) };
        set({
          session,
          connection: lifecycle === "PAUSED" ? "paused" : lifecycle === "RUNNING" && get().connection !== "reconnecting" ? "live" : get().connection,
        });
      }

      if (envelope.kind === "command_result" && isRecord(envelope.payload)) {
        const commandId = typeof envelope.payload.command_id === "string" ? envelope.payload.command_id : null;
        if (commandId) {
          const result = envelope.payload as unknown as CommandResultView;
          set({
            commandResults: { ...get().commandResults, [commandId]: result },
            pendingCommandIds: get().pendingCommandIds.filter((id) => id !== commandId),
          });
        }
      }
      if (envelope.kind === "probe" && isRecord(envelope.payload)) {
        const payload = envelope.payload as unknown as ActiveProbePayload;
        const isSagat = payload.kind === "SAGAT";
        set({ activeProbe: payload, concealOperationalState: isSagat });
      }
      if (envelope.kind === "error" && isRecord(envelope.payload)) {
        const code = typeof envelope.payload.code === "string" ? envelope.payload.code : "stream_error";
        const message = typeof envelope.payload.message === "string" ? envelope.payload.message : code;
        set({ transportError: `${code}: ${message}` });
      }
    };

    return {
      ...initialState(),
      initialize: ((sessionOrInput: SessionView | { session: SessionView; snapshot?: WorldSnapshot; locale?: Locale }, optionalSnapshot?: WorldSnapshot) => {
        const input = "session" in sessionOrInput
          ? sessionOrInput
          : { session: sessionOrInput, snapshot: optionalSnapshot };
        if (activeStream) {
          activeStream.close();
          activeStream = null;
        }
        connectionGeneration += 1;
        set({
          ...initialState(),
          session: input.session,
          snapshot: input.snapshot ? cloneSnapshot(input.snapshot) : null,
          locale: input.locale ?? input.session.locale,
          connection: input.session.lifecycle === "PAUSED" ? "paused" : "disconnected",
        });
      }) as SimulationStoreState["initialize"],
      applyEnvelope: apply,
      replaceAuthoritativeState: (snapshot) => replaceState(snapshot),
      selectAircraft: (aircraftId) => set({ selectedAircraftId: aircraftId, ...(aircraftId ? { selectedContactId: null } : {}) }),
      selectContact: (contactId) => set({ selectedContactId: contactId, ...(contactId ? { selectedAircraftId: null } : {}) }),
      submitCommand: async (command, explicitLease) => {
        const session = get().session;
        if (!session) throw new Error("simulation session is not initialized");
        const lease = explicitLease === undefined ? readLease(session.id) : explicitLease;
        if (!lease) {
          const error = new SimulationApiError(403, "invalid_lease", "controller lease is unavailable");
          throw error;
        }
        if (!get().pendingCommandIds.includes(command.command_id)) {
          set({ pendingCommandIds: [...get().pendingCommandIds, command.command_id] });
        }
        try {
          const result = await submitSimulationCommand(session.id, lease, command);
          set({
            pendingCommandIds: get().pendingCommandIds.filter((id) => id !== command.command_id),
            commandResults: { ...get().commandResults, [command.command_id]: result },
          });
          return result;
        } catch (error) {
          set({
            pendingCommandIds: get().pendingCommandIds.filter((id) => id !== command.command_id),
          });
          throw error;
        }
      },
      connect: async (options) => {
        const session = get().session;
        if (!session) throw new Error("simulation session is not initialized");
        if (isStream(options)) {
          if (activeStream) activeStream.close();
          activeStream = options;
          set({ connection: "reconnecting", transportError: null });
          options.connect();
          return;
        }
        const generation = ++connectionGeneration;
        const connectOptions = options ?? {};
        const apiBase = connectOptions.apiBase ?? await getApiBase();
        if (generation !== connectionGeneration || !get().session) return;
        if (activeStream) activeStream.close();
        const lease = connectOptions.lease === undefined ? readLease(session.id) : connectOptions.lease;
        const role = connectOptions.role ?? connectOptions.mode ?? (lease ? "controller" : "observer");
        const streamOptions: SimulationStreamOptions = {
          ...connectOptions,
          apiBase,
          sessionId: session.id,
          lease,
          role,
          afterSequence: get().lastSequence,
          onEnvelope: (envelope) => get().applyEnvelope(envelope),
          onError: (error) => set({ transportError: error.message }),
          onStatus: (status) => {
            const next = streamStatusToConnection(status, get().session);
            if (connectionGeneration === generation) set({ connection: next });
          },
        };
        activeStream = new SimulationStream(streamOptions);
        set({ connection: "reconnecting", transportError: null });
        activeStream.connect();
      },
      disconnect: () => {
        connectionGeneration += 1;
        activeStream?.close();
        activeStream = null;
        set({ connection: "disconnected" });
      },
      reset: () => {
        connectionGeneration += 1;
        activeStream?.close();
        activeStream = null;
        set(initialState());
      },
    };
  });
}

export const useSimulationStore = createSimulationStore();
