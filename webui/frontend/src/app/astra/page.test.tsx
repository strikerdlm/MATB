import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import AstraPage from "./page";
import { FixedLocaleProvider } from "@/lib/i18n";
import { astraCall } from "@/lib/astra";
import { createOpenMatbSession, getActiveOpenMatbSession, getOpenMatbDisplays, getOpenMatbReadiness } from "@/lib/openmatb/api";
const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/astra", () => ({ astraCall: vi.fn() }));
vi.mock("@/lib/openmatb/api", () => ({ getActiveOpenMatbSession: vi.fn(), getOpenMatbDisplays: vi.fn(),
  getOpenMatbReadiness: vi.fn(), createOpenMatbSession: vi.fn(), storeOpenMatbCredentials: vi.fn() }));
const names = ["CUELLAR", "ICEMAN", "COLORADO", "WHITE", "PIRATA", "BART", "CHUCKY", "VOLCANO", "K-FIR", "Irving", "Midas", "Meteoro"];
const people = names.map((callsign, i) => ({ id: `P${String(i + 1).padStart(2, "0")}`, callsign,
  mission: i < 5 ? "ASTRA-1" : "ASTRA-2", position: i < 5 ? i + 1 : i - 4, station: 1,
  time_slot: i === 11 ? "15:45–17:15" : "08:30–10:00", block_order: ["LOW", "MEDIUM", "HIGH"],
  visits: Array.from({ length: 8 }, (_, visit) => ({ id: i * 8 + visit + 1, visit_ordinal: visit + 1,
    code: `V${visit}`, scheduled_day: [0,2,4,7,10,13,15,16][visit], planned_date: "2026-11-05", completed_blocks: 0, status: "planned" })) }));
beforeEach(() => {
  vi.mocked(getActiveOpenMatbSession).mockResolvedValue(null);
  vi.mocked(getOpenMatbDisplays).mockResolvedValue([{ index: 0, label: "Pantalla 1", width: 1920, height: 1080, x: 0, y: 0 }]);
  vi.mocked(getOpenMatbReadiness).mockResolvedValue({ ready: true } as never);
  vi.mocked(astraCall).mockImplementation(async path => {
    if (path.startsWith("/astra/roster")) return { participants: people, session_minutes: 90 } as never;
    if (path === "/astra/protocol") return { active: true, version_id: "version" } as never;
    if (path === "/astra/visits/prepare") return { url: "/study/participant?assignment=assigned" } as never;
    return {} as never;
  });
});
afterEach(() => { cleanup(); vi.clearAllMocks(); });
const mount = () => render(<FixedLocaleProvider locale="es-419"><AstraPage /></FixedLocaleProvider>);
it("shows exactly five and seven crew and preserves Meteoro identity when launching V7", async () => {
  mount();
  await screen.findByRole("button", { name: /^CUELLAR/ });
  expect(screen.getByRole("button", { name: /ASTRA-1 5/ })).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: /ASTRA-2 7/ }));
  expect(screen.getByRole("button", { name: /^Meteoro/ }).textContent).toContain("15:45–17:15");
  fireEvent.click(screen.getByRole("button", { name: /^Meteoro/ }));
  fireEvent.change(screen.getByLabelText("Visita"), { target: { value: "8" } });
  const launch = screen.getByRole("button", { name: /Aplicar visita V7/ });
  expect(launch).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(launch);
  await waitFor(() => expect(astraCall).toHaveBeenCalledWith("/astra/visits/prepare", { participant_id: "P12", visit_ordinal: 8 }));
  expect(push).toHaveBeenCalledWith("/study/participant?assignment=assigned&display=0&return=astra");
});
it("adds a crew member in the selected mission without requiring a numeric code", async () => {
  mount();
  await screen.findByRole("button", { name: /^CUELLAR/ });
  fireEvent.click(screen.getByRole("button", { name: /ASTRA-2 7/ }));
  fireEvent.click(screen.getByText("Gestionar participantes"));
  fireEvent.change(screen.getByLabelText("Nuevo indicativo"), { target: { value: "NUEVO" } });
  fireEvent.submit(screen.getByLabelText("Nuevo indicativo").closest("form")!);
  await waitFor(() => expect(astraCall).toHaveBeenCalledWith("/astra/participants", { callsign: "NUEVO", mission: "ASTRA-2" }));
});

it("opens ASTRA familiarization in the current tab when only one display is connected", async () => {
  const popup = vi.spyOn(window, "open").mockReturnValue(null);
  vi.mocked(createOpenMatbSession).mockResolvedValue({ session: { id: "practice" }, participant_token: "token", controller_lease: "lease" } as never);
  mount();
  fireEvent.click(await screen.findByRole("button", { name: /^CUELLAR/ }));
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Familiarización · 5 min" }));
  await waitFor(() => expect(push).toHaveBeenCalledWith("/openmatb/participant?session=practice"));
  expect(popup).not.toHaveBeenCalled();
});
