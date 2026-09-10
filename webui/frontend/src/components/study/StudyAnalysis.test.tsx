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
      call.mock.calls.filter((c) => c[0] === "/analyses" && c[1] !== undefined),
    ).toHaveLength(0);
  });
});
