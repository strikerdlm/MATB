import { beforeEach, describe, expect, it, vi } from "vitest";

import { createPolarCapture, downloadPolarRRFile, scanPolar, startPolarCapture } from "@/lib/physiology/api";


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
      execution_purpose: "study",
      participant_pseudonym: "P01", matb_session_kind: "generic", matb_session_id: "session-1",
      settings: { ecg_sample_rate_hz: 130, ecg_resolution_bits: 14, acc_sample_rate_hz: 200, acc_resolution_bits: 16, acc_range_g: 8 },
    });
    await startPolarCapture("capture-1", "lease");
    const [url, init] = (global.fetch as any).mock.calls[1];
    expect(url).not.toContain("lease");
    expect(init.headers["X-Polar-Controller"]).toBe("lease");
    expect(JSON.parse((global.fetch as any).mock.calls[0][1].body).settings.acc_range_g).toBe(8);
  });

  it.each([
    [404, { detail: { code: "participant_not_found", message: "participant not found" } }, "participant_not_found"],
    [422, { detail: [{ loc: ["body", "participant_pseudonym"], type: "string_pattern_mismatch" }] }, "polar_request_invalid"],
    [422, { detail: { code: "exact_stream_settings_unavailable" } }, "exact_stream_settings_unavailable"],
  ])("retains a usable preparation error for HTTP %s", async (status, body, code) => {
    global.fetch = vi.fn().mockResolvedValue(response(status as number, body));
    await expect(createPolarCapture({
      execution_purpose: "practice", participant_pseudonym: "P99", matb_session_kind: "generic",
      settings: { ecg_sample_rate_hz: 130, ecg_resolution_bits: 14, acc_sample_rate_hz: 50, acc_resolution_bits: 16, acc_range_g: 2 },
    })).rejects.toMatchObject({ status, code });
  });
});

it("distinguishes schema validation from a connection failure", async () => {
  global.fetch = vi.fn().mockResolvedValue(response(422, { detail: [{ loc: ["body", "matb_session_id"], type: "missing", msg: "Field required" }] }));
  await expect(startPolarCapture("capture-1", "lease")).rejects.toMatchObject({ code: "polar_request_invalid" });
});

it("does not publish a download canceled while reading its body", async () => {
  let finish!: (value: Blob) => void;
  const blob = new Promise<Blob>((resolve) => { finish = resolve; });
  const read = vi.fn().mockReturnValue(blob);
  global.fetch = vi.fn().mockResolvedValue({ ok: true, blob: read });
  const controller = new AbortController();
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const pending = downloadPolarRRFile("capture-1", "lease", "rr.txt", controller.signal);
  const rejected = expect(pending).rejects.toMatchObject({ name: "AbortError" });
  await vi.waitFor(() => expect(read).toHaveBeenCalled());
  controller.abort();
  finish(new Blob(["1000"]));
  await rejected;
  expect(click).not.toHaveBeenCalled();
});
