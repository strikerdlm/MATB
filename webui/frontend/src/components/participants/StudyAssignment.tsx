"use client";
import { useEffect, useState } from "react";
import { createStudyContext, getStudyContext } from "@/lib/api";
import { useAppLocale } from "@/lib/i18n";
import type { Participant, StudyParticipantContext } from "@/types";
import { Button } from "@/components/ui/button";

export function StudyAssignment({ participants }: { participants: Participant[] }) {
  const { copy } = useAppLocale();
  const [participant, setParticipant] = useState("");
  const [context, setContext] = useState<StudyParticipantContext | null>(null);
  const [sequence, setSequence] = useState<"MATB_LIFTOFF" | "LIFTOFF_MATB">("MATB_LIFTOFF");
  const [fpv, setFpv] = useState("");
  const [gaming, setGaming] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  useEffect(() => {
    let active = true;
    setContext(null); setError(false);
    if (!participant) return;
    setBusy(true);
    void getStudyContext(participant).then((data) => { if (active) setContext(data); })
      .catch(() => { if (active) setError(true); }).finally(() => { if (active) setBusy(false); });
    return () => { active = false; };
  }, [participant]);
  async function save(event: React.FormEvent) {
    event.preventDefault(); setBusy(true); setError(false);
    try { setContext(await createStudyContext(participant, { task_sequence: sequence, prior_fpv_hours: Number(fpv), gaming_hours_per_week: Number(gaming) })); }
    catch { setError(true); } finally { setBusy(false); }
  }
  return <details className="rounded border border-white/15 p-5">
    <summary className="cursor-pointer font-semibold">{copy("Asignación de protocolo · Investigador", "Protocol assignment · Researcher")}</summary>
    <p className="my-4 text-sm text-muted-foreground">{copy("Registre la secuencia asignada y la experiencia declarada. La asignación queda fija para conservar el protocolo del estudio.", "Record the assigned sequence and reported experience. The assignment is fixed to preserve the study protocol.")}</p>
    <label className="block space-y-2"><span>{copy("Participante", "Participant")}</span><select className="native-select w-full" value={participant} onChange={(event) => setParticipant(event.target.value)}><option value="">—</option>{participants.map((row) => <option key={row.id}>{row.id}</option>)}</select></label>
    {error && <p role="alert" className="mt-3 text-warning">{copy("No se pudo confirmar la asignación. Compruebe la conexión o si ya existe una asignación guardada.", "Could not confirm the assignment. Check the connection or whether an assignment is already saved.")}</p>}
    {context ? <p role="status" className="mt-4">{copy("Asignación guardada", "Assignment saved")}: {context.task_sequence === "MATB_LIFTOFF" ? "MATB → Liftoff" : "Liftoff → MATB"}</p>
      : participant && <form onSubmit={(event) => void save(event)} className="mt-4 grid gap-4 sm:grid-cols-3">
        <label className="space-y-2"><span>{copy("Secuencia asignada", "Assigned sequence")}</span><select className="native-select w-full" value={sequence} onChange={(event) => setSequence(event.target.value as typeof sequence)}><option value="MATB_LIFTOFF">MATB → Liftoff</option><option value="LIFTOFF_MATB">Liftoff → MATB</option></select></label>
        <label className="space-y-2"><span>{copy("Horas previas de vuelo FPV", "Prior FPV flight hours")}</span><input className="native-select w-full" type="number" min={0} step="any" required value={fpv} onChange={(event) => setFpv(event.target.value)} /></label>
        <label className="space-y-2"><span>{copy("Videojuegos · horas/semana", "Gaming · hours/week")}</span><input className="native-select w-full" type="number" min={0} step="any" required value={gaming} onChange={(event) => setGaming(event.target.value)} /></label>
        <Button type="submit" disabled={busy || error}>{busy ? copy("Guardando…", "Saving…") : copy("Guardar asignación", "Save assignment")}</Button>
      </form>}
  </details>;
}
