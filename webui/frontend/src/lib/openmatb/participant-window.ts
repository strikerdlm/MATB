export type ParticipantWindowState = "opened" | "blocked" | "unknown";
const key = (id: string) => `openmatb.participant-window.${id}`;

export function saveParticipantWindowState(id: string, state: ParticipantWindowState): void {
  try { sessionStorage.setItem(key(id), state); } catch { /* The controller URL also carries a blocked opening. */ }
}

export function readParticipantWindowState(id: string): ParticipantWindowState {
  try {
    const value = sessionStorage.getItem(key(id));
    return value === "opened" || value === "blocked" ? value : "unknown";
  } catch { return "unknown"; }
}
