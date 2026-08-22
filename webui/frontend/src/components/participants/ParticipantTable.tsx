"use client";

import type { Participant, TrackerCell } from "@/types";
import { byParticipant } from "@/lib/tracker";

export function ParticipantTable({ participants, tracker }: { participants: Participant[]; tracker: TrackerCell[] }) {
  const rows = byParticipant(tracker);
  const doneById = new Map(rows.map((r) => [r.participantId, `${r.filled}/${r.total}`]));

  if (participants.length === 0)
    return <p className="rounded-[6px] border border-dashed border-white/15 px-4 py-8 text-center text-sm text-muted-foreground">No participants yet. Add one to generate the active protocol visits.</p>;

  return (
    <div className="data-table-wrap overflow-x-auto">
      <table className="data-table">
        <thead>
          <tr><th className="px-4 py-2">ID</th><th className="px-4 py-2">Enrolled</th><th className="px-4 py-2">Sex</th><th className="px-4 py-2">Age band</th><th className="px-4 py-2 text-right">Cells done</th></tr>
        </thead>
        <tbody>
          {participants.map((p) => (
            <tr key={p.id}>
              <td className="px-4 py-2 font-mono">{p.id}</td>
              <td className="px-4 py-2">{p.enrollment_date}</td>
              <td className="px-4 py-2">{p.sex || "—"}</td>
              <td className="px-4 py-2">{p.age_band || "—"}</td>
              <td className="px-4 py-2 text-right tabular-nums">{doneById.get(p.id) ?? "0/0"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
