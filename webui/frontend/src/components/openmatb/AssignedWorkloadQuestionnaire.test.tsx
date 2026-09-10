import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import { AssignedWorkloadQuestionnaire } from "./AssignedWorkloadQuestionnaire";
import { FixedLocaleProvider } from "@/lib/i18n";
import type { OpenMatbSession } from "@/types/openmatb";
const api = vi.hoisted(() => ({
  getSourceAttempt: vi.fn(),
  listAttempts: vi.fn(),
  repeatAttempt: vi.fn(),
}));
vi.mock("@/lib/assessments", () => api);
beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
});
it("selects the exact questionnaire, saves its identity, and separates a repeated draft", async () => {
  const original = {
    id: "q-original",
    occasion_id: "q",
    target_attempt_id: "task",
    ordinal: 1,
    acquisition_state: "interrupted",
  };
  const repeated = {
    ...original,
    id: "q-repeat",
    ordinal: 2,
    acquisition_state: "created",
  };
  api.getSourceAttempt.mockResolvedValue(original);
  api.listAttempts.mockResolvedValue([original]);
  api.repeatAttempt.mockResolvedValue(repeated);
  const submit = vi.fn(
    async () =>
      ({
        scores: {
          "q-repeat": {
            block_instance_id: "block",
            questionnaire_attempt_id: "q-repeat",
          },
        },
      }) as unknown as OpenMatbSession,
  );
  submit.mockResolvedValueOnce({scores:{old:{block_instance_id:"block",questionnaire_attempt_id:"q-original"}}} as unknown as OpenMatbSession);
  const accepted = vi.fn();
  render(
    <FixedLocaleProvider locale="en">
      <AssignedWorkloadQuestionnaire
        sessionId="suite"
        blockInstanceId="block"
        profile="HIGH"
        tokenAvailable
        onSubmit={submit}
        onAccepted={accepted}
      />
    </FixedLocaleProvider>,
  );
  await screen.findByRole("option", { name: /q-original/ });
  fireEvent.change(
    screen.getByLabelText("Questionnaire attempt for this task"),
    { target: { value: "q-original" } },
  );
  expect(
    screen.queryByRole("button", { name: "Save ratings and continue" }),
  ).toBeNull();
  fireEvent.change(screen.getByLabelText("Questionnaire repeat reason"), {
    target: { value: "Repeat interrupted answers" },
  });
  api.listAttempts.mockResolvedValue([original, repeated]);
  fireEvent.click(
    screen.getByRole("button", { name: "Create explicit repeat" }),
  );
  await screen.findByRole("button", { name: "Use 50 for Mental demand" });
  expect(api.repeatAttempt).toHaveBeenCalledWith(
    "q-original",
    "study",
    "Repeat interrupted answers",
    "task",
  );
  for (const button of screen.getAllByRole("button", { name: /Use 50 for/ }))
    fireEvent.click(button);
  fireEvent.click(
    screen.getByRole("radio", { name: /1 Insignificant workload/ }),
  );
  await waitFor(() =>
    expect(
      sessionStorage.getItem(
        "openmatb.workload-draft.openmatb-workload-v1.suite.block.q-repeat",
      ),
    ).not.toBeNull(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Save ratings and continue" }),
  );
  await screen.findByText(/server did not confirm ratings/);
  expect(accepted).not.toHaveBeenCalled();
  expect(sessionStorage.getItem("openmatb.workload-draft.openmatb-workload-v1.suite.block.q-repeat")).not.toBeNull();
  fireEvent.click(screen.getByRole("button", {name:"Save ratings and continue"}));
  await waitFor(() => expect(accepted).toHaveBeenCalled());
  expect(submit).toHaveBeenCalledWith(
    expect.objectContaining({
      questionnaire_attempt_id: "q-repeat",
      block_instance_id: "block",
    }),
  );
  expect(
    sessionStorage.getItem(
      "openmatb.workload-draft.openmatb-workload-v1.suite.block.q-repeat",
    ),
  ).toBeNull();
});
