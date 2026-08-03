import { describe, expect, it } from "vitest";
import { createProjection } from "./projection";

describe("mission projection", () => {
  it("projects mission millimetres into an SVG viewBox with y inversion", () => {
    const project = createProjection({ min_x_mm: 0, min_y_mm: 0, max_x_mm: 12_000_000, max_y_mm: 8_000_000 }, { width: 1200, height: 800 });
    expect(project.point({ x_mm: 6_000_000, y_mm: 2_000_000 })).toEqual({ x: 600, y: 600 });
  });

  it("round-trips points and serializes polygons deterministically", () => {
    const project = createProjection({ min_x_mm: -100, min_y_mm: -100, max_x_mm: 900, max_y_mm: 900 }, { width: 100, height: 100 });
    expect(project.inverse(project.point({ x_mm: 225, y_mm: 630 }))).toEqual({ x_mm: 225, y_mm: 630 });
    expect(project.polygon([{ x_mm: -100, y_mm: -100 }, { x_mm: 900, y_mm: -100 }])).toBe("0.00,100.00 100.00,100.00");
    expect(project.missionDistanceToPixels(100)).toBe(10);
  });
});
