import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { CrewBrowserRunner } from "./CrewBrowserRunner";
import { AppLocaleProvider } from "@/lib/i18n";
import { useAssignedAttempt } from "@/lib/assigned-attempt";
import { startAttempt } from "@/lib/assessments";
import { getCrewProgress } from "@/lib/crew-workflow";
import { postPvt, postScreen } from "@/lib/api";

vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams("attempt=attempt-one&crew=WHITE&return=suas") }));
vi.mock("@/lib/assigned-attempt", () => ({ useAssignedAttempt: vi.fn() }));
vi.mock("@/lib/assessments", () => ({ startAttempt: vi.fn(), interruptAttempt: vi.fn().mockResolvedValue({}), getAttempt: vi.fn() }));
vi.mock("@/lib/crew-workflow", async original => ({ ...await original<typeof import("@/lib/crew-workflow")>(), getCrewProgress: vi.fn() }));
vi.mock("@/lib/api", () => ({ postPvt: vi.fn(), postScreen: vi.fn() }));
vi.mock("@/components/instructions/InstructionAudio", () => ({ InstructionAudio: () => null }));
vi.mock("@/components/pvt/PvtRunner", () => ({ PvtRunner: ({ durationMs, onComplete }: { durationMs: number; onComplete: (value: object) => void }) => <button onClick={() => onComplete({ durationMs, administeredAt: "2026-10-06T12:00:00Z", trials: [], interruptionCount: 0, maxFrameGapMs: 16, terminalPhase: "waiting", terminalStimulusAtMs: null })}>Finish synthetic PVT</button> }));
vi.mock("next/dynamic", () => ({ default: () => ({ fast, onComplete }: { fast: boolean; onComplete: (value: object) => void }) => <button onClick={() => onComplete({ schema_version: 2, locale: "es-419", fast_mode: fast, marker: "synthetic screen evidence" })}>Finish synthetic screen</button> }));

function setup(instrument: "pvt" | "screen" = "pvt") {
  const context = { participant_id: "P01", visit_id: 1, assigned_visit: { ordinal: 1 }, instrument, locale: "es-419" };
  const attempt = { id: "attempt-one", acquisition_state: "created", execution_purpose: "study", assignment_context: context };
  vi.mocked(useAssignedAttempt).mockReturnValue({ identity: attempt.id, attempt, context, error: "" } as never);
  vi.mocked(startAttempt).mockResolvedValue({ ...attempt, acquisition_state: "started" } as never);
  vi.mocked(getCrewProgress).mockResolvedValue({ participants: [{ participant_id: "P01", callsign: "CUELLAR" }] } as never);
  return render(<AppLocaleProvider><CrewBrowserRunner /></AppLocaleProvider>);
}
beforeEach(() => { vi.clearAllMocks(); vi.mocked(postPvt).mockReset(); vi.mocked(postScreen).mockReset(); });

it("binds the actual participant and requires an explicit KSS response before PVT", async () => {
  setup();
  const next = await screen.findByRole("button", { name: "Continuar a PVT" });
  expect(next).toBeDisabled();
  expect(screen.getByText(/CUELLAR · Sesión 1/)).toBeInTheDocument();
  expect(screen.queryByText(/WHITE/)).not.toBeInTheDocument();
  expect(screen.getAllByRole("radio")).toHaveLength(9);
  expect(screen.getAllByRole("radio").every(radio => !(radio as HTMLInputElement).checked)).toBe(true);
  expect(startAttempt).toHaveBeenCalledExactlyOnceWith("attempt-one");
});

it("preserves PVT data for a failed-save retry and returns to the requested mission", async () => {
  vi.mocked(postPvt).mockRejectedValueOnce(new Error("Connection lost")).mockResolvedValueOnce({} as never);
  setup();
  fireEvent.click((await screen.findAllByRole("radio"))[4]);
  fireEvent.click(screen.getByRole("button", { name: "Continuar a PVT" }));
  fireEvent.click(screen.getByRole("button", { name: "Finish synthetic PVT" }));
  fireEvent.click(await screen.findByRole("button", { name: "Reintentar guardado" }));
  await screen.findByRole("heading", { name: "Prueba guardada" });
  const [first, second] = vi.mocked(postPvt).mock.calls;
  expect(second[0]).toEqual(first[0]);
  expect(first[0]).toMatchObject({ attempt_id: "attempt-one", participant_id: "P01", kss_score: 5, duration_ms: 600000, timing_version: 2, fast_mode: false, execution_purpose: "study" });
  expect(screen.getByRole("link", { name: "Continuar a la misión" })).toHaveAttribute("href", "/study/join?experiment=suas&purpose=study&crew=CUELLAR");
});

it("saves the full screen task under its admitted attempt", async () => {
  vi.mocked(postScreen).mockResolvedValue({} as never);
  setup("screen");
  fireEvent.click(await screen.findByRole("button", { name: "Finish synthetic screen" }));
  await waitFor(() => expect(postScreen).toHaveBeenCalledWith("P01", expect.objectContaining({ fast_mode: false, locale: "es-419" }), false, "study", "attempt-one"));
  await screen.findByRole("heading", { name: "Prueba guardada" });
});
