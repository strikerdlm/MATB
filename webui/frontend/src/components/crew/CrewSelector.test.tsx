import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CrewSelector } from "./CrewSelector";
import { AppLocaleProvider } from "@/lib/i18n";
import { getCrewProgress, prepareCrewActivity, type CrewProgress } from "@/lib/crew-workflow";
import * as native from "@/lib/openmatb/api";

const navigation = vi.hoisted(() => ({ push: vi.fn(), query: new URLSearchParams("experiment=openmatb") }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: navigation.push }), useSearchParams: () => navigation.query }));
vi.mock("@/lib/crew-workflow", async importOriginal => ({ ...await importOriginal<typeof import("@/lib/crew-workflow")>(), getCrewProgress: vi.fn(), prepareCrewActivity: vi.fn() }));
vi.mock("@/lib/openmatb/api", () => ({
  getOpenMatbReadiness: vi.fn(), getOpenMatbDisplays: vi.fn(), createOpenMatbSession: vi.fn(),
  getOpenMatbSession: vi.fn(), readOpenMatbController: vi.fn(), readOpenMatbParticipant: vi.fn(),
  recoverPendingOpenMatbSession: vi.fn(), controllerAction: vi.fn(), startOpenMatbAsParticipant: vi.fn(), storeOpenMatbCredentials: vi.fn(),
}));
vi.mock("@/lib/simulation/api", () => ({ createSimulationSession: vi.fn() }));
vi.mock("@/lib/simulation/lease", () => ({ storePreparedSessionLease: vi.fn() }));

const people: CrewProgress[] = ["CUELLAR", "COLORADO", "ICEMAN", "WHITE", "PIRATA"].map((callsign, i) => ({
  callsign, participant_id: `P0${i + 1}`, instrument: "openmatb", state: "ready", session_number: 1,
  completed_sessions: 0, completed_blocks: 0, total_sessions: 8, date: "2026-10-06",
}));
function page() { return render(<AppLocaleProvider><CrewSelector /></AppLocaleProvider>); }
beforeEach(() => {
  vi.resetAllMocks(); sessionStorage.clear();
  navigation.query = new URLSearchParams("experiment=openmatb");
  vi.mocked(getCrewProgress).mockResolvedValue({ participants: people });
});

describe("ASTRA participant entry", () => {
  it("requires a callsign selection and exposes no administrative or Polar fields", async () => {
    page();
    await screen.findByRole("button", { name: "CUELLAR" });
    expect(screen.queryByRole("button", { name: "Comenzar prueba" })).not.toBeInTheDocument();
    expect(screen.getByText("Elige tu callsign para continuar.")).toBeInTheDocument();
    expect(screen.queryByText(/Polar|Versión congelada|Asignar visita|PIN|password/i)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "WHITE" }));
    expect(screen.getByRole("heading", { name: "WHITE" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Comenzar prueba" })).toBeEnabled();
    expect(prepareCrewActivity).not.toHaveBeenCalled();
  });

  it("opens the selected browser activity and ignores a double click", async () => {
    navigation.query = new URLSearchParams("experiment=screen");
    vi.mocked(prepareCrewActivity).mockResolvedValue({ ...people[0], action: "launch", activity: "screen", attempt_id: "attempt-screen" });
    page(); fireEvent.click(await screen.findByRole("button", { name: "CUELLAR" }));
    const start = screen.getByRole("button", { name: "Comenzar prueba" });
    fireEvent.click(start); fireEvent.click(start);
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/study/run?attempt=attempt-screen&crew=CUELLAR&return=screen"));
    expect(prepareCrewActivity).toHaveBeenCalledExactlyOnceWith("CUELLAR", "screen", false);
  });

  it("does not offer a second session after today's saved completion", async () => {
    vi.mocked(getCrewProgress).mockResolvedValue({ participants: [{ ...people[0], state: "done_today", completed_sessions: 1, session_number: 2 }] });
    page(); fireEvent.click(await screen.findByRole("button", { name: "CUELLAR" }));
    expect(screen.getByRole("heading", { name: "Por hoy terminaste" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Comenzar prueba" })).not.toBeInTheDocument();
  });

  it("opens and releases the exact native attempt after real preflight succeeds", async () => {
    vi.mocked(prepareCrewActivity).mockResolvedValue({ ...people[0], action: "launch", activity: "openmatb", attempt_id: "native-attempt", visit_ordinal: 1,
      config: { preset: { id: "astra", version: "1" }, instructions: { id: "es", version: "1" }, visual: { id: "fac", version: "1" } } });
    vi.mocked(native.getOpenMatbReadiness).mockResolvedValue({ ready: true } as never);
    vi.mocked(native.getOpenMatbDisplays).mockResolvedValue([{ index: 0 }] as never);
    vi.mocked(native.createOpenMatbSession).mockResolvedValue({ session: { id: "native-session" }, controller_lease: "lease", participant_token: "token" } as never);
    vi.mocked(native.getOpenMatbSession).mockResolvedValue({ lifecycle: "PREFLIGHT_READY" } as never);
    vi.mocked(native.readOpenMatbController).mockReturnValue("lease");
    vi.mocked(native.readOpenMatbParticipant).mockReturnValue("token");
    vi.mocked(native.controllerAction).mockResolvedValue({ lifecycle: "PREFLIGHT_HELD", current_block_index: 0 } as never);
    page(); fireEvent.click(await screen.findByRole("button", { name: "CUELLAR" }));
    fireEvent.click(screen.getByRole("button", { name: "Comenzar prueba" }));
    await waitFor(() => expect(native.startOpenMatbAsParticipant).toHaveBeenCalledWith("native-session", "token", 0));
    expect(native.createOpenMatbSession).toHaveBeenCalledWith(expect.objectContaining({ preparation_only: true, attempt_id: "native-attempt", display_index: 0 }));
    expect(navigation.push).toHaveBeenCalledWith("/openmatb/participant?session=native-session&crew=CUELLAR");
  });

  it("routes an sUAS prerequisite back to the mission after KSS + PVT", async () => {
    navigation.query = new URLSearchParams("experiment=suas");
    vi.mocked(prepareCrewActivity).mockResolvedValue({ ...people[1], action: "launch", activity: "pvt", attempt_id: "pvt-before-suas" });
    page(); fireEvent.click(await screen.findByRole("button", { name: "COLORADO" }));
    fireEvent.click(screen.getByRole("button", { name: "Comenzar prueba" }));
    await waitFor(() => expect(navigation.push).toHaveBeenCalledWith("/study/run?attempt=pvt-before-suas&crew=COLORADO&return=suas"));
  });
});
