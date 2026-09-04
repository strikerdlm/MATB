import React from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MissionMap } from "./MissionMap";
import type { WorldSnapshot } from "@/types/simulation";

const snapshot = {
  scenario_id: "reference_area_search",
  scenario_sha256: "hash",
  block_id: "PRACTICE",
  tick: 1,
  simulation_time_ms: 1000,
  state_version: 4,
  state_sha256: "state",
  title: { en: "Reference", "es-CO": "Referencia" },
  description: { en: "Synthetic", "es-CO": "Sintético" },
  terrain: { bounds: { min_x_mm: 0, min_y_mm: 0, max_x_mm: 12_000_000, max_y_mm: 8_000_000 }, polygon: [{ x_mm: 0, y_mm: 0 }, { x_mm: 12_000_000, y_mm: 0 }, { x_mm: 12_000_000, y_mm: 8_000_000 }, { x_mm: 0, y_mm: 8_000_000 }] },
  home: { x_mm: 500_000, y_mm: 500_000 },
  initial_view: { center: { x_mm: 6_000_000, y_mm: 4_000_000 }, width_mm: 12_000_000, height_mm: 8_000_000 },
  sectors: { alpha: [{ x_mm: 1_000_000, y_mm: 1_000_000 }, { x_mm: 5_000_000, y_mm: 1_000_000 }, { x_mm: 5_000_000, y_mm: 4_000_000 }, { x_mm: 1_000_000, y_mm: 4_000_000 }] },
  restricted_zones: {},
  report_note_codes: {},
  aircraft: { "UAS-01": { aircraft_id: "UAS-01", label: "UAS-01", position: { x_mm: 3_000_000, y_mm: 3_000_000 }, heading_mdeg: 0, energy_units: 900, predicted_home_reserve_units: 100, mode: "SEARCH", link: "NOMINAL", sensor: "NOMINAL", assigned_sector_id: "alpha", route: [], mission_progress_ppm: 100 } },
  contacts: { "C-01": { contact_id: "C-01", evidence: "DETECTED", workflow: "DETECTED", classification: null, priority: null, report_ids: [], position: { x_mm: 8_000_000, y_mm: 5_000_000 } } },
  alerts: {},
  coverage: { grid_cell_mm: 1_000_000, origin: { x_mm: 0, y_mm: 0 }, sectors: { alpha: { covered_cells: [[3, 2]], covered_count: 1, eligible_count: 10, covered_cell_count: 1, eligible_cell_count: 10, coverage_ppm: 100_000 } } },
} as unknown as WorldSnapshot;

describe("MissionMap", () => {
  it("renders labels and non-color status for aircraft and detected contacts", () => {
    const onAircraft = vi.fn();
    const onContact = vi.fn();
    render(<MissionMap snapshot={snapshot} locale="en" onSelectAircraft={onAircraft} onSelectContact={onContact} />);
    expect(screen.getByRole("region", { name: /tactical mission map/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /UAS-01.*nominal link/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /C-01.*detected/i })).toBeVisible();
    expect(screen.queryByText(/priority truth/i)).not.toBeInTheDocument();
  });

  it("supports keyboard aircraft selection and reset view", async () => {
    const user = userEvent.setup();
    const onAircraft = vi.fn();
    render(<MissionMap snapshot={snapshot} locale="en" onSelectAircraft={onAircraft} />);
    screen.getByRole("button", { name: /UAS-01/i }).focus();
    await user.keyboard("{Enter}");
    expect(onAircraft).toHaveBeenCalledWith("UAS-01");
    await user.click(screen.getByRole("button", { name: /zoom in/i }));
    expect(screen.getByTestId("map-root")).toHaveAttribute("data-zoom", "1.25");
    await user.click(screen.getByRole("button", { name: /reset view/i }));
    expect(screen.getByTestId("map-root")).toHaveAttribute("data-zoom", "1");
  });

  it("projects covered cells into their real mission position", () => {
    const { container } = render(<MissionMap snapshot={snapshot} locale="en" />);
    const cell = container.querySelector('[data-coverage-sector="alpha"] rect');
    expect(cell).not.toBeNull();
    expect(Number(cell?.getAttribute("x"))).toBeGreaterThan(250);
    expect(Number(cell?.getAttribute("y"))).toBeGreaterThan(400);
  });
});
