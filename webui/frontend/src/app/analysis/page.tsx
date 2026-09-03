"use client";

import { useEffect, useState } from "react";
import { Download, Play } from "lucide-react";

import { BayesSection } from "@/components/analysis/BayesSection";
import { FamilyTable } from "@/components/analysis/FamilyTable";
import { LmmCard } from "@/components/analysis/LmmCard";
import { PageHeader } from "@/components/layout/PageHeader";
import { RmcorrTable } from "@/components/analysis/RmcorrTable";
import { Button } from "@/components/ui/button";
import { ScientificChart } from "@/components/charts/EChart";
import { downloadResearchBundle, getResearchContext, runAnalysis } from "@/lib/api";
import { buildLmmForestOption, buildRmcorrForestOption, lmmIntervalRows } from "@/lib/figures";
import type { AnalysisArtifact, FigureOptionExport } from "@/types";
import { useAppLocale } from "@/lib/i18n";

const METRIC_LABELS: Record<string, string> = {
  sysmon_dprime_observed_v2: "SYSMON d′ (observed v2)",
  sysmon_dprime_estimated_v1: "SYSMON d′ (estimated v1)",
  sysmon_d_prime: "SYSMON d′ (legacy alias)",
  sysmon_hit_rate: "SYSMON hit rate",
  sysmon_mean_rt_ms: "SYSMON mean RT (ms)",
  comm_d_prime: "COMM d′",
  nasatlx_rtlx_mean_0_100: "RTLX mean (0–100)",
  nasatlx_legacy_sum_0_60: "NASA-TLX legacy sum (0–60)",
  nasatlx_raw_tlx: "NASA-TLX legacy alias",
  bedford: "Bedford",
  isa_mean: "ISA (mean)",
};
const Q4_LABELS: Record<string, string> = {
  g0: "G₀ (baseline MWL)", p0: "P₀ (baseline nonfailure)", tau0: "τ₀ (baseline MTTF)",
};

