"use client";

import { ScientificChart } from "@/components/charts/EChart";
import { buildGroupTrajectoryOption } from "@/lib/figures";
import { METRICS, type GroupStats } from "@/lib/viz";
import { useAppLocale } from "@/lib/i18n";

export function GroupChart({ data, metric }: { data: GroupStats; metric: string }) {
  const { copy } = useAppLocale();
  const meta = METRICS[metric];
  return (
    <ScientificChart
      figureId={copy("Trayectoria media de la cohorte", "Cohort Mean Trajectory")}
      exportName={`${metric}-cohort-mean-ci`}
      option={buildGroupTrajectoryOption(data, metric)}
      height={420}
      caption={`${meta?.label ?? metric}: ${copy("trayectoria media de la cohorte con intervalos de confianza del 95% calculados a partir de los participantes disponibles en cada visita y nivel de carga.", "cohort mean trajectory with 95% confidence intervals computed from available participants at each visit and workload level.")}`}
    />
  );
}
