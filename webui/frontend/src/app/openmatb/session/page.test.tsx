import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SessionPage from "./page";
import * as api from "@/lib/openmatb/api";
import type { OpenMatbSession } from "@/types/openmatb";

const navigation = vi.hoisted(() => ({ query: "session=suite" }));
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(navigation.query), useRouter: () => ({ replace: vi.fn() }) }));
vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ copy: (_es: string, en: string) => en }) }));
vi.mock("@/lib/openmatb/api", () => ({ getOpenMatbSession: vi.fn(), getOpenMatbReceipt: vi.fn(), getOpenMatbDisplays: vi.fn(), retryOpenMatbEvidence: vi.fn(),
  controllerAction: vi.fn(), abortOpenMatbSession: vi.fn(), readOpenMatbController: () => "lease", readOpenMatbParticipant: () => "token" }));
vi.mock("@/lib/openmatb/errors", () => ({ openMatbErrorMessage: (error: Error | string) => typeof error === "string" ? error : error.message }));
const complete = { id: "suite", participant_id: "P01", visit_ordinal: 1, visit_code: "V1", execution_purpose: "practice", lifecycle: "COMPLETE", block_order: ["PRACTICE"], current_block_index: 1,
  scores: {}, active_block: null, active_block_instance_id: null, instruction_protocol: {}, display_index: 0 } as OpenMatbSession;

describe("OpenMATB controller continuations", () => {
  beforeEach(() => {
    navigation.query = "session=suite";
    sessionStorage.clear();
    vi.mocked(api.getOpenMatbSession).mockReset().mockResolvedValue(complete);
    vi.mocked(api.getOpenMatbReceipt).mockResolvedValue({ session_id: "suite", participant_id: "P01", visit_ordinal: 1, historical: false, attempts: [] } as never);
    vi.mocked(api.getOpenMatbDisplays).mockResolvedValue([{ index: 0 } as never]);
  });
  it("makes exact-session evidence primary and preserves practice for preparation", async () => {
    render(<SessionPage />);
    expect(await screen.findByRole("link", { name: "Review this session" })).toHaveAttribute("href", "/evidence?session=suite&purpose=all");
    expect(screen.getByRole("link", { name: "Prepare a new session" })).toHaveAttribute("href", "/openmatb/setup?purpose=practice");
    expect(screen.getByText(/does not complete a study visit/)).toBeInTheDocument();
  });
  it("clears a recovered polling error while retaining an unrelated failed action", async () => {
    const ready = { ...complete, lifecycle: "READY", current_block_index: 0 } as OpenMatbSession;
    vi.mocked(api.getOpenMatbSession).mockRejectedValueOnce(new Error("lost connection")).mockResolvedValue(ready);
    vi.mocked(api.controllerAction).mockRejectedValue(new Error("action rejected"));
    render(<SessionPage />);
    expect(await screen.findByText(/lost connection/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    const start = await screen.findByRole("button", { name: /Open OpenMATB and start/ });
    expect(screen.queryByText(/lost connection/)).toBeNull();
    fireEvent.click(start);
    expect(await screen.findByText("action rejected")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(api.getOpenMatbSession).toHaveBeenCalledTimes(3));
    expect(screen.getByText("action rejected")).toBeInTheDocument();
  });
  it("makes a blocked instructions window recoverable without launching the native task", async () => {
    navigation.query = "session=suite&participant_window=blocked";
    vi.mocked(api.getOpenMatbSession).mockResolvedValue({ ...complete, lifecycle: "INSTRUCTIONS" });
    vi.spyOn(window, "open").mockReturnValue({} as Window);
    render(<SessionPage />);
    const warning = await screen.findByText(/The browser blocked the participant instructions window/);
    expect(warning).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reopen participant instructions" }));
    expect(window.open).toHaveBeenCalledWith("/openmatb/participant?session=suite#token=token", "matb-fac-participant");
    expect(screen.queryByText(/The browser blocked/)).toBeNull();
  });
});
