import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { TechnicalTestForm } from "@/components/mission/setup/TechnicalTestForm";
import { AppLocaleProvider } from "@/lib/i18n";
import type { PreparedSession, ScenarioSummary } from "@/types/simulation";

const { createTechnical, push, transition } = vi.hoisted(() => ({
  createTechnical: vi.fn(),
  push: vi.fn(),
  transition: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
vi.mock("@/lib/simulation/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/simulation/api")>("@/lib/simulation/api");
  return {
    ...actual,
    createTechnicalSimulationSession: createTechnical,
    transitionSession: transition,
  };
});

const scenario: ScenarioSummary = {
  scenario_id: "reference_area_search",
  scenario_sha256: "a".repeat(64),
  title: "Reference area search",
  description: "Synthetic area search",
  titles: { en: "Reference area search", "es-CO": "Búsqueda en área de referencia" },
  descriptions: { en: "Synthetic area search", "es-CO": "Búsqueda sintética" },
  aircraft_count: 4,
  block_order: ["PRACTICE", "LOW", "MEDIUM", "HIGH"],
  locales: ["en", "es-CO"],
  profile_details: {
    PRACTICE: { duration_seconds: 3000, aircraft_count: 2, contact_count: 1, calibration_status: "engineering_preset_pending_human_calibration" },
    LOW: { duration_seconds: 6000, aircraft_count: 2, contact_count: 1, calibration_status: "engineering_preset_pending_human_calibration" },
    MEDIUM: { duration_seconds: 6000, aircraft_count: 4, contact_count: 2, calibration_status: "engineering_preset_pending_human_calibration" },
    HIGH: { duration_seconds: 6000, aircraft_count: 6, contact_count: 3, calibration_status: "engineering_preset_pending_human_calibration" },
  },
};

const prepared: PreparedSession = {
  id: "tech-1",
  participant_id: null,
  visit_id: null,
  visit_ordinal: null,
  session_mode: "interactive_technical",
  record_class: "technical_only",
  selected_block_id: "HIGH",
  scenario_id: scenario.scenario_id,
  scenario_sha256: scenario.scenario_sha256 ?? "",
  locale: "es-CO",
  lifecycle: "PREPARED",
  active_block_id: null,
  validity: "technical_only",
  block_order: ["HIGH"],
  state_version: 0,
  simulation_time_ms: 0,
  created_at: null,
  started_at: null,
  finished_at: null,
  interrupted_at: null,
  controller_lease: "technical-secret",
};

describe("TechnicalTestForm", () => {
  beforeEach(() => {
    localStorage.clear();
    sessionStorage.clear();
    createTechnical.mockReset().mockResolvedValue(prepared);
    transition.mockReset().mockResolvedValue({ ...prepared, lifecycle: "RUNNING", active_block_id: "HIGH" });
    push.mockReset();
  });

  it("launches the selected technical profile from the Spanish frontend", async () => {
    const user = userEvent.setup();
    render(<AppLocaleProvider><TechnicalTestForm scenarios={[scenario]} /></AppLocaleProvider>);

    expect(await screen.findByRole("heading", { name: "Pruebas MATB - FAC" })).toBeInTheDocument();
    await user.click(screen.getByRole("radio", { name: /Alta HIGH/ }));
    await user.click(screen.getByRole("checkbox", { name: /prueba técnica interactiva/i }));
    await user.click(screen.getByRole("button", { name: /Iniciar prueba interactiva.*Alta.*HIGH/i }));

    await waitFor(() => expect(createTechnical).toHaveBeenCalledWith({
      execution_purpose: "practice",
      scenario_id: "reference_area_search",
      block_id: "HIGH",
      locale: "es-CO",
    }));
    expect(transition).toHaveBeenCalledWith("tech-1", "start", "technical-secret", { block_id: "HIGH" });
    expect(sessionStorage.getItem("matb.simulation.tech-1.lease")).toBe("technical-secret");
    expect(push).toHaveBeenCalledWith("/mission?session=tech-1");
  });
});
