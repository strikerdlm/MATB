"use client";

import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { useEffect, useState } from "react";

import { TechnicalTestForm } from "@/components/mission/setup/TechnicalTestForm";
import { useAppLocale } from "@/lib/i18n";
import { listSimulationScenarios } from "@/lib/simulation/api";
import type { ScenarioSummary } from "@/types/simulation";

export default function TechnicalTestPage() {
  const { tr } = useAppLocale();
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;
    void listSimulationScenarios()
      .then((rows) => { if (mounted) setScenarios(rows); })
      .catch((reason: unknown) => {
        if (mounted) setError(reason instanceof Error ? reason.message : tr("common.error"));
      })
      .finally(() => { if (mounted) setLoading(false); });
    return () => { mounted = false; };
  }, [tr]);

  return <div className="space-y-6"><ExperimentGuide id="suas" /><TechnicalTestForm scenarios={scenarios} loading={loading} loadError={error} /></div>;
}
