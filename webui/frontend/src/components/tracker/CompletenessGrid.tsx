"use client";

import { byParticipant, summarize, LEVELS } from "@/lib/tracker";
import type { LiftoffTrackerCell, TrackerCell } from "@/types";
import { cn } from "@/lib/utils";

export function CompletenessGrid({
  cells, liftoffCells = [], showLiftoff = false, onCellClick,
}: {
  cells: TrackerCell[];
  liftoffCells?: LiftoffTrackerCell[];
  showLiftoff?: boolean;
  onCellClick?: (c: TrackerCell) => void;
}) {
  const rows = byParticipant(cells);
  const { filled, total } = summarize(cells);
  const pct = total ? Math.round((filled / total) * 100) : 0;

  const visitOrdinals = Array.from(new Set(cells.map((cell) => cell.visit_ordinal))).sort((a, b) => a - b);
  const liftoffByKey = new Map(liftoffCells.map((cell) => [`${cell.participant_id}:${cell.visit_ordinal}`, cell]));

  if (cells.length === 0 && liftoffCells.length === 0)
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
              {visitOrdinals.map((ordinal) => (
                <th key={ordinal} colSpan={showLiftoff ? 4 : 3} className="border-l border-white/10 px-2 py-3 text-center font-medium">
                  Visit {ordinal}
                </th>
              ))}
              <th className="border-l border-white/10 px-3 py-3 text-right font-medium">Done</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.participantId} className="border-t border-white/10 transition-colors hover:bg-white/[0.03]">
                <td className="sticky left-0 z-10 bg-background px-3 py-2 font-mono text-[11px] text-foreground">{row.participantId}</td>
                {visitOrdinals.flatMap((ordinal) => {
                  const workloadCells = row.cells.filter((cell) => cell.visit_ordinal === ordinal);
                  const liftoff = liftoffByKey.get(`${row.participantId}:${ordinal}`);
                  return [
                    ...workloadCells.map((c) => (
                      <td key={`${c.visit_ordinal}-${c.workload_level}`}
                          className={cn("border-l border-white/5 p-0", c.workload_level === "LOW" && "border-l-white/15")}>
                        <button
                          type="button"
                          disabled={!c.present}
                          onClick={() => c.present && onCellClick?.(c)}
                          title={`Visit ${c.visit_ordinal} · ${c.workload_level}${c.present ? "" : " (missing)"}`}
                          className={cn("h-8 w-full transition-all", c.present ? "bg-success/80 hover:bg-success" : "bg-white/[0.035]")}
                        ><span className="sr-only">{c.workload_level}</span></button>
                      </td>
                    )),
                    ...(showLiftoff ? [<td key={`${ordinal}-liftoff`} className="border-l border-white/10 p-0">
                      <div
                        title={`${liftoff?.visit_code ?? `Visit ${ordinal}`} · Liftoff · ${liftoff?.state ?? "absent"}`}
                        className={cn(
                          "grid h-8 place-items-center font-mono text-[9px] uppercase",
                          liftoff?.state === "valid_good_sync" && "bg-success text-black",
                          liftoff?.state === "valid_no_hrv" && "bg-cyan-500/70 text-black",
                          liftoff?.state === "valid_poor_sync" && "bg-warning text-black",
                          liftoff?.state === "partial" && "bg-warning/60 text-black",
                          liftoff?.state === "invalid" && "bg-danger/70 text-white",
                          liftoff?.state === "pending" && "bg-white/25 text-white",
                          (!liftoff || liftoff.state === "absent") && "bg-white/[0.035] text-muted-foreground",
                        )}
                      >FPV</div>
                    </td>] : []),
                  ];
                })}
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
        <span>columns per visit: {LEVELS.join(" / ")}{showLiftoff ? " / FPV" : ""}</span>
      </div>
    </div>
  );
}
