import React from "react";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DebriefScreen } from "./DebriefScreen";
import type { DebriefView } from "@/types/simulation";

const debrief = { session_id: "sim-1", validity: "valid_with_deviation", replay_status: "match", deterministic_replay_verified: true, frames: [{ simulation_time_ms: 0, state_version: 90 }, { simulation_time_ms: 10_000, state_version: 100 }], metrics: { coverage: 80, contacts: 3, assets: 4, timeliness: 90, isa: { mean: 6 }, sagat: { correct: 2, total: 3, accuracy: 0.6667 }, nasa_tlx: { raw_tlx: 30 }, bedford: { value: 7 } }, timeline: [{ event: "block_finished" }] } as unknown as DebriefView;

describe("DebriefScreen", () => {
  it("moves the replay to the selected five-second frame", async () => {
    const user = userEvent.setup();
    render(<DebriefScreen debrief={debrief} locale="en" />);
    await user.click(screen.getByRole("slider", { name: /replay time/i }));
    await user.keyboard("{End}");
    expect(screen.getByTestId("replay-time")).toHaveTextContent("00:10");
    expect(screen.getByRole("img", { name: /tactical mission replay/i })).toHaveAttribute("data-state-version", "100");
  });

  it("labels the composite descriptive and exposes all components", () => {
    render(<DebriefScreen debrief={debrief} locale="en" />);
    expect(screen.getByText(/descriptive feedback only/i)).toBeVisible();
    for (const name of ["Coverage", "Contacts", "Assets", "Timeliness"]) expect(screen.getByText(name)).toBeVisible();
    expect(screen.getByText(/valid with deviation/i)).toBeVisible();
    expect(screen.getByText(/deterministic replay verified/i)).toBeVisible();
  });
});
