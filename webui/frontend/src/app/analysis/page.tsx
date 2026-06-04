"use client";

import { useEffect, useState } from "react";
import { Play } from "lucide-react";

import { BayesSection } from "@/components/analysis/BayesSection";
import { FamilyTable } from "@/components/analysis/FamilyTable";
import { LmmCard } from "@/components/analysis/LmmCard";
import { RmcorrTable } from "@/components/analysis/RmcorrTable";
import { getLatestAnalysis, runAnalysis } from "@/lib/api";
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
          <FamilyTable confirmatory={artifact.confirmatory} />

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q1 — workload-level effects (LMM)</h3>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q1).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q2 — trajectories across visits (LMM)</h3>
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q2).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <RmcorrTable q3={artifact.q3} />

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q4 — DEPDF parameter drift (exploratory)</h3>
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
