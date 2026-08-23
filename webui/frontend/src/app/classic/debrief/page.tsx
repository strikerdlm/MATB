"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

import { ClassicDebrief } from "@/components/classic/ClassicDebrief";

function DebriefContent() {
  const sessionId = useSearchParams().get("session");
  if (!sessionId) {
    return <main className="mission-grid grid min-h-screen place-items-center p-8 text-danger">Session identifier is missing.</main>;
  }
  return <ClassicDebrief sessionId={sessionId} />;
}

export default function ClassicDebriefPage() {
  return (
    <Suspense fallback={<main className="mission-grid grid min-h-screen place-items-center text-muted-foreground">Loading classic MATB debrief…</main>}>
      <DebriefContent />
    </Suspense>
  );
}
