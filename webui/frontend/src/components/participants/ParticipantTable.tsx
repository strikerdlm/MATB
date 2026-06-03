"use client";

import type { Participant, TrackerCell } from "@/types";
import { byParticipant } from "@/lib/tracker";

export function ParticipantTable({ participants, tracker }: { participants: Participant[]; tracker: TrackerCell[] }) {
  const rows = byParticipant(tracker);
  const doneById = new Map(rows.map((r) => [r.participantId, `${r.filled}/${r.total}`]));

  if (participants.length === 0)
    return <p className="text-sm text-muted-foreground">No participants yet. Add one to generate its 6 visits.</p>;

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <table className="w-full text-sm">
        <thead className="bg-card text-left text-xs uppercase tracking-wide text-muted-foreground">
          <tr><th className="px-4 py-2">ID</th><th className="px-4 py-2">Enrolled</th><th className="px-4 py-2">Sex</th><th className="px-4 py-2">Age band</th><th className="px-4 py-2 text-right">Cells done</th></tr>
        </thead>
        <tbody>
          {participants.map((p) => (
            <tr key={p.id} className="border-t border-border">
              <td className="px-4 py-2 font-mono">{p.id}</td>
              <td className="px-4 py-2">{p.enrollment_date}</td>
              <td className="px-4 py-2">{p.sex || "—"}</td>
              <td className="px-4 py-2">{p.age_band || "—"}</td>
              <td className="px-4 py-2 text-right tabular-nums">{doneById.get(p.id) ?? "0/18"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
