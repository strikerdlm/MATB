"use client";

import { useEffect, useState } from "react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { getBlock } from "@/lib/api";
import type { BlockDetail, TrackerCell } from "@/types";

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border/50 py-1.5 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-mono tabular-nums">{value ?? "—"}</span>
    </div>
  );
}

export function CellDetailDialog({ cell, onClose }: { cell: TrackerCell | null; onClose: () => void }) {
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
            {cell ? `${cell.participant_id} · Visit ${cell.visit_ordinal} · ${cell.workload_level}` : ""}
          </DialogTitle>
        </DialogHeader>
        {err && <p className="text-sm text-danger">{err}</p>}
        {data && (
          <div className="space-y-3">
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Performance</h4>
              <Row label="SYSMON d′" value={fmt(data.metrics.sysmon?.d_prime)} />
              <Row label="Hit rate" value={fmt(data.metrics.sysmon?.hit_rate)} />
              <Row label="Misses" value={data.metrics.sysmon?.n_misses} />
              <Row label="Mean RT (ms)" value={fmt(data.metrics.sysmon?.mean_rt_ms, 0)} />
              <Row label="COMM d′" value={fmt(data.metrics.comm?.d_prime)} />
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">Workload</h4>
              <Row label="NASA-TLX (raw)" value={fmt(data.metrics.nasatlx?.raw_tlx, 1)} />
              <Row label="Bedford" value={data.metrics.bedford?.value} />
              <Row label="ISA (mean)" value={fmt(data.metrics.isa?.mean, 2)} />
            </div>
            <div>
              <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">DEPDF fit (visit)</h4>
              {data.depdf_fit ? (
                <>
                  <Row label="G₀" value={fmt(data.depdf_fit.g0, 2)} />
                  <Row label="P₀" value={fmt(data.depdf_fit.p0, 4)} />
                  <Row label="τ₀" value={fmt(data.depdf_fit.tau0, 2)} />
                  <Row label="HCF source" value={data.depdf_fit.hcf_source} />
                  <Row label="MWL source" value={data.depdf_fit.mwl_source} />
                </>
              ) : (
                <p className="text-sm text-muted-foreground">No fit yet (needs all 3 levels of this visit).</p>
              )}
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
