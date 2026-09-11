import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { StudyHistory } from "./StudyHistory";
import { FixedLocaleProvider } from "@/lib/i18n";
const controls = vi.hoisted(() => ({ participant: "A" }));
vi.mock("next/navigation", () => ({
  useSearchParams: () =>
    new URLSearchParams(`participant=${controls.participant}`),
}));
vi.mock("@/lib/runtime-config", () => ({
  getApiBase: async () => "http://local",
}));
vi.mock("@/lib/study", () => ({
  studyCall: async (path: string) => {
    const participant = path.includes("/A/") ? "A" : "B";
    return [
      {
        participant_id: participant,
        attempt_id: `attempt-${participant}`,
        instrument: "pvt",
        purpose_provenance_id: `purpose-${participant}`,
        purpose_origin: "unknown",
      },
      ...(participant === "B"
        ? [
            {
              participant_id: "A",
              attempt_id: "foreign-A",
              purpose_provenance_id: "purpose-A",
              purpose_origin: "unknown",
            },
          ]
        : []),
    ];
  },
}));
beforeEach(() => {
  controls.participant = "A";
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
const element = () => (
  <FixedLocaleProvider locale="en">
    <StudyHistory />
  </FixedLocaleProvider>
);
it.each(["GET", "POST"])(
  "purpose review resets participant identity and discards pending A %s on navigation to B",
  async (pendingMethod) => {
    let release!: (response: Response) => void;
    const writes: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        const url = String(input),
          method = init?.method ?? "GET";
        if (url.includes("/occasions?")) return Response.json([]);
        if (method === "POST") writes.push(url);
        if (url.includes("/purpose-A") && method === pendingMethod)
          return new Promise<Response>((resolve) => {
            release = resolve;
          });
        return Response.json({
          classifications: [
            {
              reason: url.includes("/purpose-B")
                ? "B only record"
                : "A old record",
            },
          ],
        });
      }),
    );
    const view = render(element());
    await screen.findByRole("option", { name: /attempt-A/ });
    fireEvent.change(screen.getByRole("combobox", { name: "Purpose record" }), {
      target: { value: "purpose-A" },
    });
    fireEvent.change(screen.getByLabelText("Purpose reviewer"), {
      target: { value: "Reviewer A" },
    });
    fireEvent.change(screen.getByLabelText("Purpose reason and references"), {
      target: { value: "Reason A" },
    });
    if (pendingMethod === "POST")
      fireEvent.click(
        screen.getByRole("button", { name: "Record purpose review" }),
      );
    await waitFor(() => expect(release).toBeTypeOf("function"));
    controls.participant = "B";
    view.rerender(element());
    await screen.findByRole("option", { name: /attempt-B/ });
    expect(
      screen.getByRole("combobox", { name: "Purpose record" }),
    ).toHaveValue("");
    expect(
      screen.queryByRole("option", { name: /foreign-A/ }),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Purpose reviewer")).not.toBeInTheDocument();
    await act(async () =>
      release(
        Response.json({ classifications: [{ reason: "Late A response" }] }),
      ),
    );
    expect(screen.queryByText(/Late A response/)).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Purpose record" }), {
      target: { value: "purpose-B" },
    });
    await screen.findByText(/B only record/);
    expect(screen.getByLabelText("Purpose reviewer")).toHaveValue("");
    expect(screen.getByLabelText("Purpose reason and references")).toHaveValue(
      "",
    );
    fireEvent.change(screen.getByLabelText("Purpose reviewer"), {
      target: { value: "Reviewer B" },
    });
    fireEvent.change(screen.getByLabelText("Purpose reason and references"), {
      target: { value: "Reason B" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Record purpose review" }),
    );
    await waitFor(() =>
      expect(writes.at(-1)).toBe(
        "http://local/purpose-provenance/purpose-B/classifications",
      ),
    );
    expect(writes.filter((url) => url.includes("/purpose-A/"))).toHaveLength(
      pendingMethod === "POST" ? 1 : 0,
    );
  },
);
