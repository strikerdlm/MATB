"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Activity,
  CheckCircle2,
  Download,
  FileJson2,
  FileSpreadsheet,
  FileText,
  History,
  ShieldAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  getClassicArtifacts,
  getClassicDebrief,
  getClassicHistory,
  getClassicResourceUrl,
  selectClassicAttempt,
} from "@/lib/classic/api";
import type {
  ClassicArtifact,
  ClassicDebriefView,
  ClassicSessionView,
  HrvPhaseResult,
} from "@/types/classic";

interface DownloadLinks {
  bundle: string;
  visitJson: string;
  visitCsv: string;
  visitMarkdown: string;
  artifacts: Record<string, string>;
}

function reasonMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function valueAt(root: unknown, path: string[]): unknown {
  return path.reduce<unknown>((current, key) => record(current)[key], root);
}

function numeric(root: unknown, ...path: string[]): number | null {
  const value = valueAt(root, path);
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function display(value: number | null, digits = 1): string {
  return value === null ? "—" : value.toFixed(digits).replace(/\.0$/, "");
}

function percentFromRate(value: number | null): number | null {
  if (value === null) return null;
  return value >= 0 && value <= 1 ? value * 100 : value;
}

function displayPercent(value: number | null): string {
  return value === null ? "—" : `${display(value)}%`;
}

function bytes(value: number): string {
  if (value < 1_024) return `${value} B`;
  if (value < 1_048_576) return `${(value / 1_024).toFixed(1)} KB`;
  return `${(value / 1_048_576).toFixed(1)} MB`;
}

function phaseMetric(
  phase: HrvPhaseResult | undefined,
  section: "time_domain" | "frequency_domain",
  key: string,
): number | null {
  const value = phase?.[section]?.metrics?.[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function phaseGateReasons(phase: HrvPhaseResult | undefined): string {
  const reasons = new Set<string>();
  for (const section of [phase?.time_domain, phase?.frequency_domain]) {
    for (const reason of section?.reason_codes ?? []) reasons.add(reason);
    if (section?.reason_code) reasons.add(section.reason_code);
  }
  return [...reasons].join(" · ") || "—";
}

export function ClassicDebrief({ sessionId }: { sessionId: string }) {
  const [debrief, setDebrief] = useState<ClassicDebriefView | null>(null);
  const [artifacts, setArtifacts] = useState<ClassicArtifact[]>([]);
  const [history, setHistory] = useState<ClassicSessionView[]>([]);
  const [links, setLinks] = useState<DownloadLinks | null>(null);
  const [selectionReason, setSelectionReason] = useState("manual_quality_review");
  const [selecting, setSelecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const [debriefView, artifactRows] = await Promise.all([
          getClassicDebrief(sessionId),
          getClassicArtifacts(sessionId),
        ]);
        const attemptRows = await getClassicHistory(
          debriefView.session.participant_id,
          debriefView.session.visit_ordinal,
        );
        const [bundle, visitJson, visitCsv, visitMarkdown, artifactPairs] = await Promise.all([
          getClassicResourceUrl("bundle", { sessionId }),
          getClassicResourceUrl("visit", {
            participantId: debriefView.session.participant_id,
            visitOrdinal: debriefView.session.visit_ordinal,
            format: "json",
          }),
          getClassicResourceUrl("visit", {
            participantId: debriefView.session.participant_id,
            visitOrdinal: debriefView.session.visit_ordinal,
            format: "csv",
          }),
          getClassicResourceUrl("visit", {
            participantId: debriefView.session.participant_id,
            visitOrdinal: debriefView.session.visit_ordinal,
            format: "md",
          }),
          Promise.all(artifactRows.map(async (artifact) => [
            artifact.relative_path,
            await getClassicResourceUrl("artifact", {
              sessionId,
              relativePath: artifact.relative_path,
            }),
          ] as const)),
        ]);
        if (!active) return;
        setDebrief(debriefView);
        setArtifacts(artifactRows);
        setHistory(attemptRows);
        setLinks({
          bundle,
          visitJson,
          visitCsv,
          visitMarkdown,
          artifacts: Object.fromEntries(artifactPairs),
        });
      } catch (reason: unknown) {
        if (active) setError(reasonMessage(reason, "Classic MATB debrief could not be loaded."));
      }
    };
    void load();
    return () => { active = false; };
  }, [sessionId]);

  const matbTiles = useMemo(() => {
    const metrics = debrief?.matb_metrics;
    return [
      { label: "Tracking in target", value: displayPercent(numeric(metrics, "tracking", "in_target_pct")) },
      { label: "Resource tolerance", value: displayPercent(numeric(metrics, "resource_management", "combined", "in_tolerance_pct")) },
      { label: "Sysmon hit rate", value: displayPercent(percentFromRate(numeric(metrics, "sysmon", "hit_rate"))) },
      { label: "Comm hit rate", value: displayPercent(percentFromRate(numeric(metrics, "comm", "hit_rate"))) },
      { label: "NASA-TLX mean (0–10)", value: display(numeric(metrics, "nasatlx", "raw_tlx")) },
      { label: "ISA mean", value: display(numeric(metrics, "isa", "mean"), 2) },
    ];
  }, [debrief?.matb_metrics]);

  async function selectAttempt() {
    if (
      !debrief
      || debrief.session.status !== "COMPLETE"
      || debrief.session.task_validity !== "valid"
      || !selectionReason.trim()
    ) return;
    setSelecting(true);
    setError(null);
    try {
      await selectClassicAttempt(sessionId, selectionReason.trim());
      setDebrief({ ...debrief, selected_for_visit: true });
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Attempt selection could not be recorded."));
    } finally {
      setSelecting(false);
    }
  }

  if (!debrief && !error) {
    return <main className="mission-grid grid min-h-screen place-items-center p-8 text-muted-foreground">Loading sealed classic MATB evidence…</main>;
  }

  if (!debrief) {
    return <main className="mission-grid grid min-h-screen place-items-center p-8"><p role="alert" className="border border-danger/40 bg-danger/10 p-4 text-danger">{error}</p></main>;
  }

  const phaseRows = (["baseline", "task", "recovery"] as const).map((name) => ({
    name,
    phase: debrief.hrv.phases?.[name],
  }));

  return (
    <main className="mission-grid min-h-screen p-4 sm:p-7">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="mission-panel flex flex-col gap-5 p-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="page-kicker">Sealed classic MATB evidence</p>
            <h1 className="page-title mt-2">{debrief.session.participant_id} · {debrief.session.workload_level}</h1>
            <p className="mt-3 font-mono text-xs text-muted-foreground">
              Visit {debrief.session.visit_ordinal} · attempt {debrief.session.attempt_number} · {debrief.session.id}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={debrief.session.status === "COMPLETE" ? "success" : "danger"}>
              {debrief.session.status}
            </Badge>
            <Badge variant={debrief.session.task_validity === "valid" ? "success" : "danger"}>
              Task {debrief.session.task_validity}
            </Badge>
            <Badge
              aria-label={`RR signal ${debrief.session.physiology_quality}`}
              variant={debrief.session.physiology_quality === "good" || debrief.session.physiology_quality === "excellent" ? "success" : "warning"}
            >
              RR signal {debrief.session.physiology_quality}
            </Badge>
            <Badge variant={record(debrief.hrv.summary).availability === "fully_computable" ? "success" : "warning"}>
              HRV {String(record(debrief.hrv.summary).availability ?? "availability unknown")}
            </Badge>
            <Badge variant={debrief.selected_for_visit ? "info" : "outline"}>
              {debrief.selected_for_visit ? "Selected" : "Not selected"}
            </Badge>
            {debrief.session.test_mode ? (
              <Badge variant="danger">TEST MODE · {debrief.session.wall_time_scale}× wall time</Badge>
            ) : null}
          </div>
        </header>

        {error ? <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p> : null}
        {debrief.session.failure_reason_code ? (
          <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">
            Terminal reason: <span className="font-mono">{debrief.session.failure_reason_code}</span>
          </p>
        ) : null}

        <section aria-labelledby="matb-outcomes" className="space-y-3">
          <div className="flex items-center gap-2">
            <Activity className="h-4 w-4 text-muted-foreground" />
            <h2 id="matb-outcomes" className="page-kicker">MATB workload and performance outcomes</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
            {matbTiles.map((metric) => (
              <div key={metric.label} className="metric-tile">
                <p className="page-kicker">{metric.label}</p>
                <p className="mt-3 font-display text-3xl tabular-nums">{metric.value}</p>
              </div>
            ))}
          </div>
        </section>

        <section aria-labelledby="hrv-phases" className="data-table-wrap overflow-hidden">
          <div className="flex flex-col gap-2 border-b border-white/10 p-5 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <p className="page-kicker">Phase-scoped physiology</p>
              <h2 id="hrv-phases" className="mt-2 font-display text-2xl uppercase">HRV time and frequency domain</h2>
            </div>
            <p className="max-w-lg text-xs leading-5 text-muted-foreground">Frequency metrics are blank when the prespecified duration, coverage, signal-quality, contact, disconnect, or queue-overflow gates are not met.</p>
          </div>
          <div className="overflow-x-auto">
            <table className="data-table min-w-[68rem]">
              <thead>
                <tr>
                  <th>Phase</th>
                  <th>Quality</th>
                  <th>Coverage</th>
                  <th>RR beats</th>
                  <th>Mean HR</th>
                  <th>RMSSD</th>
                  <th>SDNN</th>
                  <th>LF power</th>
                  <th>HF power</th>
                  <th>LF/HF</th>
                  <th>Gate reasons</th>
                </tr>
              </thead>
              <tbody>
                {phaseRows.map(({ name, phase }) => (
                  <tr key={name}>
                    <td className="font-semibold capitalize">{name}</td>
                    <td><Badge variant={phase?.quality?.label === "good" || phase?.quality?.label === "excellent" ? "success" : "warning"}>{phase?.quality?.label ?? "missing"}</Badge></td>
                    <td className="font-mono">{phase?.coverage_fraction === undefined ? "—" : `${display(phase.coverage_fraction * 100)}%`}</td>
                    <td className="font-mono">{phase?.raw_rr_count ?? "—"}</td>
                    <td className="font-mono">{display(phaseMetric(phase, "time_domain", "mean_hr_bpm"))}</td>
                    <td className="font-mono">{display(phaseMetric(phase, "time_domain", "rmssd_ms"))}</td>
                    <td className="font-mono">{display(phaseMetric(phase, "time_domain", "sdnn_ms"))}</td>
                    <td className="font-mono">{display(phaseMetric(phase, "frequency_domain", "lf_power_ms2"))}</td>
                    <td className="font-mono">{display(phaseMetric(phase, "frequency_domain", "hf_power_ms2"))}</td>
                    <td className="font-mono">{display(phaseMetric(phase, "frequency_domain", "lf_hf_ratio"), 2)}</td>
                    <td className="max-w-xs text-xs text-muted-foreground">{phaseGateReasons(phase)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_26rem]">
          <section aria-labelledby="artifact-inventory" className="mission-panel p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
              <div>
                <p className="page-kicker">Integrity-checked output</p>
                <h2 id="artifact-inventory" className="mt-2 font-display text-2xl uppercase">Artifact inventory</h2>
              </div>
              {links ? (
                <Button asChild>
                  <a href={links.bundle} download>
                    <Download className="mr-2 h-4 w-4" /> Download sealed bundle
                  </a>
                </Button>
              ) : null}
            </div>
            <ul className="mt-5 divide-y divide-white/10 border border-white/10">
              {artifacts.map((artifact) => (
                <li key={artifact.relative_path} className="flex flex-col gap-2 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    {links?.artifacts[artifact.relative_path] ? (
                      <a className="break-all text-sm font-semibold underline-offset-4 hover:underline" href={links.artifacts[artifact.relative_path]} download>
                        {artifact.relative_path}
                      </a>
                    ) : <span className="text-sm">{artifact.relative_path}</span>}
                    <p className="mt-1 truncate font-mono text-[10px] text-muted-foreground">SHA-256 {artifact.sha256}</p>
                  </div>
                  <span className="shrink-0 font-mono text-xs text-muted-foreground">{bytes(artifact.size_bytes)}</span>
                </li>
              ))}
            </ul>
          </section>

          <aside className="space-y-5">
            <section className="mission-panel p-5">
              <p className="page-kicker">Visit-level exports</p>
              <h2 className="mt-2 font-display text-2xl uppercase">All attempts + selection</h2>
              <div className="mt-4 grid gap-2">
                {links ? (
                  <>
                    <Button asChild variant="outline"><a href={links.visitMarkdown} download><FileText className="mr-2 h-4 w-4" /> Visit Markdown</a></Button>
                    <Button asChild variant="outline"><a href={links.visitCsv} download><FileSpreadsheet className="mr-2 h-4 w-4" /> Visit CSV</a></Button>
                    <Button asChild variant="outline"><a href={links.visitJson} download><FileJson2 className="mr-2 h-4 w-4" /> Visit JSON</a></Button>
                  </>
                ) : null}
              </div>
            </section>

            <section className="mission-panel p-5">
              <div className="flex items-center gap-2"><History className="h-4 w-4 text-muted-foreground" /><p className="page-kicker">Retake history</p></div>
              <ol className="mt-4 space-y-2">
                {history.map((attempt) => (
                  <li key={attempt.id} className={`border px-3 py-3 text-xs ${attempt.id === sessionId ? "border-white/40 bg-white/[0.04]" : "border-white/10"}`}>
                    <div className="flex items-center justify-between gap-3"><span className="font-semibold">Attempt {attempt.attempt_number}</span><span className="font-mono">{attempt.status}</span></div>
                    <p className="mt-1 text-muted-foreground">{attempt.workload_level} · task {attempt.task_validity} · physiology {attempt.physiology_quality}</p>
                  </li>
                ))}
              </ol>
              {debrief.selected_for_visit ? (
                <p className="mt-4 flex gap-2 text-sm text-success"><CheckCircle2 className="h-4 w-4 shrink-0" /> This is the selected valid attempt for the visit/workload.</p>
              ) : debrief.session.status === "COMPLETE" && debrief.session.task_validity === "valid" ? (
                <div className="mt-4 space-y-3">
                  <div className="space-y-2">
                    <Label htmlFor="selection-reason">Selection reason code</Label>
                    <Input id="selection-reason" value={selectionReason} onChange={(event) => setSelectionReason(event.target.value)} pattern={"[a-z0-9][a-z0-9_\\-]{0,63}"} />
                  </div>
                  <Button variant="secondary" className="w-full" onClick={selectAttempt} disabled={selecting || !selectionReason.trim()}>
                    {selecting ? "Recording selection…" : "Select this attempt"}
                  </Button>
                </div>
              ) : (
                <p className="mt-4 text-sm text-muted-foreground">
                  Only complete, valid attempts can be selected as the canonical visit result.
                </p>
              )}
            </section>
          </aside>
        </div>

        <div className="flex gap-3 border border-warning/30 bg-warning/5 p-4 text-sm text-warning">
          <ShieldAlert className="h-5 w-5 shrink-0" />
          Research use only. Metrics are descriptive workload and physiology outcomes; they are not medical diagnoses or individual fitness/readiness determinations.
        </div>

        <Link href="/classic/setup" className="inline-flex text-xs font-semibold uppercase tracking-[0.12em] text-muted-foreground underline-offset-4 hover:text-foreground hover:underline">
          Return to classic MATB setup
        </Link>
      </div>
    </main>
  );
}
