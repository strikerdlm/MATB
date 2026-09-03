"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { LiftoffDebrief } from "@/components/liftoff/LiftoffDebrief";
import { useAppLocale } from "@/lib/i18n";

function DebriefContent() {
  const { copy } = useAppLocale();
  const sessionId = useSearchParams().get("session");
  if (!sessionId) return <main className="grid min-h-screen place-items-center p-8 text-danger">{copy("Falta el identificador de la sesión.", "Session identifier is missing.")}</main>;
  return <main className="min-h-screen bg-background p-5 sm:p-8"><div className="mx-auto max-w-4xl"><LiftoffDebrief sessionId={sessionId} /></div></main>;
}

export default function LiftoffDebriefPage() {
  const { copy } = useAppLocale();
  return <Suspense fallback={<main className="grid min-h-screen place-items-center">{copy("Cargando el informe de Liftoff…", "Loading Liftoff debrief…")}</main>}><DebriefContent /></Suspense>;
}
