import { beforeEach, describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { UploadForm } from "@/components/upload/UploadForm";

const { mockBundle, mockCsv } = vi.hoisted(() => ({
  mockBundle: vi.fn(),
  mockCsv: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, ingestBundle: mockBundle, ingestCsv: mockCsv };
});

describe("UploadForm", () => {
  beforeEach(() => {
    mockBundle.mockReset();
    mockCsv.mockReset();
  });

  it("uploads a scientific bundle and reports run and timing quality", async () => {
    mockBundle.mockResolvedValue({
      id: 1,
      block_id: 2,
      bundle_sha256: "abc",
      schema_version: "matb-scientific-bundle-v1",
      run_status: "complete",
      quality_status: "warning",
    });
    const user = userEvent.setup();
    render(
      <UploadForm
        participants={[{ id: "P01", enrollment_date: "2026-01-01" }]}
        onIngested={vi.fn()}
      />,
    );

    await user.selectOptions(screen.getByLabelText(/package format/i), "bundle");
    await user.selectOptions(screen.getByLabelText(/participant/i), "P01");
    await user.upload(
      screen.getByLabelText(/scientific bundle/i),
      new File([new Uint8Array([80, 75])], "run.matb.zip", { type: "application/zip" }),
    );
    await user.click(screen.getByRole("button", { name: /ingest bundle/i }));

    await waitFor(() => expect(mockBundle).toHaveBeenCalledOnce());
    expect(screen.getByText(/complete; timing quality warning/i)).toBeInTheDocument();
    expect(mockCsv).not.toHaveBeenCalled();
  });
});
