import { afterEach, expect, it, vi } from "vitest";
import { renderScheduler } from "./render-scheduler";

afterEach(() => vi.unstubAllGlobals());
it("submits one frame for concurrent invalidations and stays idle afterward", () => {
  let callback: FrameRequestCallback = () => {};
  const request = vi.fn((next: FrameRequestCallback) => { callback = next; return 1; });
  vi.stubGlobal("requestAnimationFrame", request);
  vi.stubGlobal("cancelAnimationFrame", vi.fn());
  const draw = vi.fn(), scheduler = renderScheduler(draw);
  scheduler.request(); scheduler.request(); scheduler.request();
  expect(request).toHaveBeenCalledTimes(1);
  callback(10);
  expect(draw).toHaveBeenCalledTimes(1);
  expect(request).toHaveBeenCalledTimes(1);
  scheduler.request();
  expect(request).toHaveBeenCalledTimes(2);
  scheduler.dispose(); callback(20);
  expect(draw).toHaveBeenCalledTimes(1);
});
