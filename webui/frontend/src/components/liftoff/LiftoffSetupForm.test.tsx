import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LiftoffSetupForm } from "@/components/liftoff/LiftoffSetupForm";
import type { Participant, StudyProtocol } from "@/types";

const { mockPush, mockCreate, mockReadiness, mockGetContext } = vi.hoisted(() => ({
  mockPush: vi.fn(),
  mockCreate: vi.fn(),
  mockReadiness: vi.fn(),
  mockGetContext: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: mockPush }) }));
vi.mock("@/lib/liftoff/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/liftoff/api")>("@/lib/liftoff/api");
  return { ...actual, createLiftoffSession: mockCreate, getLiftoffReadiness: mockReadiness };
});
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, getStudyContext: mockGetContext };
});

const participants: Participant[] = [{ id: "P01", enrollment_date: "2026-01-01" }];
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
    mockPush.mockReset();
    mockCreate.mockReset();
    mockReadiness.mockResolvedValue({ ready: true, valid_packets: 20 });
    mockGetContext.mockResolvedValue({
      participant_id: "P01",
      protocol_id: "astra-2026",
      task_sequence: "MATB_LIFTOFF",
      prior_fpv_hours: 10,
      gaming_hours_per_week: 2,
      created_at: "2026-08-18T00:00:00Z",
    });
    window.sessionStorage.clear();
  });

  it("stores the one-time lease outside the URL", async () => {
    mockCreate.mockResolvedValue({
      id: "session-1",
      status: "PREPARED",
      controller_lease: "secret",
    });
    const user = userEvent.setup();
    render(<LiftoffSetupForm participants={participants} protocol={protocol} />);
    await waitFor(() => expect(screen.getByText(/telemetry ready/i)).toBeInTheDocument());

    await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
    await user.selectOptions(screen.getByLabelText(/visit/i), "2");
    await user.click(screen.getByRole("button", { name: /prepare/i }));

    await waitFor(() => expect(mockPush).toHaveBeenCalledWith("/liftoff/session?session=session-1"));
    expect(sessionStorage.getItem("matb.liftoff.session-1.lease")).toBe("secret");
    expect(mockPush.mock.calls[0][0]).not.toContain("secret");
  });
});
