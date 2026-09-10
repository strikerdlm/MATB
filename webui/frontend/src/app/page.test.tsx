import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import HomePage from "@/app/page";
import { AppLocaleProvider } from "@/lib/i18n";
import { NavigationRoleProvider } from "@/lib/navigation-role";

const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/store", () => ({
  useConsole: () => ({
    tracker: [], liftoffTracker: [], componentIds: [], refreshTracker: vi.fn(), error: null,
  }),
}));

describe("workspace entry", () => {
  it("asks for an explicit role and sends the researcher to the tracker", async () => {
    const user = userEvent.setup();
    render(<AppLocaleProvider><NavigationRoleProvider><HomePage /></NavigationRoleProvider></AppLocaleProvider>);
    expect(screen.getByRole("heading", { name: "Elija su espacio de trabajo" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /Investigador/ }));
    expect(sessionStorage.getItem("matb.navigation.role")).toBe("researcher");
    expect(push).toHaveBeenCalledWith("/tracker");
  });
});
