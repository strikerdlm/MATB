import type {
  AnalysisArtifact, BayesJob, BlockDetail, FitRow, IngestResult, MetricRow, Participant, ParticipantCreate, TrackerCell, Visit,
} from "@/types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}
export class IngestError extends ApiError {
  constructor(status: number, message: string) {
    super(status, message);
    this.name = "IngestError";
  }
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    return (body && (body.detail || body.message)) || res.statusText;
  } catch {
    return res.statusText;
  }
}

export async function getTracker(): Promise<TrackerCell[]> {
  const res = await fetch(`${API_BASE}/tracker`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function listParticipants(): Promise<Participant[]> {
  const res = await fetch(`${API_BASE}/participants`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function createParticipant(body: ParticipantCreate): Promise<Participant> {
  const res = await fetch(`${API_BASE}/participants`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function listVisits(participantId: string): Promise<Visit[]> {
  const res = await fetch(`${API_BASE}/participants/${participantId}/visits`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export interface IngestTags {
  participant_id: string;
  visit_ordinal: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  overwrite?: boolean;
}

export async function ingestCsv(file: File, tags: IngestTags): Promise<IngestResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("participant_id", tags.participant_id);
  form.append("visit_ordinal", String(tags.visit_ordinal));
  form.append("workload_level", tags.workload_level);
  form.append("overwrite", String(tags.overwrite ?? false));
  const res = await fetch(`${API_BASE}/ingest`, { method: "POST", body: form });
  if (!res.ok) throw new IngestError(res.status, await detail(res));
  return res.json();
}

export async function getBlock(
  participantId: string, visitOrdinal: number, level: string,
): Promise<BlockDetail> {
  const q = new URLSearchParams({
    participant_id: participantId, visit_ordinal: String(visitOrdinal), workload_level: level,
  });
  const res = await fetch(`${API_BASE}/block?${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getMetricsLong(participantId?: string): Promise<MetricRow[]> {
  const q = participantId ? `?${new URLSearchParams({ participant_id: participantId })}` : "";
  const res = await fetch(`${API_BASE}/metrics/long${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getFits(participantId?: string): Promise<FitRow[]> {
  const q = participantId ? `?${new URLSearchParams({ participant_id: participantId })}` : "";
  const res = await fetch(`${API_BASE}/fits${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function runAnalysis(): Promise<AnalysisArtifact> {
  const res = await fetch(`${API_BASE}/analysis/run`, { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getLatestAnalysis(): Promise<AnalysisArtifact | null> {
  const res = await fetch(`${API_BASE}/analysis/latest`, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function runBayes(): Promise<BayesJob> {
  const res = await fetch(`${API_BASE}/analysis/bayes/run`, { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getBayesStatus(): Promise<BayesJob | null> {
  const res = await fetch(`${API_BASE}/analysis/bayes/status`, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}
