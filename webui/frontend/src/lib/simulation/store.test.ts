import { beforeEach, describe, expect, it, vi } from "vitest";
import { createSimulationStore, validCommandsFor } from "@/lib/simulation/store";
import type { JsonValue, SessionView, StreamEnvelope, WorldSnapshot } from "@/types/simulation";

const { getSimulationState, submitSimulationCommand } = vi.hoisted(() => ({
  getSimulationState: vi.fn(),
  submitSimulationCommand: vi.fn(),
}));
vi.mock("@/lib/simulation/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/simulation/api")>("@/lib/simulation/api");
  return { ...actual, getSimulationState, submitSimulationCommand };
});

const session: SessionView = {
  id: "sim-1",
  participant_id: "P01",
  visit_id: 1,
  visit_ordinal: 1,
  session_mode: "research",
  record_class: "research",
  selected_block_id: null,
  scenario_id: "reference_area_search",
  scenario_sha256: "a".repeat(64),
  locale: "en",
  lifecycle: "RUNNING",
  active_block_id: "PRACTICE",
  validity: "valid",
  block_order: ["LOW", "MEDIUM", "HIGH"],
  state_version: 0,
  simulation_time_ms: 0,
  created_at: null,
  started_at: null,
  finished_at: null,
  interrupted_at: null,
};

function snapshot(stateVersion: number, x_mm = 0, y_mm = 0, blockId = "PRACTICE"): WorldSnapshot {
  return {
    scenario_id: "reference_area_search",
    scenario_sha256: "a".repeat(64),
    block_id: blockId,
    tick: stateVersion,
    simulation_time_ms: stateVersion * 250,
    state_version: stateVersion,
    state_sha256: "b".repeat(64),
    title: { en: "Reference", "es-CO": "Referencia" },
    description: { en: "Reference", "es-CO": "Referencia" },
    terrain: { bounds: { min_x_mm: 0, min_y_mm: 0, max_x_mm: 1000, max_y_mm: 1000 }, polygon: [] },
    home: { x_mm: 0, y_mm: 0 },
    initial_view: { center: { x_mm: 500, y_mm: 500 }, width_mm: 1000, height_mm: 1000 },
    sectors: {},
    restricted_zones: {},
    report_note_codes: {},
    aircraft: {
      "UAS-01": {
        aircraft_id: "UAS-01",
        label: "UAS-01",
        position: { x_mm, y_mm },
        heading_mdeg: 0,
        energy_units: 100,
        predicted_home_reserve_units: 20,
        mode: "SEARCH",
        link: "NOMINAL",
        sensor: "NOMINAL",
        assigned_sector_id: "S1",
        route: [{ x_mm: 200, y_mm: 200 }],
        mission_progress_ppm: 100,
      },
    },
    contacts: {},
    alerts: {},
    coverage: { sectors: {} },
  };
}

