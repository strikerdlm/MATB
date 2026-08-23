"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { ClassicSessionConsole } from "@/components/classic/ClassicSessionConsole";

function SessionContent() {
  const sessionId = useSearchParams().get("session");
  if (!sessionId) {
    return <main className="mission-grid grid min-h-screen place-items-center p-8 text-danger">Session identifier is missing.</main>;
  }
  return <ClassicSessionConsole sessionId={sessionId} />;
}

export default function ClassicSessionPage() {
  return (
    <Suspense fallback={<main className="mission-grid grid min-h-screen place-items-center text-muted-foreground">Loading classic MATB session…</main>}>
      <SessionContent />
    </Suspense>
  );
}
