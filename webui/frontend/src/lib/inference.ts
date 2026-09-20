import { evidenceRequest } from '@/lib/evidence';
import { stationFetch } from './station-fetch';
import { getApiBase } from './runtime-config';

export interface SemanticPreview {
  id: string; status: string; preview_hash?: string; payload?: string;
  error_code?:string|null;
  lineage?: { payload_hash: string; exclusions_json: string; evidence_run_id: string; [key: string]: unknown };
}
export interface SemanticRun {
  id: string; job_id: string; status: string; result_json: string | null;
  preview_id?: string; attempt_number?: number; error_code?: string | null; earliest_retry_ns?: string | null;
}
export interface SemanticNote {
  annotation_id: string; capture_id: string; original_text: string; language: string;
  source_event_ids: string[]; source_kind: string; author_role: string; created_at_ns: string;
  observation_start_ns?: string | null; observation_end_ns?: string | null; supersedes_annotation_id?: string | null;
}
export interface SemanticReview {id:string; owner_id:string; activity:string; reviewer:string; created_at_ns:string; content_json:string}
export interface SemanticPage<T> {items:T[];next_offset:number|null}
export const inferenceRequest = evidenceRequest;
export function jsonRequest(value: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) };
}

export async function downloadInference(identity: string,reviewer: string): Promise<void> {
  const response=await stationFetch(`${await getApiBase()}/inference/runs/${encodeURIComponent(identity)}/export?reviewer=${encodeURIComponent(reviewer)}`);
  if(!response.ok) throw new Error(`HTTP ${response.status}`);
  const url=URL.createObjectURL(await response.blob());
  const anchor=document.createElement('a');anchor.href=url;anchor.download=`inference-${identity}.zip`;
  anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
