"use client";

import type { Participant, TrackerCell } from "@/types";
import { byParticipant } from "@/lib/tracker";
import { useAppLocale } from "@/lib/i18n";
import { useState } from "react";
import { astraCall } from "@/lib/astra";
import { Button } from "@/components/ui/button";

export function ParticipantTable({ participants, tracker, onRemoved }: { participants: Participant[]; tracker: TrackerCell[]; onRemoved?: () => void }) {
  const { copy } = useAppLocale();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  async function remove(id: string) {
    setBusy(id); setError("");
    try { await astraCall(`/participants/${encodeURIComponent(id)}`, undefined, "DELETE"); onRemoved?.(); }
    catch (reason) { setError((reason as Error).message); }
    finally { setBusy(null); }
  }
  const rows = byParticipant(tracker);
  const doneById = new Map(rows.map((r) => [r.participantId, `${r.filled}/${r.total}`]));

  if (participants.length === 0)
    return <p className="rounded-[6px] border border-dashed border-white/15 px-4 py-8 text-center text-sm text-muted-foreground">{copy("Aún no hay participantes. Agregue uno para generar las visitas del protocolo activo.", "No participants yet. Add one to generate the active protocol visits.")}</p>;

  return (
    <div className="data-table-wrap overflow-x-auto">
      {error && <p role="alert" className="p-3 text-danger">{error}</p>}
      <table className="data-table">
        <thead>
          <tr><th className="px-4 py-2">ID</th><th className="px-4 py-2">{copy("Incluido", "Enrolled")}</th><th className="px-4 py-2">{copy("Sexo", "Sex")}</th><th className="px-4 py-2">{copy("Grupo de edad", "Age band")}</th><th className="px-4 py-2 text-right">{copy("Celdas completas", "Cells done")}</th>{onRemoved && <th className="px-4 py-2">{copy("Acciones", "Actions")}</th>}</tr>
        </thead>
        <tbody>
          {participants.map((p) => (
            <tr key={p.id}>
              <td className="px-4 py-2"><span className="font-semibold">{p.callsign ?? p.id}</span>{p.callsign && <span className="block text-xs text-muted-foreground">{p.id} · {p.mission}</span>}</td>
              <td className="px-4 py-2">{p.enrollment_date}</td>
              <td className="px-4 py-2">{p.sex || "—"}</td>
              <td className="px-4 py-2">{p.age_band || "—"}</td>
              <td className="px-4 py-2 text-right tabular-nums">{doneById.get(p.id) ?? "0/0"}</td>
              {onRemoved && <td className="px-4 py-2"><Button variant="ghost" disabled={busy !== null} onClick={() => void remove(p.id)}>{copy("Retirar", "Remove")}</Button></td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
