export interface Participant {
  id: string;
  enrollment_date: string;
  sex?: string | null;
  age_band?: string | null;
  notes?: string | null;
}

export interface Visit {
  id: number;
  participant_id: string;
  visit_ordinal: number;
  scheduled_day: number;
  actual_date?: string | null;
  status: string;
}

export interface TrackerCell {
  participant_id: string;
  visit_ordinal: number;
  scheduled_day: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  present: boolean;
}

export interface IngestResult {
  id: number;
  workload_level: string;
  visit_id: number;
}

export interface ParticipantCreate {
  id: string;
  enrollment_date: string;
  sex?: string;
  age_band?: string;
  notes?: string;
}

export interface BlockDetail {
  participant_id: string;
  visit_ordinal: number;
  workload_level: string;
  metrics: {
    sysmon?: { d_prime?: number | null; hit_rate?: number | null; n_misses?: number; mean_rt_ms?: number | null };
    comm?: { d_prime?: number | null };
    nasatlx?: { raw_tlx?: number | null };
    bedford?: { value?: number | null };
    isa?: { mean?: number | null };
  };
  depdf_fit: { g0: number; p0: number; tau0: number; hcf_source: string; mwl_source: string } | null;
}

export interface MetricRow {
  participant_id: string;
  visit_ordinal: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  metric: string;
  value: number;
}

export interface CurvePoint { r: number; p: number; }

export interface FitRow {
  participant_id: string;
  visit_ordinal: number;
  g0: number;
  p0: number;
  tau0: number;
  hcf_source: string;
  mwl_source: string;
  curve: CurvePoint[];
}

// --- Phase 3A analysis artifact (matches matb_integration.analysis.stats) ---

export type AnalysisStatus = "ok" | "insufficient_data" | "not_estimable";

export interface CoefRow {
  name: string;
  coef: number;
  ci95: [number, number];
  p: number;
  std_effect: number;
  standardizer: string;
  p_holm?: number;
  reject_holm?: boolean;
}

export interface LmmResult {
  status: AnalysisStatus;
  detail?: string;
  formula?: string;
  n_obs?: number;
  n_participants?: number;
  re_var?: number;
  resid_var?: number;
  omnibus?: { statistic: number; df: number; p: number; test: string };
  coefs?: CoefRow[];
  interactions?: CoefRow[];
  contrasts?: CoefRow[] | null;
  exploratory?: boolean;
}

export interface RmcorrResult {
  status: AnalysisStatus;
  detail?: string;
  r?: number;
  dof?: number;
  p?: number;
  ci95?: [number, number];
  n_pairs?: number;
  n_participants?: number;
  method?: string;
}

export interface FamilyTest {
  metric: string;
  test: "Q1_omnibus" | "Q2_visit_slope";
  p: number | null;
  p_fdr: number | null;
  reject: boolean | null;
}

export interface RmanovaResult {
  status: AnalysisStatus;
  detail?: string;
  F?: number;
  df?: [number, number];
  p?: number;
  partial_eta_sq?: number;
  complete_case_n?: number;
  note?: string;
}

export interface AnalysisArtifact {
  cached: boolean;
  engine_version: string;
  spec: string;
  provenance: {
    fingerprint: string;
    n_metric_rows: number;
    n_fit_rows: number;
    n_participants: number;
    libraries: Record<string, string>;
    created_utc: string | null;
  };
  confirmatory: {
    family_size_planned: number;
    family_size_actual: number;
    fdr_q: number;
    tests: FamilyTest[];
  };
  q1: Record<string, LmmResult>;
  q2: Record<string, LmmResult>;
  q3: { x: string; y: string; canonical: RmcorrResult; sensitivity?: RmcorrResult }[];
  q4: Record<string, LmmResult>;
  rmanova: Record<string, RmanovaResult>;
  caveats: string[];
}

// --- Phase 3B Bayesian sensitivity (matb_integration.analysis.stats.bayes) ---

export interface BayesCoef {
  mean: number;
  sd: number;
  eti95: [number, number];
  r_hat: number;
  ess_bulk: number;
  ess_tail: number;
}

export interface BayesModelResult {
  status: AnalysisStatus;
  detail?: string;
  n_obs?: number;
  n_participants?: number;
  coefs?: Record<string, BayesCoef>;
  diagnostics?: { max_r_hat: number; min_ess_bulk: number; divergences: number };
  converged?: boolean;
}

export interface BayesArtifact {
  bayes_version: string;
  spec: string;
  sampler: {
    seed: number; chains: number; draws: number; tune: number;
    nuts: string; cores: number; interval: string;
    priors: Record<string, string>;
  };
  provenance: {
    fingerprint: string;
    n_metric_rows: number;
    n_fit_rows: number;
    libraries: Record<string, string>;
    created_utc: string | null;
  };
  q2: Record<string, BayesModelResult>;
  q4: Record<string, BayesModelResult>;
  all_converged: boolean;
  caveats: string[];
}

export interface BayesJob {
  job_id: number;
  status: "queued" | "running" | "done" | "failed";
  cached?: boolean;
  error?: string | null;
  created_at?: string;
  finished_at?: string | null;
  artifact?: BayesArtifact;
}

// --- neurocognitive screen (matb_integration/screen) ---

export interface SubtestScore {
  valid: boolean;
  n_trials?: number;
  n_usable?: number;
  median_ms?: number | null;
  accuracy?: number | null;
  d_prime?: number | null;
  rms_norm?: number | null;
  [k: string]: unknown;
}

export interface ScreenEntry {
  participant_id: string;
  administered_at: string;
  screen_version: number;
  scores: Record<string, SubtestScore>;
  hcf_value: number | null;
  components: Record<string, number> | null;
}

export interface ScreenSummary {
  n_screened: number;
  min_cohort: number;
  hcf_active: boolean;
  screen_version: number;
  screens: ScreenEntry[];
}

export interface ScreenIngestResult {
  participant_id: string;
  screen_version: number;
  scores: Record<string, SubtestScore>;
}
