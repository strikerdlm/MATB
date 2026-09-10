import { sharedRead } from "@/lib/shared-request";
import type {
  AnalysisArtifact,
  BayesJob,
  BlockDetail,
  ConsoleCapabilities,
  CompiledExperiment,
  ExperimentSpec,
  FigureOptionExport,
  FitRow,
  IngestResult,
  MetricRow,
  Participant,
  ParticipantCreate,
  ParticipantJourney,
  PvtAssessment,
  PvtSummary,
  ResearchContext,
  ScreenIngestResult,
  ScreenSummary,
  StudyContextCreate,
  StudyParticipantContext,
  StudyProtocol,
  LiftoffTrackerCell,
  TrackerCell,
  Visit,
} from "@/types";
import { getApiBase } from "@/lib/runtime-config";

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

export async function getCapabilities(): Promise<ConsoleCapabilities> {
  return sharedRead("getCapabilities", async () => {
    const res = await request("/capabilities", { method: "GET" });
    if (!res.ok) throw new ApiError(res.status, await detail(res));
    return res.json();
  });
}

export async function compileExperiment(spec: ExperimentSpec): Promise<CompiledExperiment> {
  const res = await request("/experiments/compile", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(spec),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

async function detail(res: Response): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") return body.detail;
    if (typeof body?.detail?.message === "string") return body.detail.message;
    if (typeof body?.message === "string") return body.message;
    return res.statusText;
  } catch {
    return res.statusText;
  }
}

async function request(path: string, init: RequestInit): Promise<Response> {
  const apiBase = await getApiBase();
  return fetch(`${apiBase}${path}`, init);
}

export async function getTracker(): Promise<TrackerCell[]> {
  const res = await request("/tracker", { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getLiftoffTracker(): Promise<LiftoffTrackerCell[]> {
  const res = await request("/tracker/liftoff", { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function listParticipants(): Promise<Participant[]> {
  const res = await request("/participants", { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function createParticipant(body: ParticipantCreate): Promise<Participant> {
  const res = await request("/participants", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getStudyProtocol(): Promise<StudyProtocol> {
  return sharedRead("getStudyProtocol", async () => {
    const res = await request("/study/protocol", { method: "GET" });
    if (!res.ok) throw new ApiError(res.status, await detail(res));
    return res.json();
  });
}

export async function getStudyContext(participantId: string): Promise<StudyParticipantContext | null> {
  const path = `/participants/${encodeURIComponent(participantId)}/study-context`;
  const res = await request(path, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function createStudyContext(
  participantId: string,
  body: StudyContextCreate,
): Promise<StudyParticipantContext> {
  const path = `/participants/${encodeURIComponent(participantId)}/study-context`;
  const res = await request(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function listVisits(participantId: string): Promise<Visit[]> {
  const res = await request(`/participants/${encodeURIComponent(participantId)}/visits`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export interface IngestTags {
  participant_id: string;
  visit_ordinal: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  overwrite?: boolean;
  manifest?: File | null;
}

export async function ingestCsv(file: File, tags: IngestTags): Promise<IngestResult> {
  const form = new FormData();
  form.append("file", file);
  form.append("participant_id", tags.participant_id);
  form.append("visit_ordinal", String(tags.visit_ordinal));
  form.append("workload_level", tags.workload_level);
  form.append("overwrite", String(tags.overwrite ?? false));
  if (tags.manifest) form.append("manifest", tags.manifest);
  const res = await request("/ingest", { method: "POST", body: form });
  if (!res.ok) throw new IngestError(res.status, await detail(res));
  return res.json();
}

export async function getBlock(
  participantId: string, visitOrdinal: number, level: string,
): Promise<BlockDetail> {
  const q = new URLSearchParams({
    participant_id: participantId, visit_ordinal: String(visitOrdinal), workload_level: level,
  });
  const res = await request(`/block?${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getMetricsLong(participantId?: string): Promise<MetricRow[]> {
  const q = participantId ? `?${new URLSearchParams({ participant_id: participantId })}` : "";
  const res = await request(`/metrics/long${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getFits(participantId?: string): Promise<FitRow[]> {
  const q = participantId ? `?${new URLSearchParams({ participant_id: participantId })}` : "";
  const res = await request(`/fits${q}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function runAnalysis(): Promise<AnalysisArtifact> {
  const res = await request("/analysis/run", { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getLatestAnalysis(): Promise<AnalysisArtifact | null> {
  const res = await request("/analysis/latest", { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function runBayes(): Promise<BayesJob> {
  const res = await request("/analysis/bayes/run", { method: "POST" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getBayesStatus(jobId?: number): Promise<BayesJob | null> {
  const suffix = jobId === undefined ? "" : `/${encodeURIComponent(String(jobId))}`;
  const res = await request(`/analysis/bayes/status${suffix}`, { method: "GET" });
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function postScreen(
  participantId: string, payload: import("@/lib/screen").ScreenPayload,
  overwrite: boolean,
  executionPurpose: "practice" | "study",
  attemptId?: string,
): Promise<ScreenIngestResult> {
  const res = await request("/screen", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ participant_id: participantId, payload, overwrite, execution_purpose: executionPurpose, ...(attemptId ? {attempt_id: attemptId} : {}) }),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getScreenSummary(): Promise<ScreenSummary> {
  const res = await request("/screen", { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function postPvt(
  payload: import("@/lib/pvt").PvtPayload,
): Promise<PvtAssessment> {
  const res = await request("/pvt", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getPvtSummary(participantId?: string): Promise<PvtSummary> {
  const query = participantId
    ? `?${new URLSearchParams({ participant_id: participantId })}`
    : "";
  const res = await request(`/pvt${query}`, { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getParticipantJourney(
  participantId: string,
  visitOrdinal: number,
): Promise<ParticipantJourney> {
  const res = await request(
    `/journey/${encodeURIComponent(participantId)}/${encodeURIComponent(String(visitOrdinal))}`,
    { method: "GET" },
  );
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function getResearchContext(): Promise<ResearchContext> {
  const res = await request("/exports/research-context", { method: "GET" });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.json();
}

export async function downloadResearchBundle(figures: FigureOptionExport[]): Promise<Blob> {
  const res = await request("/exports/research-bundle", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ figures }),
  });
  if (!res.ok) throw new ApiError(res.status, await detail(res));
  return res.blob();
}
