"use client";

import { useEffect, useState } from "react";
import { Play } from "lucide-react";

import { BayesSection } from "@/components/analysis/BayesSection";
import { FamilyTable } from "@/components/analysis/FamilyTable";
import { LmmCard } from "@/components/analysis/LmmCard";
import { RmcorrTable } from "@/components/analysis/RmcorrTable";
import { ScientificChart } from "@/components/charts/EChart";
import { getLatestAnalysis, runAnalysis } from "@/lib/api";
import { buildLmmForestOption, buildRmcorrForestOption, lmmIntervalRows } from "@/lib/figures";
import type { AnalysisArtifact } from "@/types";

const METRIC_LABELS: Record<string, string> = {
  sysmon_d_prime: "SYSMON d′",
  sysmon_hit_rate: "SYSMON hit rate",
  sysmon_mean_rt_ms: "SYSMON mean RT (ms)",
  comm_d_prime: "COMM d′",
  nasatlx_raw_tlx: "NASA-TLX (raw)",
  bedford: "Bedford",
  isa_mean: "ISA (mean)",
};
const Q4_LABELS: Record<string, string> = {
  g0: "G₀ (baseline MWL)", p0: "P₀ (baseline nonfailure)", tau0: "τ₀ (baseline MTTF)",
};

function FigureEmptyState({ label }: { label: string }) {
  return (
    <div className="flex min-h-[220px] items-center justify-center rounded-md border border-dashed border-border bg-card/60 px-4 text-center text-sm text-muted-foreground">
      {label}
    </div>
  );
}

function lmmHeight(rows: number): number {
  return Math.max(360, Math.min(720, rows * 28 + 130));
}

function hasRmcorrRows(artifact: AnalysisArtifact): boolean {
  return artifact.q3.some((row) => (
    row.canonical.status === "ok" &&
    row.canonical.r != null &&
    row.canonical.ci95 != null
  ));
}

