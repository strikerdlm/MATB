"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FlaskConical } from "lucide-react";

import { StatBadge } from "@/components/analysis/StatBadge";
import { ScientificChart } from "@/components/charts/EChart";
import { Button } from "@/components/ui/button";
import { getBayesStatus, runBayes } from "@/lib/api";
import { buildBayesForestOption } from "@/lib/figures";
import { fmtNum } from "@/lib/format";
import type { BayesJob, BayesModelResult } from "@/types";

const POLL_MS = 2000;

function BayesCard({ title, result }: { title: string; result: BayesModelResult }) {
  return (
    <div className="mission-panel space-y-2 p-4">
      <div className="flex items-center justify-between">
        <h4 className="font-mono text-xs font-semibold uppercase tracking-[0.12em]">{title}</h4>
        <div className="flex items-center gap-2">
          {result.status === "ok" && result.converged === false && (
            <span className="rounded-[3px] border border-danger/40 bg-danger/10 px-2 py-0.5 font-mono text-[10px] font-semibold uppercase tracking-[0.12em] text-danger">
              not converged
            </span>
          )}
          <StatBadge status={result.status} detail={result.detail} />
        </div>
      </div>
      {result.status === "ok" && result.coefs && (
        <>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
                <th className="py-1 pr-2">Param</th>
                <th className="py-1 pr-2">mean</th>
                <th className="py-1 pr-2">95% ETI</th>
                <th className="py-1 pr-2">R̂</th>
                <th className="py-1">ESS</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.coefs).map(([name, c]) => (
                <tr key={name} className="border-t border-white/10">
                  <td className="py-1 pr-2 font-mono text-xs">{name}</td>
                  <td className="py-1 pr-2">{fmtNum(c.mean)}</td>
                  <td className="py-1 pr-2">
                    [{fmtNum(c.eti95[0])}, {fmtNum(c.eti95[1])}]
                  </td>
                  <td className="py-1 pr-2">{c.r_hat.toFixed(3)}</td>
                  <td className="py-1">{Math.round(c.ess_bulk)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {result.diagnostics && (
            <p className="text-xs text-muted-foreground">
              max R̂ {result.diagnostics.max_r_hat.toFixed(3)} · min ESS{" "}
              {Math.round(result.diagnostics.min_ess_bulk)} · divergences{" "}
              {result.diagnostics.divergences}
            </p>
          )}
        </>
      )}
    </div>
  );
}

const METRIC_LABELS: Record<string, string> = {
  sysmon_d_prime: "SYSMON d′",
  nasatlx_raw_tlx: "NASA-TLX (raw)",
  bedford: "Bedford",
  g0: "G₀", p0: "P₀", tau0: "τ₀",
};

function hasBayesRows(section: Record<string, BayesModelResult>, names: string[]): boolean {
  return Object.values(section).some((result) => (
    result.status === "ok" &&
    result.coefs &&
    names.some((name) => result.coefs?.[name])
  ));
}

export function BayesSection() {
  const [job, setJob] = useState<BayesJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  const pollRef = useRef<() => void>(() => {});

  const stopPolling = useCallback(() => {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
  }, []);

  const poll = useCallback(async () => {
    try {
      const s = await getBayesStatus();
      setJob(s);
      if (!s || s.status === "done" || s.status === "failed") {
        stopPolling();
      } else if (!timer.current) {
        timer.current = setInterval(() => pollRef.current(), POLL_MS);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      stopPolling();
    }
  }, [stopPolling]);

  pollRef.current = poll;

  useEffect(() => {
    poll();
    return stopPolling;
  }, [poll, stopPolling]);

  async function onRun() {
    setError(null);
    try {
      const j = await runBayes();
      setJob(j);
      if (j.status === "queued" || j.status === "running") {
        stopPolling();
        timer.current = setInterval(() => pollRef.current(), POLL_MS);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  const running = job?.status === "queued" || job?.status === "running";
  const art = job?.status === "done" ? job.artifact : undefined;

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">
            Bayesian sensitivity (Q2/Q4 - PyMC, async)
          </h3>
          <p className="text-xs text-muted-foreground">
            Hierarchical NUTS re-fit with pre-specified priors; separate artifact.
          </p>
        </div>
        <Button
          variant="outline"
          onClick={onRun}
          disabled={running}
        >
          <FlaskConical className="h-4 w-4" />
          {running ? `Job ${job?.status}...` : "Run Bayesian sensitivity"}
        </Button>
      </div>

      {error && (
        <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      {job?.status === "failed" && (
        <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">
          Job failed: {job.error}
        </p>
      )}
      {!job && !error && (
        <p className="text-sm text-muted-foreground">No Bayesian job yet.</p>
      )}

      {art && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
            {hasBayesRows(art.q2, ["b_visit", "b_med", "b_high"]) && (
              <ScientificChart
                figureId="Bayesian Q2"
                exportName={`bayes-q2-${art.provenance.fingerprint.slice(0, 12)}`}
                option={buildBayesForestOption(art, "q2")}
                height={420}
                caption="Bayesian sensitivity estimates for Q2. Points show posterior means; intervals show 95% equal-tailed intervals."
              />
            )}
            {hasBayesRows(art.q4, ["b_visit"]) && (
              <ScientificChart
                figureId="Bayesian Q4"
                exportName={`bayes-q4-${art.provenance.fingerprint.slice(0, 12)}`}
                option={buildBayesForestOption(art, "q4")}
                height={360}
                caption="Bayesian sensitivity estimates for exploratory DEPDF parameter drift. Points show posterior means; intervals show 95% equal-tailed intervals."
              />
            )}
          </div>
          <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
            {Object.entries(art.q2).map(([m, r]) => (
              <BayesCard key={m} title={`Q2 · ${METRIC_LABELS[m] ?? m}`} result={r} />
            ))}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            {Object.entries(art.q4).map(([p, r]) => (
              <BayesCard key={p} title={`Q4 · ${METRIC_LABELS[p] ?? p}`} result={r} />
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            Sampler: seed {art.sampler.seed} · {art.sampler.chains} chains ·{" "}
            {art.sampler.draws} draws / {art.sampler.tune} tune · priors:{" "}
            {art.sampler.priors.coefficients}; {art.sampler.priors.sds} ·{" "}
            {Object.entries(art.provenance.libraries).map(([k, v]) => `${k} ${v}`).join(" · ")}
          </p>
        </div>
      )}
    </section>
  );
}
