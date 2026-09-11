import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { StudyParticipant } from "./StudyParticipant";
import { assignmentDetail, studyCall } from "@/lib/study";
import { getOpenMatbSession, abortOpenMatbSession } from "@/lib/openmatb/api";
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
vi.mock("@/lib/openmatb/api", () => ({
  getOpenMatbSession: vi.fn(),
  abortOpenMatbSession: vi.fn(),
  readOpenMatbController: () => "lease",
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

for (const ownership of [
  "ambiguous",
  "unavailable",
  "foreign-assignment",
  "foreign-occasion",
  "foreign-terminal",
  "retained-attempt",
] as const) {
  it(`does not persist a stop when associated native ownership is ${ownership}`, async () => {
    const preparation = {
      id: "prep-A",
      occasion_key: "task",
      instrument: "openmatb",
      next_action: "resolve_mapping",
      presentation: { locale: "en", items: [] },
      events:
        ownership === "retained-attempt"
          ? [
              {
                stage: "native_presentation",
                session_id: "native-1",
                native_attempt_id: "wrong-attempt",
                passed: true,
              },
            ]
          : [],
      practice_attempt_ids: [],
    };
    const detail = {
      assignment: { id: "A", participant_id: "P01", visit_id: 1 },
      version: {
        study: {
          title: "Native",
          occasions: [
            { key: "task", instrument: "openmatb", order: 1, locale: "en" },
          ],
        },
      },
      occasions: { task: "occasion-A" },
      attempts: {
        task: [
          {
            id: "attempt-A",
            occasion_id:
              ownership === "foreign-occasion" ? "occasion-B" : "occasion-A",
            acquisition_state: "created",
            sources: (ownership === "ambiguous"
              ? ["native-1", "native-2"]
              : ["native-1"]
            ).map((source_id) => ({
              source_table: "openmatb_suite_session",
              source_id,
              role: "primary",
            })),
          },
        ],
      },
    };
    vi.mocked(assignmentDetail).mockResolvedValue(detail as never);
    vi.mocked(studyCall).mockImplementation(
      async (path) =>
        (path.endsWith("/stop")
          ? { ...preparation, next_action: "stopped" }
          : {
              preparations: [preparation],
              requirements: { task: [] },
            }) as never,
    );
    vi.mocked(getOpenMatbSession).mockImplementation(async (id) => {
      if (ownership === "unavailable")
        throw new Error("Native ownership unavailable");
      return {
        id: ownership === "foreign-terminal" ? "wrong-session" : id,
        lifecycle:
          ownership === "foreign-terminal" ? "ABORTED" : "PREFLIGHT_HELD",
        participant_id: "P01",
        study_assignment_id: ownership === "foreign-assignment" ? "B" : "A",
      } as never;
    });
    render(
      <FixedLocaleProvider locale="en">
        <StudyParticipant />
      </FixedLocaleProvider>,
    );
    const stop = await screen.findByRole("button", {
      name: "Stop preparation",
    });
    await waitFor(() => expect(stop).toBeEnabled());
    fireEvent.click(stop);
    await screen.findByRole("alert");
    expect(
      vi.mocked(studyCall).mock.calls.some(([path]) => path.endsWith("/stop")),
    ).toBe(false);
    expect(abortOpenMatbSession).not.toHaveBeenCalled();
    expect(
      screen.queryByText(/Preparation stopped. Prior records/),
    ).not.toBeInTheDocument();
  });
}
