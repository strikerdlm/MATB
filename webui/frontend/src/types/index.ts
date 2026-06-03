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
