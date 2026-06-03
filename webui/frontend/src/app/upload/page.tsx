"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { UploadForm } from "@/components/upload/UploadForm";

export default function UploadPage() {
  const { participants, refreshParticipants, refreshTracker } = useConsole();
  useEffect(() => { void refreshParticipants(); }, [refreshParticipants]);

  return (
    <div className="space-y-6">
      <header>
        <h2 className="text-xl font-semibold tracking-tight">Ingest a session</h2>
        <p className="text-sm text-muted-foreground">Upload an OpenMATB CSV and tag it to a participant / visit / level.</p>
      </header>
      <UploadForm participants={participants} onIngested={() => void refreshTracker()} />
    </div>
  );
}
