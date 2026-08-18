import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LiftoffSessionConsole } from "@/components/liftoff/LiftoffSessionConsole";

const { mockGet, mockReadiness, mockTransition } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockReadiness: vi.fn(),
  mockTransition: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));
vi.mock("@/lib/liftoff/api", () => ({
  getLiftoffSession: mockGet,
  getLiftoffReadiness: mockReadiness,
  transitionLiftoff: mockTransition,
}));

describe("LiftoffSessionConsole", () => {
  beforeEach(() => {
    mockGet.mockResolvedValue({ id: "session-1", status: "PREPARED", visit_code: "T0" });
    mockReadiness.mockResolvedValue({ ready: true, valid_packets: 20, invalid_packet_count: 0, overflow_count: 0 });
    mockTransition.mockResolvedValue({ id: "session-1", status: "BASELINE", visit_code: "T0" });
    sessionStorage.setItem("matb.liftoff.session-1.lease", "secret");
  });

  it("advances the first phase with the stored lease", async () => {
    const user = userEvent.setup();
    render(<LiftoffSessionConsole sessionId="session-1" />);

    await waitFor(() => expect(screen.getByText(/prepared/i)).toBeInTheDocument());
    await user.click(screen.getByRole("button", { name: /start baseline/i }));

    expect(mockTransition).toHaveBeenCalledWith("session-1", "baseline/start", "secret");
  });
});
