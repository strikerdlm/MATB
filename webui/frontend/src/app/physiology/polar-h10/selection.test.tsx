import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PolarPage from "./page";
import * as api from "@/lib/physiology/api";
import { listParticipants } from "@/lib/api";
import type { PolarCapture } from "@/types/physiology";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("purpose=practice") }));
vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ locale: "en", copy: (_es: string, en: string) => en }) }));
vi.mock("@/lib/assigned-attempt", () => ({ useAssignedAttempt: () => ({ context: null, attempt: null }) }));
vi.mock("@/lib/assessment-admission", () => ({ useAssessmentAdmission: () => ({ admit: vi.fn() }) }));
vi.mock("@/lib/experiment-flow", () => ({ useReportExperimentFlow: vi.fn() }));
vi.mock("@/lib/api", () => ({ listParticipants: vi.fn() }));
vi.mock("@/components/experiments/ExperimentGuide", () => ({ ExperimentGuide: () => null }));
vi.mock("@/components/instructions/InstructionAudio", () => ({ InstructionAudio: () => null }));
vi.mock("@/components/physiology/PolarCaptureReview", () => ({ PolarCaptureReview: () => null }));
vi.mock("@/lib/physiology/api", () => ({
  getActivePolarCapture: vi.fn(), getPolarCapture: vi.fn(), validatePolarControl: vi.fn(), getPolarConnection: vi.fn(), createPolarCapture: vi.fn(), startPolarCapture: vi.fn(),
  addPolarMarker: vi.fn(), openPolarStream: vi.fn(), stopPolarCapture: vi.fn(),
  getPolarAnalysis: vi.fn(), connectPolar: vi.fn(), disconnectPolar: vi.fn(),
  scanPolar: vi.fn(), listenPolarBroadcast: vi.fn(), downloadPolarBundle: vi.fn(),
}));

describe("standalone Polar recording", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.mocked(api.getActivePolarCapture).mockResolvedValue(null);
    sessionStorage.clear();
    window.history.replaceState({}, "", "/physiology/polar-h10?purpose=practice");
    vi.mocked(listParticipants).mockResolvedValue([{ id: "P99", enrollment_date: "2026-10-02" }]);
    vi.mocked(api.getPolarConnection).mockResolvedValue({ connected: true, device_alias: "Polar H10", capabilities: null });
    vi.mocked(api.openPolarStream).mockResolvedValue({ close: vi.fn() } as unknown as WebSocket);
  });

  it("prepares and starts without a test-session ID", async () => {
    const capture: PolarCapture = {
      schema_version: "1.0", participant_pseudonym: "P99", device_alias: "Polar H10",
      capture_id: "capture-standalone", execution_purpose: "practice", lifecycle: "created", gap_count: 0,
      matb_session_kind: "generic", matb_session_id: "standalone:capture-standalone", artifact_state: "none",
      requested_settings: { ecg_sample_rate_hz: 130, acc_sample_rate_hz: 50, acc_range_g: 2 },
      resolved_settings: null, stream_counters: {}, connection_epoch: 0, incomplete_reasons: [],
      started_at_utc: null, ended_at_utc: null,
    };
    vi.mocked(api.createPolarCapture).mockResolvedValue({ capture, controller_lease: "test-lease" });
    vi.mocked(api.startPolarCapture).mockResolvedValue({ ...capture, lifecycle: "capturing" });
    render(<PolarPage />);
    const prepare = screen.getByRole("button", { name: "Prepare" });
    await screen.findByRole("option", { name: "P99" });
    expect(prepare).toBeDisabled();
    expect(screen.queryByRole("option", { name: "P01" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Pseudonym"), { target: { value: "P99" } });
    await waitFor(() => expect(prepare).toBeEnabled());
    expect(screen.queryByLabelText("ID de sesión")).not.toBeInTheDocument();
    fireEvent.click(prepare);
    const start = await screen.findByRole("button", { name: "Start recording" });
    await waitFor(() => expect(start).toBeEnabled());
    expect(api.createPolarCapture).toHaveBeenCalledWith(expect.objectContaining({ participant_pseudonym: "P99", execution_purpose: "practice", matb_session_kind: "generic" }));
    expect(vi.mocked(api.createPolarCapture).mock.calls[0][0].matb_session_id).toBeUndefined();
    fireEvent.click(start);
    await waitFor(() => expect(api.startPolarCapture).toHaveBeenCalledWith("capture-standalone", "test-lease"));
    await waitFor(() => expect(api.addPolarMarker).toHaveBeenCalledWith("capture-standalone", "test-lease", "TASK_PRE"));
  });

  it("honors a registered participant link without requiring a visit", async () => {
    window.history.replaceState({}, "", "/physiology/polar-h10?purpose=practice&participant=P99");
    render(<PolarPage />);
    await waitFor(() => expect(screen.getByRole("button", { name: "Prepare" })).toBeEnabled());
    expect(screen.getByLabelText("Pseudonym")).toHaveValue("P99");
  });

  it("requires an active registered participant and never substitutes a stale linked identity", async () => {
    window.history.replaceState({}, "", "/physiology/polar-h10?purpose=practice&participant=P01");
    vi.mocked(listParticipants).mockResolvedValue([
      { id: "P01", enrollment_date: "2026-10-02", archived: true },
      { id: "P99", enrollment_date: "2026-10-02" },
    ]);
    render(<PolarPage />);
    await screen.findByRole("option", { name: "P99" });
    expect(screen.queryByRole("option", { name: "P01" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Prepare" })).toBeDisabled();
    expect(api.createPolarCapture).not.toHaveBeenCalled();
  });

  it("explains a missing participant and preserves the selected capture settings", async () => {
    vi.mocked(api.createPolarCapture).mockRejectedValueOnce({ code: "participant_not_found" });
    render(<PolarPage />);
    await screen.findByRole("option", { name: "P99" });
    fireEvent.change(screen.getByLabelText("Pseudonym"), { target: { value: "P99" } });
    fireEvent.change(screen.getByLabelText("ACC Hz"), { target: { value: "100" } });
    fireEvent.click(screen.getByRole("button", { name: "Prepare" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("not registered");
    expect(screen.getByLabelText("Pseudonym")).toHaveValue("P99");
    expect(screen.getByLabelText("ACC Hz")).toHaveValue("100");
    expect(screen.getByRole("button", { name: "Prepare" })).toBeEnabled();
  });

  it("allows retrying participant loading without reconnecting the sensor", async () => {
    vi.mocked(listParticipants).mockRejectedValueOnce(new Error("offline"));
    render(<PolarPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Reload participants" }));
    await screen.findByRole("option", { name: "P99" });
    expect(listParticipants).toHaveBeenCalledTimes(2);
    expect(api.disconnectPolar).not.toHaveBeenCalled();
  });
});
