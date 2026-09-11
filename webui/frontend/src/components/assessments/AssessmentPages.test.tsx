import React from "react";
import {
  act,
  cleanup,
  fireEvent,
  render as rtlRender,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import PvtPage from "@/app/pvt/page";
import ScreenPage from "@/app/screen/page";
import { FixedLocaleProvider, useAppLocale } from "@/lib/i18n";
import type { Attempt } from "@/lib/assessments";
import * as api from "@/lib/api";
import * as assessments from "@/lib/assessments";
const controls = vi.hoisted(() => ({
  locale: "en" as "en" | "es-419",
  query: "",
  purpose: "study" as "study" | "practice",
  select: null as null | ((a: Attempt | null) => void),
}));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(controls.query),
}));
vi.mock("@/lib/execution-purpose", () => ({
  useExecutionPurpose: () => controls.purpose,
}));
vi.mock("@/lib/console-context", () => ({
  useConsole: () => ({ catalog: [] }),
}));
vi.mock("@/lib/experiment-flow", () => ({
  useReportExperimentFlow: () => {},
  flowStageForPvt: () => "",
  flowStageForScreen: () => "",
}));
vi.mock("@/components/experiments/ExperimentGuide", () => ({
  ExperimentGuide: () => (
    <span data-testid="guide-locale">{useAppLocale().locale}</span>
  ),
  ExecutionPurposeBadge: () => null,
}));
vi.mock("@/components/instructions/InstructionAudio", () => ({
  InstructionAudio: () => null,
}));
vi.mock("@/components/layout/PageHeader", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));
vi.mock("@/components/assessments/AssessmentPicker", () => ({
  AssessmentPicker: ({
    onSelect,
    disabled,
  }: {
    onSelect: (a: Attempt | null) => void;
    disabled?: boolean;
  }) => {
    controls.select = onSelect;
    const locale = useAppLocale().locale;
    return (
      <button
        data-testid="picker-locale"
        data-locale={locale}
        disabled={disabled}
        onClick={() =>
          onSelect({
            id: "attempt-A",
            occasion_id: "occasion-A",
            execution_purpose: "study",
            acquisition_state: "created",
          } as Attempt)
        }
      >
        Choose attempt A
      </button>
    );
  },
}));
vi.mock("@/components/pvt/PvtRunner", () => ({
  PvtRunner: ({ onComplete }: { onComplete: (r: unknown) => void }) => (
    <button
      onClick={() =>
        onComplete({
          durationMs: 600000,
          administeredAt: "2026-09-10T12:00:00Z",
          trials: [],
          interruptionCount: 0,
          maxFrameGapMs: 0,
          terminalPhase: "complete",
          terminalStimulusAtMs: null,
        })
      }
    >
      Complete PVT
    </button>
  ),
}));
vi.mock("next/dynamic", () => ({
  default: () =>
    function ScreenRunner({
      onComplete,
    }: {
      onComplete: (r: unknown) => void;
    }) {
      const locale = useAppLocale().locale;
      return (
        <button
          onClick={() =>
            onComplete({
              schema_version: 2,
              locale,
              administered_at: "2026-09-10T12:00:00Z",
              simple_rt: {},
              choice_rt: {},
              nback: {},
              tracking: {},
            })
          }
        >
          Complete screen
        </button>
      );
    },
}));
vi.mock("@/lib/assessments", () => ({ startAttempt: vi.fn(), interruptAttempt: vi.fn().mockResolvedValue({}) }));
vi.mock("@/lib/api", () => ({
  listParticipants: async () => [{ id: "P01" }, { id: "P02" }],
  listVisits: async (participant: string) => [
    { id: participant === "P01" ? 7 : 8, visit_ordinal: 1, scheduled_day: 0 },
  ],
  getPvtSummary: async () => ({ assessments: [] }),
  postPvt: vi.fn(),
  postScreen: vi.fn(),
}));
function render(ui: React.ReactElement) {
  return rtlRender(ui, {
    wrapper: ({ children }) => (
      <FixedLocaleProvider locale={controls.locale}>
        {children}
      </FixedLocaleProvider>
    ),
  });
}
beforeEach(() => {
  controls.locale = "en";
  controls.query = "";
  controls.purpose = "study";
  controls.select = null;
  vi.clearAllMocks();
});
afterEach(cleanup);

