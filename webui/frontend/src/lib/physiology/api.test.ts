import { beforeEach, describe, expect, it, vi } from "vitest";

import { createPolarCapture, scanPolar, startPolarCapture } from "@/lib/physiology/api";


function response(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    statusText: "",
    json: async () => body,
  } as Response;
}

beforeEach(() => vi.restoreAllMocks());

describe("Polar H10 API", () => {
  it("uses bounded scan and receives only expiring device tokens", async () => {
    global.fetch = vi.fn().mockResolvedValue(response(200, [{
      device_token: "opaque-token", alias: "Polar H10 1",
      connectable: true, rssi: -42, broadcast_hr_bpm: 60,
      broadcast_contact: true, token_expires_in_seconds: 60,
    }]));
    const devices = await scanPolar(4);
    expect(devices[0].device_token).toBe("opaque-token");
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/physiology/polar-h10/v1/scan");
    expect(JSON.parse(init.body).timeout_seconds).toBe(4);
  });

  it("keeps the controller lease in a header and exact settings in JSON", async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(response(201, { capture: { capture_id: "capture-1" }, controller_lease: "lease" }))
      .mockResolvedValueOnce(response(200, { capture_id: "capture-1", lifecycle: "capturing" }));
    await createPolarCapture({
      participant_pseudonym: "P01", matb_session_kind: "generic", matb_session_id: "session-1",
      settings: { ecg_sample_rate_hz: 130, ecg_resolution_bits: 14, acc_sample_rate_hz: 200, acc_resolution_bits: 16, acc_range_g: 8 },
    });
    await startPolarCapture("capture-1", "lease");
    const [url, init] = (global.fetch as any).mock.calls[1];
    expect(url).not.toContain("lease");
    expect(init.headers["X-Polar-Controller"]).toBe("lease");
    expect(JSON.parse((global.fetch as any).mock.calls[0][1].body).settings.acc_range_g).toBe(8);
  });
});
