import { describe, expect, it } from "vitest";
import { getInstrument, recordInstrumentResponse } from "../src/instruments.js";

describe("research instruments", () => {
  it.each(["SAGAT", "NASA-TLX", "ISA", "Bedford", "SART"] as const)("registers the controlled %s instrument", (name) => {
    expect(getInstrument(name).status).toBe("approved-template");
  });

  it("rejects an instrument response outside the approved numeric range", () => {
    expect(() => recordInstrumentResponse({ sessionId: "SESSION-1", instrumentId: "NASA-TLX", administeredAtUtc: "2026-08-10T15:10:00.000Z", values: { workload: 101 } })).toThrow(/range/i);
  });
});
