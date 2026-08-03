import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MissionSetupForm } from "@/components/mission/setup/MissionSetupForm";
import type { Participant, Visit } from "@/types";
import type { PreparedSession, ScenarioSummary } from "@/types/simulation";

const { mockPush, mockCreate, mockGetSession, mockListVisits } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockCreate: vi.fn(),
  mockGetSession: vi.fn(),
  mockListVisits: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));
vi.mock("@/lib/simulation/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/simulation/api")>("@/lib/simulation/api");
  return { ...actual, createSimulationSession: mockCreate, getSimulationSession: mockGetSession };
});
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, listVisits: mockListVisits };
});

const participants: Participant[] = [{ id: "P01", enrollment_date: "2026-01-01" }];
const visits: Visit[] = [{ id: 1, participant_id: "P01", visit_ordinal: 1, scheduled_day: 0, status: "planned" }];
const scenarios: ScenarioSummary[] = [{
  scenario_id: "reference_area_search",
  scenario_sha256: "abcdef0123456789".repeat(4),
  title: "Reference area search",
  description: "Synthetic area search",
  aircraft_count: 4,
  block_order: ["PRACTICE", "LOW", "MEDIUM", "HIGH"],
  locales: ["en", "es-CO"],
}];
const preparedSession: PreparedSession = {
  id: "sim-1", participant_id: "P01", visit_id: 1, visit_ordinal: 1,
  scenario_id: "reference_area_search", scenario_sha256: "abcdef0123456789".repeat(4), locale: "es-CO",
  lifecycle: "PREPARED", active_block_id: null, validity: "valid", block_order: ["LOW", "MEDIUM", "HIGH"],
  state_version: 0, simulation_time_ms: 0, created_at: null, started_at: null,
  finished_at: null, interrupted_at: null, controller_lease: "secret",
};

async function completeAndSubmit(user: ReturnType<typeof userEvent.setup>) {
  await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
  await waitFor(() => expect(screen.getByRole("option", { name: "1" })).toBeInTheDocument());
  await user.selectOptions(screen.getByLabelText(/visit/i), "1");
  await user.selectOptions(screen.getByLabelText(/scenario/i), "reference_area_search");
  await user.selectOptions(screen.getByLabelText(/language/i), "es-CO");
  await user.click(screen.getByRole("checkbox", { name: /research instrument/i }));
  await user.click(screen.getByRole("button", { name: /prepare session/i }));
}

describe("MissionSetupForm", () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockCreate.mockReset();
    mockGetSession.mockReset();
    mockListVisits.mockReset();
    mockListVisits.mockResolvedValue(visits);
    window.sessionStorage.clear();
  });

  it("requires participant visit scenario locale and acknowledgement", async () => {
    const user = userEvent.setup();
    render(<MissionSetupForm participants={participants} scenarios={scenarios} />);
    expect(screen.getByRole("button", { name: /prepare session/i })).toBeDisabled();
    await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
    await waitFor(() => expect(screen.getByRole("option", { name: "1" })).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/visit/i), "1");
    await user.selectOptions(screen.getByLabelText(/scenario/i), "reference_area_search");
    await user.selectOptions(screen.getByLabelText(/language/i), "es-CO");
    expect(screen.getByRole("button", { name: /prepare session/i })).toBeDisabled();
    await user.click(screen.getByRole("checkbox", { name: /research instrument/i }));
    expect(screen.getByRole("button", { name: /prepare session/i })).toBeEnabled();
  });

  it("stores the lease in sessionStorage and never renders it", async () => {
    mockCreate.mockResolvedValue(preparedSession);
    const user = userEvent.setup();
    render(<MissionSetupForm participants={participants} scenarios={scenarios} />);
    await completeAndSubmit(user);
    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/mission?session=sim-1"));
    expect(window.sessionStorage.getItem("matb.simulation.sim-1.lease")).toBe("secret");
    expect(document.body).not.toHaveTextContent("secret");
  });

  it("only clears an older lease after confirming a terminal session", async () => {
    window.sessionStorage.setItem("matb.simulation.old-active.lease", "keep-me");
    window.sessionStorage.setItem("matb.simulation.old-finished.lease", "remove-me");
    mockGetSession.mockImplementation(async (id: string) => ({ lifecycle: id === "old-finished" ? "FINISHED" : "RUNNING" }));
    mockCreate.mockResolvedValue(preparedSession);
    const user = userEvent.setup();
    render(<MissionSetupForm participants={participants} scenarios={scenarios} />);
    await completeAndSubmit(user);
    await waitFor(() => expect(mockPush).toHaveBeenCalled());
    expect(window.sessionStorage.getItem("matb.simulation.old-active.lease")).toBe("keep-me");
    expect(window.sessionStorage.getItem("matb.simulation.old-finished.lease")).toBeNull();
  });
});
