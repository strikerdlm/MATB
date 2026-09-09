"use client";

import { useEffect, useState } from "react";
import { useConsole } from "@/lib/store";
import { PageHeader } from "@/components/layout/PageHeader";
import { UploadForm } from "@/components/upload/UploadForm";
import { useAppLocale } from "@/lib/i18n";
import { EvidenceUpload } from "@/components/evidence/EvidenceUpload";

export default function UploadPage() {
  const { copy } = useAppLocale();
  const [format, setFormat] = useState("csv");
  const [ready, setReady] = useState(false);
  const { participants, refreshParticipants, refreshTracker } = useConsole();
  useEffect(() => { setReady(true); void refreshParticipants(); }, [refreshParticipants]);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Enlace de datos", "Data uplink")}
        title={copy("Incorporar sesión", "Ingest Session")}
        description={copy("Vincule un bloque de OpenMATB con los metadatos de participante, visita y carga de trabajo.", "Attach an OpenMATB block to crew, visit, and workload metadata.")}
        stats={[
          { label: copy("Participantes", "Crew"), value: participants.length },
          { label: copy("Plan de visitas", "Visit plan"), value: copy("Activo", "Active") },
          { label: copy("Formato", "Format"), value: format === "csv" ? "CSV" : "ScientificEvent v3" },
        ]}
      />
      <label className="block text-sm">{copy("Tipo de registro", "Record type")} <select className="native-select" disabled={!ready} value={format} onChange={e => setFormat(e.target.value)}>
        <option value="csv">{copy("CSV histórico", "Legacy CSV")}</option><option value="evidence">{copy("Evidencia científica v3", "Scientific evidence v3")}</option>
      </select></label>
      {format === "csv" ? <UploadForm participants={participants} onIngested={() => void refreshTracker()} /> : <EvidenceUpload />}
    </div>
  );
}
