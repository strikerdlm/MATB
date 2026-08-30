"use client";

import { useEffect, useMemo, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getFits, getMetricsLong, getStudyProtocol, listParticipants } from "@/lib/api";
import { METRICS, groupOverview, trajectorySeries } from "@/lib/viz";
import { TrajectoryChart } from "@/components/charts/TrajectoryChart";
import { LevelBarsChart } from "@/components/charts/LevelBarsChart";
import { DepdfPanel } from "@/components/charts/DepdfPanel";
import { GroupChart } from "@/components/charts/GroupChart";
import type { FitRow, MetricRow, Participant, StudyProtocol } from "@/types";

const SELECT_CLS = "native-select min-w-[12rem]";

export default function VisualizationPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [rows, setRows] = useState<MetricRow[]>([]);
  const [fits, setFits] = useState<FitRow[]>([]);
  const [protocol, setProtocol] = useState<StudyProtocol | null>(null);
  const [pid, setPid] = useState("");
  const [metric, setMetric] = useState("sysmon_hit_rate");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listParticipants(), getMetricsLong(), getFits(), getStudyProtocol()])
      .then(([ps, ms, fs, activeProtocol]) => {
        setParticipants(ps);
        setRows(ms);
        setFits(fs);
        setProtocol(activeProtocol);
        if (ps.length) setPid((cur) => cur || ps[0].id);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const visitOrdinals = useMemo(
    () => protocol?.visits.map((visit) => visit.ordinal) ?? [],
    [protocol],
  );
  const trajectory = useMemo(
    () => trajectorySeries(rows, pid, metric, visitOrdinals),
    [rows, pid, metric, visitOrdinals],
  );
  const group = useMemo(
    () => groupOverview(rows, metric, visitOrdinals),
    [rows, metric, visitOrdinals],
  );
  const participantFits = useMemo(() => fits.filter((f) => f.participant_id === pid), [fits, pid]);
  const participantRows = useMemo(() => rows.filter((r) => r.participant_id === pid), [rows, pid]);
  const hasData = rows.length > 0;

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Figure studio"
        title="Visualization"
        description="Participant trajectories, cohort intervals, and DEPDF model figures."
        stats={[
          { label: "Crew", value: participants.length },
          { label: "Rows", value: rows.length },
          { label: "Fits", value: fits.length },
        ]}
      />
      {error && <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">{error}</p>}

      <div className="control-surface flex flex-wrap gap-3">
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Participant</span>
          <select className={SELECT_CLS} value={pid} onChange={(e) => setPid(e.target.value)}>
            {participants.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1.5 text-sm">
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Metric</span>
          <select className={SELECT_CLS} value={metric} onChange={(e) => setMetric(e.target.value)}>
            {Object.entries(METRICS).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
          </select>
        </label>
      </div>

      {!hasData ? (
        <p className="rounded-[6px] border border-dashed border-white/15 px-4 py-8 text-center text-sm text-muted-foreground">
          No data yet. Ingest sessions first.
        </p>
      ) : (
        <Tabs defaultValue="trajectories">
          <TabsList>
            <TabsTrigger value="trajectories">Participant</TabsTrigger>
            <TabsTrigger value="levels">Workload</TabsTrigger>
            <TabsTrigger value="depdf">DEPDF</TabsTrigger>
            <TabsTrigger value="group">Cohort</TabsTrigger>
          </TabsList>
          <TabsContent value="trajectories" className="pt-4">
            {participantRows.length ? (
              <TrajectoryChart data={trajectory} metric={metric} />
            ) : (
              <p className="rounded-[6px] border border-dashed border-white/15 px-4 py-8 text-center text-sm text-muted-foreground">
                No rows for this participant and metric.
              </p>
            )}
          </TabsContent>
          <TabsContent value="levels" className="pt-4">
            {participantRows.length ? (
              <LevelBarsChart data={trajectory} metric={metric} />
            ) : (
              <p className="rounded-[6px] border border-dashed border-white/15 px-4 py-8 text-center text-sm text-muted-foreground">
                No rows for this participant and metric.
              </p>
            )}
          </TabsContent>
          <TabsContent value="depdf" className="pt-4">
            <DepdfPanel fits={participantFits} />
          </TabsContent>
          <TabsContent value="group" className="pt-4">
            <GroupChart data={group} metric={metric} />
          </TabsContent>
        </Tabs>
      )}
    </div>
  );
}
