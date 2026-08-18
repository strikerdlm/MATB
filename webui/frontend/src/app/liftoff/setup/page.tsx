"use client";

import { useEffect, useState } from "react";

import { LiftoffSetupForm } from "@/components/liftoff/LiftoffSetupForm";
import { PageHeader } from "@/components/layout/PageHeader";
import { getStudyProtocol, listParticipants } from "@/lib/api";
import type { Participant, StudyProtocol } from "@/types";

export default function LiftoffSetupPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [protocol, setProtocol] = useState<StudyProtocol | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([listParticipants(), getStudyProtocol()])
      .then(([participantRows, activeProtocol]) => {
        setParticipants(participantRows);
        setProtocol(activeProtocol);
      })
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Liftoff setup could not be loaded."));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader kicker="ASTRA manual-control instrument" title="Liftoff FPV" description="Freeze the commercial simulator condition, verify telemetry and physiology, then collect baseline, task, and recovery evidence." />
      {error ? <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p> : null}
      {protocol ? <LiftoffSetupForm participants={participants} protocol={protocol} /> : <p className="text-muted-foreground">Loading active protocol…</p>}
    </div>
  );
}
