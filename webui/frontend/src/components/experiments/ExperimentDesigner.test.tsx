import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ExperimentDesigner } from "@/components/experiments/ExperimentDesigner";
import { compileExperiment } from "@/lib/api";

vi.mock("@/lib/api", () => ({ compileExperiment: vi.fn() }));

describe("ExperimentDesigner", () => {
  beforeEach(() => {
    vi.mocked(compileExperiment).mockReset();
    vi.mocked(compileExperiment).mockResolvedValue({
      scenario_text: "0:00:00;sysmon;start\n",
      manifest: {
        source_commit: "1".repeat(40),
        source_dirty: false,
        provenance_status: "complete",
        spec: { sha256: "a".repeat(64) },
        scenario: { sha256: "b".repeat(64) },
        summary: {},
        claim_boundary: "Software compilation does not establish workload calibration.",
      },
    });
  });

  it("renders the task timeline and explicit scientific claim boundary", () => {
    render(<ExperimentDesigner />);

    expect(screen.getByRole("heading", { name: "Experiment Designer" })).toBeInTheDocument();
    expect(screen.getByText("AUTOMATION")).toBeInTheDocument();
    expect(screen.getByText(/engineering presets until human calibration/i)).toBeInTheDocument();
    expect(screen.getByText("1 N / 1 T")).toBeInTheDocument();
  });

  it("adds an editable event and derives the summary from current state", () => {
    render(<ExperimentDesigner />);

    fireEvent.click(screen.getByRole("button", { name: /add event/i }));

    expect(screen.getByText("2 N / 1 T")).toBeInTheDocument();
    expect(screen.getByLabelText("Event command")).toHaveValue("open_nontarget_opportunity");
  });

  it("compiles the strict wire specification and materializes both hashes", async () => {
    render(<ExperimentDesigner />);

    fireEvent.click(screen.getByRole("button", { name: /compile & validate/i }));

    await waitFor(() => expect(compileExperiment).toHaveBeenCalledOnce());
    expect(await screen.findByText("a".repeat(64))).toBeInTheDocument();
    expect(screen.getByText("b".repeat(64))).toBeInTheDocument();
    const request = vi.mocked(compileExperiment).mock.calls[0][0];
    expect(request.duration_ns).toBe(60_000_000_000);
    expect(request.timeline.some((event) => (
      event.parameters.command === "open_nontarget_opportunity"
    ))).toBe(true);
  });

  it("never attaches a stale compile response to a design edited in flight", async () => {
    let resolveCompile!: (value: Awaited<ReturnType<typeof compileExperiment>>) => void;
    vi.mocked(compileExperiment).mockImplementation(() => new Promise((resolve) => {
      resolveCompile = resolve;
    }));
    render(<ExperimentDesigner />);

    fireEvent.click(screen.getByRole("button", { name: /compile & validate/i }));
    fireEvent.change(screen.getByLabelText("Deterministic seed"), { target: { value: "43" } });
    resolveCompile({
      scenario_text: "0:00:00;sysmon;start\n",
      manifest: {
        source_commit: "unknown",
        source_dirty: null,
        provenance_status: "provisional_missing_source_commit",
        spec: { sha256: "c".repeat(64) },
        scenario: { sha256: "d".repeat(64) },
        summary: {},
        claim_boundary: "Software only.",
      },
    });

    expect(await screen.findByRole("alert")).toHaveTextContent(/design changed during compilation/i);
    expect(screen.queryByText("c".repeat(64))).not.toBeInTheDocument();
  });

  it("ignores an older response when two compile requests resolve out of order", async () => {
    const resolvers: Array<(value: Awaited<ReturnType<typeof compileExperiment>>) => void> = [];
    vi.mocked(compileExperiment).mockImplementation(() => new Promise((resolve) => {
      resolvers.push(resolve);
    }));
    render(<ExperimentDesigner />);

    const button = screen.getByRole("button", { name: /compile & validate/i });
    fireEvent.click(button);
    fireEvent.click(button);
    expect(compileExperiment).toHaveBeenCalledTimes(2);

    resolvers[1]({
      scenario_text: "0:00:00;sysmon;start\n",
      manifest: {
        source_commit: "2".repeat(40),
        source_dirty: false,
        provenance_status: "complete",
        spec: { sha256: "e".repeat(64) },
        scenario: { sha256: "f".repeat(64) },
        summary: {},
        claim_boundary: "Software only.",
      },
    });
    expect(await screen.findByText("e".repeat(64))).toBeInTheDocument();

    resolvers[0]({
      scenario_text: "stale\n",
      manifest: {
        source_commit: "3".repeat(40),
        source_dirty: false,
        provenance_status: "complete",
        spec: { sha256: "1".repeat(64) },
        scenario: { sha256: "0".repeat(64) },
        summary: {},
        claim_boundary: "Stale.",
      },
    });
    await waitFor(() => expect(screen.queryByText("1".repeat(64))).not.toBeInTheDocument());
    expect(screen.getByText("e".repeat(64))).toBeInTheDocument();
  });
});
