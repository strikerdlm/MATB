import { ApiError } from "@/lib/api";
import { getApiBase } from "@/lib/runtime-config";
import { stationFetch } from "@/lib/station-fetch";

export const CREW_ACTIVITIES = ["openmatb", "suas", "screen", "pvt"] as const;
export type CrewActivity = typeof CREW_ACTIVITIES[number];
export function crewActivity(value: string | null): CrewActivity {
  return CREW_ACTIVITIES.includes(value as CrewActivity) ? value as CrewActivity : "openmatb";
}
export function crewHref(activity: CrewActivity, callsign?: string): string {
  const query = new URLSearchParams({ experiment: activity, purpose: "study" });
  if (callsign) query.set("crew", callsign);
  return `/study/join?${query}`;
}
export interface CrewProgress {
  callsign: string;
  participant_id: string;
  instrument: CrewActivity;
  state: "ready" | "interrupted" | "scheduled" | "activity_complete" | "complete" | "needs_review";
  session_number: number | null;
  completed_sessions: number;
  completed_blocks: number;
  total_sessions: number;
  date: string;
  day_label: string;
  scheduled_date: string;
  next_test_date: string | null;
  days_until_next: number | null;
  next_activity: CrewActivity | null;
  completed_days: number;
  activities: { instrument: CrewActivity; complete: boolean }[];
  schedule: { label: string; date: string; complete: boolean }[];
  message?: string;
}
export interface CrewPreparation extends CrewProgress {
  action: "launch" | "native_session" | "rest" | "retry_required" | "scheduled" | "activity_complete" | "complete" | "needs_review";
  activity?: CrewActivity;
  attempt_id?: string;
  visit_id?: number;
  visit_ordinal?: number;
  locale?: "es-419" | "en";
  config?: {
    preset?: { id: string; version: string };
    instructions?: { id: string; version: string };
    visual?: { id: string; version: string };
    scenario?: { id: string; sha256: string };
    presentation?: import("@/lib/simulation/presentation/contracts").PresentationConfig | null;
  };
  session_id?: string | null;
  available_at?: string;
  remaining_seconds?: number;
}
async function request<T>(path: string, body?: unknown): Promise<T> {
  const response = await stationFetch(`${await getApiBase()}/astra/crew${path}`, {
    method: body === undefined ? "GET" : "POST",
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new ApiError(response.status, typeof payload.detail === "string" ? payload.detail : payload.detail?.message ?? "No se pudo conectar con la estación.");
  }
  return response.json();
}
export const getCrewProgress = (activity: CrewActivity) => request<{ participants: CrewProgress[] }>(`?instrument=${activity}`);
export const prepareCrewActivity = (callsign: string, instrument: CrewActivity, retry = false) =>
  request<CrewPreparation>("/prepare", { callsign, instrument, retry });
