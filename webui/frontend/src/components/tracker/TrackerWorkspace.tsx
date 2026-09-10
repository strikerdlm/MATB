"use client";

import { useEffect, useState } from "react";
import { useConsole } from "@/lib/store";
import { CompletenessGrid } from "@/components/tracker/CompletenessGrid";
import { CellDetailDialog } from "@/components/tracker/CellDetailDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { summarize } from "@/lib/tracker";
import type { TrackerCell } from "@/types";
import { useAppLocale } from "@/lib/i18n";

export function TrackerWorkspace() {
  const { copy } = useAppLocale();
  const { tracker, liftoffTracker, componentIds, refreshTracker, error } = useConsole();
  const [selected, setSelected] = useState<TrackerCell | null>(null);
  const summary = summarize(tracker);
  const visitCount = new Set(tracker.map((cell) => cell.visit_ordinal)).size;
  const liftoffEnabled = componentIds.includes("matb-liftoff");

  useEffect(() => { void refreshTracker(); }, [refreshTracker]);

  return <div className="space-y-6">
    <PageHeader
      kicker={copy("Matriz de misión", "Mission grid")}
      title={copy("Completitud del estudio", "Study completeness")}
      description={liftoffEnabled
        ? copy("Visitas del protocolo en los regímenes de carga de OpenMATB y el instrumento FPV manual.", "Protocol visits across OpenMATB workload regimes and the manual FPV instrument.")
        : copy("Visitas del protocolo en los regímenes de carga de OpenMATB.", "Protocol visits across OpenMATB workload regimes.")}
      stats={[
        { label: copy("Celdas", "Cells"), value: `${summary.filled}/${summary.total || 0}` },
        { label: copy("Visitas", "Visits"), value: String(visitCount).padStart(2, "0") },
        { label: copy("Niveles", "Levels"), value: "03" },
      ]}
    />
    {error && <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">{copy("Error al cargar", "Failed to load")}: {error}</p>}
    <CompletenessGrid cells={tracker} liftoffCells={liftoffTracker} showLiftoff={liftoffEnabled} onCellClick={setSelected} />
    <CellDetailDialog cell={selected} onClose={() => setSelected(null)} />
  </div>;
}
