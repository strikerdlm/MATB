"use client";

import { useEffect } from "react";
import { useConsole } from "@/lib/store";
import { PageHeader } from "@/components/layout/PageHeader";
import { UploadForm } from "@/components/upload/UploadForm";
import { useAppLocale } from "@/lib/i18n";

export default function UploadPage() {
  const { copy } = useAppLocale();
  const { participants, refreshParticipants, refreshTracker } = useConsole();
  useEffect(() => { void refreshParticipants(); }, [refreshParticipants]);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Enlace de datos", "Data uplink")}
        title={copy("Incorporar sesión", "Ingest Session")}
        description={copy("Vincule un bloque de OpenMATB con los metadatos de participante, visita y carga de trabajo.", "Attach an OpenMATB block to crew, visit, and workload metadata.")}
        stats={[
          { label: copy("Participantes", "Crew"), value: participants.length },
          { label: copy("Plan de visitas", "Visit plan"), value: copy("Activo", "Active") },
          { label: copy("Formato", "Format"), value: "CSV" },
        ]}
      />
      <UploadForm participants={participants} onIngested={() => void refreshTracker()} />
    </div>
  );
}
