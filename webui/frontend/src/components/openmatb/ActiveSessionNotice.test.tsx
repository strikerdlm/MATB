import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { ActiveSessionNotice } from "./ActiveSessionNotice";
import { FixedLocaleProvider } from "@/lib/i18n";
import { abortOpenMatbSession, getActiveOpenMatbSession, recoverPendingOpenMatbSession, storeOpenMatbCredentials } from "@/lib/openmatb/api";
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/openmatb/api", () => ({ getActiveOpenMatbSession: vi.fn(), readOpenMatbController: () => null,
  recoverPendingOpenMatbSession: vi.fn(), storeOpenMatbCredentials: vi.fn(), abortOpenMatbSession: vi.fn() }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });
it("recovers lost credentials before closing the pending P99 session", async () => {
  const session = { id: "pending", participant_id: "P99", visit_code: "T0", lifecycle: "READY", started_at: null, active_pid: null };
  vi.mocked(getActiveOpenMatbSession).mockResolvedValue(session as never);
  const prepared = { session, controller_lease: "new-lease", participant_token: "new-participant" };
  vi.mocked(recoverPendingOpenMatbSession).mockResolvedValue(prepared as never);
  render(<FixedLocaleProvider locale="es-419"><ActiveSessionNotice /></FixedLocaleProvider>);
  fireEvent.click(await screen.findByRole("button", { name: "Cerrar sesión pendiente" }));
  await waitFor(() => expect(abortOpenMatbSession).toHaveBeenCalledWith("pending", "new-lease"));
  expect(storeOpenMatbCredentials).toHaveBeenCalledWith(prepared);
  await waitFor(() => expect(screen.queryByText(/Esta estación ya tiene/)).toBeNull());
});
it("does not offer to discard or reclaim a running acquisition", async () => {
  vi.mocked(getActiveOpenMatbSession).mockResolvedValue({ id: "running", participant_id: "P01", visit_code: "V0", lifecycle: "RUNNING", active_pid: 123 } as never);
  render(<FixedLocaleProvider locale="es-419"><ActiveSessionNotice /></FixedLocaleProvider>);
  await screen.findByRole("button", { name: "Retomar sesión" });
  expect(screen.queryByRole("button", { name: "Cerrar sesión pendiente" })).toBeNull();
  expect(recoverPendingOpenMatbSession).not.toHaveBeenCalled();
});
