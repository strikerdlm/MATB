import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { CommandBar } from "./CommandBar";
import type { AircraftSnapshot, WorldSnapshot } from "@/types/simulation";

const aircraft = {
  aircraft_id: "UAS-01",
  label: "UAS-01",
  position: { x_mm: 0, y_mm: 0 },
  heading_mdeg: 0,
  energy_units: 800,
  predicted_home_reserve_units: 100,
  mode: "SEARCH",
  link: "NOMINAL",
  sensor: "NOMINAL",
  assigned_sector_id: null,
  route: [],
  mission_progress_ppm: 0,
} as AircraftSnapshot;

const snapshot = {
  sectors: { alpha: [], bravo: [] },
  report_note_codes: {},
} as unknown as WorldSnapshot;

describe("CommandBar", () => {
  it("offers every installed sector and an explicit map waypoint mode", () => {
    const onCommand = vi.fn();
    const onWaypointMode = vi.fn();
    render(<CommandBar snapshot={snapshot} selectedAircraft={aircraft} selectedContact={null} locale="en" onCommand={onCommand} onWaypointMode={onWaypointMode} />);
    expect(screen.getByRole("button", { name: /assign sector alpha/i })).toBeVisible();
    expect(screen.getByRole("button", { name: /assign sector bravo/i })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: /set waypoint/i }));
    expect(onWaypointMode).toHaveBeenCalledOnce();
    fireEvent.click(screen.getByRole("button", { name: /assign sector bravo/i }));
    expect(onCommand).toHaveBeenCalledWith("ASSIGN_SECTOR", { aircraft_id: "UAS-01", sector_id: "bravo" });
  });
});
