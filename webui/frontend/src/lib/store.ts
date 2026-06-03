import { create } from "zustand";
import type { Participant, TrackerCell } from "@/types";
import { getTracker, listParticipants } from "@/lib/api";

interface ConsoleState {
  participants: Participant[];
  tracker: TrackerCell[];
  loading: boolean;
  error: string | null;
  refreshParticipants: () => Promise<void>;
  refreshTracker: () => Promise<void>;
  refreshAll: () => Promise<void>;
}

export const useConsole = create<ConsoleState>((set, get) => {
  // Inflight counter so concurrent refreshes (refreshAll runs two at once) don't
  // flip `loading` off until the LAST one settles.
  let inflight = 0;
  const start = () => {
    inflight += 1;
    set({ loading: true, error: null });
  };
  const stop = () => {
    inflight = Math.max(0, inflight - 1);
    if (inflight === 0) set({ loading: false });
  };

  return {
    participants: [],
    tracker: [],
    loading: false,
    error: null,
    refreshParticipants: async () => {
      start();
      try { set({ participants: await listParticipants() }); }
      catch (e) { set({ error: (e as Error).message }); }
      finally { stop(); }
    },
    refreshTracker: async () => {
      start();
      try { set({ tracker: await getTracker() }); }
      catch (e) { set({ error: (e as Error).message }); }
      finally { stop(); }
    },
    refreshAll: async () => {
      await Promise.all([get().refreshParticipants(), get().refreshTracker()]);
    },
  };
});
