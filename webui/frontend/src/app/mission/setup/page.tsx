"use client";

import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import React, { useEffect, useState } from "react";
import { listParticipants } from "@/lib/api";
import { listSimulationScenarios } from "@/lib/simulation/api";
import { MissionSetupForm } from "@/components/mission/setup/MissionSetupForm";
import type { Participant } from "@/types";
import type { ScenarioSummary } from "@/types/simulation";
import { useExecutionPurpose } from "@/lib/execution-purpose";
import { useReportExperimentFlow } from "@/lib/experiment-flow";

export default function MissionSetupPage() {
  const purpose = useExecutionPurpose();
  useReportExperimentFlow("suas", "prepare");
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    setLoading(true);
    setError(null);
    void Promise.all([listParticipants(), listSimulationScenarios()])
      .then(([participantRows, scenarioRows]) => {
        if (!mounted) return;
        setParticipants(participantRows);
        setScenarios(scenarioRows);
      })
      .catch((reason: unknown) => {
        if (!mounted) return;
        setError(reason instanceof Error ? reason.message : "Setup data could not be loaded.");
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  return (
    <div className="space-y-6"><ExperimentGuide id="suas" /><MissionSetupForm
      participants={participants}
      scenarios={scenarios}
      loading={loading}
      loadError={error}
      preparationEnabled={purpose === "study"}
    /></div>
  );
}
