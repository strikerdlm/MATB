import { getApiBase } from "@/lib/runtime-config";

export interface EvidenceMetric {
  id: string; metric: string; value: number | null; descriptive_value: number | null;
  metric_version: string; status: string; confirmatory_eligible: boolean;
  exclusion_reasons: string[]; timing_basis: string;
  physical_timing_qualification: string; human_calibration: string;
  definition: { equation: string; unit: string; required_inputs: string[]; missing_policy: string };
}
export interface EvidenceCapture {
  id: string; participant_id: string | null; condition: string; execution_purpose: string; completion: string;
  block_instance_id: string; manifest_sha256: string;
  manifest: { source_commit: string; scenario_sha256: string; profile_id: string; clocks: Record<string, string> };
  metrics: EvidenceMetric[]; runs: { id: string; status: string; reason: string | null; version: string }[];
  reconciliation: { fingerprint: string; issues: { code: string; task: string | null; event_ids: string[]; detail: string }[] } | null;
}
export interface EvidenceRecord {
  raw_json?: string; value_text?: string;
  event_id: string; sequence?: number; scenario_time_ns?: number; event_type?: string; task?: string | null;
  observation_id?: string; kind?: string; clock_id?: string; value?: number; unit?: string; evidence_source?: string;
  payload?: { record_type: string; address: string; value: unknown; automation_active: boolean | null };
}
export interface EvidencePage<T> { total: number; offset: number; limit: number; items: T[]; raw_items?: string[]; value_texts?: string[] }

export async function evidenceRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${await getApiBase()}${path}`, { ...init, cache: "no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail?.message || body?.detail?.code || body?.detail || `HTTP ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export async function downloadEvidence(captureId: string): Promise<void> {
  const response = await fetch(`${await getApiBase()}/evidence/captures/${encodeURIComponent(captureId)}/export`);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const url = URL.createObjectURL(await response.blob());
  const anchor = document.createElement("a"); anchor.href = url; anchor.download = `evidence-${captureId}.zip`;
  anchor.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
}
