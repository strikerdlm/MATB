"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { getSimulationDebrief } from "@/lib/simulation/api";
import { DebriefScreen } from "@/components/mission/debrief/DebriefScreen";
import type { DebriefView, Locale } from "@/types/simulation";

function DebriefPageContent() {
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("session");
  const [debrief, setDebrief] = useState<DebriefView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!id) { router.replace("/mission/setup"); return; }
    let mounted = true;
    void getSimulationDebrief(id).then((value) => { if (mounted) setDebrief(value); }).catch((reason: unknown) => { if (mounted) setError(reason instanceof Error ? reason.message : "Debrief unavailable."); });
    return () => { mounted = false; };
  }, [id, router]);
  if (error) return <main className="grid min-h-screen place-items-center p-8"><div role="alert" className="mission-panel p-8 text-danger">{error}</div></main>;
  if (!debrief) return <main className="grid min-h-screen place-items-center p-8 text-muted-foreground">Loading debrief…</main>;
  const locale = debrief.locale === "es-CO" ? "es-CO" : "en" as Locale;
  return <DebriefScreen debrief={debrief} locale={locale} />;
}

export default function MissionDebriefPage() { return <Suspense fallback={<main className="grid min-h-screen place-items-center p-8 text-muted-foreground">Loading debrief…</main>}><DebriefPageContent /></Suspense>; }
