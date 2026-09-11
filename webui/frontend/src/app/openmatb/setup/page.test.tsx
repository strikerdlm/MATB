import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SetupPage from "./page";
import * as api from "@/lib/openmatb/api";
import * as participantApi from "@/lib/api";

const nav = vi.hoisted(() => ({
  push: vi.fn(),
  query: new URLSearchParams("purpose=practice"),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => nav,
  useSearchParams: () => nav.query,
  usePathname: () => "/openmatb/setup",
}));
vi.mock("@/lib/i18n", () => ({
  useAppLocale: () => ({ locale: "en", copy: (_es: string, en: string) => en }),
}));
vi.mock("@/lib/api", () => ({
  listParticipants: vi.fn(async () => [{ id: "P01" }]),
  listVisits: async () => [{ id: 1, visit_ordinal: 1, scheduled_day: 0 }],
}));
vi.mock("@/lib/openmatb/api", () => ({
  getOpenMatbReadiness: vi.fn(),
  getOpenMatbDisplays: vi.fn(),
  createOpenMatbSession: vi.fn(),
  storeOpenMatbCredentials: vi.fn(),
  controllerAction: vi.fn(),
  listOpenMatbPresets: async () => [
    {
      preset_id: "preset",
      version: "1",
      label_es: "Approved preset",
      sha256: "preset-hash",
      status: "published",
      profiles: {},
    },
  ],
  listOpenMatbInstructions: async () => [
    {
      protocol_id: "instructions",
      version: "1",
      title: "Approved protocol",
      sha256: "protocol-hash",
      locale: "en",
      status: "published",
    },
  ],
  listOpenMatbVisualProfiles: async () => [
    {
      profile_id: "visual",
      version: "1",
      label: "Published visual profile",
      status: "published",
      sha256: "a".repeat(64),
    },
  ],
}));
vi.mock("@/lib/openmatb/errors", () => ({
  openMatbErrorMessage: (error: Error) => error.message,
}));
const displays = [
  { index: 0, label: "Display 1", width: 1920, height: 1080, x: 0, y: 0 },
  { index: 1, label: "Display 2", width: 1366, height: 768, x: 1920, y: 0 },
];

