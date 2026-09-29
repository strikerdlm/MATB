"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { abortOpenMatbSession, getActiveOpenMatbSession, readOpenMatbController,
  recoverPendingOpenMatbSession, storeOpenMatbCredentials } from "@/lib/openmatb/api";
import { openMatbErrorMessage } from "@/lib/openmatb/errors";
import type { OpenMatbSession } from "@/types/openmatb";

export function ActiveSessionNotice({ revision = 0, onActiveChange }: { revision?: number; onActiveChange?: (active: boolean) => void }) {
  const { copy } = useAppLocale();
  const router = useRouter();
  const [session, setSession] = useState<OpenMatbSession | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    void getActiveOpenMatbSession().then(value => { if (current) { setSession(value); onActiveChange?.(!!value); } })
      .catch(() => { /* The station check reports connection failures. */ });
    return () => { current = false; };
  }, [revision, onActiveChange]);
  if (!session) return null;
  const pending = ["INSTRUCTIONS", "READY"].includes(session.lifecycle) && !session.started_at && !session.active_pid;
  async function control(close: boolean) {
    if (!session || busy) return;
    setBusy(true); setError("");
    try {
      let lease = readOpenMatbController(session.id);
      if (!lease && pending) {
        const recovered = await recoverPendingOpenMatbSession(session.id);
        storeOpenMatbCredentials(recovered);
        lease = recovered.controller_lease;
      }
      if (close && lease) {
        await abortOpenMatbSession(session.id, lease);
        setSession(null);
        onActiveChange?.(false);
      } else router.push(`/openmatb/session?session=${encodeURIComponent(session.id)}`);
    } catch (reason) { setError(openMatbErrorMessage(reason, copy)); }
    finally { setBusy(false); }
  }
  return <section className="rounded-lg border border-warning/50 bg-warning/10 p-4" aria-label={copy("Sesión pendiente", "Pending session")}>
    <p className="font-semibold">{copy("Esta estación ya tiene una sesión", "This station already has a session")} · {session.participant_id} · {session.visit_code}</p>
    <p className="mt-1 text-sm">{pending ? copy("La tarea todavía no ha comenzado. Puede retomarla o cerrarla para cambiar de participante.", "The task has not started. Resume it or close it to switch participants.") : copy("Continúe desde el control de la sesión actual.", "Continue from the current session controls.")}</p>
    <div className="mt-3 flex flex-wrap gap-3">
      <Button disabled={busy} onClick={() => void control(false)}>{copy("Retomar sesión", "Resume session")}</Button>
      {pending && <Button variant="outline" disabled={busy} onClick={() => void control(true)}>{copy("Cerrar sesión pendiente", "Close pending session")}</Button>}
    </div>
    {error && <p role="alert" className="mt-2 text-danger">{error}</p>}
  </section>;
}
