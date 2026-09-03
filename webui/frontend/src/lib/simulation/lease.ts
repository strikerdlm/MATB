import { getSimulationSession } from "@/lib/simulation/api";
import type { PreparedSession } from "@/types/simulation";

const LEASE_KEY_PREFIX = "matb.simulation.";
const LEASE_KEY_SUFFIX = ".lease";
const TERMINAL_LIFECYCLES = new Set(["FINISHED", "ABORTED"]);

export function controllerLeaseKey(sessionId: string): string {
  return `${LEASE_KEY_PREFIX}${sessionId}${LEASE_KEY_SUFFIX}`;
}

/** Preserve recoverable leases and remove only sessions confirmed terminal. */
export async function storePreparedSessionLease(prepared: PreparedSession): Promise<void> {
  if (typeof window === "undefined") return;
  const keys: string[] = [];
  for (let index = 0; index < window.sessionStorage.length; index += 1) {
    const key = window.sessionStorage.key(index);
    if (key?.startsWith(LEASE_KEY_PREFIX) && key.endsWith(LEASE_KEY_SUFFIX)) keys.push(key);
  }
  await Promise.all(keys.map(async (key) => {
    const sessionId = key.slice(LEASE_KEY_PREFIX.length, -LEASE_KEY_SUFFIX.length);
    if (!sessionId || sessionId === prepared.id) return;
    try {
      const session = await getSimulationSession(sessionId);
      if (TERMINAL_LIFECYCLES.has(session.lifecycle)) window.sessionStorage.removeItem(key);
    } catch {
      // An unverified active lease remains recoverable.
    }
  }));
  window.sessionStorage.setItem(controllerLeaseKey(prepared.id), prepared.controller_lease);
}
