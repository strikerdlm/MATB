import type { MetricRow } from "@/types";
import { LEVELS } from "@/lib/tracker";

export const METRICS: Record<string, { label: string; decimals: number; unit?: string }> = {
  sysmon_d_prime: { label: "SYSMON d′", decimals: 3 },
  sysmon_hit_rate: { label: "SYSMON hit rate", decimals: 3 },
  sysmon_mean_rt_ms: { label: "SYSMON mean RT", decimals: 0, unit: "ms" },
  comm_d_prime: { label: "COMM d′", decimals: 3 },
  nasatlx_raw_tlx: { label: "NASA-TLX (raw)", decimals: 1 },
  bedford: { label: "Bedford", decimals: 0 },
  isa_mean: { label: "ISA (mean)", decimals: 2 },
};

export interface Trajectory {
  visits: number[];
  series: Record<string, (number | null)[]>;   // keyed by workload level
}

export function trajectorySeries(
  rows: MetricRow[],
  participantId: string,
  metric: string,
  visitOrdinals: number[],
): Trajectory {
  const visits = [...visitOrdinals];
  const series: Record<string, (number | null)[]> = {};
  for (const level of LEVELS) {
    series[level] = visits.map((v) => {
      const hit = rows.find(
        (r) => r.participant_id === participantId && r.metric === metric &&
               r.workload_level === level && r.visit_ordinal === v,
      );
      return hit ? hit.value : null;
    });
  }
  return { visits, series };
}

export interface GroupStats {
  visits: number[];
  stats: Record<string, { mean: (number | null)[]; sd: (number | null)[]; n: number[] }>;
}

export function groupOverview(rows: MetricRow[], metric: string, visitOrdinals: number[]): GroupStats {
  const visits = [...visitOrdinals];
  const stats: GroupStats["stats"] = {};
  for (const level of LEVELS) {
    const mean: (number | null)[] = [];
    const sd: (number | null)[] = [];
    const n: number[] = [];
    for (const v of visits) {
      const values = rows
        .filter((r) => r.metric === metric && r.workload_level === level && r.visit_ordinal === v)
        .map((r) => r.value);
      n.push(values.length);
      if (values.length === 0) { mean.push(null); sd.push(null); continue; }
      const m = values.reduce((a, b) => a + b, 0) / values.length;
      mean.push(m);
      if (values.length < 2) { sd.push(null); continue; }
      const variance = values.reduce((a, b) => a + (b - m) ** 2, 0) / (values.length - 1);
      sd.push(Math.sqrt(variance));
    }
    stats[level] = { mean, sd, n };
  }
  return { visits, stats };
}
