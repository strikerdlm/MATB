import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  workloadDraftKey,
  WorkloadQuestionnaire,
} from "@/components/openmatb/WorkloadQuestionnaire";
import { AppLocaleProvider } from "@/lib/i18n";
import type { OpenMatbProfile, OpenMatbSession } from "@/types/openmatb";

const SESSION_ID = "session-123";
const BLOCK_ID = "11111111-2222-4333-8444-555555555555";
const TLX_LABELS = [
  "Mental demand",
  "Physical demand",
  "Temporal demand",
  "Performance",
  "Effort",
  "Frustration",
];

const INSTRUMENT_COPY = [
  {
    locale: "en" as const,
    tlx: [
      ["mental_demand", "Mental demand", "Low", "High"],
      ["physical_demand", "Physical demand", "Low", "High"],
      ["temporal_demand", "Temporal demand", "Low", "High"],
      ["performance", "Performance", "Good", "Poor"],
      ["effort", "Effort", "Low", "High"],
      ["frustration", "Frustration", "Low", "High"],
    ],
    bedford: [
      "Insignificant workload.",
      "Low workload.",
      "Enough spare capacity for all desirable additional tasks.",
      "Not enough spare capacity to easily attend to additional tasks.",
      "Reduced spare capacity; additional tasks do not receive the desired attention.",
      "Little spare capacity; effort permits little attention to additional tasks.",
      "Very little spare capacity, but effort on the primary tasks can be maintained.",
      "Very high workload, almost no spare capacity; effort is difficult to maintain.",
      "Extremely high workload, no spare capacity; serious doubts about maintaining effort.",
      "Tasks abandoned; sufficient effort could not be applied.",
    ],
  },
  {
    locale: "es-419" as const,
    tlx: [
      ["mental_demand", "Demanda mental", "Baja", "Alta"],
      ["physical_demand", "Demanda física", "Baja", "Alta"],
      ["temporal_demand", "Demanda temporal", "Baja", "Alta"],
      ["performance", "Rendimiento", "Bueno", "Deficiente"],
      ["effort", "Esfuerzo", "Bajo", "Alto"],
      ["frustration", "Frustración", "Baja", "Alta"],
    ],
    bedford: [
      "Carga insignificante.",
      "Carga baja.",
      "Capacidad sobrante suficiente para todas las tareas adicionales deseables.",
      "Capacidad sobrante insuficiente para atender fácilmente tareas adicionales.",
      "Capacidad sobrante reducida; las tareas adicionales no reciben la atención deseada.",
      "Poca capacidad sobrante; el esfuerzo permite poca atención a tareas adicionales.",
      "Muy poca capacidad sobrante, pero se puede mantener el esfuerzo en las tareas principales.",
      "Carga muy alta, casi sin capacidad sobrante; es difícil mantener el esfuerzo.",
      "Carga extremadamente alta, sin capacidad sobrante; existen dudas serias sobre mantener el esfuerzo.",
      "Tareas abandonadas; no fue posible aplicar esfuerzo suficiente.",
    ],
  },
];

function sessionResponse(blockInstanceId: string, profile: OpenMatbProfile = "LOW"): OpenMatbSession {
  return {
    execution_purpose: "study",
    locale: "en",
    id: SESSION_ID,
    participant_id: "P01",
    visit_ordinal: 1,
    visit_code: "T0",
    scheduled_day: 0,
    lifecycle: "BETWEEN_BLOCKS",
    block_order: ["PRACTICE", "LOW", "MEDIUM", "HIGH"],
    current_block_index: 2,
    active_block: null,
    active_block_instance_id: null,
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
      title: "Instructions",
      steps: [],
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
    scores: { [profile]: { block_instance_id: blockInstanceId } },
    active_pid: null,
    last_error: null,
    created_at: "2026-09-10T00:00:00Z",
    started_at: "2026-09-10T00:01:00Z",
    finished_at: null,
  };
}

function renderQuestionnaire(overrides: Partial<React.ComponentProps<typeof WorkloadQuestionnaire>> = {}) {
  const props: React.ComponentProps<typeof WorkloadQuestionnaire> = {
    sessionId: SESSION_ID,
    blockInstanceId: BLOCK_ID,
    profile: "LOW",
    tokenAvailable: true,
    onSubmit: vi.fn().mockResolvedValue(sessionResponse(BLOCK_ID)),
    onAccepted: vi.fn(),
    ...overrides,
  };
  return { props, view: render(<AppLocaleProvider><WorkloadQuestionnaire {...props} /></AppLocaleProvider>) };
}

async function answerAllAtMidpoint(user: ReturnType<typeof userEvent.setup>) {
  for (const label of TLX_LABELS) {
    await user.click(screen.getByRole("button", { name: `Use 50 for ${label}` }));
  }
  await user.click(screen.getByRole("radio", { name: /5 Reduced spare capacity/ }));
}

