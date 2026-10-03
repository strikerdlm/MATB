import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PolarCaptureReview } from "./PolarCaptureReview";
import * as api from "@/lib/physiology/api";
import type { PolarCapture, PolarRRExport, PolarReview } from "@/types/physiology";

vi.mock("@/components/charts/EChart", () => ({ EChart: () => <div>Signal figure</div> }));
vi.mock("@/lib/physiology/api", () => ({ getPolarReview: vi.fn(), getPolarRRExport: vi.fn(), downloadPolarRRFile: vi.fn() }));
const copy = (_es: string, en: string) => en;
const capture = { capture_id: "capture-1", execution_purpose: "practice", artifact_state: "finalized" } as PolarCapture;
const exported: PolarRRExport = {
  capture_id: "capture-1", execution_purpose: "practice", units: "ms", row_count: 2, rr_count: 2,
  excluded_nonpositive_or_nonfinite: 0, contact_not_detected_count: 0, segment_count: 1,
  segments: [{ segment_id: 1, rr_count: 2, first_beat_index: 1, last_beat_index: 2, txt_filename: "practice_rr_ms.txt", csv_filename: "practice_rr_ms.csv" }],
  preview: [{ beat_index: 1, rr_ms: 1000.9765625, segment_id: 1 }], files: [], incomplete_reasons: [],
};
const review: PolarReview = {
  schema_version: "1.0", capture_id: "capture-1", execution_purpose: "practice", metrics: null,
  rr_tachogram: [[0, 1000]], poincare: [], incomplete_reasons: [],
  respiration: { status: "unavailable", respiratory_rate_bpm: null, accuracy_bpm: null,
    validated_against_reference: false, accepted_windows: 0, evaluated_windows: 0, accepted_window_percent: 0,
    windows: [], waveform: [] },
};
beforeEach(() => {
  vi.resetAllMocks();
  vi.mocked(api.getPolarRRExport).mockResolvedValue(exported);
  vi.mocked(api.getPolarReview).mockResolvedValue(review);
  vi.mocked(api.downloadPolarRRFile).mockResolvedValue();
});

describe("finalized Polar review", () => {
  it("downloads exact RR milliseconds even for standalone practice", async () => {
    render(<PolarCaptureReview capture={capture} lease="secret-lease" copy={copy} />);
    fireEvent.click(await screen.findByRole("button", { name: "TXT Kubios · ms" }));
    await waitFor(() => expect(api.downloadPolarRRFile).toHaveBeenCalledWith("capture-1", "secret-lease", "practice_rr_ms.txt", expect.any(AbortSignal)));
    expect(screen.getByText("1000.977")).toBeInTheDocument();
    expect(screen.queryByText(/Estimated respiratory rate/)).not.toBeInTheDocument();
  });
  it("keeps RR downloads usable when optional analysis fails", async () => {
    vi.mocked(api.getPolarReview).mockRejectedValue(new Error("analysis failed"));
    render(<PolarCaptureReview capture={capture} lease="lease" copy={copy} />);
    expect(await screen.findByRole("button", { name: "CSV RR · ms" })).toBeEnabled();
    expect(await screen.findByRole("button", { name: "Reload" })).toBeEnabled();
  });
  it("labels a respiratory estimate as experimental without claiming accuracy", async () => {
    vi.mocked(api.getPolarReview).mockResolvedValue({ ...review, respiration: { ...review.respiration,
      status: "estimated", respiratory_rate_bpm: 18, accepted_windows: 2, evaluated_windows: 3,
      windows: [{ time_s: 0, rate_bpm: 18, accepted: true }], waveform: [[0, 1]] } });
    render(<PolarCaptureReview capture={capture} lease="lease" copy={copy} />);
    expect(await screen.findByText("Estimated respiratory rate · experimental")).toBeInTheDocument();
    expect(screen.getByText(/Accuracy against a respiratory reference has not yet been validated/)).toBeInTheDocument();
  });
  it("does not read unfinished files during capture", () => {
    render(<PolarCaptureReview capture={{ ...capture, artifact_state: "partial" }} lease="lease" copy={copy} />);
    expect(api.getPolarReview).not.toHaveBeenCalled();
    expect(api.getPolarRRExport).not.toHaveBeenCalled();
  });
});