function FigureEmptyState({ label }: { label: string }) {
  return (
    <div className="flex min-h-[220px] items-center justify-center rounded-[6px] border border-dashed border-white/15 bg-card/60 px-4 text-center text-sm text-muted-foreground">
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
  const { copy } = useAppLocale();
  const [artifact, setArtifact] = useState<AnalysisArtifact | null>(null);
  const [running, setRunning] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getResearchContext().then((ctx) => setArtifact(ctx.analysis_latest)).catch((e) => setError(String(e)));
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

  async function onExportBundle() {
    if (!artifact) return;
    setExporting(true);
    setError(null);
    try {
      const figures: FigureOptionExport[] = [];
      if (lmmIntervalRows(artifact.q1, "q1").length) {
        figures.push({ name: "q1-workload-effects", option: buildLmmForestOption(artifact.q1, "q1") });
      }
      if (lmmIntervalRows(artifact.q2, "q2").length) {
        figures.push({ name: "q2-visit-slopes", option: buildLmmForestOption(artifact.q2, "q2") });
      }
      if (hasRmcorrRows(artifact)) {
        figures.push({ name: "q3-rmcorr", option: buildRmcorrForestOption(artifact.q3) });
      }
      if (lmmIntervalRows(artifact.q4, "q4").length) {
        figures.push({ name: "q4-depdf-drift", option: buildLmmForestOption(artifact.q4, "q4") });
      }
      const blob = await downloadResearchBundle(figures);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `matb_research_bundle_${artifact.provenance.fingerprint.slice(0, 12)}.zip`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Motor de análisis", "Analysis engine")}
        title={copy("Análisis estadístico", "Statistical Analysis")}
        description={copy("Flujo preespecificado Q1-Q4: LMM, rmcorr, sensibilidad rmANOVA y BH-FDR.", "Pre-specified Q1-Q4 pipeline: LMM, rmcorr, rmANOVA sensitivity, and BH-FDR.")}
        actions={
          <>
          {artifact && (
            <Button
              variant="outline"
              onClick={onExportBundle}
              disabled={exporting}
            >
              <Download className="h-4 w-4" />
              {exporting ? copy("Exportando…", "Exporting...") : copy("Paquete de investigación", "Research bundle")}
            </Button>
          )}
          <Button
            onClick={onRun}
            disabled={running}
          >
            <Play className="h-4 w-4" />
            {running ? copy("Ejecutando…", "Running...") : copy("Ejecutar análisis", "Run analysis")}
          </Button>
          </>
        }
      />

      {error && (
        <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </p>
      )}

      {!artifact && !error && (
        <div className="flex h-48 items-center justify-center rounded-[6px] border border-dashed border-white/15">
          <p className="text-muted-foreground">{copy("Aún no hay análisis: incorpore los datos y luego ejecútelo.", "No analysis yet — ingest data, then run.")}</p>
        </div>
      )}

      {artifact && (
        <div className="space-y-8">
          <section className="space-y-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
              <div className="metric-tile p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{copy("Participantes", "Participants")}</p>
                <p className="mt-1 text-2xl font-semibold">{artifact.provenance.n_participants}</p>
              </div>
              <div className="metric-tile p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{copy("Filas de métricas", "Metric rows")}</p>
                <p className="mt-1 text-2xl font-semibold">{artifact.provenance.n_metric_rows}</p>
              </div>
              <div className="metric-tile p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{copy("Ajustes DEPDF", "DEPDF fits")}</p>
                <p className="mt-1 text-2xl font-semibold">{artifact.provenance.n_fit_rows}</p>
              </div>
              <div className="metric-tile p-4">
                <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{copy("Familia FDR", "FDR family")}</p>
                <p className="mt-1 text-2xl font-semibold">
                  {artifact.confirmatory.family_size_actual}/{artifact.confirmatory.family_size_planned}
                </p>
              </div>
            </div>
            <FamilyTable confirmatory={artifact.confirmatory} />
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q1 — {copy("efectos del nivel de carga (LMM)", "workload-level effects (LMM)")}</h3>
            {lmmIntervalRows(artifact.q1, "q1").length > 0 ? (
              <ScientificChart
                figureId="Figure Q1"
                exportName={`q1-workload-effects-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildLmmForestOption(artifact.q1, "q1")}
                height={lmmHeight(lmmIntervalRows(artifact.q1, "q1").length)}
                caption={copy("Efectos fijos del nivel de carga y contrastes elegibles con corrección de Holm del análisis LMM preespecificado. Las barras muestran intervalos de confianza de Wald del 95%.", "Workload-level fixed effects and eligible Holm-corrected contrasts from the pre-specified LMM analysis. Error bars show 95% Wald confidence intervals.")}
              />
            ) : (
              <FigureEmptyState label={copy("Aún no hay estimaciones de intervalo Q1 calculables.", "No estimable Q1 interval estimates yet.")} />
            )}
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q1).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q2 — {copy("trayectorias entre visitas (LMM)", "trajectories across visits (LMM)")}</h3>
            {lmmIntervalRows(artifact.q2, "q2").length > 0 ? (
              <ScientificChart
                figureId="Figure Q2"
                exportName={`q2-visit-slopes-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildLmmForestOption(artifact.q2, "q2")}
                height={lmmHeight(lmmIntervalRows(artifact.q2, "q2").length)}
                caption={copy("Pendientes comunes de visita ajustadas por nivel del análisis LMM longitudinal preespecificado. Las barras muestran intervalos de confianza de Wald del 95%.", "Level-adjusted common visit slopes from the pre-specified longitudinal LMM analysis. Error bars show 95% Wald confidence intervals.")}
              />
            ) : (
              <FigureEmptyState label={copy("Aún no hay estimaciones de intervalo Q2 calculables.", "No estimable Q2 interval estimates yet.")} />
            )}
            <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
              {Object.entries(artifact.q2).map(([m, r]) => (
                <LmmCard key={m} title={METRIC_LABELS[m] ?? m} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q3 — {copy("asociación de medidas repetidas", "repeated-measures coupling")}</h3>
            {hasRmcorrRows(artifact) ? (
              <ScientificChart
                figureId="Figure Q3"
                exportName={`q3-rmcorr-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildRmcorrForestOption(artifact.q3)}
                height={Math.max(360, Math.min(720, artifact.q3.length * 56 + 120))}
                caption={copy("Correlaciones canónicas de medidas repetidas con estimaciones de sensibilidad ajustadas por nivel cuando están disponibles. Las barras muestran intervalos de confianza del 95% mediante z de Fisher.", "Canonical repeated-measures correlations with level-adjusted sensitivity estimates when available. Error bars show Fisher-z 95% confidence intervals.")}
              />
            ) : (
              <FigureEmptyState label={copy("Aún no hay correlaciones Q3 de medidas repetidas calculables.", "No estimable Q3 repeated-measures correlations yet.")} />
            )}
            <RmcorrTable q3={artifact.q3} />
          </section>

          <section className="space-y-3">
            <h3 className="text-sm font-semibold">Q4 — {copy("deriva de parámetros DEPDF (exploratoria)", "DEPDF parameter drift (exploratory)")}</h3>
            {lmmIntervalRows(artifact.q4, "q4").length > 0 ? (
              <ScientificChart
                figureId="Figure Q4"
                exportName={`q4-depdf-drift-${artifact.provenance.fingerprint.slice(0, 12)}`}
                option={buildLmmForestOption(artifact.q4, "q4")}
                height={lmmHeight(lmmIntervalRows(artifact.q4, "q4").length)}
                caption={copy("Pendientes exploratorias por visita para los parámetros DEPDF ajustados. Las barras muestran intervalos de confianza de Wald del 95%.", "Exploratory visit slopes for fitted DEPDF parameters. Error bars show 95% Wald confidence intervals.")}
              />
            ) : (
              <FigureEmptyState label={copy("Aún no hay estimaciones Q4 calculables de deriva DEPDF.", "No estimable Q4 DEPDF drift estimates yet.")} />
            )}
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              {Object.entries(artifact.q4).map(([param, r]) => (
                <LmmCard key={param} title={Q4_LABELS[param] ?? param} result={r} />
              ))}
            </div>
          </section>

          <section className="space-y-2">
            <h3 className="text-sm font-semibold">{copy("Sensibilidad rmANOVA (descriptiva)", "rmANOVA sensitivity (descriptive)")}</h3>
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

          <footer className="mission-panel space-y-1 p-4 text-xs text-muted-foreground">
            <p>
              Engine v{artifact.engine_version} · fingerprint{" "}
              <span className="font-mono">{artifact.provenance.fingerprint.slice(0, 12)}…</span> ·{" "}
              {artifact.provenance.n_metric_rows} {copy("filas de métricas", "metric rows")} · {artifact.provenance.n_fit_rows}{" "}
              {copy("ajustes", "fits")} · {artifact.provenance.n_participants} {copy("participantes", "participants")} ·{" "}
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
