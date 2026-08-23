import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ClassicSetupConsole } from "@/components/classic/ClassicSetupConsole";
import type { Participant, StudyProtocol } from "@/types";

const {
  mockPush,
  mockStatus,
  mockScenarios,
  mockHistory,
  mockScan,
  mockConnect,
  mockDisconnect,
  mockPreflight,
  mockPrepare,
} = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockStatus: vi.fn(),
  mockScenarios: vi.fn(),
  mockHistory: vi.fn(),
  mockScan: vi.fn(),
  mockConnect: vi.fn(),
  mockDisconnect: vi.fn(),
  mockPreflight: vi.fn(),
  mockPrepare: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));
vi.mock("@/lib/classic/api", () => ({
  getPolarStatus: mockStatus,
  getClassicScenarios: mockScenarios,
  getClassicHistory: mockHistory,
  scanPolar: mockScan,
  connectPolar: mockConnect,
  disconnectPolar: mockDisconnect,
  polarPreflight: mockPreflight,
  prepareClassicSession: mockPrepare,
}));

const participants: Participant[] = [{ id: "P01", enrollment_date: "2026-08-23" }];
const protocol: StudyProtocol = {
  protocol_id: "astra-2026",
  protocol_version: "1.0.0",
  schedule_sha256: "hash",
  visits: [{ ordinal: 1, code: "T0", scheduled_day: 0 }],
};

describe("ClassicSetupConsole", () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockStatus.mockResolvedValue({
      state: "disconnected",
      backend_name: "bleak",
      connected_device_name: null,
      battery_level: null,
      recording: false,
      reconnect_attempts: 0,
      last_error_code: null,
      preflight_ready: false,
      last_rr_at_utc_ns: null,
      sensor_contact_detected: null,
    });
    mockScenarios.mockResolvedValue([
      { name: "military_aviation/low_workload.txt", workload_level: "LOW" },
      { name: "military_aviation/medium_workload.txt", workload_level: "MEDIUM" },
      { name: "military_aviation/high_workload.txt", workload_level: "HIGH" },
    ]);
    mockHistory.mockResolvedValue([]);
    mockScan.mockResolvedValue([{
      device_token: "opaque",
      display_name: "Polar H10 1234",
      rssi: -42,
      is_polar_h10: true,
      heart_rate_service_advertised: true,
      token_expires_at_utc_ns: "1",
    }]);
    mockConnect.mockResolvedValue({
      state: "connected",
      backend_name: "bleak",
      connected_device_name: "Polar H10 1234",
      battery_level: 91,
      recording: false,
      reconnect_attempts: 0,
      last_error_code: null,
      preflight_ready: false,
      last_rr_at_utc_ns: null,
      sensor_contact_detected: true,
    });
    mockDisconnect.mockResolvedValue({
      state: "disconnected",
      backend_name: "bleak",
      connected_device_name: null,
      battery_level: null,
      recording: false,
      reconnect_attempts: 0,
      last_error_code: null,
      preflight_ready: false,
      last_rr_at_utc_ns: null,
      sensor_contact_detected: null,
    });
    mockPreflight.mockResolvedValue({
      ready: true,
      heart_rate_bpm: 63,
      rr_count: 2,
      sensor_contact_detected: true,
      battery_level: 91,
      measured_at_utc_ns: "1",
      reason_code: null,
    });
    mockPrepare.mockResolvedValue({ id: "classic-1", status: "PREPARED", controller_lease: "secret" });
    sessionStorage.clear();
  });

  it("requires live RR preflight, stores the lease locally, and prepares the matched workload", async () => {
    const user = userEvent.setup();
    render(<ClassicSetupConsole participants={participants} protocol={protocol} />);

    await waitFor(() => expect(screen.getByRole("button", { name: /scan for polar h10/i })).toBeEnabled());
    expect(screen.getByText(/allow up to 35 minutes total/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /prepare classic matb/i })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /scan for polar h10/i }));
    await user.click(await screen.findByRole("button", { name: /connect polar h10 1234/i }));
    await user.click(screen.getByRole("button", { name: /verify live rr signal/i }));

    await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
    await user.selectOptions(screen.getByLabelText(/visit/i), "1");
    await user.selectOptions(screen.getByLabelText(/workload/i), "HIGH");
    await user.click(screen.getByRole("button", { name: /prepare classic matb/i }));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/classic/session?session=classic-1"));
    expect(mockPrepare).toHaveBeenCalledWith(expect.objectContaining({
      participant_id: "P01",
      visit_ordinal: 1,
      workload_level: "HIGH",
      scenario_name: "military_aviation/high_workload.txt",
      performance_only_override: false,
    }));
    expect(sessionStorage.getItem("matb.classic.classic-1.lease")).toBe("secret");
    expect(mockPush.mock.calls[0][0]).not.toContain("secret");
  });

  it("makes the performance-only exception explicit and reason-coded", async () => {
    const user = userEvent.setup();
    render(<ClassicSetupConsole participants={participants} protocol={protocol} />);
    await waitFor(() => expect(screen.getByText(/polar h10 acquisition/i)).toBeInTheDocument());
    await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
    await user.selectOptions(screen.getByLabelText(/visit/i), "1");
    await user.click(screen.getByLabelText(/performance-only exception/i));

    expect(screen.getByLabelText(/exception reason code/i)).toHaveAttribute(
      "pattern",
      "[a-z0-9][a-z0-9_\\-]{0,63}",
    );
    const prepare = screen.getByRole("button", { name: /prepare classic matb/i });
    expect(prepare).toBeDisabled();
    await user.type(screen.getByLabelText(/exception reason code/i), "sensor_unavailable");
    expect(prepare).toBeEnabled();
    await user.click(prepare);

    expect(mockPrepare).toHaveBeenCalledWith(expect.objectContaining({
      performance_only_override: true,
      override_reason_code: "sensor_unavailable",
    }));
  });

  it("requires the exception reason even after a prior good physiology preflight", async () => {
    mockStatus.mockResolvedValueOnce({
      state: "connected",
      backend_name: "bleak",
      connected_device_name: "Polar H10 1234",
      battery_level: 91,
      recording: false,
      reconnect_attempts: 0,
      last_error_code: null,
      preflight_ready: true,
      last_rr_at_utc_ns: "1",
      sensor_contact_detected: true,
    });
    const user = userEvent.setup();
    render(<ClassicSetupConsole participants={participants} protocol={protocol} />);
    await user.selectOptions(await screen.findByLabelText(/participant/i), "P01");
    await user.selectOptions(screen.getByLabelText(/visit/i), "1");
    await user.click(screen.getByLabelText(/performance-only exception/i));

    expect(screen.getByRole("button", { name: /prepare classic matb/i })).toBeDisabled();
  });

  it("disconnects and clears stale preflight state before switching sensors", async () => {
    mockStatus.mockResolvedValueOnce({
      state: "connected",
      backend_name: "bleak",
      connected_device_name: "Polar H10 1234",
      battery_level: 91,
      recording: false,
      reconnect_attempts: 0,
      last_error_code: null,
      preflight_ready: true,
      last_rr_at_utc_ns: "1",
      sensor_contact_detected: true,
    });
    const user = userEvent.setup();
    render(<ClassicSetupConsole participants={participants} protocol={protocol} />);

    await user.click(await screen.findByRole("button", { name: /disconnect.*switch sensor/i }));

    await waitFor(() => expect(mockDisconnect).toHaveBeenCalledTimes(1));
    expect(screen.getByRole("button", { name: /scan for polar h10/i })).toBeEnabled();
  });
});
