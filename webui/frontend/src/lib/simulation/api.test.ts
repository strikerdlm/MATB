import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  SimulationApiError,
  createSimulationSession,
  createTechnicalSimulationSession,
  getSimulationState,
  simulationWsUrl,
  submitSimulationCommand,
  transitionSession,
} from "@/lib/simulation/api";
import { resetApiBaseCache } from "@/lib/runtime-config";
import type { PreparedSession, WorldSnapshot } from "@/types/simulation";

function mockFetch(status: number, body: unknown) {
  return vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    statusText: status === 200 ? "OK" : "Created",
    json: async () => body,
  } as Response);
}

const prepared: PreparedSession = {
  id: "sim-1", participant_id: "P01", visit_id: 1, visit_ordinal: 1,
  session_mode: "research", record_class: "research", selected_block_id: null,
  scenario_id: "reference_area_search", scenario_sha256: "a".repeat(64), locale: "es-CO",
  lifecycle: "PREPARED", active_block_id: null, validity: "valid",
  block_order: ["LOW", "MEDIUM", "HIGH"], state_version: 0, simulation_time_ms: 0,
  created_at: null, started_at: null, finished_at: null, interrupted_at: null,
  controller_lease: "secret",
};

const session = { ...prepared, controller_lease: undefined };
const snapshot = { scenario_id: "reference_area_search" } as unknown as WorldSnapshot;

describe("simulation API adapter", () => {
  beforeEach(() => {
    resetApiBaseCache();
    vi.restoreAllMocks();
  });

  it("prepares a session and sends the controller header only on mutations", async () => {
    global.fetch = mockFetch(201, prepared);
    const result = await createSimulationSession({
        execution_purpose: "study",
      participant_id: "P01", visit_ordinal: 1,
      scenario_id: "reference_area_search", locale: "es-CO",
    });
    expect(result.controller_lease).toBe("secret");
    const [, createInit] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(new Headers(createInit.headers).get("X-Simulation-Controller")).toBeNull();

    global.fetch = mockFetch(200, session);
    await transitionSession(prepared.id, "start", "secret", { block_id: "PRACTICE" });
    const [, transitionInit] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(new Headers(transitionInit.headers).get("X-Simulation-Controller")).toBe("secret");
  });

  it("prepares a segregated technical session through its dedicated endpoint", async () => {
    global.fetch = mockFetch(201, prepared);
    await createTechnicalSimulationSession({
        execution_purpose: "practice",
      scenario_id: "reference_area_search",
      block_id: "HIGH",
      locale: "es-CO",
    });
    const [url, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toContain("/simulation/technical-sessions");
    expect(JSON.parse(init.body as string)).toEqual({
      execution_purpose: "practice",
      scenario_id: "reference_area_search",
      block_id: "HIGH",
      locale: "es-CO",
    });
  });

  it("converts local HTTP API bases to WebSocket URLs", () => {
    expect(simulationWsUrl("http://127.0.0.1:8000", "sim-1", 20))
      .toBe("ws://127.0.0.1:8000/simulation/sessions/sim-1/stream?after_sequence=20");
    expect(simulationWsUrl("https://lab-host:8443", "sim/1", 0, "s ecret"))
      .toContain("wss://lab-host:8443/simulation/sessions/sim%2F1/stream?after_sequence=0&lease=s+ecret");
  });

  it("maps structured backend errors into stable SimulationApiError", async () => {
    global.fetch = mockFetch(409, {
      detail: { code: "active_session", message: "another session is active", context: { active: true } },
    });
    await expect(getSimulationState("sim-1")).rejects.toMatchObject({
      status: 409, code: "active_session", message: "another session is active",
    } satisfies Partial<SimulationApiError>);
  });

  it("posts command JSON with the controller lease", async () => {
    global.fetch = mockFetch(200, { command_id: "cmd-1", status: "accepted", payload: {} });
    await submitSimulationCommand("sim-1", "secret", {
      command_id: "cmd-1", expected_state_version: 4, kind: "HOLD", payload: { aircraft_id: "UAS-01" },
    });
    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(new Headers(init.headers).get("X-Simulation-Controller")).toBe("secret");
    expect(JSON.parse(init.body as string).kind).toBe("HOLD");
  });

  it("fetches authoritative state without a lease header", async () => {
    global.fetch = mockFetch(200, snapshot);
    await getSimulationState("sim-1");
    const [, init] = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(new Headers(init.headers).get("X-Simulation-Controller")).toBeNull();
  });
});