describe("WorkloadQuestionnaire", () => {
  beforeEach(() => {
    window.localStorage.setItem("matb-fac.locale", "en");
    window.sessionStorage.clear();
    vi.restoreAllMocks();
  });

  it("keeps the midpoint unanswered until the participant deliberately chooses 50", async () => {
    const user = userEvent.setup();
    renderQuestionnaire();

    const mental = await screen.findByRole("slider", { name: "Mental demand" });
    expect(mental).toHaveAttribute("min", "0");
    expect(mental).toHaveAttribute("max", "100");
    expect(mental).toHaveAttribute("step", "5");
    expect(screen.getByText("7 unanswered: Mental demand, Physical demand, Temporal demand, Performance, Effort, Frustration, Bedford.")).toBeInTheDocument();
    expect(screen.getAllByText("Not answered")).toHaveLength(6);

    await user.click(screen.getByRole("button", { name: "Use 50 for Mental demand" }));
    expect(screen.getByText("6 unanswered: Physical demand, Temporal demand, Performance, Effort, Frustration, Bedford.")).toBeInTheDocument();
    expect(screen.getByTestId("mental_demand-value")).toHaveTextContent("50");
  });

  it.each(INSTRUMENT_COPY)("preserves every $locale TLX anchor and Bedford description", async ({ locale, tlx, bedford }) => {
    window.localStorage.setItem("matb-fac.locale", locale);
    renderQuestionnaire();
    await screen.findByRole("slider", { name: tlx[0][1] });

    for (const [key, label, low, high] of tlx) {
      const scale = within(screen.getByTestId(`${key}-scale`));
      const slider = scale.getByRole("slider", { name: label });
      expect(slider).toHaveAttribute("min", "0");
      expect(slider).toHaveAttribute("max", "100");
      expect(slider).toHaveAttribute("step", "5");
      expect(scale.getByText(low)).toBeInTheDocument();
      expect(scale.getByText(high)).toBeInTheDocument();
    }
    expect(screen.getAllByRole("radio")).toHaveLength(10);
    for (const [index, description] of bedford.entries()) {
      expect(screen.getByRole("radio", { name: `${index + 1} ${description}` })).toBeInTheDocument();
    }
  });

  it("restores a valid draft only for the same session and block", async () => {
    const user = userEvent.setup();
    const first = renderQuestionnaire();
    await screen.findByRole("slider", { name: "Mental demand" });
    fireEvent.change(screen.getByRole("slider", { name: "Mental demand" }), { target: { value: "65" } });
    await waitFor(() => expect(sessionStorage.getItem(workloadDraftKey(SESSION_ID, BLOCK_ID))).toContain('"mental_demand":65'));
    first.view.unmount();

    const restored = renderQuestionnaire();
    expect(await screen.findByText("Draft restored for this block.")).toBeInTheDocument();
    expect(screen.getByTestId("mental_demand-value")).toHaveTextContent("65");

    restored.view.unmount();
    renderQuestionnaire({ blockInstanceId: "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee" });
    expect(await screen.findByTestId("mental_demand-value")).toHaveTextContent("Not answered");
    expect(screen.queryByText("Draft restored for this block.")).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Use 50 for Mental demand" }));
  });

  it("never writes block A answers under block B and preserves block B's existing draft", async () => {
    const blockB = "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee";
    const blockBKey = workloadDraftKey(SESSION_ID, blockB);
    const blockBDraft = JSON.stringify({
      instrument_version: "openmatb-workload-v1",
      session_id: SESSION_ID,
      block_instance_id: blockB,
      nasa_tlx: { mental_demand: 25 },
      bedford: null,
    });
    const first = renderQuestionnaire();
    await screen.findByRole("slider", { name: "Mental demand" });
    fireEvent.change(screen.getByRole("slider", { name: "Mental demand" }), { target: { value: "65" } });
    await waitFor(() => expect(sessionStorage.getItem(workloadDraftKey(SESSION_ID, BLOCK_ID))).toContain('"mental_demand":65'));
    sessionStorage.setItem(blockBKey, blockBDraft);

    const writesToBlockB: string[] = [];
    const originalSetItem = Storage.prototype.setItem;
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(function (this: Storage, key, value) {
      if (key === blockBKey) writesToBlockB.push(value);
      return originalSetItem.call(this, key, value);
    });
    first.view.rerender(<AppLocaleProvider><WorkloadQuestionnaire {...first.props} blockInstanceId={blockB} /></AppLocaleProvider>);

    expect(await screen.findByText("Draft restored for this block.")).toBeInTheDocument();
    expect(screen.getByTestId("mental_demand-value")).toHaveTextContent("25");
    expect(writesToBlockB.every((value) => !value.includes('"mental_demand":65'))).toBe(true);
    expect(sessionStorage.getItem(blockBKey)).toBe(blockBDraft);
  });

  it("rejects corrupt or invalid saved drafts with visible feedback", async () => {
    sessionStorage.setItem(workloadDraftKey(SESSION_ID, BLOCK_ID), JSON.stringify({
      instrument_version: "openmatb-workload-v1",
      session_id: SESSION_ID,
      block_instance_id: BLOCK_ID,
      nasa_tlx: { mental_demand: 63 },
      bedford: null,
    }));
    renderQuestionnaire();

    expect(await screen.findByRole("alert")).toHaveTextContent("Saved draft was invalid and was not restored.");
    expect(screen.getByTestId("mental_demand-value")).toHaveTextContent("Not answered");
  });

  it("reports unavailable draft storage instead of losing the error", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation((key) => {
      if (key.startsWith("openmatb.workload-draft.")) throw new DOMException("blocked", "SecurityError");
    });
    renderQuestionnaire();
    await screen.findByRole("slider", { name: "Mental demand" });
    fireEvent.change(screen.getByRole("slider", { name: "Mental demand" }), { target: { value: "60" } });

    expect(await screen.findByRole("alert")).toHaveTextContent("Draft storage is unavailable in this tab. Keep this page open until ratings are saved.");
  });

  it("keeps the exact block-bound draft after failure and clears it only after confirmed success", async () => {
    const user = userEvent.setup();
    const failedSubmit = vi.fn().mockRejectedValue(new Error("network down"));
    const failed = renderQuestionnaire({ onSubmit: failedSubmit });
    await screen.findByRole("slider", { name: "Mental demand" });
    await answerAllAtMidpoint(user);
    await user.click(screen.getByRole("button", { name: "Save ratings and continue" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("network down");
    expect(sessionStorage.getItem(workloadDraftKey(SESSION_ID, BLOCK_ID))).not.toBeNull();
    failed.view.unmount();

    const accepted = vi.fn();
    const success = renderQuestionnaire({ onAccepted: accepted });
    expect(await screen.findByText("Draft restored for this block.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Save ratings and continue" }));
    await waitFor(() => expect(accepted).toHaveBeenCalledTimes(1));
    expect(sessionStorage.getItem(workloadDraftKey(SESSION_ID, BLOCK_ID))).toBeNull();
    success.view.unmount();

    sessionStorage.setItem(workloadDraftKey(SESSION_ID, BLOCK_ID), "retained");
    const mismatch = renderQuestionnaire({ onSubmit: vi.fn().mockResolvedValue(sessionResponse("different-block")) });
    await screen.findByRole("slider", { name: "Mental demand" });
    await answerAllAtMidpoint(user);
    await user.click(screen.getByRole("button", { name: "Save ratings and continue" }));
    expect(await screen.findByText("The server did not confirm ratings for this block. Your draft was kept; try again.")).toBeInTheDocument();
    expect(sessionStorage.getItem(workloadDraftKey(SESSION_ID, BLOCK_ID))).not.toBeNull();
    mismatch.view.unmount();
  });

  it("shows pending submission and sends the explicit identity with all responses", async () => {
    const user = userEvent.setup();
    let resolve!: (session: OpenMatbSession) => void;
    const onSubmit = vi.fn(() => new Promise<OpenMatbSession>((done) => { resolve = done; }));
    renderQuestionnaire({ onSubmit });
    await screen.findByRole("slider", { name: "Mental demand" });
    await answerAllAtMidpoint(user);
    await user.click(screen.getByRole("button", { name: "Save ratings and continue" }));

    expect(screen.getByRole("button", { name: "Saving…" })).toBeDisabled();
    expect(onSubmit).toHaveBeenCalledWith({
      block_instance_id: BLOCK_ID,
      nasa_tlx: {
        mental_demand: 50,
        physical_demand: 50,
        temporal_demand: 50,
        performance: 50,
        effort: 50,
        frustration: 50,
      },
      bedford: 5,
    });
    resolve(sessionResponse(BLOCK_ID));
  });

  it("requires recovery when a legacy session has no block identity", async () => {
    renderQuestionnaire({ blockInstanceId: null });
    expect(await screen.findByRole("alert")).toHaveTextContent("This block cannot be identified. Refresh this page. If the message remains, ask the researcher to reopen the participant display.");
    expect(screen.queryByRole("slider")).not.toBeInTheDocument();
    expect([...Array(sessionStorage.length)].map((_, index) => sessionStorage.key(index))).not.toContainEqual(expect.stringContaining("null"));
  });
});