async function choose(kind: "pvt" | "screen") {
  const participant = await screen.findByLabelText(
    kind === "pvt" ? "Participant" : "Your participant code",
  );
  await waitFor(() =>
    expect(screen.getByRole("option", { name: "P01" })).toBeInTheDocument(),
  );
  fireEvent.change(participant, { target: { value: "P01" } });
  await waitFor(() =>
    expect(screen.getByLabelText("Visit")).toHaveValue(
      kind === "pvt" ? "1" : "7",
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Choose attempt A" }));
  return participant;
}

it.each(["pvt", "screen"] as const)(
  "%s ignores a stale start response and locks context controls while admitting",
  async (kind) => {
    let resolveStart!: (a: Attempt) => void;
    vi.mocked(assessments.startAttempt).mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveStart = resolve;
        }),
    );
    render(kind === "pvt" ? <PvtPage /> : <ScreenPage />);
    const participant = await choose(kind);
    fireEvent.click(
      screen.getByRole("button", {
        name:
          kind === "pvt" ? "Continue to KSS" : "View instructions and begin",
      }),
    );
    await waitFor(() => expect(resolveStart).toBeTypeOf("function"));
    expect(participant).toBeDisabled();
    expect(screen.getByLabelText("Visit")).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "Choose attempt A" }),
    ).toBeDisabled();
    // A late external/context update must also invalidate admission, even though
    // ordinary user changes are prevented by the disabled selection controls.
    fireEvent.change(participant, { target: { value: "P02" } });
    await act(async () => {
      resolveStart({
        id: "attempt-A",
        acquisition_state: "started",
        assignment_context: {
          participant_id: "P01",
          visit_id: 7,
          locale: "en",
        },
      } as Attempt);
    });
    expect(screen.queryByRole("radio")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Complete screen" }),
    ).not.toBeInTheDocument();
    expect(participant).toHaveValue("P02");
    expect(api.postPvt).not.toHaveBeenCalled();
    expect(api.postScreen).not.toHaveBeenCalled();
  },
);