describe("routine OpenMATB preparation", () => {
  beforeEach(() => {
    vi.mocked(api.getOpenMatbReadiness).mockResolvedValue({
      ready: true,
      checks: { python: true, graphical_display: true },
      warnings: [],
    } as never);
    vi.mocked(api.getOpenMatbDisplays).mockResolvedValue(displays);
    vi.mocked(api.createOpenMatbSession).mockReset();
    vi.mocked(participantApi.listParticipants).mockResolvedValue([
      { id: "P01" },
    ] as never);
    nav.push.mockReset();
    sessionStorage.clear();
  });
  it("puts readiness first, labels real displays and explains unmet requirements", async () => {
    render(<SetupPage />);
    const station = await screen.findByRole("heading", {
      name: /Is the station ready/,
    });
    const participant = screen.getByRole("heading", {
      name: /Who is participating/,
    });
    expect(
      station.compareDocumentPosition(participant) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    await waitFor(() =>
      expect(screen.getByLabelText("Participant display")).toHaveValue("1"),
    );
    expect(
      screen.getByRole("option", { name: /Display 2.*1366.*768/ }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "Create session and open instructions",
      }),
    ).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Select a participant" }),
    );
    expect(screen.getByLabelText("Participant")).toHaveFocus();
    expect(
      screen.getByText("View configuration").closest("details"),
    ).not.toHaveAttribute("open");
  });
  it("keeps the participant focus helper unavailable until delayed choices can accept focus", async () => {
    let finish!: (
      value: Awaited<ReturnType<typeof participantApi.listParticipants>>,
    ) => void;
    vi.mocked(participantApi.listParticipants).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    render(<SetupPage />);
    await waitFor(() =>
      expect(screen.getByLabelText("Participant display")).toHaveValue("1"),
    );
    const helper = screen.getByRole("button", { name: "Select a participant" });
    expect(helper).toBeDisabled();
    expect(screen.getByLabelText("Participant")).toBeDisabled();
    fireEvent.click(helper);
    expect(screen.getByLabelText("Participant")).not.toHaveFocus();
    finish([{ id: "P01" }] as never);
    await waitFor(() => expect(helper).toBeEnabled());
    fireEvent.click(helper);
    expect(screen.getByLabelText("Participant")).toHaveFocus();
  });
  it("explains a pending recheck after all choices are complete and keeps hashes in configuration", async () => {
    render(<SetupPage />);
    await waitFor(() =>
      expect(screen.getByLabelText("Participant")).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("Participant"), {
      target: { value: "P01" },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Assigned visit")).toHaveValue("1"),
    );
    fireEvent.click(screen.getByRole("checkbox"));
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: "Create session and open instructions",
        }),
      ).toBeEnabled(),
    );
    vi.mocked(api.getOpenMatbReadiness).mockReturnValue(new Promise(() => {}));
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(
      screen.getByRole("button", {
        name: "Create session and open instructions",
      }),
    ).toBeDisabled();
    expect(
      screen.getByText("Checking the station requirements…"),
    ).toBeVisible();
    const hashes = screen.getByText(/"preset_sha256": "preset-hash"/);
    expect(hashes).toHaveTextContent(
      '"instruction_protocol_sha256": "protocol-hash"',
    );
    expect(hashes).toHaveTextContent(
      '"visual_profile_sha256": "' + "a".repeat(64) + '"',
    );
    expect(
      hashes.closest("details")?.parentElement?.closest("details"),
    ).not.toHaveAttribute("open");
  });
  it("preserves choices during recheck and reports a blocked browser window on the controller route", async () => {
    vi.spyOn(window, "open").mockReturnValue(null);
    vi.mocked(api.createOpenMatbSession).mockResolvedValue({
      session: { id: "suite" },
      participant_token: "token",
      controller_lease: "lease",
    } as never);
    render(<SetupPage />);
    await waitFor(() =>
      expect(screen.getByLabelText("Participant")).toBeEnabled(),
    );
    fireEvent.change(screen.getByLabelText("Participant"), {
      target: { value: "P01" },
    });
    await waitFor(() =>
      expect(screen.getByLabelText("Assigned visit")).toHaveValue("1"),
    );
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    await waitFor(() =>
      expect(
        screen.getByRole("button", {
          name: "Create session and open instructions",
        }),
      ).toBeEnabled(),
    );
    expect(screen.getByLabelText("Participant display")).toHaveValue("1");
    fireEvent.click(
      screen.getByRole("button", {
        name: "Create session and open instructions",
      }),
    );
    await waitFor(() =>
      expect(api.createOpenMatbSession).toHaveBeenCalledWith(
        expect.objectContaining({
          execution_purpose: "practice",
          participant_id: "P01",
          display_index: 1,
        }),
      ),
    );
    expect(nav.push).toHaveBeenCalledWith(
      expect.stringMatching(/session=suite.*participant_window=blocked/),
    );
    expect(api.controllerAction).not.toHaveBeenCalled();
  });
  it("does not silently move a selected participant display when it disconnects", async () => {
    render(<SetupPage />);
    await waitFor(() =>
      expect(screen.getByLabelText("Participant display")).toHaveValue("1"),
    );
    vi.mocked(api.getOpenMatbDisplays).mockResolvedValue(displays.slice(0, 1));
    fireEvent.click(screen.getByRole("button", { name: "Check again" }));
    expect(
      await screen.findByRole("option", { name: /Disconnected/ }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Participant display")).toHaveValue("1");
    expect(
      screen.getByRole("button", {
        name: "Create session and open instructions",
      }),
    ).toBeDisabled();
  });
});
