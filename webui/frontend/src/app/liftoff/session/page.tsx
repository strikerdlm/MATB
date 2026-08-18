"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { LiftoffSessionConsole } from "@/components/liftoff/LiftoffSessionConsole";

function SessionContent() {
  const sessionId = useSearchParams().get("session");
  if (!sessionId) return <main className="grid min-h-screen place-items-center p-8 text-danger">Session identifier is missing.</main>;
  return <main className="min-h-screen bg-background p-5 sm:p-8"><div className="mx-auto max-w-6xl"><LiftoffSessionConsole sessionId={sessionId} /></div></main>;
}

export default function LiftoffSessionPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center">Loading Liftoff session…</main>}><SessionContent /></Suspense>;
}
