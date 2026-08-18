"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { PageHeader } from "@/components/layout/PageHeader";
import { ParticipantTable } from "@/components/participants/ParticipantTable";
import { AddParticipantDialog } from "@/components/participants/AddParticipantDialog";

export default function ParticipantsPage() {
  const { participants, tracker, refreshAll, error } = useConsole();
  const visitCount = new Set(tracker.map((cell) => cell.visit_ordinal)).size;
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
          { label: "Visits", value: String(visitCount).padStart(2, "0") },
          { label: "Cells", value: tracker.filter((cell) => cell.present).length },
        ]}
      />
      {error && <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">{error}</p>}
      <ParticipantTable participants={participants} tracker={tracker} />
    </div>
  );
}
