"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getBlock } from "@/lib/api";
import type { BlockDetail, TrackerCell } from "@/types";
import { useAppLocale } from "@/lib/i18n";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border/50 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{value ?? "—"}</span>
    </div>
  );
}

export function CellDetailDialog({ cell, onClose }: { cell: TrackerCell | null; onClose: () => void }) {
  const { copy } = useAppLocale();
  const [data, setData] = useState<BlockDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (!cell) { setData(null); setErr(null); return; }
    getBlock(cell.participant_id, cell.visit_ordinal, cell.workload_level)
      .then(setData).catch((e) => setErr((e as Error).message));
  }, [cell]);

  const fmt = (n: number | null | undefined, d = 3) =>
    n === null || n === undefined ? "—" : n.toFixed(d);

  return (
    <Dialog open={!!cell} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {cell ? `${cell.participant_id} · ${copy("Visita", "Visit")} ${cell.visit_ordinal} · ${cell.workload_level}` : ""}
          </DialogTitle>
        </DialogHeader>
        {err && <p className="text-sm text-danger">{err}</p>}
        {data && (
          <div className="space-y-3">
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{copy("Desempeño", "Performance")}</h4>
              <Row label="SYSMON d′ (observed)" value={fmt(data.metrics.sysmon?.dprime_observed_v2)} />
              <Row
                label={copy("SYSMON d′ (estimado; exploratorio)", "SYSMON d′ (estimated; exploratory)")}
                value={fmt(data.metrics.sysmon?.dprime_estimated_v1 ?? data.metrics.sysmon?.d_prime)}
              />
              <Row label={copy("Tasa de aciertos", "Hit rate")} value={fmt(data.metrics.sysmon?.hit_rate)} />
              <Row label={copy("Omisiones", "Misses")} value={data.metrics.sysmon?.n_misses} />
              <Row label={copy("TR medio (ms)", "Mean RT (ms)")} value={fmt(data.metrics.sysmon?.mean_rt_ms, 0)} />
              <Row label="COMM d′" value={fmt(data.metrics.comm?.d_prime)} />
              <Row label="TRACK RMSE" value={fmt(data.metrics.track?.rmse_deviation)} />
              <Row label={copy("TRACK tiempo en objetivo (%)", "TRACK time in target (%)")} value={fmt(data.metrics.track?.percent_time_in_target, 1)} />
              <Row label={copy("RESMAN desviación absoluta media", "RESMAN mean absolute deviation")} value={fmt(data.metrics.resman?.mean_absolute_deviation, 1)} />
              <Row label={copy("RESMAN tiempo dentro de tolerancia (%)", "RESMAN time in tolerance (%)")} value={fmt(data.metrics.resman?.percent_time_in_tolerance, 1)} />
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{copy("Carga de trabajo", "Workload")}</h4>
              <Row label="RTLX mean (0–100)" value={fmt(data.metrics.nasatlx?.rtlx_mean_0_100, 1)} />
              <Row
                label={copy("Suma TLX heredada (exploratoria)", "TLX legacy sum (exploratory)")}
                value={fmt(
                  data.metrics.nasatlx?.legacy_subscale_sum_0_60 ?? data.metrics.nasatlx?.raw_tlx,
                  1,
                )}
              />
              <Row label="Bedford" value={data.metrics.bedford?.value} />
              <Row label="ISA (mean)" value={fmt(data.metrics.isa?.mean, 2)} />
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{copy("Ajuste DEPDF (visita)", "DEPDF fit (visit)")}</h4>
              {data.depdf_fit ? (
                <>
                  <Row label="G₀" value={fmt(data.depdf_fit.g0, 2)} />
                  <Row label="P₀" value={fmt(data.depdf_fit.p0, 4)} />
                  <Row label="τ₀" value={fmt(data.depdf_fit.tau0, 2)} />
                  <Row label={copy("Fuente HCF", "HCF source")} value={data.depdf_fit.hcf_source} />
                  <Row label={copy("Fuente MWL", "MWL source")} value={data.depdf_fit.mwl_source} />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{copy("Aún no hay ajuste (requiere los 3 niveles de esta visita).", "No fit yet (needs all 3 levels of this visit).")}</p>
              )}
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">{copy("Procedencia del escenario", "Scenario provenance")}</h4>
              {data.provenance ? (
                <>
                  <Row label={copy("Validación", "Validation")} value={data.provenance.validation_status} />
                  <Row label={copy("Manifiesto", "Manifest")} value={data.provenance.manifest_filename ?? "—"} />
                  <Row
                    label={copy("Hash del manifiesto", "Manifest hash")}
                    value={data.provenance.manifest_hash ? `${data.provenance.manifest_hash.slice(0, 12)}…` : "—"}
                  />
                  {data.provenance.validation_issues.length > 0 && (
                    <div className="mt-2 space-y-1">
                      {data.provenance.validation_issues.slice(0, 4).map((issue) => (
                        <p key={`${issue.code}-${issue.message}`} className="text-xs text-muted-foreground">
                          <span className={issue.severity === "error" ? "text-danger" : "text-warning"}>
                            {issue.code}
                          </span>{" "}
                          {issue.message}
                        </p>
                      ))}
                    </div>
                  )}
                </>
              ) : (
                <p className="text-sm text-muted-foreground">{copy("No se registró procedencia.", "No provenance recorded.")}</p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
