import type {AssignmentContext} from './study';
import { ApiError } from './api';
import { getApiBase } from './runtime-config';
export type InterruptionCategory = 'withdrawal' | 'operator_stop' | 'hardware_failure' | 'software_failure' | 'planned_interruption' | 'unknown' | 'participant_stop' | 'technical_failure' | 'lost_connection' | 'other';
export type Instrument = 'pvt' | 'screen' | 'openmatb' | 'liftoff' | 'suas' | 'physiology' | 'questionnaire';
export interface Occasion { id: string; participant_id: string | null; visit_id: number | null; instrument: Instrument; phase: string | null; order: number | null; condition: string | null; version_ref: string | null; origin: string; collection_group_id: string | null; accompanying_occasion_id: string | null }
export interface Attempt { preparation_admission?: {attempt_id: string; assignment_id: string; snapshot_json: string; snapshot_sha256: string; created_at: string} | null; preparation_context?: (AssignmentContext & {preparation_id: string}) | null; assignment_context?: AssignmentContext | null; id: string; occasion_id: string; ordinal: number; execution_purpose: 'practice' | 'study'; purpose_provenance_id: string | null; repeat_of: string | null; repeat_reason: string | null; target_attempt_id: string | null; acquisition_state: string; interruption_category: string | null; receipt: {raw_saving: string; acquisition: string; ratings: string; processing: string}; sources: {source_table: string; source_id: string; role: string}[] }
export interface OccasionInput { participant_id: string; visit_id: number; instrument: Instrument; phase: string; order: number; condition?: string; version_ref?: string; collection_group_id?: string; accompanying_occasion_id?: string }
async function call<T>(path: string, body?: unknown, method = body === undefined ? 'GET' : 'POST'): Promise<T> {
  const res = await fetch(`${await getApiBase()}/assessments${path}`, {method, headers: {'Content-Type': 'application/json'}, ...(body === undefined ? {} : {body: JSON.stringify(body)})});
  if (!res.ok) { const error = await res.json(); throw new ApiError(res.status, typeof error.detail === 'string' ? error.detail : error.detail?.message ?? error.detail?.code ?? 'Assessment request failed'); }
  return res.json();
}
const id = encodeURIComponent;
export const listOccasions = (participant: string, instrument: Instrument) => call<Occasion[]>(`/occasions?participant_id=${id(participant)}&instrument=${id(instrument)}`);
export const createOccasion = (body: OccasionInput) => call<Occasion>('/occasions', body);
export const listAttempts = (occasion: string) => call<Attempt[]>(`/occasions/${id(occasion)}/attempts`);
export const createAttempt = (occasion: string, purpose: 'study' | 'practice', target_attempt_id?: string) => call<Attempt>(`/occasions/${id(occasion)}/attempts`, {execution_purpose: purpose, ...(target_attempt_id ? {target_attempt_id} : {})});
export const repeatAttempt = (attempt: string, purpose: 'study' | 'practice', reason: string, target_attempt_id?: string) => call<Attempt>(`/attempts/${id(attempt)}/repeat`, {execution_purpose: purpose, reason, ...(target_attempt_id ? {target_attempt_id} : {})});
export const startAttempt = (attempt: string) => call<Attempt>(`/attempts/${id(attempt)}/start`, undefined, 'POST');
export const interruptAttempt = (attempt: string, category: InterruptionCategory) => call<Attempt>(`/attempts/${id(attempt)}/interrupt`, {category});
export const getAttemptRaw = (attempt: string) => call<{attempt: Attempt; record: Record<string, unknown> | null}>(`/attempts/${id(attempt)}/raw`);

export const getAttempt = (attempt: string) => call<Attempt>(`/attempts/${id(attempt)}`);

export const getSourceAttempt = (table: string, identity: string, role = "acquisition") => call<Attempt>(`/sources/${id(table)}/${id(identity)}?role=${id(role)}`);
