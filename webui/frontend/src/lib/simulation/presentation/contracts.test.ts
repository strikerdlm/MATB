import { describe, expect, it } from "vitest";
import {
  elevationAt,
  headingRadians,
  missionToWorld,
  validateElevation,
  worldToMission,
  type ElevationGrid,
} from "./contracts";
const bounds = {
  min_x_mm: 0,
  min_y_mm: 0,
  max_x_mm: 12000000,
  max_y_mm: 8000000,
};
const grid: ElevationGrid = {
  width: 2,
  height: 2,
  bounds_m: [-2000, -2000, 14000, 10000],
  values: [100, 200, 300, 400],
};
describe("geographic presentation", () => {
  it("round-trips local millimetres with north on negative Z", () => {
    for (const point of [
      { x_mm: 0, y_mm: 0 },
      { x_mm: 12000000, y_mm: 8000000 },
      { x_mm: 6123456, y_mm: 4234567 },
    ]) {
      const [x, y, z] = missionToWorld(point, 123);
      expect(y).toBe(123);
      expect(worldToMission(x, z, bounds)).toEqual(point);
    }
    expect(missionToWorld({ x_mm: 6000000, y_mm: 5000000 }, 0)[2]).toBe(-1000);
    expect(worldToMission(9000, 0, bounds)).toBeNull();
  });
  it("converts north-clockwise headings", () => {
    expect(headingRadians(90000)).toBeCloseTo(-Math.PI / 2);
    expect(headingRadians(0)).toBe(-0);
  });
  it("bilinearly samples and rejects terrain gaps", () => {
    expect(elevationAt(grid, { x_mm: 6000000, y_mm: 4000000 })).toBe(250);
    expect(elevationAt(grid, { x_mm: -2000000, y_mm: -2000000 })).toBe(100);
    expect(() => elevationAt(grid, { x_mm: -3000000, y_mm: 0 })).toThrow();
    expect(() =>
      validateElevation({ ...grid, values: [NaN, 1, 2, 3] }),
    ).toThrow();
  });
});
