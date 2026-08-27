import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ClassicDebrief } from "@/components/classic/ClassicDebrief";

const { mockDebrief, mockArtifacts, mockHistory, mockSelect, mockUrl } = vi.hoisted(() => ({
  mockDebrief: vi.fn(),
  mockArtifacts: vi.fn(),
  mockHistory: vi.fn(),
  mockSelect: vi.fn(),
  mockUrl: vi.fn(),
}));

vi.mock("@/lib/classic/api", () => ({
  getClassicDebrief: mockDebrief,
  getClassicArtifacts: mockArtifacts,
  getClassicHistory: mockHistory,
  selectClassicAttempt: mockSelect,
  getClassicResourceUrl: mockUrl,
}));

const attempt = {
  id: "classic-2",
  participant_id: "P01",
  visit_id: 1,
  visit_ordinal: 1,
  workload_level: "HIGH",
  attempt_number: 2,
  scenario_name: "military_aviation/high_workload.txt",
  scenario_sha256: "a".repeat(64),
  openmatb_source_sha256: "b".repeat(64),
  test_mode: false,
  wall_time_scale: 1,
  post_task_timeout_seconds: 600,
  status: "COMPLETE",
  task_validity: "valid",
  physiology_quality: "good",
  performance_only_override: false,
  failure_reason_code: null,
  battery_level_at_start: 91,
  created_at: "2026-08-23T00:00:00Z",
  baseline_started_at: "2026-08-23T00:00:01Z",
  task_started_at: "2026-08-23T00:05:01Z",
  task_finished_at: "2026-08-23T00:20:01Z",
  recovery_started_at: "2026-08-23T00:20:10Z",
  recovery_finished_at: "2026-08-23T00:25:01Z",
  finished_at: "2026-08-23T00:25:02Z",
};

describe("ClassicDebrief", () => {
  beforeEach(() => {
    mockDebrief.mockResolvedValue({
      session: attempt,
      matb_metrics: {
        n_rows: 200,
        tracking: { in_target_pct: 93.4, rmse: 0.18 },
        resource_management: { combined: { in_tolerance_pct: 87.2 } },
        comm: { hit_rate: 0.88, d_prime: 1.7 },
        nasatlx: { raw_tlx: 7.7 },
      },
      hrv: {
        phases: {
          baseline: { quality: { label: "good" }, time_domain: { status: "ok", metrics: { rmssd_ms: 42.3, sdnn_ms: 51.2, mean_hr_bpm: 63.1 } }, frequency_domain: { status: "ok", metrics: { lf_power_ms2: 820, hf_power_ms2: 610, lf_hf_ratio: 1.34 } } },
          task: { quality: { label: "good" }, time_domain: { status: "ok", metrics: { rmssd_ms: 31.1, sdnn_ms: 43.0, mean_hr_bpm: 74.2 } }, frequency_domain: { status: "ok", metrics: { lf_power_ms2: 780, hf_power_ms2: 410, lf_hf_ratio: 1.9 } } },
          recovery: { quality: { label: "acceptable" }, time_domain: { status: "ok", metrics: { rmssd_ms: 38.9, sdnn_ms: 48.8, mean_hr_bpm: 68.5 } }, frequency_domain: { status: "ok", metrics: { lf_power_ms2: 800, hf_power_ms2: 520, lf_hf_ratio: 1.54 } } },
        },
        summary: { quality: "good", disconnect_count: 0 },
      },
      selected_for_visit: false,
    });
    mockArtifacts.mockResolvedValue([
      { kind: "report_en", relative_path: "report.en.md", sha256: "abc", size_bytes: 1200 },
      { kind: "rr_csv", relative_path: "rr-intervals.csv", sha256: "def", size_bytes: 4200 },
      { kind: "session_json", relative_path: "session.json", sha256: "ghi", size_bytes: 2000 },
    ]);
    mockHistory.mockResolvedValue([{ ...attempt, id: "classic-1", attempt_number: 1 }, attempt]);
    mockSelect.mockResolvedValue(attempt);
    mockUrl.mockImplementation(async (kind: string, options: { relativePath?: string; format?: string }) => `http://localhost/${kind}/${options.relativePath ?? options.format ?? "bundle"}`);
  });

  it("keeps task validity and physiology quality separate and exposes HRV plus artifacts", async () => {
    render(<ClassicDebrief sessionId="classic-2" />);

    expect(await screen.findByText("93.4%")).toBeInTheDocument();
    expect(screen.getByText(/^task valid$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/^rr signal good$/i)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: /rmssd/i })).toBeInTheDocument();
    expect(screen.getByText("42.3")).toBeInTheDocument();
    expect(screen.getByText(/NASA-TLX mean \(0–10\)/i)).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: /report.en.md/i })).toHaveAttribute("href", expect.stringContaining("report.en.md"));
    expect(screen.getByRole("link", { name: /download sealed bundle/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /visit markdown/i })).toBeInTheDocument();
  });

  it("retains retake history and records manual selection with a reason code", async () => {
    const user = userEvent.setup();
    render(<ClassicDebrief sessionId="classic-2" />);

    expect(await screen.findByText(/attempt 1/i)).toBeInTheDocument();
    expect(screen.getByText(/^attempt 2$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/selection reason code/i)).toHaveAttribute(
      "pattern",
      "[a-z0-9][a-z0-9_\\-]{0,63}",
    );
    await user.click(screen.getByRole("button", { name: /select this attempt/i }));

    await waitFor(() => expect(mockSelect).toHaveBeenCalledWith("classic-2", "manual_quality_review"));
  });

  it("does not offer canonical selection for an invalid attempt", async () => {
    const invalidAttempt = {
      ...attempt,
      status: "ABORTED",
      task_validity: "invalid",
      failure_reason_code: "software_failure",
    };
    mockDebrief.mockResolvedValueOnce({
      session: invalidAttempt,
      matb_metrics: {},
      hrv: { phases: {}, summary: { quality: "missing_performance_only" } },
      selected_for_visit: false,
    });
    mockHistory.mockResolvedValueOnce([invalidAttempt]);

    render(<ClassicDebrief sessionId="classic-2" />);

    expect(await screen.findByText(/only complete, valid attempts/i)).toBeInTheDocument();
    expect(screen.queryAllByText("—%")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /select this attempt/i })).not.toBeInTheDocument();
  });

  it("shows terminal failure, HRV gate reasons, and non-production provenance", async () => {
    const testAttempt = {
      ...attempt,
      test_mode: true,
      wall_time_scale: 0.001,
      task_validity: "invalid",
      physiology_quality: "excellent",
      failure_reason_code: "test_mode_attempt",
    };
    mockDebrief.mockResolvedValueOnce({
      session: testAttempt,
      matb_metrics: {},
      hrv: {
        phases: {
          task: {
            quality: { label: "excellent" },
            time_domain: { status: "ok", metrics: {} },
            frequency_domain: {
              status: "not_computable",
              reason_codes: ["sensor_contact_loss", "bluetooth_disconnect"],
              metrics: null,
            },
          },
        },
        summary: { quality: "excellent", availability: "gated" },
      },
      selected_for_visit: false,
    });
    mockHistory.mockResolvedValueOnce([testAttempt]);

    render(<ClassicDebrief sessionId="classic-2" />);

    expect(await screen.findByText(/test mode.*0\.001/i)).toBeInTheDocument();
    expect(screen.getByText(/test_mode_attempt/i)).toBeInTheDocument();
    expect(screen.getByText(/sensor_contact_loss.*bluetooth_disconnect/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/rr signal excellent/i)).toBeInTheDocument();
  });
});
