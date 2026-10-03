import React from "react";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import Page from "./page";
import { listParticipants } from "@/lib/api";
import * as api from "@/lib/physiology/api";
import type { PolarCapture } from "@/types/physiology";
vi.mock("@/lib/assigned-attempt", () => ({ useAssignedAttempt: () => ({ context: null, attempt: null }) }));
vi.mock("@/lib/assessment-admission", () => ({ useAssessmentAdmission: () => ({ admit: vi.fn() }) }));
vi.mock("@/lib/execution-purpose", () => ({ useExecutionPurpose: () => "practice", withExecutionPurpose: (s: string) => s }));
vi.mock("@/lib/experiment-flow", () => ({ useReportExperimentFlow: vi.fn() }));
vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ locale: "en", copy: (_es: string, en: string) => en }) }));
vi.mock("@/components/experiments/ExperimentGuide", () => ({ ExperimentGuide: () => null }));
vi.mock("@/lib/api", () => ({ listParticipants: vi.fn() }));
vi.mock("@/components/physiology/PolarCaptureReview", () => ({ PolarCaptureReview: () => null }));
vi.mock("@/lib/physiology/api", () => ({
  getPolarConnection: vi.fn(), getActivePolarCapture: vi.fn(), getPolarCapture: vi.fn(), validatePolarControl: vi.fn(),
  openPolarStream: vi.fn(), createPolarCapture: vi.fn(), startPolarCapture: vi.fn(), stopPolarCapture: vi.fn(),
  getPolarAnalysis: vi.fn(), addPolarMarker: vi.fn(), scanPolar: vi.fn(), connectPolar: vi.fn(), disconnectPolar: vi.fn(),
  listenPolarBroadcast: vi.fn(), downloadPolarBundle: vi.fn(),
}));
const active = { capture_id: "capture-current", participant_pseudonym: "P02", execution_purpose: "practice", matb_session_kind: "generic", matb_session_id: "capture-current", lifecycle: "capturing", requested_settings: {}, artifact_state: "partial", incomplete_reasons: [] } as unknown as PolarCapture;
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear();
  vi.mocked(listParticipants).mockResolvedValue(["P01", "P02", "P03", "P99"].map(id => ({ id, enrollment_date: "2026-10-02" })));
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
  await screen.findByRole("option", { name: "P01" });
  fireEvent.change(screen.getByLabelText("Pseudonym"), { target: { value: "P01" } });
  await waitFor(() => expect(screen.getByRole("button", { name: "Prepare" })).toBeEnabled());
  expect(screen.queryByLabelText("MATB session ID")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Prepare" }));
  const start = screen.getByRole("button", { name: "Start recording" });
  await waitFor(() => expect(start).toBeEnabled());
  fireEvent.click(start);
  await screen.findByRole("button", { name: "Stop and finalize" });
  expect(api.createPolarCapture).toHaveBeenCalledWith(expect.objectContaining({ matb_session_kind: "generic", matb_session_id: undefined, execution_purpose: "practice" }));
  expect(api.addPolarMarker).toHaveBeenCalledWith("capture-current", "valid", "TASK_PRE");
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
  await screen.findByText(/An assigned visit reserves the station/);
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
  await waitFor(() => expect(api.getPolarAnalysis).toHaveBeenCalled());
  expect(screen.queryByText("Five-minute phase response")).not.toBeInTheDocument();
  vi.mocked(api.getActivePolarCapture).mockResolvedValue({ ...active, capture_id: "other-capture", participant_pseudonym: "P03" });
  fireEvent.click(screen.getByRole("button", { name: "Refresh status" }));
  await screen.findByText("other-capture");
  await waitFor(() => expect(screen.queryByText("Five-minute phase response")).not.toBeInTheDocument());
});
it("explains an unregistered pseudonym without suggesting a connection problem", async () => {
  vi.mocked(api.createPolarCapture).mockRejectedValue({ code: "participant_not_found" });
  render(<Page />);
  await screen.findByRole("option", { name: "P01" });
  fireEvent.change(screen.getByLabelText("Pseudonym"), { target: { value: "P99" } });
  const prepare = screen.getByRole("button", { name: "Prepare" });
  await waitFor(() => expect(prepare).toBeEnabled());
  fireEvent.click(prepare);
  await screen.findByText(/participant is not registered/);
  expect(screen.getByRole("button", { name: "Start recording" })).toBeDisabled();
  expect(api.startPolarCapture).not.toHaveBeenCalled();
});

const strap = (token: string, alias = "Polar H10 1") => ({ device_token: token, alias, connectable: true, rssi: -55, broadcast_hr_bpm: null, broadcast_contact: null, token_expires_in_seconds: 60 });
const caps = { device_alias: "Polar H10 1", battery_percent: 85, firmware: "test" } as Awaited<ReturnType<typeof api.connectPolar>>;

async function disconnectedPage() {
  vi.mocked(api.getPolarConnection).mockResolvedValue({ connected: false, device_alias: null, capabilities: null });
  render(<Page />);
  const find = screen.getByRole("button", { name: "Find and connect H10" });
  await waitFor(() => expect(find).toBeEnabled());
  expect(screen.getByRole("button", { name: "Prepare" })).toHaveAccessibleDescription("Connect the H10 first. Press Find and connect H10.");
  return find;
}

