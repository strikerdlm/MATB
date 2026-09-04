import { describe, expect, it } from "vitest";
import { cvdFilterValues, cvdMatrix, simulateHex } from "./cvd";

describe("Machado CVD preview matrices", () => {
  it("leaves normal color unchanged", () => {
    expect(simulateHex("normal", 100, "#27C840")).toBe("#27C840");
    expect(cvdMatrix("normal", 70)).toEqual([1, 0, 0, 0, 1, 0, 0, 0, 1]);
  });

  it("uses the published full-severity protanomaly matrix", () => {
    expect(simulateHex("protanomaly", 100, "#FF0000")).toBe("#271D00");
  });

  it("interpolates and clamps severity", () => {
    const halfway = cvdMatrix("deuteranomaly", 5);
    expect(halfway[0]).toBeCloseTo((1 + 0.866435) / 2, 6);
    expect(cvdMatrix("tritanomaly", 150)).toEqual(cvdMatrix("tritanomaly", 100));
    expect(cvdFilterValues("normal", 100).split(" ")).toHaveLength(20);
  });
});
