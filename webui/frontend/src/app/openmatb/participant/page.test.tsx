import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OpenMatbParticipantPage from "@/app/openmatb/participant/page";
import { AppLocaleProvider } from "@/lib/i18n";
import { ExperimentFlowProvider, useExperimentFlowProgress } from "@/lib/experiment-flow";
import { OpenMatbApiError } from "@/lib/openmatb/api";
import type { OpenMatbLifecycle, OpenMatbProfile, OpenMatbSession } from "@/types/openmatb";

const { mockStart, mockGetSession, mockReadParticipant, mockSubmit } = vi.hoisted(() => ({
  mockStart: vi.fn(),
  mockGetSession: vi.fn(),
  mockReadParticipant: vi.fn(),
  mockSubmit: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/openmatb/participant",
  useSearchParams: () => new URLSearchParams("session=session-123&purpose=practice"),
}));

vi.mock("@/lib/openmatb/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/openmatb/api")>("@/lib/openmatb/api");
  return {
    ...actual,
    startOpenMatbAsParticipant: mockStart,
    getOpenMatbSession: mockGetSession,
    readOpenMatbParticipant: mockReadParticipant,
    submitOpenMatbScales: mockSubmit,
  };
});

function makeSession(
  lifecycle: OpenMatbLifecycle,
  activeBlock: OpenMatbProfile | null = null,
  overrides: Partial<OpenMatbSession> = {},
): OpenMatbSession {
  return {
    execution_purpose: "study",
    locale: "en",
    id: "session-123",
    participant_id: "P01",
    visit_ordinal: 1,
    visit_code: "T0",
    scheduled_day: 0,
    lifecycle,
    block_order: ["PRACTICE", "LOW", "MEDIUM", "HIGH"],
    current_block_index: activeBlock === "PRACTICE" ? 0 : 1,
    active_block: activeBlock,
    active_block_instance_id: activeBlock ? "11111111-2222-4333-8444-555555555555" : null,
    evidence_processing: false,
    native_recovery_required: false,
    preset_id: "published",
    preset_version: "1.0.0",
    preset_sha256: "preset-sha",
    instruction_protocol: {
      protocol_id: "standard",
      version: "1.0.0",
      locale: "en",
      status: "published",
      sha256: "instruction-sha",
      title: "Participant instructions",
      steps: ["Read the display."],
      task_instructions: {},
      visit_instructions: {},
    },
    visit_instruction: "Complete the visit.",
    visual_theme: "classic",
    visual_profile_id: null,
    visual_profile_version: null,
    visual_profile_schema_version: null,
    visual_profile_sha256: null,
    display_index: 0,
    scores: {},
    active_pid: null,
    last_error: null,
    created_at: "2026-09-10T00:00:00Z",
    started_at: "2026-09-10T00:01:00Z",
    finished_at: null,
    ...overrides,
  };
}

function FlowObserver() {
  const progress = useExperimentFlowProgress();
  return <output aria-label="flow-stage">{progress ? `${progress.experimentId}:${progress.stage}:${progress.purpose ?? "unset"}` : "unknown"}</output>;
}

function renderPage() {
  return render(
    <AppLocaleProvider>
      <ExperimentFlowProvider>
        <OpenMatbParticipantPage />
        <FlowObserver />
      </ExperimentFlowProvider>
    </AppLocaleProvider>,
  );
}

