import { simulationWsUrl } from "@/lib/simulation/api";
import type { ConnectionMode, StreamEnvelope, StreamKind } from "@/types/simulation";

/** The small subset of WebSocket used by the stream adapter. */
export interface SimulationWebSocket {
  onopen: ((event: Event) => void) | null;
  onmessage: ((event: MessageEvent<unknown>) => void) | null;
  onerror: ((event: Event) => void) | null;
  onclose: ((event: CloseEvent) => void) | null;
  send?(data: string): void;
  close(code?: number, reason?: string): void;
  readonly readyState?: number;
}

export type SimulationWebSocketFactory = (url: string) => SimulationWebSocket;

export type StreamStatus = Extract<ConnectionMode, "live" | "reconnecting" | "disconnected">;

export interface SimulationStreamTimers {
  setTimeout: (handler: () => void, timeout: number) => unknown;
  clearTimeout: (handle: unknown) => void;
}

export interface SimulationStreamOptions {
  apiBase: string;
  sessionId: string;
  /** A lease is serialized into the URL only when role is controller. */
  lease?: string | null;
  role?: "controller" | "observer";
  /** `mode` is accepted as an ergonomic alias for callers that use UI terms. */
  mode?: "controller" | "observer";
  afterSequence?: number;
  webSocketFactory?: SimulationWebSocketFactory;
  timers?: Partial<SimulationStreamTimers>;
  /** Top-level timer aliases keep the adapter easy to inject in unit tests. */
  setTimeout?: SimulationStreamTimers["setTimeout"];
  clearTimeout?: SimulationStreamTimers["clearTimeout"];
  onEnvelope?: (envelope: StreamEnvelope) => void | Promise<void>;
  onError?: (error: Error) => void;
  onStatus?: (status: StreamStatus) => void;
  onConnectionChange?: (status: StreamStatus) => void;
}

const STREAM_KINDS: ReadonlySet<string> = new Set<StreamKind>([
  "snapshot",
  "domain_event",
  "alert",
  "command_result",
  "probe",
  "lifecycle",
  "checkpoint",
  "error",
]);

const RETRY_DELAYS_MS = [250, 500, 1_000, 2_000] as const;

function defaultTimers(): SimulationStreamTimers {
  return {
    setTimeout: (handler, timeout) => globalThis.setTimeout(handler, timeout),
    clearTimeout: (handle) => globalThis.clearTimeout(handle as ReturnType<typeof setTimeout>),
  };
}

