import { describe, expect, it, vi } from "vitest";

import { loadTrackerData } from "@/lib/tracker-data";

const tracker = [
  { participant_id: "P01", visit_ordinal: 1, scheduled_day: 0, workload_level: "LOW" as const, present: true },
];

describe("tracker capability loading", () => {
  it("does not request the Liftoff endpoint in a research-core distribution", async () => {
    const getLiftoffTracker = vi.fn();
    const result = await loadTrackerData({
      getCapabilities: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        components: [
          { component_id: "matb-console" },
          { component_id: "matb-contracts" },
          { component_id: "matb-research" },
        ],
      }),
      getTracker: vi.fn().mockResolvedValue(tracker),
      getLiftoffTracker,
    });

    expect(result.tracker).toEqual(tracker);
    expect(result.liftoffTracker).toEqual([]);
    expect(result.componentIds).toEqual(["matb-console", "matb-contracts", "matb-research"]);
    expect(getLiftoffTracker).not.toHaveBeenCalled();
  });

  it("loads Liftoff completeness only when that capability is active", async () => {
    const liftoff = [{ participant_id: "P01", visit_ordinal: 1, state: "absent" }];
    const getLiftoffTracker = vi.fn().mockResolvedValue(liftoff);
    const result = await loadTrackerData({
      getCapabilities: vi.fn().mockResolvedValue({
        schema_version: "1.0",
        components: [{ component_id: "matb-liftoff" }, { component_id: "matb-console" }],
      }),
      getTracker: vi.fn().mockResolvedValue(tracker),
      getLiftoffTracker,
    });

    expect(result.liftoffTracker).toEqual(liftoff);
    expect(getLiftoffTracker).toHaveBeenCalledOnce();
  });
});
