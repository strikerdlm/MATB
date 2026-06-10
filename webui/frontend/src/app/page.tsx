"use client";

import { useEffect, useState } from "react";
import { useConsole } from "@/lib/store";
import { CompletenessGrid } from "@/components/tracker/CompletenessGrid";
import { CellDetailDialog } from "@/components/tracker/CellDetailDialog";
import { PageHeader } from "@/components/layout/PageHeader";
import { summarize } from "@/lib/tracker";
import type { TrackerCell } from "@/types";

export default function TrackerPage() {
  const { tracker, refreshTracker, error } = useConsole();
  const [selected, setSelected] = useState<TrackerCell | null>(null);
  const summary = summarize(tracker);

  useEffect(() => { void refreshTracker(); }, [refreshTracker]);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Mission grid"
        title="Study Completeness"
        description="Twelve crews, six sorties, three workload regimes."
        stats={[
          { label: "Cells", value: `${summary.filled}/${summary.total || 0}` },
          { label: "Visits", value: "06" },
          { label: "Levels", value: "03" },
        ]}
      />
      {error && <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">Failed to load: {error}</p>}
      <CompletenessGrid cells={tracker} onCellClick={setSelected} />
      <CellDetailDialog cell={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