function defaultWebSocketFactory(url: string): SimulationWebSocket {
  if (typeof WebSocket === "undefined") {
    throw new Error("WebSocket is unavailable in this runtime");
  }
  return new WebSocket(url);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function nonNegativeInteger(value: unknown, field: string): number {
  if (typeof value !== "number" || !Number.isInteger(value) || value < 0) {
    throw new Error(`stream envelope ${field} must be a non-negative integer`);
  }
  return value;
}

function positiveInteger(value: unknown, field: string): number {
  const result = nonNegativeInteger(value, field);
  if (result < 1) throw new Error(`stream envelope ${field} must be positive`);
  return result;
}

/**
 * Validate the wire envelope before it reaches mission state.  Payloads are
 * intentionally opaque here: individual domain payloads evolve independently
 * while the envelope remains the ordering and resynchronization contract.
 */
export function parseStreamEnvelope(value: unknown): StreamEnvelope {
  if (!isRecord(value)) throw new Error("stream message must be an object");
  const sessionId = value.session_id;
  if (typeof sessionId !== "string" || sessionId.length === 0) {
    throw new Error("stream envelope session_id is invalid");
  }
  const wallTime = value.wall_time_utc;
  if (typeof wallTime !== "string" || wallTime.length === 0) {
    throw new Error("stream envelope wall_time_utc is invalid");
  }
  if (!STREAM_KINDS.has(String(value.kind))) {
    throw new Error("stream envelope kind is invalid");
  }
  if (!isRecord(value.payload)) throw new Error("stream envelope payload must be an object");
  const envelope: StreamEnvelope = {
    session_id: sessionId,
    sequence: positiveInteger(value.sequence, "sequence"),
    simulation_time_ms: nonNegativeInteger(value.simulation_time_ms, "simulation_time_ms"),
    wall_time_utc: wallTime,
    state_version: nonNegativeInteger(value.state_version, "state_version"),
    kind: value.kind as StreamKind,
    payload: value.payload as StreamEnvelope["payload"],
  };
  if (value.resynchronizes_after_sequence !== undefined) {
    envelope.resynchronizes_after_sequence = nonNegativeInteger(
      value.resynchronizes_after_sequence,
      "resynchronizes_after_sequence",
    );
  }
  return envelope;
}

function messageData(event: MessageEvent<unknown>): unknown {
  return event.data;
}

function decodeMessage(data: unknown): unknown {
  if (typeof data === "string") return JSON.parse(data) as unknown;
  if (data instanceof ArrayBuffer) return JSON.parse(new TextDecoder().decode(data)) as unknown;
  // Browser WebSockets normally deliver text for this API.  Supporting a
  // Blob-like test double costs little and keeps malformed input fail-closed.
  if (typeof Blob !== "undefined" && data instanceof Blob) {
    throw new Error("binary stream messages are not supported");
  }
  throw new Error("stream message must be JSON text");
}

function errorFromUnknown(value: unknown, fallback: string): Error {
  if (value instanceof Error) return value;
  return new Error(typeof value === "string" ? value : fallback);
}

/**
 * Ordered WebSocket transport for the native simulation stream.
 *
 * This class has no mission logic.  It only validates envelopes, tracks the
 * latest transport sequence for reconnect URLs, and exposes bounded retry
 * behavior to the simulation store.
 */
export class SimulationStream {
  private readonly options: SimulationStreamOptions;
  private readonly role: "controller" | "observer";
  private readonly webSocketFactory: SimulationWebSocketFactory;
  private readonly timers: SimulationStreamTimers;
  private socket: SimulationWebSocket | null = null;
  private retryTimer: unknown = null;
  private retryAttempt = 0;
  private transportSequence: number;
  private waitingForSnapshot = true;
  private intentionallyClosed = false;
  private currentUrl: string | null = null;
  private socketGeneration = 0;

  constructor(options: SimulationStreamOptions) {
    if (!options.apiBase) throw new Error("SimulationStream requires apiBase");
    if (!options.sessionId) throw new Error("SimulationStream requires sessionId");
    this.options = options;
    this.role = options.role ?? options.mode ?? (options.lease ? "controller" : "observer");
    this.webSocketFactory = options.webSocketFactory ?? defaultWebSocketFactory;
    const defaults = defaultTimers();
    this.timers = {
      setTimeout: options.setTimeout ?? options.timers?.setTimeout ?? defaults.setTimeout,
      clearTimeout: options.clearTimeout ?? options.timers?.clearTimeout ?? defaults.clearTimeout,
    };
    this.transportSequence = Math.max(0, Math.trunc(options.afterSequence ?? 0));
  }

  get lastSequence(): number {
    return this.transportSequence;
  }

  get url(): string | null {
    return this.currentUrl;
  }

  get connected(): boolean {
    return this.socket !== null;
  }

  /** Begin (or resume) the stream. Calling connect twice is idempotent. */
  connect(): this {
    this.intentionallyClosed = false;
    if (this.socket) return this;
    this.clearRetryTimer();
    this.waitingForSnapshot = true;
    this.emitStatus("reconnecting");
    const lease = this.role === "controller" ? this.options.lease ?? undefined : undefined;
    this.currentUrl = simulationWsUrl(
      this.options.apiBase,
      this.options.sessionId,
      this.transportSequence,
      lease,
    );
    try {
      const socket = this.webSocketFactory(this.currentUrl);
      const generation = ++this.socketGeneration;
      this.socket = socket;
      socket.onopen = () => {
        if (this.socket !== socket || this.socketGeneration !== generation) return;
        // An open TCP/WebSocket connection is not yet authoritative. The
        // server must send its full snapshot before the UI is considered live.
        this.waitingForSnapshot = true;
        this.emitStatus("reconnecting");
      };
      socket.onmessage = (event) => {
        if (this.socket !== socket || this.socketGeneration !== generation) return;
        void this.handleMessage(event, socket, generation);
      };
      socket.onerror = () => {
        if (this.socket !== socket || this.socketGeneration !== generation) return;
        this.reportError(new Error("simulation stream socket error"));
      };
      socket.onclose = () => {
        if (this.socket !== socket || this.socketGeneration !== generation) return;
        this.socket = null;
        if (this.intentionallyClosed) {
          this.emitStatus("disconnected");
          return;
        }
        this.emitStatus("reconnecting");
        this.scheduleRetry();
      };
    } catch (error) {
      this.socket = null;
      this.reportError(errorFromUnknown(error, "simulation stream could not connect"));
      this.scheduleRetry();
    }
    return this;
  }

  /** Stop the stream and cancel all future retry work. */
  close(): void {
    this.intentionallyClosed = true;
    this.socketGeneration += 1;
    this.clearRetryTimer();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      try {
        socket.close(1000, "client closed stream");
      } catch (error) {
        this.reportError(errorFromUnknown(error, "simulation stream close failed"));
      }
    }
    this.emitStatus("disconnected");
  }

  private async handleMessage(
    event: MessageEvent<unknown>,
    socket: SimulationWebSocket,
    generation: number,
  ): Promise<void> {
    try {
      const envelope = parseStreamEnvelope(decodeMessage(messageData(event)));
      if (envelope.session_id !== this.options.sessionId) {
        throw new Error("stream envelope session_id does not match the requested session");
      }
      const payload = envelope.payload as Record<string, unknown>;
      let resynchronizesAfter = envelope.resynchronizes_after_sequence;
      if (resynchronizesAfter === undefined && payload.resynchronizes_after_sequence !== undefined) {
        resynchronizesAfter = nonNegativeInteger(
          payload.resynchronizes_after_sequence,
          "resynchronizes_after_sequence",
        );
      }
      if (this.waitingForSnapshot) {
        if (envelope.kind !== "snapshot") {
          throw new Error("simulation stream must begin with a full snapshot");
        }
        if (resynchronizesAfter === undefined) {
          throw new Error("simulation stream snapshot is missing resynchronizes_after_sequence");
        }
        this.waitingForSnapshot = false;
        this.retryAttempt = 0;
      }
      this.transportSequence = Math.max(this.transportSequence, envelope.sequence);
      await this.options.onEnvelope?.(envelope);
      if (
        this.socket === socket &&
        this.socketGeneration === generation &&
        envelope.kind === "snapshot" &&
        resynchronizesAfter !== undefined
      ) {
        this.emitStatus("live");
      }
    } catch (error) {
      this.reportError(errorFromUnknown(error, "invalid simulation stream message"));
      if (this.socket === socket && this.socketGeneration === generation) {
        try {
          socket.close(1003, "invalid stream message");
        } catch (closeError) {
          this.reportError(errorFromUnknown(closeError, "simulation stream close failed"));
        }
      }
    }
  }

  private scheduleRetry(): void {
    if (this.intentionallyClosed || this.retryTimer !== null) return;
    const delay = RETRY_DELAYS_MS[Math.min(this.retryAttempt, RETRY_DELAYS_MS.length - 1)];
    this.retryAttempt += 1;
    this.retryTimer = this.timers.setTimeout(() => {
      this.retryTimer = null;
      this.connect();
    }, delay);
  }

  private clearRetryTimer(): void {
    if (this.retryTimer === null) return;
    this.timers.clearTimeout(this.retryTimer);
    this.retryTimer = null;
  }

  private reportError(error: Error): void {
    try {
      this.options.onError?.(error);
    } catch {
      // Error observers are diagnostics only; they cannot break transport
      // cleanup or create an unbounded reconnect loop.
    }
  }

  private emitStatus(status: StreamStatus): void {
    try {
      this.options.onStatus?.(status);
      this.options.onConnectionChange?.(status);
    } catch {
      // Status observers are intentionally non-authoritative.
    }
  }
}

export const SIMULATION_STREAM_RETRY_DELAYS_MS = RETRY_DELAYS_MS;
