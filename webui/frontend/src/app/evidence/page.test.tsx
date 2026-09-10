import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EvidencePageView from "./page";
import { evidenceRequest } from "@/lib/evidence";

const navigation = vi.hoisted(() => ({ query: "", push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useSearchParams: () => new URLSearchParams(navigation.query),
  useRouter: () => ({ push: navigation.push }),
}));
vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ locale: "en", copy: (_es: string, en: string) => en }) }));
vi.mock("@/lib/evidence", () => ({ evidenceRequest: vi.fn() }));
vi.mock("@/components/evidence/EvidenceInspector", () => ({ EvidenceInspector: ({ capture }: { capture: { id: string } }) => <div>Reviewing {capture.id}</div> }));
const request = vi.mocked(evidenceRequest);
const row = { id: "capture-a", participant_id: "P01", visit_ordinal: 1, block_instance_id: "block-a", condition: "LOW",
  execution_purpose: "study", completion: "completed", created_at: "2026-09-09T12:00:00Z", capture_status: "reconciled",
  qualification: { physical_timing: "not_qualified", human_calibration: "not_qualified", protocol_eligibility: { status: "not_assessed" } } };

describe("evidence discovery", () => {
  beforeEach(() => { navigation.query = "purpose=all&session=suite-a&capture=capture-a"; navigation.push.mockReset(); request.mockReset(); });

  it("loads the exact URL capture independently of a failed list request", async () => {
    request.mockImplementation(async url => {
      if (url.includes("?")) throw new Error("list unavailable");
      return { id: "capture-a" };
    });
    render(<EvidencePageView />);
    expect(await screen.findByText("Reviewing capture-a")).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("list unavailable");
    expect(request).toHaveBeenCalledWith(expect.stringContaining("session=suite-a"), expect.anything());
  });

  it("highlights selected capture and preserves it when changing search or pages", async () => {
    request.mockImplementation(async url => url.includes("?") ? { total: 26, offset: 0, limit: 25, items: [row] } : { id: "capture-a" });
    render(<EvidencePageView />);
    const selected = await screen.findByRole("link", { name: /Review P01/ });
    expect(selected).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("columnheader", { name: "Registered" })).toBeInTheDocument();
    expect(screen.getByText(/Timing: Not qualified/)).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "P02" } });
    fireEvent.submit(screen.getByRole("search"));
    expect(navigation.push).toHaveBeenCalledWith(expect.stringMatching(/capture=capture-a.*q=P02/), { scroll: false });
    const next = screen.getByRole("link", { name: "Next" });
    expect(next.getAttribute("href")).toContain("capture=capture-a");
    expect(next.getAttribute("href")).toContain("offset=25");
  });

  it("shows independent loading states and ignores a previous capture response after navigation", async () => {
    let oldCapture!: (value: unknown) => void;
    request.mockImplementation(url => {
      if (url.includes("?")) return Promise.resolve({ total: 0, offset: 0, limit: 25, items: [] });
      if (url.endsWith("capture-a")) return new Promise(resolve => { oldCapture = resolve; });
      return Promise.resolve({ id: "capture-b" });
    });
    const view = render(<EvidencePageView />);
    expect(screen.getByText("Loading selected capture…")).toBeInTheDocument();
    navigation.query = "purpose=all&capture=capture-b";
    view.rerender(<EvidencePageView />);
    expect(await screen.findByText("Reviewing capture-b")).toBeInTheDocument();
    await act(async () => oldCapture({ id: "capture-a" }));
    await waitFor(() => expect(screen.queryByText("Reviewing capture-a")).not.toBeInTheDocument());
  });
});
