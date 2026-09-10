import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SessionReceipt } from "./SessionReceipt";
import type { OpenMatbReceipt } from "@/types/openmatb";
vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ copy: (_es: string, en: string) => en }) }));

describe("completion receipt", () => {
  it("keeps saved ratings, failed import and pending processing separate", () => {
    const receipt = { session_id: "suite", participant_id: "P01", visit_ordinal: 2, historical: false, attempts: [{
      block_instance_id: "attempt", profile: "LOW", task_status: "completed", artifact_status: "saved", ratings_status: "saved",
      legacy_import_status: "failed", evidence_status: "queued", capture_id: null, qualification: null,
    }] } as OpenMatbReceipt;
    render(<SessionReceipt receipt={receipt} />);
    expect(screen.getByText(/P01 · V2/)).toBeInTheDocument();
    expect(screen.getByText("Study import").nextSibling).toHaveTextContent("Failed");
    expect(screen.getByText("Ratings").nextSibling).toHaveTextContent("Saved");
    expect(screen.getByText("Evidence processing").nextSibling).toHaveTextContent("Queued");
    expect(screen.getByText("Physical timing").nextSibling).toHaveTextContent("Not assessed");
    expect(screen.queryByText("Success")).toBeNull();
  });
  it("reports missing historical receipt facts without fabricating successful blocks", () => {
    render(<SessionReceipt receipt={{ session_id: "old", participant_id: "P01", visit_ordinal: 1, historical: true, attempts: [] } as unknown as OpenMatbReceipt} />);
    expect(screen.getByText(/Detailed save states were not recorded/)).toBeInTheDocument();
    expect(screen.queryByText("Saved")).toBeNull();
  });
});
