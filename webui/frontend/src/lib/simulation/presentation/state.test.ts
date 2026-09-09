import { describe, expect, it, vi } from "vitest";
import { initialPresentation, presentationReducer, resolveExposure, cycleEntity, type ExposureEvent } from "./state";
import { CameraController } from "./camera-controller";
import { ExposureQueue } from "./queue";
import type { CameraPose } from "./contracts";

describe("resolved presentation exposure", () => {
  it("isolates observed focus from the simulator command target", () => {
    const state = { ...initialPresentation(null, "LOW"), aircraft_id: "UAS-01" };
    const next = presentationReducer(state, { type: "selection", entity: { category: "observed", id: "UAS-01" } });
    expect(next.aircraft_id).toBe("UAS-01");
    expect(next.focus).toEqual({ category: "observed", id: "UAS-01" });
    expect(next.observed_id).toBe("UAS-01");
  });
  it("restores complete state backwards and orders paused-time actions", () => {
    const initial = initialPresentation(null, "LOW");
    const changed = { ...initial, operational_layers: { ...initial.operational_layers, routes: false }, observed_id: "obs" };
    const events: ExposureEvent[] = [
      { version: 2, block_id: "LOW", simulation_time_ms: 0, sequence: 1, resolved: initial },
      { version: 2, block_id: "LOW", simulation_time_ms: 100, sequence: 2, resolved: changed },
      { version: 2, block_id: "LOW", simulation_time_ms: 100, sequence: 3, resolved: { ...changed, visibility: "concealed" } },
    ];
    expect(resolveExposure(events, "LOW", 100)?.visibility).toBe("concealed");
    expect(resolveExposure(events, "LOW", 100, 2)).toEqual(changed);
    expect(resolveExposure(events, "LOW", 0)).toEqual(initial);
    expect(resolveExposure(events, "HIGH", 100)).toBeUndefined();
  });
  it("does not interpolate across concealment or target changes", () => {
    const initial = initialPresentation(null, "LOW");
    const pose: CameraPose = { camera_position: [0, 1, 0], camera_quaternion: [0, 0, 0, 1] };
    const events: ExposureEvent[] = [
      { version: 2, block_id: "LOW", simulation_time_ms: 0, resolved: { ...initial, pose } },
      { version: 2, block_id: "LOW", simulation_time_ms: 1000, kind: "render", resolved: { ...initial, pose: { ...pose, camera_position: [10, 1, 0] }, visibility: "concealed" } },
    ];
    expect(resolveExposure(events, "LOW", 500)?.pose).toEqual(pose);
  });
  it("cycles deterministically with empty and disappearing selections", () => {
    expect(cycleEntity([], null, 1)).toBeNull();
    expect(cycleEntity(["b", "a", "b"], "b", 1)).toBe("a");
    expect(cycleEntity(["b", "a"], "gone", -1)).toBe("b");
  });
});

describe("camera motion ownership", () => {
  const from: CameraPose = { camera_position: [0, 0, 0], camera_quaternion: [0, 0, 0, 1] };
  const to: CameraPose = { camera_position: [100, 0, 0], camera_quaternion: [0, 1, 0, 0] };
  it("finishes without an overshoot and releases transition ownership", () => {
    const camera = new CameraController();
    camera.begin(from, to, 0, 600, "follow");
    expect(camera.sample(300)?.camera_position[0]).toBeCloseTo(50);
    expect(camera.sample(1000)?.camera_position).toEqual(to.camera_position);
    expect(camera.owner).toBe("follow");
    expect(camera.sample(1200)).toBeNull();
  });
  it("cancels on takeover and supports zero-motion conditions", () => {
    const camera = new CameraController();
    camera.begin(from, to, 0, 600, "follow");
    expect(camera.cancel("manual")).toBe(true);
    expect(camera.sample(300)).toBeNull();
    camera.begin(from, to, 0, 0, "drone");
    expect(camera.owner).toBe("drone");
    expect(camera.sample(0)).toBeNull();
  });
});

describe("exposure delivery", () => {
  it("waits for acknowledgement before allowing a complete seal", async () => {
    vi.useFakeTimers();
    let acknowledge!: () => void;
    const queue = new ExposureQueue(() => new Promise<void>(resolve => { acknowledge = resolve; }), vi.fn());
    queue.push("last display change");
    let sealed = false;
    const flush = queue.flush().then(() => { sealed = true; });
    await vi.advanceTimersByTimeAsync(40);
    expect(sealed).toBe(false);
    acknowledge();
    await vi.runAllTimersAsync();
    await flush;
    expect(sealed).toBe(true);
    vi.useRealTimers();
  });
  it("retries the same item without reordering discrete actions", async () => {
    vi.useFakeTimers();
    const send = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(undefined);
    const fail = vi.fn();
    const queue = new ExposureQueue(send, fail);
    queue.push("first"); queue.push("second");
    await vi.runAllTimersAsync();
    expect(send.mock.calls.map(c => c[0])).toEqual(["first", "first", "second"]);
    expect(fail).not.toHaveBeenCalled();
    vi.useRealTimers();
  });
  it("reports capacity exhaustion instead of silently dropping changes", () => {
    const fail = vi.fn();
    const queue = new ExposureQueue(() => new Promise(() => {}), fail, 1);
    queue.push("first"); queue.push("second");
    expect(queue.failed).toBe(true);
    expect(fail).toHaveBeenCalledOnce();
  });
});
