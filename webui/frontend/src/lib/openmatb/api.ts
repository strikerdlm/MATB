import { getApiBase } from "@/lib/runtime-config";
import type { OpenMatbInstructionProtocol, OpenMatbPresetSet, OpenMatbReadiness, OpenMatbSession, PreparedOpenMatbSession, WorkloadScaleSubmission } from "@/types/openmatb";

export class OpenMatbApiError extends Error {
  constructor(public status: number, public code: string, message: string) {
    super(message);
    this.name = "OpenMatbApiError";
  }
}

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = await getApiBase();
  const response = await fetch(`${base}${path}`, init);
  if (!response.ok) {
    let code = "openmatb_request_failed";
    let message = response.statusText;
    try {
      const payload = await response.json();
      code = payload?.detail?.code ?? code;
      message = payload?.detail?.message ?? message;
    } catch { /* retain HTTP fallback */ }
    throw new OpenMatbApiError(response.status, code, message);
  }
  return response.json() as Promise<T>;
}

const json = (body: object, headers: HeadersInit = {}): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json", ...headers }, body: JSON.stringify(body),
});

export const getOpenMatbReadiness = () => call<OpenMatbReadiness>("/openmatb/readiness");
export const listOpenMatbPresets = () => call<OpenMatbPresetSet[]>("/openmatb/presets");
export const listOpenMatbInstructions = () => call<OpenMatbInstructionProtocol[]>("/openmatb/instruction-protocols");
export const getOpenMatbSession = (id: string) => call<OpenMatbSession>(`/openmatb/sessions/${encodeURIComponent(id)}`);

export function createOpenMatbSession(body: {
  participant_id: string; visit_ordinal: number; preset_id: string; preset_version: string;
  instruction_protocol_id: string; instruction_version: string; display_index: number;
}) {
  return call<PreparedOpenMatbSession>("/openmatb/sessions", json(body));
}

export function controllerAction(id: string, action: "start" | "pause" | "resume" | "repeat-practice", lease: string) {
  return call<OpenMatbSession>(`/openmatb/sessions/${encodeURIComponent(id)}/${action}`, json({}, { "X-OpenMATB-Controller": lease }));
}

export function abortOpenMatbSession(id: string, lease: string) {
  return call<OpenMatbSession>(`/openmatb/sessions/${encodeURIComponent(id)}/abort`, json({ reason: "operator_abort" }, { "X-OpenMATB-Controller": lease }));
}

export function acknowledgeOpenMatbInstructions(id: string, token: string) {
  return call<OpenMatbSession>(`/openmatb/sessions/${encodeURIComponent(id)}/instructions/acknowledge`, json({}, { "X-OpenMATB-Participant": token }));
}

export function submitOpenMatbScales(id: string, token: string, body: WorkloadScaleSubmission) {
  return call<OpenMatbSession>(`/openmatb/sessions/${encodeURIComponent(id)}/scales`, json(body, { "X-OpenMATB-Participant": token }));
}

export function storeOpenMatbCredentials(prepared: PreparedOpenMatbSession): void {
  sessionStorage.setItem(`openmatb.controller.${prepared.session.id}`, prepared.controller_lease);
  sessionStorage.setItem(`openmatb.participant.${prepared.session.id}`, prepared.participant_token);
}

export const readOpenMatbController = (id: string) => sessionStorage.getItem(`openmatb.controller.${id}`);
export const readOpenMatbParticipant = (id: string) => sessionStorage.getItem(`openmatb.participant.${id}`);

export function cloneOpenMatbPreset(source: OpenMatbPresetSet, body: { preset_id: string; version: string; label_es: string }) {
  return call<OpenMatbPresetSet>(`/openmatb/presets/${encodeURIComponent(source.preset_id)}/${encodeURIComponent(source.version)}/clone`, json(body));
}

export function updateOpenMatbPreset(preset: OpenMatbPresetSet) {
  return call<OpenMatbPresetSet>(`/openmatb/presets/${encodeURIComponent(preset.preset_id)}/${encodeURIComponent(preset.version)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ profiles: preset.profiles }) });
}

export function publishOpenMatbPreset(preset: OpenMatbPresetSet) {
  return call<OpenMatbPresetSet>(`/openmatb/presets/${encodeURIComponent(preset.preset_id)}/${encodeURIComponent(preset.version)}/publish`, json({}));
}

export function cloneOpenMatbInstructions(source: OpenMatbInstructionProtocol, body: { protocol_id: string; version: string }) {
  return call<OpenMatbInstructionProtocol>(`/openmatb/instruction-protocols/${encodeURIComponent(source.protocol_id)}/${encodeURIComponent(source.version)}/clone`, json(body));
}

export function updateOpenMatbInstructions(protocol: OpenMatbInstructionProtocol) {
  return call<OpenMatbInstructionProtocol>(`/openmatb/instruction-protocols/${encodeURIComponent(protocol.protocol_id)}/${encodeURIComponent(protocol.version)}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ title: protocol.title, steps: protocol.steps, task_instructions: protocol.task_instructions, visit_instructions: protocol.visit_instructions }) });
}

export function publishOpenMatbInstructions(protocol: OpenMatbInstructionProtocol) {
  return call<OpenMatbInstructionProtocol>(`/openmatb/instruction-protocols/${encodeURIComponent(protocol.protocol_id)}/${encodeURIComponent(protocol.version)}/publish`, json({}));
}
