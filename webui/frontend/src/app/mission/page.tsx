"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getSimulationSession, getSimulationState } from "@/lib/simulation/api";
import { MissionConsole } from "@/components/mission/MissionConsole";
import type { SessionView, WorldSnapshot } from "@/types/simulation";

function MissionPageContent() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("session");
  const [session, setSession] = useState<SessionView | null>(null);
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) { router.replace("/mission/setup"); return; }
    let mounted = true;
    void getSimulationSession(id).then((value) => {
      if (!mounted) return;
      setSession(value);
      return getSimulationState(id).then((state) => { if (mounted && state.aircraft) setSnapshot(state); }).catch(() => undefined);
    }).catch((reason: unknown) => { if (mounted) setError(reason instanceof Error ? reason.message : "Simulation session unavailable."); });
    return () => { mounted = false; };
  }, [id, router]);

  if (error) return <main className="grid min-h-screen place-items-center p-8"><div role="alert" className="mission-panel max-w-xl p-8 text-danger">{error}</div></main>;
  if (!session) return <main className="grid min-h-screen place-items-center p-8 text-muted-foreground">Loading mission…</main>;
  return <MissionConsole initialSession={session} initialSnapshot={snapshot} onFinished={() => router.push(`/mission/debrief?session=${encodeURIComponent(session.id)}`)} />;
}

export default function MissionPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center p-8 text-muted-foreground">Loading mission…</main>}><MissionPageContent /></Suspense>;
}
