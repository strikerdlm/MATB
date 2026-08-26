import { describe, expect, it } from "vitest";
import { canonicalizeTelemetry, type CanonicalTelemetry } from "../src/index.js";
import { ReadOnlyTelemetryAdapterFixture } from "../test-support/index.js";

const validTelemetry: CanonicalTelemetry = {
  eventId: "telemetry-1",
  aircraftId: "aircraft-1",
  observedAtUtc: "2026-08-09T18:00:00.000Z",
  position: { lat: 4.7, lon: -74.1, altitudeMslM: 2600, heightAglM: 120 },
  motion: { headingDeg: 90, groundSpeedKt: 45, verticalRateFpm: 0 },
  energy: { stateOfChargePercent: 78, voltageV: 22.4, temperatureC: 28 },
  platform: { propulsion: "normal", gnss: "normal", c2Link: "normal" },
  route: { legId: "leg-1", crossTrackM: 2, approvedArea: true },
  sourcePackageIds: ["telemetry-package-1"],
};

describe("read-only telemetry contract", () => {
  it("exposes no command or control methods", () => {
    const methods = Object.getOwnPropertyNames(ReadOnlyTelemetryAdapterFixture.prototype);
    expect(methods).toContain("connect");
    expect(methods).toContain("readStatus");
    expect(methods).toContain("subscribe");
    expect(methods).toContain("close");
    expect(methods).not.toContain("sendCommand");
    expect(methods).not.toContain("arm");
    expect(methods).not.toContain("launch");
  });

  it("normalizes bounded units and returns detached immutable telemetry", () => {
    const event = canonicalizeTelemetry(validTelemetry, { aircraftId: "aircraft-1" });
    expect(event).toMatchObject({ eventId: "telemetry-1", aircraftId: "aircraft-1" });
    expect(Object.isFrozen(event)).toBe(true);
    expect(Object.isFrozen(event.position)).toBe(true);
  });

  it("rejects command-shaped fields, invalid coordinates, and missing sources", () => {
    expect(() => canonicalizeTelemetry({ ...validTelemetry, command: "forbidden" } as never)).toThrow(/unsupported|control/i);
    expect(() => canonicalizeTelemetry({ ...validTelemetry, position: { lat: 91, lon: 0 } })).toThrow(/lat/i);
    expect(() => canonicalizeTelemetry({ ...validTelemetry, sourcePackageIds: [] })).toThrow(/source/i);
  });
});
