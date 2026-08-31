export interface Participant {
  id: string;
  enrollment_date: string;
  sex?: string | null;
  age_band?: string | null;
  notes?: string | null;
}

export interface ComponentManifest {
  schema_version: "1.0";
  component_id: string;
  component_version: string;
  component_kind: "contracts" | "runtime" | "research" | "console" | "physiology" | "automation" | "simulation" | "governance";
  stability: "stable" | "candidate" | "experimental";
  distribution: "core" | "optional";
  capabilities: string[];
  requires: string[];
  python_entrypoint: string | null;
  license_expression: string;
}

export interface ConsoleCapabilities {
  schema_version: "1.0";
  components: ComponentManifest[];
}

export interface ExperimentTimelineEvent {
  eventKey: string;
  atSeconds: number;
  durationSeconds: number | null;
  task: string;
  command: string;
  value?: string | number | boolean;
}

export interface ExperimentSpec {
  schema_version: "1.0";
  experiment_id: string;
  revision: number;
  title: string;
  seed: number;
  profile_id: string;
  duration_ns: number;
  components: string[];
  timeline: Array<{
    event_key: string;
    at_ns: number;
    duration_ns: number | null;
    component_id: string;
    task: string;
    event_type: "openmatb.command";
    parameters: Record<string, string | number | boolean>;
  }>;
  metadata: Record<string, string | number | boolean>;
}

export interface ExperimentSummary {
  sourceCommandCount: number;
  sourceCommandRatePerMinute: number;
  perTaskSourceCommandRatePerMinute: Record<string, number>;
  stimulusOpportunityCount: number;
  stimulusOpportunityRatePerMinute: number;
  perTaskStimulusOpportunityRatePerMinute: Record<string, number>;
  minimumStimulusRefractoryMsByTask: Record<string, number | null>;
  overlapCount: number;
  overlapPercent: number;
  sysmonTargetOpportunities: number;
  sysmonNontargetOpportunities: number;
}

export interface TimelineConstraint {
  id: string;
  label: string;
  status: "pass" | "warning" | "fail";
  detail: string;
}

export interface CompiledExperiment {
  scenario_text: string;
  manifest: {
    source_commit: string;
    source_dirty: boolean | null;
    provenance_status: "complete" | "provisional_dirty_source_tree" | "provisional_unverified_source_tree" | "provisional_missing_source_commit" | "provisional_invalid_source_commit";
    spec: { sha256: string };
    scenario: { sha256: string };
    summary: Record<string, unknown>;
    claim_boundary: string;
    [key: string]: unknown;
  };
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

export interface LiftoffTrackerCell {
  participant_id: string;
  visit_ordinal: number;
  visit_code: string;
  scheduled_day: number;
  attempt_count: number;
  session_id?: string | null;
  status?: string | null;
  validity?: string | null;
  metrics_present: boolean;
  hrv_measurement_id?: string | null;
  sync_quality: string;
  present: boolean;
  state: "absent" | "pending" | "partial" | "invalid" | "valid_no_hrv" | "valid_poor_sync" | "valid_good_sync";
}

export interface IngestResult {
  id: number;
  workload_level: string;
  visit_id: number;
  validation?: ValidationSummary;
}

export interface ValidationIssue {
  severity: "warning" | "error" | string;
  code: string;
  message: string;
  expected?: unknown;
  observed?: unknown;
}

export interface ValidationSummary {
  status: string;
  issue_count: number;
  issues_preview: ValidationIssue[];
}

export interface BlockProvenance {
  manifest_filename?: string | null;
  manifest_hash?: string | null;
  validation_status: string;
  validation_issues: ValidationIssue[];
  manifest_summary?: Record<string, unknown> | null;
}

export interface ParticipantCreate {
  id: string;
  enrollment_date: string;
  sex?: string;
  age_band?: string;
  notes?: string;
}

export interface StudyVisitDefinition {
  ordinal: number;
  code: "T0" | "DM8" | "DM15" | string;
  scheduled_day: number;
}

export interface StudyProtocol {
  protocol_id: string;
  protocol_version: string;
  schedule_sha256: string;
  visits: StudyVisitDefinition[];
}

export interface StudyContextCreate {
  task_sequence: "MATB_LIFTOFF" | "LIFTOFF_MATB";
  prior_fpv_hours: number;
  gaming_hours_per_week: number;
}

export interface StudyParticipantContext extends StudyContextCreate {
  participant_id: string;
  protocol_id: string;
  created_at: string;
}

export interface BlockDetail {
  participant_id: string;
  visit_ordinal: number;
  workload_level: string;
  metrics: {
    sysmon?: {
      d_prime?: number | null;
      dprime_observed_v2?: number | null;
      dprime_estimated_v1?: number | null;
      observed_dprime_status?: string;
      hit_rate?: number | null;
      n_misses?: number;
      mean_rt_ms?: number | null;
    };
    track?: { rmse_deviation?: number | null; percent_time_in_target?: number | null };
    resman?: { mean_absolute_deviation?: number | null; percent_time_in_tolerance?: number | null };
    comm?: { d_prime?: number | null };
    nasatlx?: {
      rtlx_mean_0_100?: number | null;
      legacy_subscale_sum_0_60?: number | null;
      raw_tlx?: number | null;
      complete?: boolean;
    };
    bedford?: { value?: number | null };
    isa?: { mean?: number | null };
  };
  depdf_fit: { g0: number; p0: number; tau0: number; hcf_source: string; mwl_source: string } | null;
  provenance?: BlockProvenance | null;
}

export interface MetricRow {
  participant_id: string;
  visit_ordinal: number;
  workload_level: "LOW" | "MEDIUM" | "HIGH";
  metric: string;
  value: number;
  metrics_schema_version?: string;
  metric_version?: string;
  scientific_source_status?: string;
  confirmatory_eligible?: boolean;
}

export interface CurvePoint { r: number; p: number; }

export interface FitRow {
  participant_id: string;
  visit_ordinal: number;
  g0: number;
  p0: number;
  tau0: number;
  hcf_source: string;
  hcf_value: number;
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
  last_attempt_at?: string;
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

// --- P0 reproducibility export ---

export interface FigureOptionExport {
  name: string;
  option: Record<string, unknown>;
}

export interface ResearchContext {
  bundle_version: string;
  created_utc: string;
  participants: Participant[];
  visits: Visit[];
  tracker: TrackerCell[];
  metrics_long: MetricRow[];
  fits: FitRow[];
  analysis_latest: AnalysisArtifact | null;
  bayes_latest: BayesArtifact | null;
  block_provenance: Array<BlockProvenance & { block_id: number }>;
  validation_status_counts: Record<string, number>;
  counts: Record<string, number>;
}
