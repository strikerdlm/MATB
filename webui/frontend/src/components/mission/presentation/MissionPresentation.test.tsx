import React from "react";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { MissionPresentation, preflightSnapshot } from "./MissionPresentation";
import type { SessionView } from "@/types/simulation";
import type { ThreeMissionViewProps } from "./ThreeMissionView";

vi.mock("@/lib/simulation/api", () => ({
  sendPresentationEvent: vi.fn().mockResolvedValue(undefined),
  getSimulationSession: vi.fn().mockResolvedValue({}),
}));
vi.mock("next/dynamic", () => ({ default: () => function FakeRenderer(props: ThreeMissionViewProps) {
  return <div><span data-testid="camera-mode">{props.viewState?.camera}</span>
    <button onClick={() => props.onViewAction?.({ type: "camera", camera: "follow" })}>Choose follow</button>
    <button onClick={() => props.onEvent?.("render", "overview", 1, { camera_position: [0, 1, 0], camera_quaternion: [0, 0, 0, 1] })}>Old render callback</button>
  </div>;
} }));

describe("presentation action ownership", () => {
  it("does not let a stale renderer sample overwrite the selected camera mode", () => {
    const session = { id: "camera-race", session_mode: "research", lifecycle: "RUNNING", presentation: {
      version: 2, scene_id: "test", scene_sha256: "0".repeat(64), blocks: { LOW: "3d" }, camera: "overview",
    } } as SessionView;
    render(<MissionPresentation session={session} snapshot={preflightSnapshot("LOW")} locale="en" replay />);
    fireEvent.click(screen.getByText("Choose follow"));
    fireEvent.click(screen.getByText("Old render callback"));
    expect(screen.getByTestId("camera-mode")).toHaveTextContent("follow");
  });
});
