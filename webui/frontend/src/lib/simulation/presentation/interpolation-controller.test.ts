import { afterEach, expect, it, vi } from "vitest";
import { animateSnapshot } from "./interpolation-controller";
import { preflightSnapshot } from "@/components/mission/presentation/MissionPresentation";

afterEach(() => vi.unstubAllGlobals());
it("releases its frame owner and rejects late callbacks after concealment cancellation", () => {
  const request = vi.fn((callback: FrameRequestCallback) => { void callback; return 8; }), cancel = vi.fn(), draw = vi.fn();
  vi.stubGlobal("requestAnimationFrame", request); vi.stubGlobal("cancelAnimationFrame", cancel);
  const before = preflightSnapshot("LOW"), after = { ...before, simulation_time_ms: 100 };
  const stop = animateSnapshot(before, after, true, draw);
  expect(draw).toHaveBeenCalledTimes(1);
  stop(); request.mock.calls[0][0](performance.now()+160);
  expect(cancel).toHaveBeenCalledWith(8); expect(draw).toHaveBeenCalledTimes(1);
});
it("does not schedule animation across blocks or under an immediate condition", () => {
  const request = vi.fn(), draw = vi.fn(); vi.stubGlobal("requestAnimationFrame", request);
  const before = preflightSnapshot("LOW"), after = preflightSnapshot("HIGH");
  animateSnapshot(before, after, true, draw);
  animateSnapshot(before, before, false, draw);
  expect(request).not.toHaveBeenCalled(); expect(draw).toHaveBeenLastCalledWith(before);
});
