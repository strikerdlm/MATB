"use client";

import { useEffect, useState } from "react";

import { LiftoffSetupForm } from "@/components/liftoff/LiftoffSetupForm";
import { PageHeader } from "@/components/layout/PageHeader";
import { getStudyProtocol, listParticipants } from "@/lib/api";
import type { Participant, StudyProtocol } from "@/types";
import { useAppLocale } from "@/lib/i18n";

export default function LiftoffSetupPage() {
  const { copy } = useAppLocale();
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [protocol, setProtocol] = useState<StudyProtocol | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([listParticipants(), getStudyProtocol()])
      .then(([participantRows, activeProtocol]) => {
        setParticipants(participantRows);
        setProtocol(activeProtocol);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : copy("No se pudo cargar la configuración de Liftoff.", "Liftoff setup could not be loaded.")));
  }, [copy]);

  return (
    <div className="space-y-6">
      <PageHeader kicker={copy("Instrumento ASTRA de control manual", "ASTRA manual-control instrument")} title="Liftoff FPV" description={copy("Fije la condición del simulador comercial, verifique la telemetría y la fisiología, y luego recolecte evidencia basal, de tarea y de recuperación.", "Freeze the commercial simulator condition, verify telemetry and physiology, then collect baseline, task, and recovery evidence.")} />
      {error ? <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p> : null}
      {protocol ? <LiftoffSetupForm participants={participants} protocol={protocol} /> : <p className="text-muted-foreground">{copy("Cargando el protocolo activo…", "Loading active protocol…")}</p>}
    </div>
  );
}
