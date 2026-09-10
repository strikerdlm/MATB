import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SidebarNav } from "@/components/layout/SidebarNav";
import { AppLocaleProvider } from "@/lib/i18n";
import { ExperimentFlowProvider, useReportExperimentFlow } from "@/lib/experiment-flow";
import { NavigationRoleProvider } from "@/lib/navigation-role";

let pathname = "/pvt";
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useSearchParams: () => new URLSearchParams("purpose=practice"),
}));

function ReportInstructions() {
  useReportExperimentFlow("pvt", "instructions");
  return null;
}

function renderNav(reporter: React.ReactNode = null) {
  return render(
    <AppLocaleProvider>
      <NavigationRoleProvider>
        <ExperimentFlowProvider>{reporter}<SidebarNav /></ExperimentFlowProvider>
      </NavigationRoleProvider>
    </AppLocaleProvider>,
  );
}

describe("SidebarNav", () => {
  beforeEach(() => { window.sessionStorage.clear(); pathname = "/pvt"; });

  it("uses the stored session purpose even when the URL disagrees and the lifecycle is unknown", () => {
    pathname = "/openmatb/session";
    function ReportStoredSession() {
      useReportExperimentFlow("openmatb", null, "study");
      return null;
    }
    renderNav(<ReportStoredSession />);
    expect(screen.getByRole("link", { name: "Todos los experimentos" })).toHaveAttribute("href", "/start?purpose=study");
    expect(document.querySelector('[aria-current="step"]')).toBeNull();
  });

  it("shows only typed session stages and leaves progress unknown without a report", () => {
    renderNav();
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    expect(screen.queryByText("Elegir")).toBeNull();
    expect(document.querySelector('[aria-current="step"]')).toBeNull();
  });

  it("marks the stage published by the current flow", () => {
    renderNav(<ReportInstructions />);
    expect(screen.getByText("Instrucciones").closest("li"))
      .toHaveAttribute("aria-current", "step");
  });

  it("expands researcher tools and highlights nested routes", async () => {
    pathname = "/analysis/liftoff";
    window.sessionStorage.setItem("matb.navigation.role", "researcher");
    renderNav();
    const tools = screen.getByText("Herramientas del investigador").closest("details");
    await waitFor(() => expect(tools).toHaveAttribute("open"));
    expect(screen.getByRole("link", { name: "Análisis" })).toHaveAttribute("aria-current", "page");
  });
});
