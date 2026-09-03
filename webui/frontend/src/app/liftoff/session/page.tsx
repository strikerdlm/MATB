"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { LiftoffSessionConsole } from "@/components/liftoff/LiftoffSessionConsole";
import { useAppLocale } from "@/lib/i18n";

function SessionContent() {
  const { copy } = useAppLocale();
  const sessionId = useSearchParams().get("session");
  if (!sessionId) return <main className="grid min-h-screen place-items-center p-8 text-danger">{copy("Falta el identificador de la sesión.", "Session identifier is missing.")}</main>;
  return <main className="min-h-screen bg-background p-5 sm:p-8"><div className="mx-auto max-w-6xl"><LiftoffSessionConsole sessionId={sessionId} /></div></main>;
}

export default function LiftoffSessionPage() {
  const { copy } = useAppLocale();
  return <Suspense fallback={<main className="grid min-h-screen place-items-center">{copy("Cargando la sesión de Liftoff…", "Loading Liftoff session…")}</main>}><SessionContent /></Suspense>;
}
