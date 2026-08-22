"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { PageHeader } from "@/components/layout/PageHeader";
import { UploadForm } from "@/components/upload/UploadForm";

export default function UploadPage() {
  const { participants, refreshParticipants, refreshTracker } = useConsole();
  useEffect(() => { void refreshParticipants(); }, [refreshParticipants]);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="Data uplink"
        title="Ingest Session"
        description="Attach an OpenMATB block to crew, visit, and workload metadata."
        stats={[
          { label: "Crew", value: participants.length },
          { label: "Visit plan", value: "Active" },
          { label: "Format", value: "CSV" },
        ]}
      />
      <UploadForm participants={participants} onIngested={() => void refreshTracker()} />
    </div>
  );
}
