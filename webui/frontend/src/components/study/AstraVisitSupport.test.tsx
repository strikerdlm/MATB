import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { FixedLocaleProvider } from "@/lib/i18n";
import { studyCall, type AssignmentDetail } from "@/lib/study";
import { AstraRecovery } from "./AstraVisitSupport";
vi.mock("@/lib/study", () => ({ studyCall: vi.fn() }));
afterEach(() => { cleanup(); vi.useRealTimers(); vi.clearAllMocks(); });
const interval = { key: "rest1", anchor_key: "ratings1", before_key: "block2", duration_seconds: 180 };
const detail = { assignment: { id: "visit" }, version: { actor: "Investigadora" }, attempts: { ratings1: [{ id: "ratings-exact", acquisition_state: "finished" }] } } as unknown as AssignmentDetail;

it("records the exact rating anchor and waits for the complete break before continuing", async () => {
  vi.useFakeTimers(); vi.setSystemTime(new Date("2026-09-29T12:00:00Z"));
  vi.mocked(studyCall).mockResolvedValue({ started_at: "2026-09-29T12:00:00" });
  const complete = vi.fn().mockResolvedValue(undefined);
  render(<FixedLocaleProvider locale="es-419"><AstraRecovery detail={detail} interval={interval} onComplete={complete} /></FixedLocaleProvider>);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Iniciar pausa" })); });
  expect(studyCall).toHaveBeenCalledWith("/assignments/visit/recovery/rest1/start?anchor_attempt_id=ratings-exact", expect.objectContaining({ actor: "Investigadora" }));
  expect(screen.getByRole("button", { name: "Finalizar pausa y continuar" })).toBeDisabled();
  act(() => vi.advanceTimersByTime(179000));
  expect(screen.getByRole("timer")).toHaveTextContent("0:01");
  act(() => vi.advanceTimersByTime(1000));
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Finalizar pausa y continuar" })); });
  expect(studyCall).toHaveBeenLastCalledWith("/assignments/visit/recovery/rest1/finish", expect.objectContaining({ actor: "Investigadora" }));
  expect(complete).toHaveBeenCalledOnce();
});

it("does not choose among multiple completed rating attempts", async () => {
  const ambiguous = { ...detail, attempts: { ratings1: [detail.attempts.ratings1[0], { ...detail.attempts.ratings1[0], id: "second" }] } };
  render(<FixedLocaleProvider locale="es-419"><AstraRecovery detail={ambiguous} interval={interval} onComplete={vi.fn()} /></FixedLocaleProvider>);
  await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Iniciar pausa" })); });
  expect(screen.getByRole("alert")).toHaveTextContent("Revise los intentos");
  expect(studyCall).not.toHaveBeenCalled();
});
