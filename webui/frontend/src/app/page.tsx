"use client";

import { useEffect, useState } from "react";
import { useConsole } from "@/lib/store";
import { CompletenessGrid } from "@/components/tracker/CompletenessGrid";
import { CellDetailDialog } from "@/components/tracker/CellDetailDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { summarize } from "@/lib/tracker";
import type { TrackerCell } from "@/types";

export default function TrackerPage() {
  const { tracker, liftoffTracker, componentIds, refreshTracker, error } = useConsole();
  const [selected, setSelected] = useState<TrackerCell | null>(null);
  const summary = summarize(tracker);
  const visitCount = new Set(tracker.map((cell) => cell.visit_ordinal)).size;
  const liftoffEnabled = componentIds.includes("matb-liftoff");

  useEffect(() => { void refreshTracker(); }, [refreshTracker]);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Mission grid"
        title="Study Completeness"
        description={liftoffEnabled
          ? "Protocol visits across OpenMATB workload regimes and the manual FPV instrument."
          : "Protocol visits across OpenMATB workload regimes."}
        stats={[
          { label: "Cells", value: `${summary.filled}/${summary.total || 0}` },
          { label: "Visits", value: String(visitCount).padStart(2, "0") },
          { label: "Levels", value: "03" },
        ]}
      />
      {error && <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">Failed to load: {error}</p>}
      <CompletenessGrid
        cells={tracker}
        liftoffCells={liftoffTracker}
        showLiftoff={liftoffEnabled}
        onCellClick={setSelected}
      />
      <CellDetailDialog cell={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