it("review regression: clears previous capture data after identity changes without a lease", async () => {
  const view = render(<PolarCaptureReview capture={capture} lease="lease-A" copy={copy} />);
  await screen.findByRole("button", { name: "TXT Kubios · ms" });
  view.rerender(<PolarCaptureReview capture={{ ...capture, capture_id: "capture-B" }} lease="" copy={copy} />);
  expect(screen.queryByText("1000.977")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "TXT Kubios · ms" })).not.toBeInTheDocument();
});

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => { resolve = done; });
  return { promise, resolve };
}

it.each(["lease", "unfinished"])("removes existing review on %s change", async (change) => {
  const view = render(<PolarCaptureReview capture={capture} lease="lease-A" copy={copy} />);
  await screen.findByText("1000.977");
  view.rerender(<PolarCaptureReview capture={{ ...capture, artifact_state: change === "unfinished" ? "partial" : "finalized" }} lease={change === "lease" ? "" : "lease-A"} copy={copy} />);
  expect(screen.queryByText("1000.977")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "TXT Kubios · ms" })).not.toBeInTheDocument();
});

it("ignores late responses after switching to another authorized capture", async () => {
  const oldExport = deferred<PolarRRExport>();
  const oldReview = deferred<PolarReview>();
  vi.mocked(api.getPolarRRExport).mockReturnValueOnce(oldExport.promise).mockResolvedValueOnce({ ...exported, capture_id: "capture-B", preview: [] });
  vi.mocked(api.getPolarReview).mockReturnValueOnce(oldReview.promise).mockResolvedValueOnce({ ...review, capture_id: "capture-B", rr_tachogram: [] });
  const view = render(<PolarCaptureReview capture={capture} lease="lease-A" copy={copy} />);
  view.rerender(<PolarCaptureReview capture={{ ...capture, capture_id: "capture-B" }} lease="lease-B" copy={copy} />);
  await screen.findByRole("button", { name: "TXT Kubios · ms" });
  await act(async () => { oldExport.resolve(exported); oldReview.resolve(review); });
  expect(screen.queryByText("1000.977")).not.toBeInTheDocument();
  expect(screen.queryByText("Signal figure")).not.toBeInTheDocument();
});

it("rejects response identities that differ from the selected capture", async () => {
  vi.mocked(api.getPolarRRExport).mockResolvedValue({ ...exported, capture_id: "wrong-capture" });
  vi.mocked(api.getPolarReview).mockResolvedValue({ ...review, capture_id: "wrong-capture" });
  render(<PolarCaptureReview capture={capture} lease="lease" copy={copy} />);
  await screen.findByRole("button", { name: "Reload" });
  expect(screen.queryByText("1000.977")).not.toBeInTheDocument();
  expect(screen.queryByText("Signal figure")).not.toBeInTheDocument();
});

it("aborts pending downloads when control is lost", async () => {
  const pending = deferred<void>();
  vi.mocked(api.downloadPolarRRFile).mockReturnValue(pending.promise);
  const view = render(<PolarCaptureReview capture={capture} lease="lease" copy={copy} />);
  fireEvent.click(await screen.findByRole("button", { name: "TXT Kubios · ms" }));
  const signal = vi.mocked(api.downloadPolarRRFile).mock.calls[0][3];
  view.rerender(<PolarCaptureReview capture={capture} lease="" copy={copy} />);
  expect(signal?.aborted).toBe(true);
  await act(async () => pending.resolve());
  expect(screen.queryByRole("button", { name: "TXT Kubios · ms" })).not.toBeInTheDocument();
});

it("allows downloads after retry cancels an older download", async () => {
  const pending = deferred<void>();
  vi.mocked(api.downloadPolarRRFile).mockReturnValueOnce(pending.promise).mockResolvedValueOnce();
  vi.mocked(api.getPolarReview).mockRejectedValueOnce(new Error("retry review"));
  render(<PolarCaptureReview capture={capture} lease="lease" copy={copy} />);
  fireEvent.click(await screen.findByRole("button", { name: "TXT Kubios · ms" }));
  const oldSignal = vi.mocked(api.downloadPolarRRFile).mock.calls[0][3];
  fireEvent.click(await screen.findByRole("button", { name: "Reload" }));
  expect(oldSignal?.aborted).toBe(true);
  await waitFor(() => expect(screen.getByRole("button", { name: "TXT Kubios · ms" })).toBeEnabled());
  await act(async () => pending.resolve());
  fireEvent.click(screen.getByRole("button", { name: "TXT Kubios · ms" }));
  await waitFor(() => expect(api.downloadPolarRRFile).toHaveBeenCalledTimes(2));
  expect(vi.mocked(api.downloadPolarRRFile).mock.calls[1][3]?.aborted).toBe(false);
});
