import { describe, it, expect } from "vitest";
import {
  mulberry32, genSimpleRtIsis, genChoiceSides, genNbackSequence,
  targetPosition, SCREEN_CONFIG, FAST_CONFIG,
} from "@/lib/screen";

describe("screen lib", () => {
  it("mulberry32 is deterministic", () => {
    const a = mulberry32(42), b = mulberry32(42);
    expect([a(), a(), a()]).toEqual([b(), b(), b()]);
  });

  it("genSimpleRtIsis yields n ISIs within [1000, 3000] ms", () => {
    const isis = genSimpleRtIsis(30, mulberry32(1));
    expect(isis).toHaveLength(30);
    expect(Math.min(...isis)).toBeGreaterThanOrEqual(1000);
    expect(Math.max(...isis)).toBeLessThanOrEqual(3000);
  });

  it("genChoiceSides is balanced within 10%", () => {
    const sides = genChoiceSides(30, mulberry32(2));
    const left = sides.filter((s) => s === "left").length;
    expect(left).toBeGreaterThanOrEqual(12);
    expect(left).toBeLessThanOrEqual(18);
  });

  it("genNbackSequence has the requested target count and no 3-runs", () => {
    const { letters, isTarget } = genNbackSequence(60, 18, mulberry32(3));
    expect(letters).toHaveLength(60);
    expect(isTarget.filter(Boolean)).toHaveLength(18);
    // targets are defined as letter[i] === letter[i-2]
    isTarget.forEach((t, i) => {
      if (i >= 2) expect(t).toBe(letters[i] === letters[i - 2]);
      else expect(t).toBe(false);
    });
    // no 3 identical consecutive letters (would make 1-back == 2-back)
    for (let i = 2; i < letters.length; i++) {
      expect(letters[i] === letters[i - 1] && letters[i - 1] === letters[i - 2]).toBe(false);
    }
  });

  it("targetPosition is a bounded sum-of-sines", () => {
    for (const t of [0, 5, 30, 90]) {
      const { x, y } = targetPosition(t, 100);
      expect(Math.abs(x)).toBeLessThanOrEqual(100);
      expect(Math.abs(y)).toBeLessThanOrEqual(100);
    }
  });

  it("configs expose prereg counts and fast mode shrinks them", () => {
    expect(SCREEN_CONFIG.simpleRtTrials).toBe(30);
    expect(SCREEN_CONFIG.nbackTrials).toBe(60);
    expect(SCREEN_CONFIG.trackingSeconds).toBe(90);
    expect(FAST_CONFIG.simpleRtTrials).toBeLessThan(SCREEN_CONFIG.simpleRtTrials);
  });
});
