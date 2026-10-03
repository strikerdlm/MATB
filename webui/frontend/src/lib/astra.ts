import { getApiBase } from "@/lib/runtime-config";
import type { Participant, Visit } from "@/types";
export interface AstraVisit extends Visit { code: string; planned_date: string; completed_blocks: number }
export interface AstraParticipant extends Participant {
  callsign: string; mission: "ASTRA-1" | "ASTRA-2"; position: number;
  rank: string | null; unit: string | null; role: string | null;
  time_slot: string | null; station: number; block_order: string[]; visits: AstraVisit[];
}
export interface AstraRoster { participants: AstraParticipant[]; session_minutes: number; experimental_block_seconds: number }
export interface AstraProtocol { active: boolean; version_id: string | null; title: string | null; includes_polar?: boolean }
export async function astraCall<T>(path: string, body?: object, method = body ? "POST" : "GET"): Promise<T> {
  const response = await fetch(`${await getApiBase()}${path}`, { method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined });
  const value = await response.json();
  if (!response.ok) throw new Error(typeof value.detail === "string" ? value.detail : value.detail?.message ??
    value.detail?.issues?.map((issue: { message: string }) => issue.message).join(" ") ?? "No se pudo completar la solicitud.");
  return value as T;
}
