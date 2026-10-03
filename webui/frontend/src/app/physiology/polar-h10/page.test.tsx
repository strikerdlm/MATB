import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import Page from "./page";
import * as api from "@/lib/physiology/api";
import type { PolarCapture } from "@/types/physiology";
vi.mock("@/lib/assigned-attempt", () => ({ useAssignedAttempt: () => ({ context: null, attempt: null }) }));
vi.mock("@/lib/assessment-admission", () => ({ useAssessmentAdmission: () => ({ admit: vi.fn() }) }));
vi.mock("@/lib/execution-purpose", () => ({ useExecutionPurpose: () => "practice", withExecutionPurpose: (s: string) => s }));
vi.mock("@/lib/experiment-flow", () => ({ useReportExperimentFlow: vi.fn() }));
vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ locale: "en", copy: (_es: string, en: string) => en }) }));
vi.mock("@/components/experiments/ExperimentGuide", () => ({ ExperimentGuide: () => null }));
vi.mock("@/lib/physiology/api", () => ({
  getPolarConnection: vi.fn(), getActivePolarCapture: vi.fn(), getPolarCapture: vi.fn(), validatePolarControl: vi.fn(),
  openPolarStream: vi.fn(), createPolarCapture: vi.fn(), startPolarCapture: vi.fn(), stopPolarCapture: vi.fn(),
  getPolarAnalysis: vi.fn(), addPolarMarker: vi.fn(), scanPolar: vi.fn(), connectPolar: vi.fn(), disconnectPolar: vi.fn(),
  listenPolarBroadcast: vi.fn(), downloadPolarBundle: vi.fn(),
}));
const active = { capture_id: "capture-current", participant_pseudonym: "P02", execution_purpose: "practice", matb_session_kind: "generic", matb_session_id: "capture-current", lifecycle: "capturing", requested_settings: {}, artifact_state: "partial", incomplete_reasons: [] } as unknown as PolarCapture;
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear();
  vi.mocked(api.getPolarConnection).mockResolvedValue({ connected: true, device_alias: "Polar", capabilities: null });
  vi.mocked(api.getActivePolarCapture).mockResolvedValue(null);
  vi.mocked(api.openPolarStream).mockResolvedValue({ close: vi.fn() } as unknown as WebSocket);
  vi.mocked(api.validatePolarControl).mockResolvedValue(active);
  vi.mocked(api.getPolarCapture).mockResolvedValue(active);
});
it("prepares standalone without a MATB session or automatic baseline marker", async () => {
  vi.mocked(api.createPolarCapture).mockResolvedValue({ capture: { ...active, lifecycle: "created" }, controller_lease: "valid" });
  vi.mocked(api.startPolarCapture).mockResolvedValue(active);
  render(<Page />);
  expect(screen.getByRole("button", { name: "Prepare" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Pseudonym"), { target: { value: "P01" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "Prepare" })).toBeEnabled());
  expect(screen.queryByLabelText("MATB session ID")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Prepare" }));
  fireEvent.click(await screen.findByRole("button", { name: "Start recording" }));
  await screen.findByRole("button", { name: "Stop and finalize" });
  expect(api.createPolarCapture).toHaveBeenCalledWith(expect.objectContaining({ matb_session_kind: "generic", matb_session_id: undefined, execution_purpose: "practice" }));
  expect(api.addPolarMarker).not.toHaveBeenCalled();
});
it("restores actual active identity and valid lease, then finalizes despite analysis failure", async () => {
  sessionStorage.setItem("polar.selected", "old-capture");
  sessionStorage.setItem("polar.controller.capture-current", "valid");
  vi.mocked(api.getActivePolarCapture).mockResolvedValue(active);
  vi.mocked(api.stopPolarCapture).mockResolvedValue({ ...active, lifecycle: "complete", artifact_state: "finalized" });
  vi.mocked(api.getPolarAnalysis).mockRejectedValue(new Error("analysis unavailable"));
  render(<Page />);
  const stop = await screen.findByRole("button", { name: "Stop and finalize" });
  await waitFor(() => expect(stop).toBeEnabled());
  expect(screen.getByDisplayValue("P02")).toBeInTheDocument();
  expect(api.validatePolarControl).toHaveBeenCalledWith("capture-current", "valid");
  fireEvent.click(stop);
  await waitFor(() => expect(api.stopPolarCapture).toHaveBeenCalledWith("capture-current", "valid"));
  await waitFor(() => expect(screen.getByText(/complete · ECG/)).toBeInTheDocument());
});
it.each(["", "invalid"])("shows active identity without control for missing/invalid lease %s", async lease => {
  if (lease) sessionStorage.setItem("polar.controller.capture-current", lease);
  vi.mocked(api.getActivePolarCapture).mockResolvedValue(active);
  vi.mocked(api.validatePolarControl).mockRejectedValue(new Error("invalid lease"));
  render(<Page />);
  const stop = await screen.findByRole("button", { name: "Stop and finalize" });
  await waitFor(() => expect(screen.getByText(/owning browser tab/)).toBeInTheDocument());
  expect(stop).toBeDisabled();
  expect(screen.getByText("capture-current")).toBeInTheDocument();
  expect(api.stopPolarCapture).not.toHaveBeenCalled();
  expect(api.openPolarStream).not.toHaveBeenCalled();
});
it("keeps the prepared capture and explains a station-blocked start", async () => {
  sessionStorage.setItem("polar.selected", active.capture_id);
  sessionStorage.setItem(`polar.controller.${active.capture_id}`, "valid");
  const prepared = { ...active, lifecycle: "created" as const };
  vi.mocked(api.getPolarCapture).mockResolvedValue(prepared);
  vi.mocked(api.validatePolarControl).mockResolvedValue(prepared);
  vi.mocked(api.startPolarCapture).mockRejectedValue({ code: "station_visit_reserved" });
  render(<Page />);
  const start = await screen.findByRole("button", { name: "Start recording" });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  await screen.findByText(/Another visit owns the station/);
  expect(screen.getByText(active.capture_id)).toBeInTheDocument();
  expect(api.stopPolarCapture).not.toHaveBeenCalled();
});
it("does not restore an old capture when a pending refresh finishes after preparing another", async () => {
  const finished = { ...active, lifecycle: "complete" as const, artifact_state: "finalized" as const };
  sessionStorage.setItem("polar.selected", active.capture_id);
  sessionStorage.setItem(`polar.controller.${active.capture_id}`, "valid");
  vi.mocked(api.getPolarCapture).mockResolvedValue(finished);
  vi.mocked(api.validatePolarControl).mockResolvedValue(finished);
  render(<Page />);
  await screen.findByRole("button", { name: "Prepare another recording" });
  let resolve!: (value: PolarCapture) => void;
  vi.mocked(api.validatePolarControl).mockImplementationOnce(() => new Promise(r => { resolve = r; }));
  fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
  await waitFor(() => expect(resolve).toBeTypeOf("function"));
  fireEvent.click(screen.getByRole("button", { name: "Prepare another recording" }));
  resolve(finished);
  await waitFor(() => expect(screen.getByRole("button", { name: "Prepare" })).toBeEnabled());
  expect(sessionStorage.getItem("polar.selected")).toBe("");
});
it("clears previous phase analysis when another capture becomes active", async () => {
  sessionStorage.setItem(`polar.controller.${active.capture_id}`, "valid");
  vi.mocked(api.getActivePolarCapture).mockResolvedValue(active);
  vi.mocked(api.stopPolarCapture).mockResolvedValue({ ...active, lifecycle: "complete", artifact_state: "finalized" });
  vi.mocked(api.getPolarAnalysis).mockResolvedValue({ capture_id: active.capture_id, valid: true, workload_responses: [] } as unknown as Awaited<ReturnType<typeof api.getPolarAnalysis>>);
  render(<Page />);
  const stop = await screen.findByRole("button", { name: "Stop and finalize" });
  await waitFor(() => expect(stop).toBeEnabled());
  fireEvent.click(stop);
  await screen.findByText("Five-minute phase response");
  vi.mocked(api.getActivePolarCapture).mockResolvedValue({ ...active, capture_id: "other-capture", participant_pseudonym: "P03" });
  fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
  await screen.findByText("other-capture");
  await waitFor(() => expect(screen.queryByText("Five-minute phase response")).not.toBeInTheDocument());
});
it("explains an unregistered pseudonym without suggesting a connection problem", async () => {
  vi.mocked(api.createPolarCapture).mockRejectedValue({ code: "participant_not_found" });
  render(<Page />);
  fireEvent.change(screen.getByLabelText("Pseudonym"), { target: { value: "P99" } });
  const prepare = screen.getByRole("button", { name: "Prepare" });
  await waitFor(() => expect(prepare).toBeEnabled());
  fireEvent.click(prepare);
  await screen.findByText(/pseudonym is not registered/);
  expect(screen.queryByRole("button", { name: "Start recording" })).not.toBeInTheDocument();
  expect(api.startPolarCapture).not.toHaveBeenCalled();
});
