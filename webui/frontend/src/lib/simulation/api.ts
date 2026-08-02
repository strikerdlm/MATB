import { getApiBase } from "@/lib/runtime-config";
import type {
  ArtifactView,
  CommandRequest,
  CommandResultView,
  CreateSimulationSession,
  DebriefView,
  FinishRequest,
  LifecycleRequest,
  PreparedSession,
  RecoverRequest,
  RecoveryView,
  ScenarioSummary,
  ScenarioValidationView,
  SessionView,
  StreamEnvelope,
  WorldSnapshot,
} from "@/types/simulation";

export class SimulationApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public context?: Record<string, unknown>,
  ) {
    super(message);
    this.name = "SimulationApiError";
  }
}

async function simulationRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const apiBase = await getApiBase();
  const response = await fetch(`${apiBase}${path}`, init);
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => ({}));
    const detail = body && typeof body === "object" && "detail" in body
      ? (body as { detail?: unknown }).detail
      : body;
    const error = detail && typeof detail === "object" ? detail as Record<string, unknown> : {};
    const message = typeof error.message === "string"
      ? error.message
      : typeof detail === "string" ? detail : response.statusText || `request failed (${response.status})`;
    const code = typeof error.code === "string" ? error.code : "unknown_error";
    const context = error.context && typeof error.context === "object"
      ? error.context as Record<string, unknown>
      : undefined;
    throw new SimulationApiError(response.status, code, message, context);
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

function jsonInit(method: string, body: unknown, lease?: string | null): RequestInit {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (lease) headers.set("X-Simulation-Controller", lease);
  return { method, headers, body: JSON.stringify(body) };
}

function leaseInit(method: string, lease: string, body: unknown = {}): RequestInit {
  return jsonInit(method, body, lease);
}

export async function listSimulationScenarios(): Promise<ScenarioSummary[]> {
  return simulationRequest<ScenarioSummary[]>("/simulation/scenarios", { method: "GET" });
}

export async function validateSimulationScenario(file: File | Blob): Promise<ScenarioValidationView> {
  const form = new FormData();
  form.append("file", file, file instanceof File ? file.name : "scenario.yaml");
  return simulationRequest<ScenarioValidationView>("/simulation/scenarios/validate", {
    method: "POST",
    body: form,
  });
}

export async function createSimulationSession(body: CreateSimulationSession): Promise<PreparedSession> {
  return simulationRequest<PreparedSession>("/simulation/sessions", jsonInit("POST", body));
}

export type SessionTransition = "start" | "pause" | "resume" | "finish";

export async function getSimulationSession(id: string): Promise<SessionView> {
  return simulationRequest<SessionView>(`/simulation/sessions/${encodeURIComponent(id)}`, { method: "GET" });
}

export async function transitionSession(
  id: string,
  action: SessionTransition,
  lease: string,
  body: LifecycleRequest | FinishRequest = {},
): Promise<SessionView> {
  return simulationRequest<SessionView>(
    `/simulation/sessions/${encodeURIComponent(id)}/${action}`,
    leaseInit("POST", lease, body),
  );
}

export async function recoverSimulationSession(
  id: string,
  lease: string | null,
  body: RecoverRequest,
): Promise<RecoveryView> {
  return simulationRequest<RecoveryView>(
    `/simulation/sessions/${encodeURIComponent(id)}/recover`,
    jsonInit("POST", body, lease),
  );
}

export async function submitSimulationCommand(
  id: string,
  lease: string,
  command: CommandRequest,
): Promise<CommandResultView> {
  return simulationRequest<CommandResultView>(
    `/simulation/sessions/${encodeURIComponent(id)}/commands`,
    leaseInit("POST", lease, command),
  );
}

export async function getSimulationState(id: string): Promise<WorldSnapshot> {
  return simulationRequest<WorldSnapshot>(`/simulation/sessions/${encodeURIComponent(id)}/state`, { method: "GET" });
}

export async function getSimulationDebrief(id: string): Promise<DebriefView> {
  return simulationRequest<DebriefView>(`/simulation/sessions/${encodeURIComponent(id)}/debrief`, { method: "GET" });
}

export async function listSimulationArtifacts(id: string): Promise<ArtifactView[]> {
  return simulationRequest<ArtifactView[]>(`/simulation/sessions/${encodeURIComponent(id)}/artifacts`, { method: "GET" });
}

export function simulationWsUrl(
  apiBase: string,
  sessionId: string,
  afterSequence = 0,
  lease?: string,
): string {
  const url = new URL(`/simulation/sessions/${encodeURIComponent(sessionId)}/stream`, apiBase);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  url.searchParams.set("after_sequence", String(Math.max(0, Math.trunc(afterSequence))));
  if (lease) url.searchParams.set("lease", lease);
  return url.toString();
}

/** Namespace used by mission components without duplicating endpoint wiring. */
export const simulationApi = {
  listSimulationScenarios,
  validateSimulationScenario,
  createSimulationSession,
  getSimulationSession,
  transitionSession,
  recoverSimulationSession,
  submitSimulationCommand,
  getSimulationState,
  getSimulationDebrief,
  listSimulationArtifacts,
  simulationWsUrl,
};

export { simulationRequest };
