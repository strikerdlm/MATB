import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  SimulationStream,
  parseStreamEnvelope,
  type SimulationWebSocket,
} from "@/lib/simulation/stream";

interface FakeSocket extends SimulationWebSocket {
  emitOpen: () => void;
  emitMessage: (value: unknown) => void;
  emitClose: () => void;
}

function socketFactory(urls: string[]): { factory: (url: string) => FakeSocket; sockets: FakeSocket[] } {
  const sockets: FakeSocket[] = [];
  return {
    sockets,
    factory: (url: string) => {
      urls.push(url);
      const socket: FakeSocket = {
        onopen: null,
        onmessage: null,
        onerror: null,
        onclose: null,
        close: vi.fn(),
        emitOpen: () => socket.onopen?.(new Event("open")),
        emitMessage: (value) => socket.onmessage?.({ data: JSON.stringify(value) } as MessageEvent),
        emitClose: () => socket.onclose?.({} as CloseEvent),
      };
      sockets.push(socket);
      return socket;
    },
  };
}

function envelope(sequence: number, kind: "snapshot" | "domain_event", payload: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    session_id: "sim-1",
    sequence,
    simulation_time_ms: sequence * 250,
    wall_time_utc: "2026-08-02T00:00:00Z",
    state_version: sequence,
    kind,
    payload,
  };
}

describe("SimulationStream", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("validates envelopes and waits for a resynchronizing snapshot before live", async () => {
    const urls: string[] = [];
    const { factory, sockets } = socketFactory(urls);
    const received: unknown[] = [];
    const statuses: string[] = [];
    const stream = new SimulationStream({
      apiBase: "http://127.0.0.1:8000",
      sessionId: "sim-1",
      role: "controller",
      lease: "s ecret",
      afterSequence: 20,
      webSocketFactory: factory,
      onEnvelope: (value) => { received.push(value); },
      onStatus: (status) => statuses.push(status),
    });
    stream.connect();
    expect(urls[0]).toContain("after_sequence=20");
    expect(urls[0]).toContain("lease=s+ecret");
    sockets[0].emitOpen();
    expect(statuses.at(-1)).toBe("reconnecting");
    sockets[0].emitMessage(envelope(21, "snapshot", { resynchronizes_after_sequence: 20 }));
    await Promise.resolve();
    expect(received).toHaveLength(1);
    expect(statuses.at(-1)).toBe("live");
    expect(stream.lastSequence).toBe(21);
  });

  it("keeps observer URLs lease-free, rejects malformed messages, and backs off", async () => {
    const urls: string[] = [];
    const { factory, sockets } = socketFactory(urls);
    const errors: Error[] = [];
    const scheduled: number[] = [];
    const timerCallbacks: Array<() => void> = [];
    const stream = new SimulationStream({
      apiBase: "http://localhost:8000",
      sessionId: "sim-1",
      role: "observer",
      lease: "must-not-appear",
      webSocketFactory: factory,
      onError: (error) => errors.push(error),
      setTimeout: (callback, delay) => {
        scheduled.push(delay);
        timerCallbacks.push(callback);
        return timerCallbacks.length;
      },
      clearTimeout: vi.fn(),
    });
    stream.connect();
    expect(urls[0]).not.toContain("lease=");
    sockets[0].emitOpen();
    sockets[0].emitMessage({ bad: true });
    await Promise.resolve();
    expect(errors[0]?.message).toMatch(/session_id|message/);
    sockets[0].emitClose();
    expect(scheduled[0]).toBe(250);
    timerCallbacks[0]();
    sockets[1].emitClose();
    expect(scheduled[1]).toBe(500);
    timerCallbacks[1]();
    sockets[2].emitClose();
    expect(scheduled[2]).toBe(1_000);
    timerCallbacks[2]();
    sockets[3].emitClose();
    expect(scheduled[3]).toBe(2_000);
  });

  it("requires the resynchronization marker on the first snapshot", async () => {
    const urls: string[] = [];
    const { factory, sockets } = socketFactory(urls);
    const errors: Error[] = [];
    const stream = new SimulationStream({
      apiBase: "http://localhost:8000",
      sessionId: "sim-1",
      webSocketFactory: factory,
      onError: (error) => errors.push(error),
    });
    stream.connect();
    sockets[0].emitOpen();
    sockets[0].emitMessage(envelope(1, "snapshot"));
    await Promise.resolve();
    expect(errors.map((error) => error.message).join(" ")).toContain("resynchronizes_after_sequence");
  });

  it("parses only strict envelope shapes", () => {
    expect(parseStreamEnvelope(envelope(1, "domain_event"))).toMatchObject({ sequence: 1, kind: "domain_event" });
    expect(() => parseStreamEnvelope({ ...envelope(0, "domain_event"), sequence: 0 })).toThrow(/sequence/);
    expect(() => parseStreamEnvelope({ ...envelope(1, "domain_event"), payload: [] })).toThrow(/payload/);
  });
});
