import React from "react";
import { act, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import {
  ExperimentFlowProvider,
  flowStageForPvt,
  flowStageForScreen,
  useExperimentFlowProgress,
  useReportExperimentFlow,
  type ExperimentFlowStage,
} from "@/lib/experiment-flow";

let pathname = "/pvt";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

function Observer() {
  const progress = useExperimentFlowProgress();
  return <output>{progress ? `${progress.experimentId}:${progress.stage}` : "unknown"}</output>;
}

function Reporter({ stage }: { stage: ExperimentFlowStage }) {
  useReportExperimentFlow("pvt", stage);
  return null;
}

describe("experiment flow progress", () => {
  it("maps PVT and screen preparation, instructions, performance, and completion from real state", () => {
    expect(flowStageForPvt("select", false)).toBe("prepare");
    expect(flowStageForPvt("kss", false)).toBe("instructions");
    expect(flowStageForPvt("pvt", false)).toBe("instructions");
    expect(flowStageForPvt("pvt", true)).toBe("perform");
    expect(flowStageForPvt("complete", true)).toBe("complete");

    expect(flowStageForScreen("select", false, false)).toBe("prepare");
    expect(flowStageForScreen("run", false, false)).toBe("instructions");
    expect(flowStageForScreen("run", true, false)).toBe("perform");
    expect(flowStageForScreen("review", true, false)).toBe("perform");
    expect(flowStageForScreen("review", true, true)).toBe("complete");
  });

  it("stays unknown until a page publishes typed progress", () => {
    render(<ExperimentFlowProvider><Observer /></ExperimentFlowProvider>);
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });

  it("reports the current page stage and does not carry it to another route", () => {
    const view = render(
      <ExperimentFlowProvider><Reporter stage="instructions" /><Observer /></ExperimentFlowProvider>,
    );
    expect(screen.getByText("pvt:instructions")).toBeInTheDocument();

    pathname = "/analysis";
    act(() => view.rerender(
      <ExperimentFlowProvider><Observer /></ExperimentFlowProvider>,
    ));
    expect(screen.getByText("unknown")).toBeInTheDocument();
  });
});