export default function AnalysisPage() {
  const [artifact, setArtifact] = useState<AnalysisArtifact | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getLatestAnalysis().then(setArtifact).catch((e) => setError(String(e)));
  }, []);

  async function onRun() {
    setRunning(true);
    setError(null);
    try {
      setArtifact(await runAnalysis());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold">Statistical analysis</h2>
          <p className="text-sm text-muted-foreground">
            Pre-specified engine (Q1–Q4) — LMM, rmcorr, rmANOVA sensitivity, BH-FDR.
          </p>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
        >
          <Play className="h-4 w-4" />
          {running ? "Running…" : "Run analysis"}
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </p>
      )}

      {!artifact && !error && (
        <div className="flex h-48 items-center justify-center rounded-lg border border-dashed border-border">
          <p className="text-muted-foreground">No analysis yet — ingest data, then run.</p>
        </div>
      )}

      {artifact && (
        <div className="space-y-8">
          <section className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <div className="rounded-md border border-border bg-card p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Participants</p>
                <p className="mt-1 text-2xl font-semibold">{artifact.provenance.n_participants}</p>
              </div>
              <div className="rounded-md border border-border bg-card p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Metric rows</p>
                <p className="mt-1 text-2xl font-semibold">{artifact.provenance.n_metric_rows}</p>
              </div>
              <div className="rounded-md border border-border bg-card p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">DEPDF fits</p>
                <p className="mt-1 text-2xl font-semibold">{artifact.provenance.n_fit_rows}</p>
              </div>
              <div className="rounded-md border border-border bg-card p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">FDR family</p>
                <p className="mt-1 text-2xl font-semibold">
                  {artifact.confirmatory.family_size_actual}/{artifact.confirmatory.family_size_planned}
                </p>
              </div>
            </div>
            <FamilyTable confirmatory={artifact.confirmatory} />
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q1 — workload-level effects (LMM)</h3>
            {lmmIntervalRows(artifact.q1, "q1").length > 0 ? (
              <ScientificChart
                figureId="Figure Q1"
                exportName={`q1-workload-effects-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildLmmForestOption(artifact.q1, "q1")}
                height={lmmHeight(lmmIntervalRows(artifact.q1, "q1").length)}
                caption="Workload-level fixed effects and eligible Holm-corrected contrasts from the pre-specified LMM analysis. Error bars show 95% Wald confidence intervals."
              />
            ) : (
              <FigureEmptyState label="No estimable Q1 interval estimates yet." />
            )}
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q1).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q2 — trajectories across visits (LMM)</h3>
            {lmmIntervalRows(artifact.q2, "q2").length > 0 ? (
              <ScientificChart
                figureId="Figure Q2"
                exportName={`q2-visit-slopes-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildLmmForestOption(artifact.q2, "q2")}
                height={lmmHeight(lmmIntervalRows(artifact.q2, "q2").length)}
                caption="Level-adjusted common visit slopes from the pre-specified longitudinal LMM analysis. Error bars show 95% Wald confidence intervals."
              />
            ) : (
              <FigureEmptyState label="No estimable Q2 interval estimates yet." />
            )}
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q2).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q3 — repeated-measures coupling</h3>
            {hasRmcorrRows(artifact) ? (
              <ScientificChart
                figureId="Figure Q3"
                exportName={`q3-rmcorr-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildRmcorrForestOption(artifact.q3)}
                height={Math.max(360, Math.min(720, artifact.q3.length * 56 + 120))}
                caption="Canonical repeated-measures correlations with level-adjusted sensitivity estimates when available. Error bars show Fisher-z 95% confidence intervals."
              />
            ) : (
              <FigureEmptyState label="No estimable Q3 repeated-measures correlations yet." />
            )}
            <RmcorrTable q3={artifact.q3} />
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q4 — DEPDF parameter drift (exploratory)</h3>
            {lmmIntervalRows(artifact.q4, "q4").length > 0 ? (
              <ScientificChart
                figureId="Figure Q4"
                exportName={`q4-depdf-drift-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildLmmForestOption(artifact.q4, "q4")}
                height={lmmHeight(lmmIntervalRows(artifact.q4, "q4").length)}
                caption="Exploratory visit slopes for fitted DEPDF parameters. Error bars show 95% Wald confidence intervals."
              />
            ) : (
              <FigureEmptyState label="No estimable Q4 DEPDF drift estimates yet." />
            )}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {Object.entries(artifact.q4).map(([param, r]) => (
                <LmmCard key={param} title={Q4_LABELS[param] ?? param} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">rmANOVA sensitivity (descriptive)</h3>
            {Object.entries(artifact.rmanova).map(([m, r]) => (
              <p key={m} className="text-sm text-muted-foreground">
                <span className="font-mono text-xs">{METRIC_LABELS[m] ?? m}</span>{" "}
                {r.status === "ok"
                  ? `F(${r.df?.[0]}, ${r.df?.[1]}) = ${r.F?.toFixed(2)}, p = ${
                      r.p != null && r.p < 0.001 ? "<0.001" : r.p?.toFixed(3)
                    }, partial η² = ${r.partial_eta_sq?.toFixed(3)} (n=${r.complete_case_n})`
                  : `${r.status}${r.detail ? ` — ${r.detail}` : ""}`}
              </p>
            ))}
          </section>

          <BayesSection />

          <footer className="space-y-1 rounded-lg border border-border p-4 text-xs text-muted-foreground">
            <p>
              Engine v{artifact.engine_version} · fingerprint{" "}
              <span className="font-mono">{artifact.provenance.fingerprint.slice(0, 12)}…</span> ·{" "}
              {artifact.provenance.n_metric_rows} metric rows · {artifact.provenance.n_fit_rows}{" "}
              fits · {artifact.provenance.n_participants} participants ·{" "}
              {Object.entries(artifact.provenance.libraries)
                .map(([k, v]) => `${k} ${v}`)
                .join(" · ")}
            </p>
            <ul className="list-inside list-disc">
              {artifact.caveats.map((c) => (
                <li key={c}>{c}</li>
              ))}
            </ul>
          </footer>
        </div>
      )}
    </div>
  );
}
