"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { FlaskConical } from "lucide-react";

import { StatBadge } from "@/components/analysis/StatBadge";
import { getBayesStatus, runBayes } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import type { BayesJob, BayesModelResult } from "@/types";

const POLL_MS = 2000;

function BayesCard({ title, result }: { title: string; result: BayesModelResult }) {
  return (
    <div className="space-y-2 rounded-lg border border-border p-4">
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">{title}</h4>
        <div className="flex items-center gap-2">
          {result.status === "ok" && result.converged === false && (
            <span className="rounded-full border border-red-500/30 bg-red-500/15 px-2 py-0.5 text-xs font-medium text-red-400">
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
              <tr className="text-left text-muted-foreground">
                <th className="py-1 pr-2">Param</th>
                <th className="py-1 pr-2">mean</th>
                <th className="py-1 pr-2">95% ETI</th>
                <th className="py-1 pr-2">R̂</th>
                <th className="py-1">ESS</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(result.coefs).map(([name, c]) => (
                <tr key={name} className="border-t border-border/40">
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

export function BayesSection() {
  const [job, setJob] = useState<BayesJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (timer.current) { clearInterval(timer.current); timer.current = null; }
  }, []);

  const poll = useCallback(async () => {
    try {
      const s = await getBayesStatus();
      setJob(s);
      if (!s || s.status === "done" || s.status === "failed") stopPolling();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      stopPolling();
    }
  }, [stopPolling]);

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
        timer.current = setInterval(poll, POLL_MS);
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
          <h3 className="text-sm font-semibold">
            Bayesian sensitivity (Q2/Q4 — PyMC, async)
          </h3>
          <p className="text-xs text-muted-foreground">
            Hierarchical NUTS re-fit with pre-specified priors; separate artifact.
          </p>
        </div>
        <button
          onClick={onRun}
          disabled={running}
          className="inline-flex items-center gap-2 rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent disabled:opacity-50"
        >
          <FlaskConical className="h-4 w-4" />
          {running ? `Job ${job?.status}…` : "Run Bayesian sensitivity"}
        </button>
      </div>

      {error && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          {error}
        </p>
      )}
      {job?.status === "failed" && (
        <p className="rounded-md border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-400">
          Job failed: {job.error}
        </p>
      )}
      {!job && !error && (
        <p className="text-sm text-muted-foreground">No Bayesian job yet.</p>
      )}

      {art && (
        <div className="space-y-4">
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
