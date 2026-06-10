"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { PageHeader } from "@/components/layout/PageHeader";
import { ParticipantTable } from "@/components/participants/ParticipantTable";
import { AddParticipantDialog } from "@/components/participants/AddParticipantDialog";

export default function ParticipantsPage() {
  const { participants, tracker, refreshAll, error } = useConsole();
  useEffect(() => { void refreshAll(); }, [refreshAll]);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Crew manifest"
        title="Participants"
        description="Pseudonymized enrollment roster with visit-cell readiness."
        actions={<AddParticipantDialog onCreated={() => void refreshAll()} />}
        stats={[
          { label: "Crew", value: participants.length },
          { label: "Visits", value: "06" },
          { label: "Cells", value: tracker.filter((cell) => cell.present).length },
        ]}
      />
      {error && <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">{error}</p>}
      <ParticipantTable participants={participants} tracker={tracker} />
    </div>
  );
}
