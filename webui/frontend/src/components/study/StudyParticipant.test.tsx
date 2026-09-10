import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { StudyParticipant } from "./StudyParticipant";
import { assignmentDetail, studyCall } from "@/lib/study";
import { FixedLocaleProvider } from "@/lib/i18n";
const controls = vi.hoisted(() => ({ identity: "A" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(`assignment=${controls.identity}`),
  useRouter: () => ({ push: vi.fn() }),
}));
vi.mock("@/lib/study", () => ({
  assignmentDetail: vi.fn(),
  studyCall: vi.fn(),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
  controls.identity = "A";
});
it("a pending A readiness response cannot create an active stop target under assignment B", async () => {
  const detail = (id: string) => ({
    assignment: { id, participant_id: `participant-${id}`, visit_id: 1 },
    version: {
      study: {
        title: `Study ${id}`,
        occasions: [{ key: "task", instrument: "pvt", order: 1, locale: "en" }],
      },
    },
    occasions: { task: `occasion-${id}` },
    attempts: { task: [] },
  });
  vi.mocked(assignmentDetail).mockImplementation(
    async (id) => detail(id) as never,
  );
  let releaseA!: (value: unknown) => void;
  vi.mocked(studyCall).mockImplementation(async (path) =>
    path.includes("/A/")
      ? new Promise((resolve) => {
          releaseA = resolve;
        })
      : ({ requirements: { task: [] }, preparations: [] } as never),
  );
  const element = () => (
    <FixedLocaleProvider locale="en">
      <StudyParticipant />
    </FixedLocaleProvider>
  );
  const view = render(element());
  await waitFor(() => expect(releaseA).toBeTypeOf("function"));
  controls.identity = "B";
  view.rerender(element());
  await screen.findByRole("heading", {
    name: "Participant visit: participant-B",
  });
  await act(async () =>
    releaseA({
      requirements: { task: [{ occasion_key: "task", state: "required" }] },
      preparations: [
        {
          id: "A-prep",
          occasion_key: "task",
          next_action: "practice",
          events: [],
          presentation: { locale: "en", items: [] },
        },
      ],
    }),
  );
  expect(
    screen.getByRole("button", { name: "Stop preparation" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Prepare · task" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByText(/A-prep/)).not.toBeInTheDocument();
});
