import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  createLiftoffSession,
  getLiftoffReadiness,
  transitionLiftoff,
} from "@/lib/liftoff/api";
import type { CreateLiftoffSession, PreparedLiftoffSession } from "@/types/liftoff";

beforeEach(() => vi.restoreAllMocks());

const request: CreateLiftoffSession = {
  execution_purpose: "study",
  participant_id: "P01",
  visit_ordinal: 2,
  configuration: {
    liftoff_build: "1.6.0",
    track_id: "astra-neutral-time-trial-v1",
    drone_id: "astra-standard-quad-v1",
    flight_mode: "acro",
    camera_angle_deg: 25,
    fov_deg: 110,
    rates_profile: "astra-v1",
    controller_model: "research-rc",
    controller_firmware: "1.0.0",
    resolution: "1920x1080",
    refresh_rate_hz: 120,
    graphics_preset: "medium",
    damage_enabled: false,
    battery_enabled: false,
    telemetry_profile: "liftoff-telemetry-all-v1",
  },
  polar_recording_confirmed: true,
  performance_only_reason: null,
};

const prepared: PreparedLiftoffSession = {
  execution_purpose: "study",
  id: "session-1",
  participant_id: "P01",
  visit_id: 2,
  visit_ordinal: 2,
  visit_code: "DM8",
  attempt_number: 1,
  protocol_id: "astra-2026",
  protocol_version: "1.0.0",
  liftoff_build: "1.6.0",
  track_id: "astra-neutral-time-trial-v1",
  telemetry_profile: "liftoff-telemetry-all-v1",
  status: "PREPARED",
  validity: "pending_review",
  sync_quality: "missing",
  polar_recording_confirmed: true,
  created_at: "2026-08-18T00:00:00Z",
  started_at: null,
  finished_at: null,
  interrupted_at: null,
  controller_lease: "secret",
};

function response(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    statusText: "",
  } as Response;
}

describe("Liftoff API", () => {
  it("creates a session with JSON and returns the one-time lease", async () => {
    global.fetch = vi.fn().mockResolvedValue(response(201, prepared));

    expect(await createLiftoffSession(request)).toEqual(prepared);
    const [url, init] = (global.fetch as any).mock.calls[0];
    expect(url).toContain("/liftoff/sessions");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body).visit_ordinal).toBe(2);
  });

  it("reads readiness and sends the lease only in the controller header", async () => {
    global.fetch = vi.fn()
      .mockResolvedValueOnce(response(200, { ready: true, valid_packets: 20 }))
      .mockResolvedValueOnce(response(200, { ...prepared, status: "BASELINE", controller_lease: undefined }));

    expect((await getLiftoffReadiness()).ready).toBe(true);
    await transitionLiftoff("session-1", "baseline/start", "secret");
    const [url, init] = (global.fetch as any).mock.calls[1];
    expect(url).not.toContain("secret");
    expect(init.headers["X-Liftoff-Controller"]).toBe("secret");
  });
});
