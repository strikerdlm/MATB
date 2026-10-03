import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
    await waitFor(() => expect(api.downloadPolarRRFile).toHaveBeenCalledWith("capture-1", "secret-lease", "practice_rr_ms.txt"));
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
