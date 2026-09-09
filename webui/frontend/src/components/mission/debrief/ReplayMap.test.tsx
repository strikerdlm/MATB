import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReplayMap } from "./ReplayMap";
import type { ReplayFrame } from "./ReplayTimeline";
import type { DebriefView } from "@/types/simulation";
vi.mock("../presentation/MissionPresentation", () => ({
  MissionPresentation: ({ session }: { session: { presentation: { blocks: { LOW: string } } } }) =>
    <div data-testid="condition">{session.presentation.blocks.LOW}</div>,
}));
describe("recorded presentation", () => {
  it("restores technical fallback and subsequent 3D readiness when seeking", () => {
    const debrief = {
      presentation: { version: 1, blocks: { LOW: "3d" }, scene_id: "pilot" },
      presentation_events: [
        { block_id: "LOW", simulation_time_ms: 0, kind: "ready" },
        { block_id: "LOW", simulation_time_ms: 1000, kind: "fallback" },
        { block_id: "LOW", simulation_time_ms: 2000, kind: "ready" },
      ],
    } as unknown as DebriefView;
    const frame = (time: number) => ({ block_id: "LOW", simulation_time_ms: time, state_version: 1,
      snapshot: { block_id: "LOW", terrain: {}, aircraft: {} } }) as ReplayFrame;
    const { rerender } = render(<ReplayMap debrief={debrief} frame={frame(1500)} locale="en" />);
    expect(screen.getByTestId("condition")).toHaveTextContent("2d");
    rerender(<ReplayMap debrief={debrief} frame={frame(2500)} locale="en" />);
    expect(screen.getByTestId("condition")).toHaveTextContent("3d");
    rerender(<ReplayMap debrief={debrief} frame={frame(500)} locale="en" />);
    expect(screen.getByTestId("condition")).toHaveTextContent("3d");
  });
});
