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

export const useConsole = create<ConsoleState>((set, get) => ({
  participants: [],
  tracker: [],
  loading: false,
  error: null,
  refreshParticipants: async () => {
    set({ loading: true, error: null });
    try { set({ participants: await listParticipants() }); }
    catch (e) { set({ error: (e as Error).message }); }
    finally { set({ loading: false }); }
  },
  refreshTracker: async () => {
    set({ loading: true, error: null });
    try { set({ tracker: await getTracker() }); }
    catch (e) { set({ error: (e as Error).message }); }
    finally { set({ loading: false }); }
  },
  refreshAll: async () => {
    await Promise.all([get().refreshParticipants(), get().refreshTracker()]);
  },
}));
