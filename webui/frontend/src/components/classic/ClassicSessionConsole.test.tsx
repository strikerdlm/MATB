import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ClassicSessionConsole } from "@/components/classic/ClassicSessionConsole";

const { mockPush, mockGet, mockPolar, mockPreflight, mockStart, mockAbort } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockGet: vi.fn(),
  mockPolar: vi.fn(),
  mockPreflight: vi.fn(),
  mockStart: vi.fn(),
  mockAbort: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));
vi.mock("@/lib/classic/api", () => ({
  getClassicSession: mockGet,
  getPolarStatus: mockPolar,
  polarPreflight: mockPreflight,
  startClassicSession: mockStart,
  abortClassicSession: mockAbort,
}));

const prepared = {
  id: "classic-1",
  participant_id: "P01",
  visit_id: 1,
  visit_ordinal: 1,
  workload_level: "LOW",
  attempt_number: 1,
  scenario_name: "military_aviation/low_workload.txt",
  scenario_sha256: "a".repeat(64),
  openmatb_source_sha256: "b".repeat(64),
  test_mode: false,
  wall_time_scale: 1,
  post_task_timeout_seconds: 600,
  status: "PREPARED",
  task_validity: "pending",
  physiology_quality: "pending",
  performance_only_override: false,
  failure_reason_code: null,
  battery_level_at_start: 91,
  created_at: "2026-08-23T00:00:00Z",
  baseline_started_at: null,
  task_started_at: null,
  task_finished_at: null,
  recovery_started_at: null,
  recovery_finished_at: null,
  finished_at: null,
};

describe("ClassicSessionConsole", () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockPreflight.mockReset();
    mockGet.mockResolvedValue(prepared);
    mockPolar.mockResolvedValue({
      state: "connected",
      connected_device_name: "Polar H10 1234",
      battery_level: 91,
      recording: false,
      reconnect_attempts: 0,
      preflight_ready: true,
      last_rr_at_utc_ns: String(BigInt(Date.now()) * BigInt(1_000_000)),
    });
    mockPreflight.mockResolvedValue({
      ready: true,
      heart_rate_bpm: 67,
      rr_count: 1,
      sensor_contact_detected: true,
      battery_level: 91,
      measured_at_utc_ns: String(BigInt(Date.now()) * BigInt(1_000_000)),
      reason_code: null,
    });
    mockStart.mockResolvedValue({ ...prepared, status: "BASELINE", baseline_started_at: "2026-08-23T00:00:00Z" });
    mockAbort.mockResolvedValue({ ...prepared, status: "ABORTED", failure_reason_code: "participant_requested_stop" });
    sessionStorage.setItem("matb.classic.classic-1.lease", "secret");
  });

  it("starts the automatic baseline-task-recovery protocol with the stored lease", async () => {
    mockGet
      .mockResolvedValueOnce(prepared)
      .mockResolvedValue({ ...prepared, status: "BASELINE", baseline_started_at: "2026-08-23T00:00:00Z" });
    const user = userEvent.setup();
    render(<ClassicSessionConsole sessionId="classic-1" />);

    await waitFor(() => expect(screen.getByText(/prepared/i)).toBeInTheDocument());
    expect(screen.getByText(/25-minute collection plus up to 10 minutes/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /start 25-minute collection/i }));

    expect(mockStart).toHaveBeenCalledWith("classic-1", "secret");
    expect(await screen.findByText(/automatic phase control is active/i)).toBeInTheDocument();
    expect(screen.getByText("Baseline")).toBeInTheDocument();
    expect(screen.getByText("MATB task")).toBeInTheDocument();
    expect(screen.getByText("Recovery")).toBeInTheDocument();
  });

  it("records an operator abort reason through the controller lease", async () => {
    const user = userEvent.setup();
    render(<ClassicSessionConsole sessionId="classic-1" />);
    await waitFor(() => expect(screen.getByRole("button", { name: /abort session/i })).toBeEnabled());
    await user.selectOptions(
      screen.getByRole("combobox", { name: /abort reason/i }),
      "operator_safety_stop",
    );
    await user.click(screen.getByRole("button", { name: /abort session/i }));

    await waitFor(() => expect(mockAbort).toHaveBeenCalledWith(
      "classic-1",
      "secret",
      "operator_safety_stop",
    ));
    expect(mockPush).toHaveBeenCalledWith("/classic/debrief?session=classic-1");
  });

  it("prominently labels an accelerated non-production session", async () => {
    mockGet.mockResolvedValue({ ...prepared, test_mode: true, wall_time_scale: 0.001 });

    render(<ClassicSessionConsole sessionId="classic-1" />);

    expect(await screen.findByText(/test mode.*0\.001/i)).toBeInTheDocument();
  });

  it("lets the operator refresh a prepared session's Polar RR preflight", async () => {
    const user = userEvent.setup();
    render(<ClassicSessionConsole sessionId="classic-1" />);

    await user.click(await screen.findByRole("button", { name: /recheck polar rr/i }));

    expect(mockPreflight).toHaveBeenCalledWith(8);
    expect(await screen.findByText(/rr preflight refreshed.*67 bpm/i)).toBeInTheDocument();
  });

  it("exposes the bounded post-task questionnaire interval", async () => {
    mockGet.mockResolvedValue({
      ...prepared,
      status: "POST_TASK",
      task_started_at: "2026-08-23T00:00:00Z",
      task_finished_at: new Date().toISOString(),
    });

    render(<ClassicSessionConsole sessionId="classic-1" />);

    expect(await screen.findByRole("heading", { name: /post-task questionnaire/i })).toBeInTheDocument();
    expect(screen.getByText(/10-minute response limit/i)).toBeInTheDocument();
  });
});
