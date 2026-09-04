import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { LiftoffDebrief } from "@/components/liftoff/LiftoffDebrief";

const { mockResults, mockQuestionnaires, mockSeal } = vi.hoisted(() => ({
  mockResults: vi.fn(),
  mockQuestionnaires: vi.fn(),
  mockSeal: vi.fn(),
}));

vi.mock("@/lib/liftoff/api", () => ({
  submitLiftoffResults: mockResults,
  submitLiftoffQuestionnaires: mockQuestionnaires,
  sealLiftoffSession: mockSeal,
}));

describe("LiftoffDebrief", () => {
  beforeEach(() => {
    sessionStorage.setItem("matb.liftoff.session-1.lease", "secret");
    mockResults.mockResolvedValue(undefined);
    mockQuestionnaires.mockResolvedValue(undefined);
    mockSeal.mockResolvedValue({ id: "session-1", status: "FINISHED", validity: "valid" });
  });

  it("records visible outcomes and questionnaires before sealing", async () => {
    const user = userEvent.setup();
    render(<LiftoffDebrief sessionId="session-1" />);
    await user.type(screen.getByLabelText(/valid lap times/i), "61.2, 63.0");
    const file = new File(["png"], "result.png", { type: "image/png" });
    await user.upload(screen.getByLabelText(/result screenshot/i), file);
    expect(screen.getByRole("button", { name: /seal session/i })).toBeDisabled();
    await user.type(screen.getByLabelText(/sleepiness.*1.*9/i), "3");
    for (const label of ["Mental demand", "Physical demand", "Temporal demand", "Performance", "Effort", "Frustration"]) {
      await user.type(screen.getByLabelText(label, { exact: true }), "25");
    }
    await user.click(screen.getByRole("button", { name: /seal session/i }));

    await waitFor(() => expect(mockSeal).toHaveBeenCalledWith("session-1", "secret"));
    expect(mockResults).toHaveBeenCalled();
    expect(mockQuestionnaires).toHaveBeenCalledWith("session-1", "secret", expect.objectContaining({ kss: 3, mental_demand: 25, frustration: 25 }));
  });
});
