import { describe, expect, it } from "vitest";
import { evaluateSpi } from "../src/indicators.js";

describe("SMS safety performance indicators", () => {
  it("raises an SPI alert at the configured policy threshold", () => {
    expect(evaluateSpi({ value: 4, unit: "events/100-flight-hours" }, { alertAt: 3, actionAt: 5 }).level).toBe("alert");
  });

  it("does not calculate a meaningful indicator from incomplete data", () => {
    expect(evaluateSpi({ value: undefined, unit: "events/100-flight-hours" }, { alertAt: 3, actionAt: 5 }).dataQuality).toBe("incomplete");
  });
});
