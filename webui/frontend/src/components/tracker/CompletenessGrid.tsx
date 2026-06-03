"use client";

import { byParticipant, summarize, LEVELS } from "@/lib/tracker";
import type { TrackerCell } from "@/types";
import { cn } from "@/lib/utils";

export function CompletenessGrid({
  cells, onCellClick,
}: { cells: TrackerCell[]; onCellClick?: (c: TrackerCell) => void }) {
  const rows = byParticipant(cells);
  const { filled, total } = summarize(cells);

  if (cells.length === 0)
    return <p className="text-sm text-muted-foreground">No participants enrolled yet.</p>;

  return (
    <div className="space-y-4">
      <div className="text-sm text-muted-foreground">
        <span className="font-semibold text-foreground">{filled}</span> / {total} cells filled
      </div>
      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-card">
              <th className="sticky left-0 z-10 bg-card px-3 py-2 text-left font-medium">Participant</th>
              {Array.from({ length: 6 }, (_, i) => (
                <th key={i} colSpan={3} className="border-l border-border px-2 py-2 text-center font-medium">
                  Visit {i + 1}
                </th>
              ))}
              <th className="border-l border-border px-3 py-2 text-right font-medium">Done</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.participantId} className="border-t border-border">
                <td className="sticky left-0 z-10 bg-background px-3 py-2 font-mono">{row.participantId}</td>
                {row.cells.map((c) => (
                  <td key={`${c.visit_ordinal}-${c.workload_level}`}
                      className={cn("border-l border-border/50 p-0", c.workload_level === "LOW" && "border-l-border")}>
                    <button
                      type="button"
                      disabled={!c.present}
                      onClick={() => c.present && onCellClick?.(c)}
                      title={`Visit ${c.visit_ordinal} · ${c.workload_level}${c.present ? "" : " (missing)"}`}
                      className={cn(
                        "h-7 w-full transition-colors",
                        c.present ? "bg-success/80 hover:bg-success" : "bg-muted/40",
                      )}
                    >
                      <span className="sr-only">{c.workload_level}</span>
                    </button>
                  </td>
                ))}
                <td className="border-l border-border px-3 py-2 text-right tabular-nums">
                  {row.filled}/{row.total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-success/80" /> present</span>
        <span className="inline-flex items-center gap-1"><span className="h-3 w-3 rounded-sm bg-muted/40" /> expected, missing</span>
        <span>columns per visit: {LEVELS.join(" · ")}</span>
      </div>
    </div>
  );
}
