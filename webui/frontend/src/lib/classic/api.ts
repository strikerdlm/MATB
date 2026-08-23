import { getApiBase } from "@/lib/runtime-config";
import type {
  ClassicArtifact,
  ClassicDebriefView,
  ClassicResourceRequest,
  ClassicScenario,
  ClassicSessionView,
  CreateClassicSession,
  PolarCapabilities,
  PolarDevice,
  PolarPreflight,
  PolarStatus,
  PreparedClassicSession,
} from "@/types/classic";

export class ClassicApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "ClassicApiError";
  }
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const base = await getApiBase();
  return fetch(`${base}${path}`, init);
}

async function checked<T>(response: Response): Promise<T> {
  if (response.ok) return response.json();
  const payload = await response.json().catch(() => null) as {
    detail?: { code?: string; message?: string } | string;
  } | null;
  const detail = payload?.detail;
  const code = typeof detail === "object" && detail?.code
    ? detail.code
    : "classic_request_failed";
  const message = typeof detail === "object" && detail?.message
    ? detail.message
    : typeof detail === "string" ? detail : response.statusText;
  throw new ClassicApiError(response.status, code, message);
}

function json(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function controlledJson(lease: string, body: unknown): RequestInit {
  return {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Classic-Controller": lease,
    },
    body: JSON.stringify(body),
  };
}

export async function getPolarCapabilities(): Promise<PolarCapabilities> {
  return checked(await request("/classic/polar/capabilities", { method: "GET" }));
}

export async function getPolarStatus(): Promise<PolarStatus> {
  return checked(await request("/classic/polar/status", { method: "GET" }));
}

export async function scanPolar(timeoutSeconds = 5): Promise<PolarDevice[]> {
  return checked(await request("/classic/polar/scan", json({ timeout_seconds: timeoutSeconds })));
}

export async function connectPolar(deviceToken: string): Promise<PolarStatus> {
  return checked(await request("/classic/polar/connect", json({ device_token: deviceToken })));
}

export async function polarPreflight(timeoutSeconds = 8): Promise<PolarPreflight> {
  return checked(await request("/classic/polar/preflight", json({ timeout_seconds: timeoutSeconds })));
}

export async function disconnectPolar(): Promise<PolarStatus> {
  return checked(await request("/classic/polar/disconnect", json({})));
}

export async function getClassicScenarios(): Promise<ClassicScenario[]> {
  return checked(await request("/classic/scenarios", { method: "GET" }));
}

export async function prepareClassicSession(
  body: CreateClassicSession,
): Promise<PreparedClassicSession> {
  return checked(await request("/classic/sessions/prepare", json(body)));
}

export async function getClassicSession(sessionId: string): Promise<ClassicSessionView> {
  return checked(await request(`/classic/sessions/${encodeURIComponent(sessionId)}`, { method: "GET" }));
}

export async function startClassicSession(
  sessionId: string,
  lease: string,
): Promise<ClassicSessionView> {
  return checked(await request(
    `/classic/sessions/${encodeURIComponent(sessionId)}/start`,
    controlledJson(lease, {}),
  ));
}

export async function abortClassicSession(
  sessionId: string,
  lease: string,
  reasonCode: string,
): Promise<ClassicSessionView> {
  return checked(await request(
    `/classic/sessions/${encodeURIComponent(sessionId)}/abort`,
    controlledJson(lease, { reason_code: reasonCode }),
  ));
}

export async function getClassicHistory(
  participantId?: string,
  visitOrdinal?: number,
): Promise<ClassicSessionView[]> {
  const query = new URLSearchParams();
  if (participantId) query.set("participant_id", participantId);
  if (visitOrdinal !== undefined) query.set("visit_ordinal", String(visitOrdinal));
  const suffix = query.size ? `?${query.toString()}` : "";
  return checked(await request(`/classic/sessions${suffix}`, { method: "GET" }));
}

export async function getClassicDebrief(sessionId: string): Promise<ClassicDebriefView> {
  return checked(await request(`/classic/sessions/${encodeURIComponent(sessionId)}/debrief`, { method: "GET" }));
}

export async function getClassicArtifacts(sessionId: string): Promise<ClassicArtifact[]> {
  return checked(await request(`/classic/sessions/${encodeURIComponent(sessionId)}/artifacts`, { method: "GET" }));
}

export async function selectClassicAttempt(
  sessionId: string,
  reasonCode: string,
): Promise<ClassicSessionView> {
  return checked(await request(
    `/classic/sessions/${encodeURIComponent(sessionId)}/select`,
    json({ reason_code: reasonCode }),
  ));
}

function encodedPath(path: string): string {
  return path.split("/").map((part) => encodeURIComponent(part)).join("/");
}

export async function getClassicResourceUrl(
  kind: "bundle" | "artifact" | "visit",
  options: ClassicResourceRequest,
): Promise<string> {
  const base = await getApiBase();
  if (kind === "visit" && "participantId" in options && options.participantId) {
    return `${base}/classic/visits/${encodeURIComponent(options.participantId)}/${options.visitOrdinal}/summary.${options.format}`;
  }
  if (!("sessionId" in options) || !options.sessionId) {
    throw new Error("sessionId is required for a classic session resource");
  }
  const prefix = `${base}/classic/sessions/${encodeURIComponent(options.sessionId)}`;
  if (kind === "bundle") return `${prefix}/bundle`;
  if (kind === "artifact" && "relativePath" in options && options.relativePath) {
    return `${prefix}/artifacts/${encodedPath(options.relativePath)}`;
  }
  throw new Error("relativePath is required for a classic artifact resource");
}
