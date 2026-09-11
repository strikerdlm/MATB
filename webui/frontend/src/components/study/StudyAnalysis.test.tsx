import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { vi, describe, it, expect } from "vitest";
import { StudyAnalysis } from "./StudyAnalysis";
vi.mock("@/lib/i18n", () => ({
  useAppLocale: () => ({ copy: (_es: string, en: string) => en }),
}));
const call = vi.fn();
vi.mock("@/lib/study", () => ({
  studyCall: (...args: unknown[]) => call(...args),
  studyVersions: async () => ({
    versions: [
      { id: "v1", analysis_plan_id: "plan1", study: { title: "Frozen study" } },
    ],
  }),
}));
vi.mock("@/lib/runtime-config", () => ({ getApiBase: async () => "/api" }));
describe("StudyAnalysis", () => {
  it("requires explicit preview/run and keeps missing occasion visible", async () => {
    call.mockImplementation(async (path: string) =>
      path === "/analyses"
        ? []
        : path === "/analyses/hcf"
          ? []
          : {
              rows: [
                {
                  occasion_id: "o1",
                  occasion_key: "pre",
                  participant_id: "p1",
                  attempt_id: null,
                  attempts: [],
                  denominator: true,
                  eligible: false,
                  criteria: {
                    selection: {
                      passed: false,
                      required: true,
                      reason: "Missing attempt",
                    },
                  },
                },
              ],
              comparisons: {},
              plan: { eligibility_policy: { repeat_selection: "explicit" } },
            },
    );
    render(<StudyAnalysis />);
    await screen.findByText("Frozen study");
    expect(call.mock.calls.some((c) => c[0] === "/analyses/preview")).toBe(
      false,
    );
    fireEvent.change(screen.getByLabelText("Frozen plan"), {
      target: { value: "v1" },
    });
    fireEvent.change(screen.getByLabelText("Researcher"), {
      target: { value: "Dr Test" },
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Descriptive review" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Inspect eligibility" }),
    );
    await waitFor(() =>
      expect(screen.getByText("Missing attempt")).toBeInTheDocument(),
    );
    expect(screen.getByText(/Included in denominator/)).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Original evidence" }),
    ).toHaveAttribute("href", "/api/assessments/occasions/o1");
    expect(
      call.mock.calls.filter((c) => c[0] === "/analyses" && c[1] !== undefined),
    ).toHaveLength(0);
  });
});

function savedSnapshot(attempt: string) {
  return {
    rows: [
      {
        occasion_id: "old-occasion",
        occasion_key: "native",
        participant_id: "p1",
        instrument: "openmatb",
        attempt_id: attempt,
        attempts: [{ id: attempt, ordinal: 1, acquisition_state: "finished" }],
        denominator: true,
        eligible: true,
        criteria: {},
        values: { score: 0.8 },
      },
    ],
    comparisons: {},
    plan: { eligibility_policy: { repeat_selection: "explicit" } },
  };
}

it.each(["button", "url"])(
  "keeps %s reopened evidence outside editable requests",
  async (mode) => {
    window.history.replaceState(null, "", "/study/analysis");
    call.mockClear();
    const saved = {
      id: "saved-id",
      version_id: "saved-other-version",
      data_sha256: "data",
      plan_sha256: "plan",
      snapshot: savedSnapshot("saved-attempt"),
      result: { outcomes: {} },
      current_applicability: { changed: false },
    };
    call.mockImplementation(async (path: string, body?: unknown) => {
      if (path === "/analyses/saved-id") return saved;
      if (path === "/analyses/preview") return savedSnapshot("prior-attempt");
      if (path === "/analyses" && body) return { ...saved, id: "new-id" };
      return [];
    });
    let rendered = render(<StudyAnalysis />);
    await screen.findByText("Frozen study");
    fireEvent.change(screen.getByLabelText("Frozen plan"), {
      target: { value: "v1" },
    });
    fireEvent.change(screen.getByLabelText("Researcher"), {
      target: { value: "Dr Prior" },
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Prior selection" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Inspect eligibility" }),
    );
    await screen.findByText("prior-attempt", { exact: false });
    fireEvent.change(screen.getByLabelText("Exact attempt"), {
      target: { value: "prior-attempt" },
    });
    fireEvent.change(
      screen.getByLabelText("Exact native metric IDs (comma separated)"),
      { target: { value: "prior-metric" } },
    );
    fireEvent.change(screen.getByLabelText("physical_timing"), {
      target: { value: "prior-qualification" },
    });
    if (mode === "url") {
      rendered.unmount();
      window.history.replaceState(
        null,
        "",
        "/study/analysis?execution=saved-id",
      );
      rendered = render(<StudyAnalysis />);
    } else {
      fireEvent.change(screen.getByLabelText("Execution ID"), {
        target: { value: "saved-id" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Reopen" }));
    }
    await screen.findByRole("link", {
      name: "Export data, code and offline replay",
    });
    expect(
      screen.queryByRole("button", { name: "Execute and freeze description" }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("combobox", { name: "Exact attempt" }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Frozen eligibility and selection"),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "Start a new analysis" }),
    );
    expect(screen.getByLabelText("Frozen plan")).toHaveValue("");
    expect(
      screen.queryByRole("button", { name: "Execute and freeze description" }),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Frozen plan"), {
      target: { value: "v1" },
    });
    fireEvent.change(screen.getByLabelText("Researcher"), {
      target: { value: "Dr New" },
    });
    fireEvent.change(screen.getByLabelText("Reason"), {
      target: { value: "Fresh review" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Inspect eligibility" }),
    );
    await waitFor(() =>
      expect(call).toHaveBeenLastCalledWith("/analyses/preview", {
        version_id: "v1",
        actor: "Dr New",
        reason: "Fresh review",
        attempts: {},
        native_metric_ids: {},
        hcf_attempts: {},
        qualification_ids: {},
      }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Execute and freeze description" }),
    );
    await waitFor(() =>
      expect(
        call.mock.calls.filter(([path, body]) => path === "/analyses" && body),
      ).toEqual([
        [
          "/analyses",
          {
            version_id: "v1",
            actor: "Dr New",
            reason: "Fresh review",
            attempts: {},
            native_metric_ids: {},
            hcf_attempts: {},
            qualification_ids: {},
          },
        ],
      ]),
    );
    rendered.unmount();
    window.history.replaceState(null, "", "/study/analysis");
  },
);
