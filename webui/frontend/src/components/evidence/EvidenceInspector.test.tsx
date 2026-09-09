import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { EvidenceInspector } from "./EvidenceInspector";
import type { EvidenceCapture } from "@/lib/evidence";

vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ copy: (_es: string, en: string) => en }) }));
vi.mock("@/lib/evidence", async importOriginal => ({
  ...await importOriginal<typeof import("@/lib/evidence")>(),
  evidenceRequest: vi.fn(async (url: string) => url.includes("/context")
    ? { task: "track", events: [{ record: { event_id: "event-42", event_type: "track.sample" }, raw_json: '{"event_id":"event-42"}', scenario_time_ns_text: "1000000000" }], task_fields: [], truncated: {},
        timing: [{ record: { event_id: "event-42", observation_id: "obs-42", kind: "software_receipt", clock_id: "python.perf_counter", unit: "ns", evidence_source: "software" }, value_text: "123" }] }
    : { total: 1, items: [{ event_id: "event-42", sequence: 42, scenario_time_ns: 1000000000, event_type: "track.sample", payload: { address: "center_deviation", value: 3 } }] }),
}));

describe("evidence inspection", () => {
  it("links an excluded metric to its original event and software observation", async () => {
    const capture = { id: "capture", participant_id: "P01", condition: "A", execution_purpose: "study", completion: "interrupted",
      runs: [{ id: "run", version: "1", status: "failed", reason: null }], manifest: { source_commit: "abc", scenario_sha256: "sha" },
      metrics: [{ id: "metric", metric: "track_rmse_deviation", value: null, descriptive_value: 3, metric_version: "2", status: "failed",
        confirmatory_eligible: false, exclusion_reasons: ["sample_gap"], definition: { equation: "root mean square", unit: "deviation", required_inputs: ["sample"], missing_policy: "no interpolation" },
        physical_timing_qualification: "not_qualified", human_calibration: "not_qualified" }], reconciliation: { issues: [] },
    } as unknown as EvidenceCapture;
    render(<EvidenceInspector capture={capture} />);
    expect(screen.getByRole("checkbox", { name: "Include track_rmse_deviation" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: /Tracking error/ }));
    expect(screen.getByText("sample_gap")).toBeInTheDocument();
    fireEvent.click(await screen.findByRole("button", { name: /track.sample/ }));
    expect(await screen.findByText(/software_receipt · software · python.perf_counter/)).toBeInTheDocument();
    expect(screen.getByText("obs-42")).toBeInTheDocument();
  });
});
