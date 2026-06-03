"use client";

import { useEffect, useState } from "react";
import { useConsole } from "@/lib/store";
import { CompletenessGrid } from "@/components/tracker/CompletenessGrid";
import { CellDetailDialog } from "@/components/tracker/CellDetailDialog";
import type { TrackerCell } from "@/types";

export default function TrackerPage() {
  const { tracker, refreshTracker, error } = useConsole();
  const [selected, setSelected] = useState<TrackerCell | null>(null);

  useEffect(() => { void refreshTracker(); }, [refreshTracker]);

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Study completeness</h2>
        <p className="text-sm text-muted-foreground">12 participants × 6 visits × 3 workload levels.</p>
      </header>
      {error && <p className="text-sm text-danger">Failed to load: {error}</p>}
      <CompletenessGrid cells={tracker} onCellClick={setSelected} />
      <CellDetailDialog cell={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
