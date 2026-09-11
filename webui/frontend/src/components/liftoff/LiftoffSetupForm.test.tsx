import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LiftoffSetupForm } from "@/components/liftoff/LiftoffSetupForm";
import type { Participant, StudyProtocol } from "@/types";

const {
  mockPush,
  mockCreate,
  mockReadiness,
  mockGetContext,
  mockAssigned,
  mockGetAttempt,
} = vi.hoisted(() => ({
  mockAssigned: { current: null as unknown },
  mockGetAttempt: vi.fn(),
  mockPush: vi.fn(),
  mockCreate: vi.fn(),
  mockReadiness: vi.fn(),
  mockGetContext: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => "/liftoff/setup",
  useSearchParams: () => new URLSearchParams("purpose=study"),
  useRouter: () => ({ push: mockPush }),
}));
vi.mock("@/lib/liftoff/api", async () => {
  const actual =
    await vi.importActual<typeof import("@/lib/liftoff/api")>(
      "@/lib/liftoff/api",
    );
  return {
    ...actual,
    createLiftoffSession: mockCreate,
    getLiftoffReadiness: mockReadiness,
  };
});
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getStudyContext: mockGetContext,
    listVisits: vi.fn(async () => [
      {
        id: 2,
        participant_id: "P01",
        visit_ordinal: 2,
        scheduled_day: 8,
        status: "planned",
      },
    ]),
  };
});

// Transport fixture for an already approved assignment; backend approval/admission is integration-tested separately.
vi.mock("@/lib/assigned-attempt", () => ({
  useAssignedAttempt: () => mockAssigned.current,
}));
vi.mock("@/lib/assessments", async () => ({
  ...(await vi.importActual<typeof import("@/lib/assessments")>(
    "@/lib/assessments",
  )),
  getAttempt: mockGetAttempt,
}));

const participants: Participant[] = [
  { id: "P01", enrollment_date: "2026-01-01" },
];
const protocol: StudyProtocol = {
  protocol_id: "astra-2026",
  protocol_version: "1.0.0",
  schedule_sha256: "hash",
  visits: [
    { ordinal: 1, code: "T0", scheduled_day: 0 },
    { ordinal: 2, code: "DM8", scheduled_day: 8 },
    { ordinal: 3, code: "DM15", scheduled_day: 15 },
  ],
};

describe("LiftoffSetupForm", () => {
  beforeEach(() => {
    const context = {
      participant_id: "P01",
      visit_id: 2,
      assigned_visit: { ordinal: 16, code: "CUSTOM", scheduled_day: 44 },
      locale: "en",
      config: {
        configuration: {
          liftoff_build: "fixture-build",
          controller_firmware: "fixture-firmware",
        },
      },
    };
    mockAssigned.current = {
      attempt: { id: "assigned-liftoff" },
      context,
      error: "",
    };
    mockGetAttempt.mockResolvedValue({
      id: "assigned-liftoff",
      assignment_context: context,
    });
    mockPush.mockReset();
    mockCreate.mockReset();
    mockReadiness.mockResolvedValue({ ready: true, valid_packets: 20 });
    mockGetContext.mockRejectedValue(new Error("No legacy study context"));
    window.sessionStorage.clear();
  });

  it("stores the one-time lease outside the URL", async () => {
    mockCreate.mockResolvedValue({
      id: "session-1",
      status: "PREPARED",
      controller_lease: "secret",
    });
    const user = userEvent.setup();
    render(
      <LiftoffSetupForm participants={participants} protocol={protocol} />,
    );
    await waitFor(() =>
      expect(screen.getByText(/telemetry ready/i)).toBeInTheDocument(),
    );

    await waitFor(() =>
      expect(screen.getByLabelText(/visit/i)).toHaveValue("16"),
    );
    expect(screen.getByLabelText(/participant/i)).toBeDisabled();
    await user.click(screen.getByRole("button", { name: /prepare/i }));

    await waitFor(() =>
      expect(mockPush).toHaveBeenCalledWith(
        "/liftoff/session?session=session-1",
      ),
    );
    expect(sessionStorage.getItem("matb.liftoff.session-1.lease")).toBe(
      "secret",
    );
    expect(mockPush.mock.calls[0][0]).not.toContain("secret");
    expect(mockGetContext).not.toHaveBeenCalled();
    expect(mockCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        visit_ordinal: 16,
        attempt_id: "assigned-liftoff",
      }),
    );
  });
});
