import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  abortClassicSession,
  connectPolar,
  getClassicHistory,
  getClassicResourceUrl,
  polarPreflight,
  prepareClassicSession,
  scanPolar,
  startClassicSession,
} from "@/lib/classic/api";

beforeEach(() => vi.restoreAllMocks());

function response(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    statusText: "",
  } as Response;
}

describe("classic MATB API", () => {
  it("scans, connects with an opaque body token, and performs RR preflight", async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(response(200, [{
        device_token: "opaque-token",
        display_name: "Polar H10 1234",
        rssi: -48,
        is_polar_h10: true,
        heart_rate_service_advertised: true,
        token_expires_at_utc_ns: "1",
      }]))
      .mockResolvedValueOnce(response(200, { state: "connected", preflight_ready: false }))
      .mockResolvedValueOnce(response(200, { ready: true, rr_count: 2, heart_rate_bpm: 64 }));

    expect((await scanPolar(4))[0].display_name).toContain("H10");
    await connectPolar("opaque-token");
    expect((await polarPreflight(8)).ready).toBe(true);

    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[0][0]).toContain("/classic/polar/scan");
    expect(JSON.parse(calls[0][1].body)).toEqual({ timeout_seconds: 4 });
    expect(calls[1][0]).not.toContain("opaque-token");
    expect(JSON.parse(calls[1][1].body)).toEqual({ device_token: "opaque-token" });
    expect(JSON.parse(calls[2][1].body)).toEqual({ timeout_seconds: 8 });
  });

  it("keeps the one-time controller lease out of URLs and request bodies", async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(response(201, { id: "classic-1", controller_lease: "secret" }))
      .mockResolvedValueOnce(response(200, { id: "classic-1", status: "BASELINE" }))
      .mockResolvedValueOnce(response(200, { id: "classic-1", status: "ABORTED" }));

    await prepareClassicSession({
      participant_id: "P01",
      visit_ordinal: 1,
      workload_level: "LOW",
      scenario_name: "military_aviation/low_workload.txt",
      performance_only_override: false,
      override_reason_code: null,
    });
    await startClassicSession("classic-1", "secret");
    await abortClassicSession("classic-1", "secret", "participant_requested_stop");

    const calls = (global.fetch as ReturnType<typeof vi.fn>).mock.calls;
    expect(calls[1][0]).not.toContain("secret");
    expect(calls[1][1].headers["X-Classic-Controller"]).toBe("secret");
    expect(calls[1][1].body).toBe("{}");
    expect(calls[2][1].headers["X-Classic-Controller"]).toBe("secret");
    expect(JSON.parse(calls[2][1].body)).toEqual({ reason_code: "participant_requested_stop" });
  });

  it("encodes history filters and builds safe artifact and visit export URLs", async () => {
    global.fetch = vi.fn().mockResolvedValue(response(200, []));

    await getClassicHistory("P01", 2);
    const historyUrl = (global.fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string;
    expect(historyUrl).toContain("participant_id=P01");
    expect(historyUrl).toContain("visit_ordinal=2");

    await expect(getClassicResourceUrl("bundle", {
      sessionId: "attempt/one",
    })).resolves.toContain("/classic/sessions/attempt%2Fone/bundle");
    await expect(getClassicResourceUrl("artifact", {
      sessionId: "attempt/one",
      relativePath: "report.en.md",
    })).resolves.toContain("/artifacts/report.en.md");
    await expect(getClassicResourceUrl("visit", {
      participantId: "P01",
      visitOrdinal: 2,
      format: "md",
    })).resolves.toContain("/classic/visits/P01/2/summary.md");
  });
});
