import { getApiBase } from "@/lib/runtime-config";
import type {
  CreateLiftoffSession,
  LiftoffAction,
  LiftoffArtifactView,
  LiftoffDebriefView,
  LiftoffQuestionnaires,
  LiftoffReadiness,
  LiftoffSessionView,
  LiftoffVisibleResults,
  PreparedLiftoffSession,
} from "@/types/liftoff";

export class LiftoffApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "LiftoffApiError";
  }
}

async function request(path: string, init: RequestInit): Promise<Response> {
  const base = await getApiBase();
  return fetch(`${base}${path}`, init);
}

async function checked<T>(response: Response): Promise<T> {
  if (response.ok) return response.json();
  const payload = await response.json().catch(() => null) as {
    detail?: { code?: string; message?: string } | string;
  } | null;
  const detail = payload?.detail;
  const code = typeof detail === "object" && detail?.code ? detail.code : "liftoff_request_failed";
  const message = typeof detail === "object" && detail?.message
    ? detail.message
    : typeof detail === "string" ? detail : response.statusText;
  throw new LiftoffApiError(response.status, code, message);
}

function controllerHeaders(lease: string): Record<string, string> {
  return {
    "Content-Type": "application/json",
    "X-Liftoff-Controller": lease,
  };
}

export async function getLiftoffReadiness(): Promise<LiftoffReadiness> {
  return checked(await request("/liftoff/readiness", { method: "GET" }));
}

export async function createLiftoffSession(
  body: CreateLiftoffSession,
): Promise<PreparedLiftoffSession> {
  return checked(await request("/liftoff/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }));
}

export async function getLiftoffSession(sessionId: string): Promise<LiftoffSessionView> {
  return checked(await request(`/liftoff/sessions/${encodeURIComponent(sessionId)}`, { method: "GET" }));
}

export async function transitionLiftoff(
  sessionId: string,
  action: LiftoffAction,
  lease: string,
): Promise<LiftoffSessionView> {
  return checked(await request(`/liftoff/sessions/${encodeURIComponent(sessionId)}/${action}`, {
    method: "POST",
    headers: controllerHeaders(lease),
    body: "{}",
  }));
}

async function sha256Hex(file: File): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function submitLiftoffResults(
  sessionId: string,
  lease: string,
  results: LiftoffVisibleResults,
  screenshot: File,
): Promise<void> {
  const form = new FormData();
  form.append("metadata", JSON.stringify({ ...results, screenshot_sha256: await sha256Hex(screenshot) }));
  form.append("screenshot", screenshot, "result-screen");
  await checked(await request(`/liftoff/sessions/${encodeURIComponent(sessionId)}/results`, {
    method: "POST",
    headers: { "X-Liftoff-Controller": lease },
    body: form,
  }));
}

export async function submitLiftoffQuestionnaires(
  sessionId: string,
  lease: string,
  body: LiftoffQuestionnaires,
): Promise<void> {
  await checked(await request(`/liftoff/sessions/${encodeURIComponent(sessionId)}/questionnaires`, {
    method: "POST",
    headers: controllerHeaders(lease),
    body: JSON.stringify(body),
  }));
}

export async function sealLiftoffSession(
  sessionId: string,
  lease: string,
): Promise<LiftoffDebriefView> {
  return checked(await request(`/liftoff/sessions/${encodeURIComponent(sessionId)}/seal`, {
    method: "POST",
    headers: controllerHeaders(lease),
    body: "{}",
  }));
}

export async function getLiftoffDebrief(sessionId: string): Promise<LiftoffDebriefView> {
  return checked(await request(`/liftoff/sessions/${encodeURIComponent(sessionId)}/debrief`, { method: "GET" }));
}

export async function getLiftoffArtifacts(sessionId: string): Promise<LiftoffArtifactView[]> {
  return checked(await request(`/liftoff/sessions/${encodeURIComponent(sessionId)}/artifacts`, { method: "GET" }));
}
