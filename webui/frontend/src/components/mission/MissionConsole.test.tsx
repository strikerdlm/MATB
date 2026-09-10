import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, it, vi } from "vitest";
import { MissionConsole } from "./MissionConsole";
import { useSimulationStore } from "@/lib/simulation/store";
import { MISSION_CONSOLE_PROFILE } from "@/lib/simulation/console-profile";
import type { SessionView, WorldSnapshot } from "@/types/simulation";

vi.mock("./presentation/MissionPresentation", () => ({ MissionPresentation: () => <div>Instrument unchanged</div>, preflightSnapshot: vi.fn() }));
vi.mock("./MissionJourneyRail", () => ({ MissionJourneyRail: () => null }));
vi.mock("./MissionInstructionPanel", () => ({ MissionInstructionPanel: () => null }));
vi.mock("./FleetPanel", () => ({ FleetPanel: () => null }));
vi.mock("./CommandBar", () => ({ CommandBar: ({ onCommand }: { onCommand: (kind: string, payload: object) => void }) => <button onClick={() => onCommand("HOLD", { aircraft_id: "UAS-01" })}>Hold task</button> }));
const submit = vi.fn();
const session = { id: "mission-profile-test", locale: "en", lifecycle: "RUNNING", record_class: "technical_only", session_mode: "interactive_technical", state_version: 1 } as SessionView;
const snapshot = { aircraft: {}, contacts: {}, alerts: {}, state_version: 1 } as unknown as WorldSnapshot;

beforeEach(() => {
  sessionStorage.setItem(`matb.simulation.${session.id}.lease`, "test-lease");
  useSimulationStore.getState().reset();
  useSimulationStore.setState({ connect: vi.fn().mockResolvedValue(undefined), disconnect: vi.fn(), submitCommand: submit });
  submit.mockReset();
});
it.each([false, true])("retains sweep only for historical sessions (modern %s)", modern => {
  const { container } = render(<MissionConsole initialSession={{ ...session, console_profile: modern ? MISSION_CONSOLE_PROFILE : undefined }} initialSnapshot={snapshot} />);
  expect(container.querySelector(".signal-sweep") !== null).toBe(!modern);
  expect(screen.getByRole("button", { name: /pause/i })).toHaveClass(modern ? "normal-case" : "uppercase");
});
it("keeps a rejected command visible across reconnect; acceptance is receipt only", async () => {
  const user = userEvent.setup();
  render(<MissionConsole initialSession={{ ...session, console_profile: MISSION_CONSOLE_PROFILE }} initialSnapshot={snapshot} />);
  submit.mockResolvedValueOnce({ status: "rejected", message: "Aircraft unavailable" });
  await user.click(screen.getByRole("button", { name: "Hold task" }));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("Aircraft unavailable"));
  act(() => useSimulationStore.setState({ transportError: "Socket lost", connection: "reconnecting" }));
  expect(screen.getAllByRole("alert")).toHaveLength(2);
  act(() => useSimulationStore.setState({ transportError: null, connection: "live" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Aircraft unavailable");
  submit.mockResolvedValueOnce({ status: "accepted" });
  await user.click(screen.getByRole("button", { name: "Hold task" }));
  await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("does not evaluate performance"));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
