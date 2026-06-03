"use client";

import { useEffect, useMemo, useState } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { getFits, getMetricsLong, listParticipants } from "@/lib/api";
import { METRICS, groupOverview, trajectorySeries } from "@/lib/viz";
import { TrajectoryChart } from "@/components/charts/TrajectoryChart";
import { LevelBarsChart } from "@/components/charts/LevelBarsChart";
import { DepdfPanel } from "@/components/charts/DepdfPanel";
import { GroupChart } from "@/components/charts/GroupChart";
import type { FitRow, MetricRow, Participant } from "@/types";

const SELECT_CLS = "flex h-10 rounded-md border border-input bg-background px-3 text-sm";

export default function VisualizationPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [rows, setRows] = useState<MetricRow[]>([]);
  const [fits, setFits] = useState<FitRow[]>([]);
  const [pid, setPid] = useState("");
  const [metric, setMetric] = useState("sysmon_d_prime");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([listParticipants(), getMetricsLong(), getFits()])
      .then(([ps, ms, fs]) => {
        setParticipants(ps);
        setRows(ms);
        setFits(fs);
        if (ps.length) setPid((cur) => cur || ps[0].id);
      })
      .catch((e) => setError((e as Error).message));
  }, []);

  const trajectory = useMemo(() => trajectorySeries(rows, pid, metric), [rows, pid, metric]);
  const group = useMemo(() => groupOverview(rows, metric), [rows, metric]);
  const participantFits = useMemo(() => fits.filter((f) => f.participant_id === pid), [fits, pid]);
  const hasData = rows.length > 0;

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Visualization</h2>
        <p className="text-sm text-muted-foreground">Descriptive views. Inferential statistics arrive with the Analysis module (Phase 3).</p>
      </header>
      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="flex flex-wrap gap-3">
        <label className="flex items-center gap-2 text-sm">
          Participant
          <select className={SELECT_CLS} value={pid} onChange={(e) => setPid(e.target.value)}>
            {participants.map((p) => <option key={p.id} value={p.id}>{p.id}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-sm">
          Metric
          <select className={SELECT_CLS} value={metric} onChange={(e) => setMetric(e.target.value)}>
            {Object.entries(METRICS).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
          </select>
        </label>
      </div>

      {!hasData ? (
        <p className="text-sm text-muted-foreground">No data yet — ingest sessions first.</p>
      ) : (
        <Tabs defaultValue="trajectories">
          <TabsList>
            <TabsTrigger value="trajectories">Trajectories</TabsTrigger>
            <TabsTrigger value="levels">Levels</TabsTrigger>
            <TabsTrigger value="depdf">DEPDF</TabsTrigger>
            <TabsTrigger value="group">Group</TabsTrigger>
          </TabsList>
          <TabsContent value="trajectories" className="pt-4">
            <TrajectoryChart data={trajectory} metric={metric} />
          </TabsContent>
          <TabsContent value="levels" className="pt-4">
            <LevelBarsChart data={trajectory} metric={metric} />
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
