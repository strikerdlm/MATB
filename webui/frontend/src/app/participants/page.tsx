"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { ParticipantTable } from "@/components/participants/ParticipantTable";
import { AddParticipantDialog } from "@/components/participants/AddParticipantDialog";

export default function ParticipantsPage() {
  const { participants, tracker, refreshAll, error } = useConsole();
  useEffect(() => { void refreshAll(); }, [refreshAll]);

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-semibold tracking-tight">Participants</h2>
          <p className="text-sm text-muted-foreground">Pseudonymized IDs only. Creating one generates its 6 visits.</p>
        </div>
        <AddParticipantDialog onCreated={() => void refreshAll()} />
      </header>
      {error && <p className="text-sm text-danger">{error}</p>}
      <ParticipantTable participants={participants} tracker={tracker} />
    </div>
  );
}