function envelope(
  sequence: number,
  kind: StreamEnvelope["kind"],
  payload: Record<string, JsonValue>,
): StreamEnvelope {
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

describe("simulation store", () => {
  beforeEach(() => {
    getSimulationState.mockReset();
    submitSimulationCommand.mockReset();
    sessionStorage.clear();
  });

  it("applies ordered envelopes and fetches truth after a gap", async () => {
    const store = createSimulationStore();
    store.getState().initialize(session);
    getSimulationState.mockResolvedValue(snapshot(10));
    await store.getState().applyEnvelope(envelope(10, "snapshot", snapshot(10) as unknown as Record<string, JsonValue>));
    await store.getState().applyEnvelope(envelope(12, "domain_event", {}));
    expect(store.getState().connection).toBe("reconnecting");
    expect(getSimulationState).toHaveBeenCalledWith("sim-1");
    expect(store.getState().lastSequence).toBe(10);
  });

  it("never applies an older snapshot", () => {
    const store = createSimulationStore();
    store.getState().initialize(session);
    void store.getState().applyEnvelope(envelope(4, "snapshot", snapshot(8) as unknown as Record<string, JsonValue>));
    void store.getState().applyEnvelope(envelope(5, "snapshot", snapshot(7) as unknown as Record<string, JsonValue>));
    expect(store.getState().snapshot?.state_version).toBe(8);
  });

  it("accepts a lower engine version when the authoritative block changes", async () => {
    const store = createSimulationStore();
    store.getState().initialize(session, snapshot(8));
    await store.getState().applyEnvelope(envelope(1, "snapshot", snapshot(0, 0, 0, "LOW") as unknown as Record<string, JsonValue>));
    expect(store.getState().snapshot?.block_id).toBe("LOW");
    expect(store.getState().snapshot?.state_version).toBe(0);
  });

  it("accepts a jump only for a marked resynchronizing snapshot", async () => {
    const store = createSimulationStore();
    store.getState().initialize(session);
    await store.getState().applyEnvelope({
      ...envelope(20, "snapshot", { ...snapshot(20), resynchronizes_after_sequence: 4 } as unknown as Record<string, JsonValue>),
    });
    expect(store.getState().lastSequence).toBe(20);
    expect(store.getState().snapshot?.state_version).toBe(20);
  });

  it("uses the lifecycle carried by a resynchronizing snapshot", async () => {
    const store = createSimulationStore();
    store.getState().initialize(session, snapshot(4));
    await store.getState().applyEnvelope({
      ...envelope(20, "snapshot", { ...snapshot(20), lifecycle: "PAUSED", resynchronizes_after_sequence: 4 } as unknown as Record<string, JsonValue>),
    });
    expect(store.getState().session?.lifecycle).toBe("PAUSED");
    expect(store.getState().connection).toBe("paused");
  });

  it("tracks command pending state without optimistic aircraft mutation", async () => {
    const store = createSimulationStore();
    store.getState().initialize(session, snapshot(4));
    sessionStorage.setItem("matb.simulation.sim-1.lease", "secret");
    submitSimulationCommand.mockResolvedValue({
      command_id: "cmd-1", status: "accepted", code: "accepted", message: null,
      expected_state_version: 4, state_version: 5, simulation_time_ms: 1000, payload: {},
    });
    const promise = store.getState().submitCommand({
      command_id: "cmd-1", expected_state_version: 4, kind: "HOLD", payload: { aircraft_id: "UAS-01" },
    });
    expect(store.getState().pendingCommandIds).toContain("cmd-1");
    await promise;
    expect(store.getState().pendingCommandIds).not.toContain("cmd-1");
    expect(store.getState().snapshot?.aircraft["UAS-01"].mode).toBe("SEARCH");
  });

  it("changes paused lifecycle connection without discarding state", async () => {
    const store = createSimulationStore();
    store.getState().initialize(session, snapshot(4));
    await store.getState().applyEnvelope(envelope(1, "lifecycle", { event: "session_paused" }));
    expect(store.getState().connection).toBe("paused");
    expect(store.getState().snapshot?.state_version).toBe(4);
  });
});

describe("validCommandsFor", () => {
  it("mirrors safe aircraft and contact workflow affordances", () => {
    const aircraft = {
      aircraft_id: "UAS-01", label: "UAS-01", position: { x_mm: 0, y_mm: 0 }, heading_mdeg: 0,
      energy_units: 100, predicted_home_reserve_units: 20, mode: "HOLD", link: "NOMINAL", sensor: "NOMINAL",
      assigned_sector_id: null, route: [{ x_mm: 1, y_mm: 1 }], mission_progress_ppm: 0,
    };
    expect(validCommandsFor(aircraft as never)).toContain("RESUME_MISSION");
    expect(validCommandsFor({ ...aircraft, link: "LOST" } as never)).toEqual([]);
    const contact = {
      contact_id: "C-01", evidence: "INSPECTABLE", workflow: "DETECTED", classification: null,
      priority: null, report_ids: [], position: { x_mm: 1, y_mm: 1 },
    } as never;
    expect(validCommandsFor(contact)).toEqual(["INSPECT_CONTACT"]);
  });
});