it("connects a single discovered strap without starting or preparing a recording", async () => {
  vi.mocked(api.scanPolar).mockResolvedValue([strap("fresh")]);
  vi.mocked(api.connectPolar).mockResolvedValue(caps);
  fireEvent.click(await disconnectedPage());
  await screen.findByRole("button", { name: "Change strap" });
  expect(api.scanPolar).toHaveBeenCalledWith(8);
  expect(api.connectPolar).toHaveBeenCalledWith("fresh");
  expect(api.createPolarCapture).not.toHaveBeenCalled();
  expect(api.startPolarCapture).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Prepare" })).toHaveAccessibleDescription("Select the participant under Pseudonym to enable Prepare.");
});

it("requires a choice when several straps are visible, including occupied ones", async () => {
  vi.mocked(api.scanPolar).mockResolvedValue([strap("one"), { ...strap("two", "Polar H10 2"), connectable: false }]);
  vi.mocked(api.connectPolar).mockResolvedValue(caps);
  fireEvent.click(await disconnectedPage());
  const first = await screen.findByRole("button", { name: "Connect Polar H10 1" });
  expect(screen.getByRole("button", { name: "Connect Polar H10 2" })).toBeDisabled();
  expect(api.connectPolar).not.toHaveBeenCalled();
  fireEvent.click(first);
  await waitFor(() => expect(api.connectPolar).toHaveBeenCalledWith("one"));
});

it("explains an empty scan and retries discovery after a consumed connection token", async () => {
  vi.mocked(api.scanPolar).mockResolvedValueOnce([]).mockResolvedValueOnce([strap("first")]).mockResolvedValueOnce([strap("retry")]);
  vi.mocked(api.connectPolar).mockRejectedValueOnce({ code: "polar_connection_failed" }).mockResolvedValue(caps);
  const find = await disconnectedPage();
  fireEvent.click(find);
  await screen.findByText(/No H10 appeared/);
  expect(api.connectPolar).not.toHaveBeenCalled();
  fireEvent.click(find);
  await screen.findByText(/H10 was found but could not connect/);
  fireEvent.click(find);
  await screen.findByRole("button", { name: "Change strap" });
  expect(vi.mocked(api.connectPolar).mock.calls.map(args => args[0])).toEqual(["first", "retry"]);
});

it("changes a finished strap in one action and requires selecting the next participant", async () => {
  const finished = { ...active, lifecycle: "complete" as const, artifact_state: "finalized" as const };
  sessionStorage.setItem("polar.selected", active.capture_id);
  sessionStorage.setItem(`polar.controller.${active.capture_id}`, "valid");
  vi.mocked(api.getPolarCapture).mockResolvedValue(finished);
  vi.mocked(api.validatePolarControl).mockResolvedValue(finished);
  vi.mocked(api.disconnectPolar).mockResolvedValue({ connected: false, device_alias: null, capabilities: null });
  vi.mocked(api.scanPolar).mockResolvedValue([strap("next")]);
  vi.mocked(api.connectPolar).mockResolvedValue(caps);
  render(<Page />);
  const change = await screen.findByRole("button", { name: "Change strap" });
  await waitFor(() => expect(change).toBeEnabled());
  fireEvent.click(change);
  await screen.findByText(/Last saved recording.*P02/);
  await waitFor(() => expect(api.connectPolar).toHaveBeenCalledWith("next"));
  expect(vi.mocked(api.disconnectPolar).mock.invocationCallOrder[0]).toBeLessThan(vi.mocked(api.scanPolar).mock.invocationCallOrder[0]);
  expect(screen.getByLabelText("Pseudonym")).toHaveValue("");
  expect(screen.getByRole("button", { name: "Prepare" })).toBeDisabled();
  expect(sessionStorage.getItem(`polar.controller.${active.capture_id}`)).toBe("valid");
});

it("does not disconnect an active recording to switch straps", async () => {
  vi.mocked(api.getActivePolarCapture).mockResolvedValue(active);
  sessionStorage.setItem(`polar.controller.${active.capture_id}`, "valid");
  render(<Page />);
  await screen.findByRole("button", { name: "Stop and finalize" });
  expect(screen.getByRole("button", { name: "Change strap" })).toBeDisabled();
  expect(api.disconnectPolar).not.toHaveBeenCalled();
  expect(api.scanPolar).not.toHaveBeenCalled();
});

it("keeps the finished capture selected if disconnecting the previous strap fails", async () => {
  const finished = { ...active, lifecycle: "complete" as const, artifact_state: "finalized" as const };
  sessionStorage.setItem("polar.selected", active.capture_id);
  sessionStorage.setItem(`polar.controller.${active.capture_id}`, "valid");
  vi.mocked(api.getPolarCapture).mockResolvedValue(finished);
  vi.mocked(api.validatePolarControl).mockResolvedValue(finished);
  vi.mocked(api.disconnectPolar).mockRejectedValue({ code: "capture_active" });
  render(<Page />);
  const change = await screen.findByRole("button", { name: "Change strap" });
  await waitFor(() => expect(change).toBeEnabled());
  fireEvent.click(change);
  await screen.findByText(/Finalize the current recording before changing straps/);
  expect(sessionStorage.getItem("polar.selected")).toBe(active.capture_id);
  expect(screen.getByLabelText("Pseudonym")).toHaveValue("P02");
  expect(api.scanPolar).not.toHaveBeenCalled();
});
