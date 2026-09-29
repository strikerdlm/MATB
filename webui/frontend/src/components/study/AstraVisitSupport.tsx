"use client";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { astraCall, type AstraRoster, type AstraParticipant } from "@/lib/astra";
import { studyCall, type AssignmentDetail, type StudyPayload } from "@/lib/study";
import { useAppLocale } from "@/lib/i18n";

export function AstraVisitHeader({ detail }: { detail: AssignmentDetail }) {
  const { copy } = useAppLocale();
  const [person, setPerson] = useState<AstraParticipant | null>(null);
  useEffect(() => {
    let active = true;
    void astraCall<AstraRoster>("/astra/roster?include_archived=true").then(roster => {
      if (active) setPerson(roster.participants.find(p => p.id === detail.assignment.participant_id) ?? null);
    }).catch(() => {});
    return () => { active = false; };
  }, [detail.assignment.participant_id]);
  const visit = person?.visits.find(v => v.id === detail.assignment.visit_id);
  return <header>
    <h1 className="text-2xl font-semibold">{person?.callsign ?? detail.assignment.participant_id} · {visit?.code ?? "MATB"}</h1>
    <p className="mt-2 text-muted-foreground">{person?.mission} · {copy("Tres bloques de 15 min. Siga el botón de cada paso.", "Three 15 min blocks. Follow each step's button.")}</p>
  </header>;
}

export function AstraRecovery({ detail, interval, onComplete }: {
  detail: AssignmentDetail;
  interval: StudyPayload["study"]["recovery_intervals"][number];
  onComplete: () => Promise<void>;
}) {
  const { copy } = useAppLocale();
  const recorded = detail.recovery_intervals?.find(item => item.interval_key === interval.key);
  const [started, setStarted] = useState(recorded?.started_at ?? null);
  const [actor, setActor] = useState(detail.version.actor);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);
  // SQLite may return UTC without a suffix. Keep the station countdown in UTC.
  const startedMs = started ? Date.parse(/[Zz]|[+-]\d{2}:\d{2}$/.test(started) ? started : `${started}Z`) : null;
  const remaining = startedMs === null ? interval.duration_seconds : Math.max(0, interval.duration_seconds - Math.floor((now - startedMs) / 1000));
  async function advance() {
    setBusy(true); setError("");
    try {
      const path = `/assignments/${detail.assignment.id}/recovery/${interval.key}`;
      if (!started) {
        const anchors = detail.attempts[interval.anchor_key]?.filter(a => a.acquisition_state === "finished") ?? [];
        if (anchors.length !== 1) throw new Error(copy("Revise los intentos de las valoraciones antes de iniciar la pausa.", "Review the rating attempts before starting the break."));
        const result = await studyCall<{ started_at: string }>(`${path}/start?anchor_attempt_id=${encodeURIComponent(anchors[0].id)}`, { actor: actor.trim(), reason: "Inicio de pausa ASTRA entre bloques" });
        setStarted(result.started_at); setNow(Date.now());
      } else {
        await studyCall(`${path}/finish`, { actor: actor.trim(), reason: "Fin de pausa ASTRA entre bloques" });
        await onComplete();
      }
    } catch (reason) { setError((reason as Error).message); }
    finally { setBusy(false); }
  }
  return <section className="space-y-4 rounded-lg border p-5">
    <h2 className="text-xl font-semibold">{copy("Pausa entre bloques", "Break between blocks")}</h2>
    <p className="text-4xl tabular-nums" role="timer">{Math.floor(remaining / 60)}:{String(remaining % 60).padStart(2, "0")}</p>
    <label className="block text-sm">{copy("Investigador responsable", "Responsible researcher")}<Input className=" mt-1 block w-full" value={actor} onChange={event => setActor(event.target.value)} /></label>
    <Button disabled={busy || actor.trim().length < 3 || (!!started && remaining > 0)} onClick={() => void advance()}>{started ? copy("Finalizar pausa y continuar", "Finish break and continue") : copy("Iniciar pausa", "Start break")}</Button>
    {error && <p role="alert">{error}</p>}
  </section>;
}
