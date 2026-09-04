import { describe, expect, it } from "vitest";

import {
  PVT_MAX_WAIT_MS,
  PVT_MIN_WAIT_MS,
  PVT_PROTOCOL_DURATION_MS,
  classifyPvtResponse,
  randomPvtWait,
} from "@/lib/pvt";

describe("PVT protocol helpers", () => {
  it("uses the standard 10-minute duration", () => {
    expect(PVT_PROTOCOL_DURATION_MS).toBe(600_000);
  });

  it("generates inclusive 2–10 second waiting intervals", () => {
    expect(randomPvtWait(() => 0)).toBe(PVT_MIN_WAIT_MS);
    expect(randomPvtWait(() => 0.999999)).toBe(PVT_MAX_WAIT_MS);
  });

  it("classifies false starts and lapses at protocol thresholds", () => {
    expect(classifyPvtResponse(99.99)).toBe("false_start");
    expect(classifyPvtResponse(100)).toBe("response");
    expect(classifyPvtResponse(499.99)).toBe("response");
    expect(classifyPvtResponse(500)).toBe("lapse");
  });
});