it.each(["pvt", "screen"] as const)(
  "%s saves and retries with the admitted immutable context",
  async (kind) => {
    vi.mocked(assessments.startAttempt).mockResolvedValue({
      id: "attempt-A",
      acquisition_state: "started",
      assignment_context: { participant_id: "P01", visit_id: 7, locale: "en" },
    } as Attempt);
    vi.mocked(api.postPvt)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({
        id: 42,
        kss_score: 3,
        protocol_valid: false,
        metrics: { median_rt_ms: null, lapses: 0, false_starts: 0 },
      } as never);
    vi.mocked(api.postScreen)
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValue({
        participant_id: "P01",
        screen_version: 2,
        scores: {},
      });
    const view = render(kind === "pvt" ? <PvtPage /> : <ScreenPage />);
    await choose(kind);
    fireEvent.click(
      screen.getByRole("button", {
        name:
          kind === "pvt" ? "Continue to KSS" : "View instructions and begin",
      }),
    );
    if (kind === "pvt") {
      const radios = await screen.findAllByRole("radio");
      fireEvent.click(radios[2]);
      fireEvent.click(
        screen.getByRole("button", {
          name: "Confirm KSS and view PVT instructions",
        }),
      );
      fireEvent.click(screen.getByRole("button", { name: "I am ready" }));
    }
    await screen.findByRole("button", {
      name: kind === "pvt" ? "Complete PVT" : "Complete screen",
    });
    controls.purpose = "practice";
    act(() => controls.select?.(null));
    view.rerender(kind === "pvt" ? <PvtPage /> : <ScreenPage />);
    fireEvent.click(
      screen.getByRole("button", {
        name: kind === "pvt" ? "Complete PVT" : "Complete screen",
      }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Retry saving" }),
    );
    await waitFor(() =>
      expect(
        kind === "pvt" ? api.postPvt : api.postScreen,
      ).toHaveBeenCalledTimes(2),
    );
    if (kind === "pvt") {
      for (const [payload] of vi.mocked(api.postPvt).mock.calls)
        expect(payload).toMatchObject({
          attempt_id: "attempt-A",
          participant_id: "P01",
          visit_ordinal: 1,
          execution_purpose: "study",
          kss_score: 3,
          locale: "en",
        });
      expect(vi.mocked(api.postPvt).mock.calls[0][0]).toEqual(
        vi.mocked(api.postPvt).mock.calls[1][0],
      );
    } else {
      for (const [participant, , , purpose, attemptId] of vi.mocked(
        api.postScreen,
      ).mock.calls)
        expect([participant, purpose, attemptId]).toEqual([
          "P01",
          "study",
          "attempt-A",
        ]);
      expect(vi.mocked(api.postScreen).mock.calls[0]).toEqual(
        vi.mocked(api.postScreen).mock.calls[1],
      );
    }
  },
);

it.each(["pvt", "screen"] as const)(
  "%s updates visible participant and clears old selection on same-path assignment navigation",
  async (kind) => {
    controls.query = "attempt=A&participant=P01&visit=7";
    const element = () => (kind === "pvt" ? <PvtPage /> : <ScreenPage />);
    const view = render(element());
    await choose(kind);
    controls.query = "attempt=B&participant=P02&visit=8";
    view.rerender(element());
    await waitFor(() =>
      expect(
        screen.getByLabelText(
          kind === "pvt" ? "Participant" : "Your participant code",
        ),
      ).toHaveValue("P02"),
    );
    await waitFor(() =>
      expect(screen.getByLabelText("Visit")).toHaveValue(
        kind === "pvt" ? "1" : "8",
      ),
    );
    expect(
      screen.getByRole("button", {
        name:
          kind === "pvt" ? "Continue to KSS" : "View instructions and begin",
      }),
    ).toBeDisabled();
  },
);

it.each([
  ["en", "assignment_context"],
  ["es-419", "assignment_context"],
  ["en", "preparation_context"],
  ["es-419", "preparation_context"],
] as const)(
  "screen binds all participant copy to %s from %s through setup, pending save, retry and review",
  async (boundLocale, binding) => {
    controls.purpose = binding === "preparation_context" ? "practice" : "study";
    controls.locale = boundLocale === "en" ? "es-419" : "en";
    const en = boundLocale === "en";
    const selected = {
      id: "attempt-A",
      occasion_id: "occasion-A",
      execution_purpose: controls.purpose,
      acquisition_state: "created",
      ordinal: 1,
      purpose_provenance_id: "purpose-A",
      repeat_of: null,
      repeat_reason: null,
      target_attempt_id: null,
      interruption_category: null,
      receipt: {
        raw_saving: "pending",
        acquisition: "created",
        ratings: "pending",
        processing: "pending",
      },
      sources: [],
      [binding]: {
        participant_id: "P01",
        visit_id: 7,
        locale: boundLocale,
        assignment_id: "assignment-A",
      },
    } as Attempt;
    vi.mocked(assessments.startAttempt).mockResolvedValue({
      ...selected,
      acquisition_state: "started",
    });
    let rejectSave!: (reason: Error) => void;
    vi.mocked(api.postScreen)
      .mockImplementationOnce(
        () =>
          new Promise((_resolve, reject) => {
            rejectSave = reject;
          }),
      )
      .mockResolvedValue({
        participant_id: "P01",
        screen_version: 2,
        scores: {},
      });
    const view = render(<ScreenPage />);
    const selector = await screen.findByLabelText(
      controls.locale === "en"
        ? "Your participant code"
        : "Su código de participante",
    );
    await waitFor(() =>
      expect(screen.getByRole("option", { name: "P01" })).toBeInTheDocument(),
    );
    fireEvent.change(selector, { target: { value: "P01" } });
    await waitFor(() =>
      expect(
        screen.getByLabelText(controls.locale === "en" ? "Visit" : "Visita"),
      ).toHaveValue("7"),
    );
    act(() => controls.select?.(selected));
    expect(
      screen.getByRole("heading", {
        name: en ? "Cognitive battery" : "Batería cognitiva",
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByLabelText(
        en ? "Your participant code" : "Su código de participante",
      ),
    ).toBeInTheDocument();
    expect(screen.getByTestId("guide-locale")).toHaveTextContent(boundLocale);
    expect(screen.getByTestId("picker-locale")).toHaveAttribute(
      "data-locale",
      boundLocale,
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: en
          ? "View instructions and begin"
          : "Ver instrucciones y comenzar",
      }),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "Complete screen" }),
    );
    await waitFor(() => expect(rejectSave).toBeTypeOf("function"));
    expect(screen.getByRole("status")).toHaveTextContent(
      en ? "Saving responses…" : "Guardando respuestas…",
    );
    act(() =>
      controls.select?.({
        ...selected,
        id: "attempt-B",
        assignment_context: {
          ...selected.assignment_context!,
          locale: controls.locale,
          assignment_id: "assignment-B",
        },
      }),
    );
    view.rerender(<ScreenPage />);
    expect(screen.getByRole("status")).toHaveTextContent(
      en ? "Saving responses…" : "Guardando respuestas…",
    );
    await act(async () => rejectSave(new Error("offline")));
    expect(screen.getByRole("alert")).toHaveTextContent(
      en ? "Could not save" : "No se pudo guardar",
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: en ? "Retry saving" : "Reintentar guardado",
      }),
    );
    await screen.findByRole("heading", {
      name: en ? "Responses saved" : "Respuestas guardadas",
    });
    expect(
      screen.getByRole("link", {
        name: en
          ? "Continue visit: next action"
          : "Continuar visita: siguiente acción",
      }),
    ).toHaveAttribute("href", "/study/participant?assignment=assignment-A");
    expect(
      screen.getByRole("heading", {
        name: en ? "Simple reaction" : "Reacción simple",
      }),
    ).toBeInTheDocument();
    for (const [participant, payload, , purpose, attemptId] of vi.mocked(
      api.postScreen,
    ).mock.calls) {
      expect([participant, purpose, attemptId]).toEqual([
        "P01",
        controls.purpose,
        "attempt-A",
      ]);
      expect(payload.locale).toBe(boundLocale);
    }
  },
);
