import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { AppShell } from "@/components/layout/AppShell";
import { AppLocaleProvider } from "@/lib/i18n";
import { ExperimentFlowProvider } from "@/lib/experiment-flow";
import { NavigationRoleProvider } from "@/lib/navigation-role";

vi.mock("next/navigation", () => ({
  usePathname: () => "/analysis",
  useSearchParams: () => new URLSearchParams(),
}));
vi.mock("@/lib/console-context", () => ({
  useConsole: () => ({ status: "offline" }),
}));

describe("AppShell", () => {
  it("shows the connection and per-tab role switch at every width", () => {
    render(
      <AppLocaleProvider>
        <NavigationRoleProvider>
          <ExperimentFlowProvider><AppShell><p>Content</p></AppShell></ExperimentFlowProvider>
        </NavigationRoleProvider>
      </AppLocaleProvider>,
    );

    expect(screen.getByRole("status", { name: /Estado de conexión/ })).toHaveTextContent("Sin conexión");
    expect(screen.getByRole("status", { name: /Estado de conexión/ }).className).not.toContain("hidden");
    expect(screen.getByRole("link", { name: "Participante" })).toHaveAttribute("href", "/start");
    expect(screen.getByRole("link", { name: "Investigador" })).toHaveAttribute("href", "/tracker");
    expect(screen.getByRole("heading", { name: "MATB - FAC" })).toBeInTheDocument();
  });
});
