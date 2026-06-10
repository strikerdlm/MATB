"use client";

import { byParticipant, summarize, LEVELS } from "@/lib/tracker";
import type { TrackerCell } from "@/types";
import { cn } from "@/lib/utils";

export function CompletenessGrid({
  cells, onCellClick,
}: { cells: TrackerCell[]; onCellClick?: (c: TrackerCell) => void }) {
  const rows = byParticipant(cells);
  const { filled, total } = summarize(cells);
  const pct = total ? Math.round((filled / total) * 100) : 0;

  if (cells.length === 0)
    return <p className="rounded-[6px] border border-dashed border-white/15 px-4 py-8 text-center text-sm text-muted-foreground">No participants enrolled yet.</p>;

  return (
    <div className="space-y-4 animate-telemetry-in">
      <div className="control-surface flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Acquisition status</p>
          <p className="mt-1 text-sm text-muted-foreground">
            <span className="font-mono text-lg text-foreground">{filled}</span> / {total} cells filled
          </p>
        </div>
        <div className="h-2 w-full overflow-hidden rounded-full bg-white/10 sm:w-72">
          <div className="h-full bg-primary transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>
      <div className="data-table-wrap overflow-x-auto">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="bg-white/[0.04] font-mono uppercase tracking-[0.14em] text-muted-foreground">
              <th className="sticky left-0 z-10 bg-[#111214] px-3 py-3 text-left font-medium">Participant</th>
              {Array.from({ length: 6 }, (_, i) => (
                <th key={i} colSpan={3} className="border-l border-white/10 px-2 py-3 text-center font-medium">
                  Visit {i + 1}
                </th>
              ))}
              <th className="border-l border-white/10 px-3 py-3 text-right font-medium">Done</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.participantId} className="border-t border-white/10 transition-colors hover:bg-white/[0.03]">
                <td className="sticky left-0 z-10 bg-background px-3 py-2 font-mono text-[11px] text-foreground">{row.participantId}</td>
                {row.cells.map((c) => (
                  <td key={`${c.visit_ordinal}-${c.workload_level}`}
                      className={cn("border-l border-white/5 p-0", c.workload_level === "LOW" && "border-l-white/15")}>
                    <button
                      type="button"
                      disabled={!c.present}
                      onClick={() => c.present && onCellClick?.(c)}
                      title={`Visit ${c.visit_ordinal} · ${c.workload_level}${c.present ? "" : " (missing)"}`}
                      className={cn(
                        "h-8 w-full transition-all",
                        c.present
                          ? "bg-success/80 shadow-[inset_0_0_0_1px_rgb(255_255_255/0.22)] hover:bg-success"
                          : "bg-white/[0.035] hover:bg-white/[0.06]",
                      )}
                    >
                      <span className="sr-only">{c.workload_level}</span>
                    </button>
                  </td>
                ))}
                <td className="border-l border-white/10 px-3 py-2 text-right font-mono tabular-nums text-muted-foreground">
                  {row.filled}/{row.total}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap items-center gap-4 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 bg-success/80" /> present</span>
        <span className="inline-flex items-center gap-1.5"><span className="h-2.5 w-2.5 bg-white/[0.12]" /> expected</span>
        <span>columns per visit: {LEVELS.join(" / ")}</span>
      </div>
    </div>
  );
}