describe("OpenMATB participant page", () => {
  beforeEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
    mockStart.mockReset();
    window.localStorage.setItem("matb-fac.locale", "en");
    window.sessionStorage.clear();
    mockReadParticipant.mockReturnValue("participant-token");
  });

  it("uses the authoritative session purpose and reports lifecycle progress after loading", async () => {
    let resolve!: (session: OpenMatbSession) => void;
    mockGetSession.mockReturnValue(new Promise<OpenMatbSession>((done) => { resolve = done; }));
    renderPage();

    await waitFor(() => expect(screen.getByLabelText("flow-stage")).toHaveTextContent("openmatb:null:unset"));
    resolve(makeSession("INSTRUCTIONS", null, { execution_purpose: "study" }));
    expect(await screen.findByText("Study session")).toBeInTheDocument();
    expect(screen.getByText(/Use the code and visit assigned for this study/)).toBeInTheDocument();
    expect(screen.getByText(/MATB - FAC · T0 · P01/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("flow-stage")).toHaveTextContent("openmatb:instructions:study"));
  });

  it.each(["INSTRUCTIONS", "READY", "BETWEEN_BLOCKS"] as const)("starts directly from %s only when the participant is ready", async lifecycle => {
    const waiting = makeSession(lifecycle, "PRACTICE", { execution_purpose: "practice" });
    const running = makeSession("RUNNING", "PRACTICE", { execution_purpose: "practice" });
    mockGetSession.mockResolvedValue(waiting);
    let finish!: (value: OpenMatbSession) => void;
    mockStart.mockReturnValue(new Promise<OpenMatbSession>(resolve => { finish = resolve; }));
    const user = userEvent.setup();
    renderPage();
    const button = await screen.findByRole("button", { name: /I am ready: start/ });
    expect(mockStart).not.toHaveBeenCalled();
    await user.click(button);
    expect(mockStart).toHaveBeenCalledExactlyOnceWith("session-123", "participant-token", 0);
    expect(screen.getByRole("button", { name: "Opening the task…" })).toBeDisabled();
    mockGetSession.mockResolvedValue(running);
    finish(running);
    expect(await screen.findByRole("heading", { name: "OpenMATB running" })).toBeInTheDocument();
  });

  it("does not start without a participant credential", async () => {
    mockGetSession.mockResolvedValue(makeSession("READY"));
    mockReadParticipant.mockReturnValue(null);
    renderPage();
    expect(await screen.findByRole("button", { name: "I am ready: start" })).toBeDisabled();
    expect(mockStart).not.toHaveBeenCalled();
  });

  it.each(["INSTRUCTIONS", "READY", "BETWEEN_BLOCKS"] as const)("offers Spanish instructions before %s and prevents overlapping playback", async lifecycle => {
    mockGetSession.mockResolvedValue(makeSession(lifecycle, "PRACTICE", { locale: "es-419" }));
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    const view = renderPage();
    const audio = await screen.findByLabelText("Instrucciones MATB en español");
    expect(audio).toHaveAttribute("src", "/audio/instructions/openmatb-es.wav");
    const start = screen.getByRole("button", { name: /Estoy listo: iniciar/ });
    fireEvent.play(audio);
    expect(start).toBeDisabled();
    expect(mockStart).not.toHaveBeenCalled();
    fireEvent.ended(audio);
    expect(start).toBeEnabled();
    view.unmount();
    expect(pause).toHaveBeenCalled();
    pause.mockRestore();
  });

  it("provides a readable fallback when the Spanish audio is unavailable", async () => {
    mockGetSession.mockResolvedValue(makeSession("INSTRUCTIONS", "PRACTICE", { locale: "es-419" }));
    const pause = vi.spyOn(HTMLMediaElement.prototype, "pause").mockImplementation(() => {});
    const view = renderPage();
    const audio = await screen.findByLabelText("Instrucciones MATB en español");
    fireEvent.error(audio);
    expect(screen.getByRole("alert")).toHaveTextContent("No se pudo reproducir la explicación");
    expect(screen.getByRole("link", { name: "Leer la transcripción completa" })).toBeInTheDocument();
    view.unmount();
    pause.mockRestore();
  });

  it.each([
    ["STARTING", "Opening the native task window", "Wait while the task window appears on the selected display."],
    ["RUNNING", "OpenMATB running", "Use the task controls. This display will return when the block ends."],
    ["PAUSED", "OpenMATB paused", "The task is paused. Wait for the researcher before continuing."],
  ] as const)("renders a distinct %s participant state", async (lifecycle, heading, guidance) => {
    mockGetSession.mockResolvedValue(makeSession(lifecycle, "LOW"));
    renderPage();

    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
    expect(screen.getByText(guidance)).toBeInTheDocument();
    expect(screen.getByText("Study session")).toBeInTheDocument();
    await waitFor(() => expect(screen.getByLabelText("flow-stage")).toHaveTextContent("openmatb:perform:study"));
  });

  it("renders ratings for a durable study block but never for the practice block", async () => {
    mockGetSession.mockResolvedValue(makeSession("AWAITING_SCALE", "LOW"));
    const study = renderPage();
    expect(await screen.findByRole("region", { name: "Workload questionnaire" })).toBeInTheDocument();
    study.unmount();

    mockGetSession.mockResolvedValue(makeSession("AWAITING_SCALE", "PRACTICE"));
    renderPage();
    expect(await screen.findByText("Practice blocks do not collect workload ratings. Wait while the session advances.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Workload questionnaire" })).not.toBeInTheDocument();
  });

  it("shows explicit legacy recovery instead of fabricating a block identity", async () => {
    mockGetSession.mockResolvedValue(makeSession("AWAITING_SCALE", "LOW", { active_block_instance_id: null }));
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("This block cannot be identified. Refresh this page.");
    expect(mockSubmit).not.toHaveBeenCalled();
  });

  it("does not render data or bind a draft when polling returns another session", async () => {
    mockGetSession.mockResolvedValue(makeSession("AWAITING_SCALE", "LOW", { id: "different-session" }));
    renderPage();

    expect(await screen.findByText("Loading…")).toBeInTheDocument();
    expect(screen.queryByText("Study session")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Workload questionnaire" })).not.toBeInTheDocument();
    expect(sessionStorage.getItem("openmatb.workload-draft.openmatb-workload-v1.different-session.11111111-2222-4333-8444-555555555555")).toBeNull();
  });

  it("keeps draft-clear failure feedback visible after applying the accepted response", async () => {
    const blockId = "11111111-2222-4333-8444-555555555555";
    const waiting = makeSession("AWAITING_SCALE", "LOW");
    const accepted = makeSession("BETWEEN_BLOCKS", null, {
      current_block_index: 2,
      scores: { LOW: { block_instance_id: blockId } },
    });
    mockGetSession.mockResolvedValue(waiting);
    mockSubmit.mockImplementation(async () => {
      mockGetSession.mockResolvedValue(accepted);
      return accepted;
    });
    const originalRemoveItem = Storage.prototype.removeItem;
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(function (this: Storage, key) {
      if (key.startsWith("openmatb.workload-draft.")) throw new DOMException("blocked", "SecurityError");
      return originalRemoveItem.call(this, key);
    });
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole("region", { name: "Workload questionnaire" });
    for (const button of screen.getAllByRole("button", { name: /Use 50 for/ })) await user.click(button);
    await user.click(screen.getByRole("radio", { name: /5 Reduced spare capacity/ }));
    await user.click(screen.getByRole("button", { name: "Save ratings and continue" }));

    expect(await screen.findByText("Ratings were saved, but the draft could not be removed from this tab.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Ready to continue" })).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Workload questionnaire" })).not.toBeInTheDocument();
  });

  it("keeps action failures after a successful poll and translates known API errors", async () => {
    mockGetSession.mockResolvedValue(makeSession("INSTRUCTIONS"));
    mockStart.mockRejectedValue(new OpenMatbApiError(409, "openmatb_block_mismatch", "raw"));
    const user = userEvent.setup();
    renderPage();
    await user.click(await screen.findByRole("button", { name: "I have read the instructions. I am ready: start" }));

    expect(await screen.findByText("These ratings belong to a different block. Refresh the session; ratings cannot transfer between blocks.")).toBeInTheDocument();
    await waitFor(() => expect(mockGetSession.mock.calls.length).toBeGreaterThanOrEqual(2), { timeout: 2_000 });
    expect(screen.getByText("These ratings belong to a different block. Refresh the session; ratings cannot transfer between blocks.")).toBeInTheDocument();
  });
});
