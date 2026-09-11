"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useAppLocale } from "@/lib/i18n";
import { EXPERIMENTS, experimentForRoute } from "@/lib/experiments";
import { resolveExecutionPurpose, withExecutionPurpose } from "@/lib/execution-purpose";
import { useExperimentFlowProgress, type ExperimentFlowStage } from "@/lib/experiment-flow";
import { isRouteActive, useNavigationRole } from "@/lib/navigation-role";
import { cn } from "@/lib/utils";

export function SidebarNav() {
  const { copy } = useAppLocale();
  const path = usePathname() ?? "/";
  const queryPurpose = resolveExecutionPurpose(useSearchParams());
  const { role } = useNavigationRole();
  const progress = useExperimentFlowProgress();
  const experiment = experimentForRoute(path);
  const purpose = progress && experiment && progress.experimentId === experiment.id ? progress.purpose ?? queryPurpose : queryPurpose;
  const stage = progress && experiment && progress.experimentId === experiment.id ? progress.stage : null;
  const steps: Array<[ExperimentFlowStage, string]> = [
    ["prepare", copy("Preparar", "Prepare")],
    ["instructions", copy("Instrucciones", "Instructions")],
    ["perform", copy("Realizar actividad", "Run activity")],
    ["complete", copy("Completar", "Complete")],
  ];
  const researcher = [
    ["/colombia", copy("Colombia · mapas y tráfico", "Colombia · maps and traffic")],
    ["/tracker", copy("Seguimiento", "Tracker")], ["/participants", copy("Participantes", "Participants")],
    ["/experiments", copy("Diseñador de experimentos", "Experiment designer")], ["/openmatb/settings", copy("Configuración OpenMATB", "OpenMATB settings")],
    ["/upload", copy("Cargar datos", "Upload data")], ["/visualization", copy("Visualización", "Visualization")], ["/analysis", copy("Análisis", "Analysis")],
    ["/evidence", copy("Evidencia científica", "Scientific evidence")],
  ];
  const researcherActive = researcher.some(([href]) => isRouteActive(path, href));
  const catalogHref = purpose ? withExecutionPurpose("/start", purpose) : "/start";
  return <nav aria-label={copy("Navegación de experimentos", "Experiment navigation")} className="p-4">
    <Link href={catalogHref} className="block rounded border border-info/30 px-3 py-3 text-sm font-semibold text-info" aria-current={path === "/start" ? "page" : undefined}>{copy("Todos los experimentos", "All experiments")}</Link>
    {experiment && <p className="mt-4 text-sm font-semibold">{copy(...experiment.title)}</p>}
    {(experiment || path === "/start") && <ol className="my-4 flex flex-wrap gap-2 md:block md:space-y-2" aria-label={copy("Pasos del experimento", "Experiment steps")}>
      {steps.map(([step, label], index) => <li key={step} aria-current={step === stage ? "step" : undefined} className={cn("flex items-center gap-3 rounded px-3 py-2 text-sm", step === stage ? "bg-white text-black" : "text-muted-foreground")}><span aria-hidden="true" className="font-mono text-xs">{index + 1}</span>{label}</li>)}
    </ol>}
    <details className="mt-4 border-t border-white/10 pt-4">
      <summary className="cursor-pointer text-sm font-medium">{copy("Cambiar experimento", "Change experiment")}</summary>
      <div className="mt-3 grid gap-1">{EXPERIMENTS.map((item) => {
        const href = `/start?experiment=${item.id}`;
        return <Link key={item.id} href={purpose ? withExecutionPurpose(href, purpose) : href} className="rounded px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">{copy(...item.title)}</Link>;
      })}</div>
    </details>
    <details open={role === "researcher" || researcherActive} className="mt-4 border-t border-white/10 pt-4">
      <summary className="cursor-pointer text-sm font-medium">{copy("Herramientas del investigador", "Researcher tools")}</summary>
      <Link href="/station" className="block px-3 py-2 text-sm">{copy("Estación y cola", "Station and queue")}</Link>
      <div className="mt-3 grid gap-1">{researcher.map(([href, label]) => {
        const active = isRouteActive(path, href);
        return <Link key={href} href={href} aria-current={active ? "page" : undefined} className={cn("rounded px-3 py-2 text-sm hover:bg-white/5 hover:text-foreground", active ? "bg-white/10 text-foreground" : "text-muted-foreground")}>{label}</Link>;
      })}</div>
    </details>
  </nav>;
}
