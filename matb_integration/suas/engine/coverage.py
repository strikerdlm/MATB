"""Integer grid coverage accounting for nominal aircraft sensor scans."""

from __future__ import annotations

from matb_integration.suas.domain.geometry import PointMM
from matb_integration.suas.domain.models import ScenarioDefinition, WorldState


class CoverageGrid:
    """A terrain-derived grid with deterministic, per-sector coverage summaries."""

    def __init__(self, scenario: ScenarioDefinition) -> None:
        self._scenario = scenario
        self._eligible_by_sector = {
            sector_id: tuple(
                cell for cell in self._terrain_cells()
                if sector.contains(self.cell_center(cell))
            )
            for sector_id, sector in sorted(scenario.sectors.items())
        }

    def mark_scan(self, state: WorldState, aircraft_id: str) -> tuple[tuple[int, int], ...]:
        """Record cells newly sensed by one aircraft's nominal sensor scan."""

        aircraft = state.aircraft[aircraft_id]
        sector_id = aircraft.assigned_sector_id
        if aircraft.sensor.value != "NOMINAL" or sector_id is None:
            return ()
        try:
            candidates = self._eligible_by_sector[sector_id]
        except KeyError as error:
            raise ValueError(f"unknown assigned sector {sector_id}") from error
        radius = self._scenario.aircraft[aircraft_id].sensor.radius_mm
        radius_squared = radius * radius
        new_cells = tuple(
            cell for cell in candidates
            if cell not in state.coverage_cells
            and _distance_squared(aircraft.position, self.cell_center(cell)) <= radius_squared
        )
        state.coverage_cells.update(new_cells)
        return new_cells

    def cell_center(self, cell: tuple[int, int]) -> PointMM:
        minimum_x, minimum_y, _, _ = self._scenario.terrain.bounds
        cell_mm = self._scenario.grid_cell_mm
        return PointMM(
            minimum_x + cell[0] * cell_mm + cell_mm // 2,
            minimum_y + cell[1] * cell_mm + cell_mm // 2,
        )

    def public_snapshot(self, state: WorldState) -> dict[str, object]:
        """Return only sorted JSON-safe coverage state with integer ratios."""

        sectors: dict[str, dict[str, object]] = {}
        for sector_id, eligible in self._eligible_by_sector.items():
            eligible_set = set(eligible)
            covered = sorted(eligible_set.intersection(state.coverage_cells))
            eligible_count = len(eligible)
            covered_count = len(covered)
            sectors[sector_id] = {
                "covered_cells": [[x, y] for x, y in covered],
                "covered_count": covered_count,
                "eligible_count": eligible_count,
                "covered_cell_count": covered_count,
                "eligible_cell_count": eligible_count,
                "coverage_ppm": covered_count * 1_000_000 // eligible_count if eligible_count else 0,
            }
        return {"sectors": sectors}

    def _terrain_cells(self) -> tuple[tuple[int, int], ...]:
        minimum_x, minimum_y, maximum_x, maximum_y = self._scenario.terrain.bounds
        cell_mm = self._scenario.grid_cell_mm
        columns = (maximum_x - minimum_x + cell_mm - 1) // cell_mm
        rows = (maximum_y - minimum_y + cell_mm - 1) // cell_mm
        return tuple(
            (x_index, y_index)
            for y_index in range(rows)
            for x_index in range(columns)
            if self._scenario.terrain.contains(self.cell_center((x_index, y_index)))
        )


def _distance_squared(left: PointMM, right: PointMM) -> int:
    return (left.x_mm - right.x_mm) ** 2 + (left.y_mm - right.y_mm) ** 2
