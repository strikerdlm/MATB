import { getCapabilities, getLiftoffTracker, getTracker } from "@/lib/api";
import { activeComponentIds, hasComponent } from "@/lib/capabilities";
import type { ConsoleCapabilities, LiftoffTrackerCell, TrackerCell } from "@/types";

interface TrackerFetchers {
  getCapabilities: () => Promise<Pick<ConsoleCapabilities, "components">>;
  getTracker: () => Promise<TrackerCell[]>;
  getLiftoffTracker: () => Promise<LiftoffTrackerCell[]>;
}

const DEFAULT_FETCHERS: TrackerFetchers = {
  getCapabilities,
  getTracker,
  getLiftoffTracker,
};

export interface TrackerData {
  tracker: TrackerCell[];
  liftoffTracker: LiftoffTrackerCell[];
  componentIds: string[];
}

export async function loadTrackerData(fetchers: TrackerFetchers = DEFAULT_FETCHERS): Promise<TrackerData> {
  const [capabilities, tracker] = await Promise.all([
    fetchers.getCapabilities(),
    fetchers.getTracker(),
  ]);
  const liftoffTracker = hasComponent(capabilities, "matb-liftoff")
    ? await fetchers.getLiftoffTracker()
    : [];
  return {
    tracker,
    liftoffTracker,
    componentIds: activeComponentIds(capabilities),
  };
}
