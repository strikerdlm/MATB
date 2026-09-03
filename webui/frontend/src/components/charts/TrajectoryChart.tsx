"use client";

import { ScientificChart } from "@/components/charts/EChart";
import { buildTrajectoryOption } from "@/lib/figures";
import { type Trajectory } from "@/lib/viz";
import { useAppLocale } from "@/lib/i18n";

export function TrajectoryChart({ data, metric, kind = "line" }: {
  data: Trajectory; metric: string; kind?: "line" | "bar";
}) {
  const { copy } = useAppLocale();
  return (
    <ScientificChart
      figureId={kind === "bar" ? copy("Perfil de carga del participante", "Participant Workload Profile") : copy("Trayectoria del participante", "Participant Trajectory")}
      exportName={`${metric}-${kind === "bar" ? "workload-profile" : "participant-trajectory"}`}
      option={buildTrajectoryOption(data, metric, kind)}
      caption={copy("Valores métricos observados por participante durante las seis visitas planificadas, estratificados por nivel de carga MATB.", "Per-participant observed metric values across the six planned visits, stratified by MATB workload level.")}
    />
  );
}
