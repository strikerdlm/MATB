"use client";

import { useEffect, useState } from "react";

import { ClassicSetupConsole } from "@/components/classic/ClassicSetupConsole";
import { PageHeader } from "@/components/layout/PageHeader";
import { getStudyProtocol, listParticipants } from "@/lib/api";
import type { Participant, StudyProtocol } from "@/types";

export default function ClassicSetupPage() {
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [protocol, setProtocol] = useState<StudyProtocol | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void Promise.all([listParticipants(), getStudyProtocol()])
      .then(([participantRows, activeProtocol]) => {
        setParticipants(participantRows);
        setProtocol(activeProtocol);
      })
      .catch((reason: unknown) => setError(
        reason instanceof Error ? reason.message : "Classic MATB setup could not be loaded.",
      ));
  }, []);

  return (
    <div className="space-y-6">
      <PageHeader
        kicker="ASTRA multi-attribute workload instrument"
        title="Classic MATB + Polar H10"
        description="Connect and verify live Polar RR intervals, freeze an allowlisted workload scenario, then collect a synchronized baseline, 15-minute MATB task, and recovery session."
        stats={[
          { label: "Baseline", value: "05m" },
          { label: "Task", value: "15m" },
          { label: "Recovery", value: "05m" },
        ]}
      />
      {error ? <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p> : null}
      {protocol ? (
        <ClassicSetupConsole participants={participants} protocol={protocol} />
      ) : (
        <p className="text-muted-foreground">Loading active protocol and participants…</p>
      )}
    </div>
  );
}
