"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { PageHeader } from "@/components/layout/PageHeader";
import { StudyAssignment } from "@/components/participants/StudyAssignment";
import { ParticipantTable } from "@/components/participants/ParticipantTable";
import { AddParticipantDialog } from "@/components/participants/AddParticipantDialog";
import { useAppLocale } from "@/lib/i18n";

export default function ParticipantsPage() {
  const { copy } = useAppLocale();
  const { participants, tracker, refreshAll, error } = useConsole();
  const visitCount = new Set(tracker.map((cell) => cell.visit_ordinal)).size;
  useEffect(() => { void refreshAll(); }, [refreshAll]);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Manifiesto de participantes", "Crew manifest")}
        title={copy("Participantes", "Participants")}
        description={copy("Registro seudonimizado con el estado de preparación de las celdas de visita.", "Pseudonymized enrollment roster with visit-cell readiness.")}
        actions={<AddParticipantDialog onCreated={() => void refreshAll()} />}
        stats={[
          { label: copy("Participantes", "Crew"), value: participants.length },
          { label: copy("Visitas", "Visits"), value: String(visitCount).padStart(2, "0") },
          { label: copy("Celdas", "Cells"), value: tracker.filter((cell) => cell.present).length },
        ]}
      />
      {error && <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">{error}</p>}
      <StudyAssignment participants={participants} />
      <ParticipantTable participants={participants} tracker={tracker} />
    </div>
  );
}
