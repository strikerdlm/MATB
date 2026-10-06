import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import StartPage from "@/app/start/page";
import { AppLocaleProvider } from "@/lib/i18n";

const search = new URLSearchParams("experiment=screen");
vi.mock("next/navigation", () => ({ useSearchParams: () => search }));
vi.mock("@/lib/console-context", () => ({
  useConsole: () => ({
    status: "online",
    refresh: vi.fn(),
    catalog: [{
      id: "screen",
      route: "/screen",
      component_id: "screen",
      component_available: true,
      supported_modes: ["practice", "study"],
      readiness_url: null,
      configuration_url: null,
      profiles: [],
      duration_seconds: null,
      study_prerequisites: [],
      unavailable_reason: null,
    }],
  }),
}));

describe("experiment catalog purpose selection", () => {
  beforeEach(() => window.history.replaceState(null, "", "/start?experiment=screen"));

  it("does not enable preparation until the participant chooses a purpose", async () => {
    const user = userEvent.setup();
    render(<AppLocaleProvider><StartPage /></AppLocaleProvider>);

    expect(screen.getByRole("radio", { name: /^Practicar/ })).not.toBeChecked();
    expect(screen.getByRole("radio", { name: /Participar en mi estudio/ })).not.toBeChecked();
    expect(screen.queryByRole("link", { name: "Preparar experimento" })).toBeNull();

    await user.click(screen.getByRole("radio", { name: /Participar en mi estudio/ }));
    expect(screen.getByRole("link", { name: "Preparar experimento" }))
      .toHaveAttribute("href", "/study/join?experiment=screen&purpose=study");
  });
});
