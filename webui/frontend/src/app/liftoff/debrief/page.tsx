"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { LiftoffDebrief } from "@/components/liftoff/LiftoffDebrief";

function DebriefContent() {
  const sessionId = useSearchParams().get("session");
  if (!sessionId) return <main className="grid min-h-screen place-items-center p-8 text-danger">Session identifier is missing.</main>;
  return <main className="min-h-screen bg-background p-5 sm:p-8"><div className="mx-auto max-w-4xl"><LiftoffDebrief sessionId={sessionId} /></div></main>;
}

export default function LiftoffDebriefPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center">Loading Liftoff debrief…</main>}><DebriefContent /></Suspense>;
}
