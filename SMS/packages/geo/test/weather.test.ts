import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import {
  decodeMetar,
  decodeSigmet,
  decodeTaf,
  validateWeatherForRoute,
} from "../src/weather.js";
import type { WeatherRouteInput } from "../src/weather.js";

const fixture = JSON.parse(readFileSync(new URL("./fixtures/weather.json", import.meta.url), "utf8")) as Record<string, string>;
const weatherInput: WeatherRouteInput = {
  observations: [decodeMetar(fixture.metar, "weather-pkg-1")],
  nowUtc: "2026-08-08T16:30:00Z",
  maxAgeMinutes: 60,
  minimumVisibilityM: 5_000,
  minimumCeilingFtAgl: 1_000,
  maxWindKt: 25,
};

describe("source-preserving aviation weather", () => {
  it("decodes METAR wind, visibility, clouds, temperature, and QNH in UTC", () => {
    const observation = decodeMetar(fixture.metar, "weather-pkg-1");
    expect(observation.source).toBe("metar");
    expect(observation.station).toBe("SKBO");
    expect(observation.observedAtUtc).toBe("2026-08-08T16:00:00Z");
    expect(observation.windKt?.speedKt).toBe(12);
    expect(observation.windKt?.gustKt).toBe(20);
    expect(observation.visibilityM).toBeGreaterThan(9_000);
    expect(observation.cloudLayers?.[0]).toMatchObject({ amount: "SCT", baseFtAgl: 2_000 });
    expect(observation.temperatureC).toBe(18);
    expect(observation.qnhHpa).toBe(1023);
    expect(observation.sourcePackageId).toBe("weather-pkg-1");
  });

  it("preserves TAF and SIGMET source/time fields while retaining raw text", () => {
    expect(decodeTaf(fixture.taf, "weather-pkg-1")).toMatchObject({ source: "taf", station: "SKBO", raw: fixture.taf, sourcePackageId: "weather-pkg-1", visibilityM: expect.any(Number), validFromUtc: "2026-08-08T16:00:00Z", validUntilUtc: "2026-08-09T18:00:00Z" });
    expect(decodeSigmet(fixture.sigmet, "weather-pkg-1")).toMatchObject({ source: "sigmet", station: "SKBO", raw: fixture.sigmet, sourcePackageId: "weather-pkg-1", validUntilUtc: "2026-08-08T19:30:00Z" });
  });

  it("passes current observations and expires critical stale weather", () => {
    expect(validateWeatherForRoute(weatherInput).status).toBe("pass");
    const stale = validateWeatherForRoute({ ...weatherInput, nowUtc: "2026-08-08T18:00:00Z" });
    expect(stale.status).toBe("expired");
  });

  it("blocks below-limit visibility and reports malformed critical observations as unknown", () => {
    const lowVisibility = decodeMetar("METAR 2026-08-08T16:00:00Z SKBO 081600Z 32012KT 1000 BKN005 18/10 Q1023=", "weather-pkg-1");
    expect(validateWeatherForRoute({ ...weatherInput, observations: [lowVisibility] }).status).toBe("blocked");
    const malformed = decodeMetar("METAR SKBO malformed", "weather-pkg-1");
    expect(validateWeatherForRoute({ ...weatherInput, observations: [malformed] }).status).toBe("unknown");
  });
});
