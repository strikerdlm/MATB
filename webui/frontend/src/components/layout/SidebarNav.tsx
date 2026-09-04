"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useAppLocale } from "@/lib/i18n";
import { EXPERIMENTS, experimentForRoute } from "@/lib/experiments";
import { cn } from "@/lib/utils";

export function SidebarNav() {
  const { copy } = useAppLocale();
  const path = usePathname() ?? "/";
  const experiment = experimentForRoute(path);
  const [reportedStage, setReportedStage] = useState<{ path: string; stage: number } | null>(null);
  useEffect(() => {
    const changed = (event: Event) => setReportedStage({ path, stage: (event as CustomEvent<number>).detail });
    window.addEventListener("matb-experiment-stage", changed);
    return () => window.removeEventListener("matb-experiment-stage", changed);
  }, [path]);
  const stage = reportedStage?.path === path ? reportedStage.stage : path === "/start" ? 0 : path.includes("debrief") ? 4 : path.includes("session") ? 3 : 1;
  const steps = [copy("Elegir", "Choose"), copy("Preparar", "Prepare"), copy("Instrucciones", "Instructions"), copy("Realizar actividad", "Run activity"), copy("Resultados", "Results")];
  const researcher = [
    ["/", copy("Seguimiento", "Tracker")], ["/participants", copy("Participantes", "Participants")],
    ["/experiments", copy("Diseñador de experimentos", "Experiment designer")], ["/openmatb/settings", copy("Configuración OpenMATB", "OpenMATB settings")],
    ["/upload", copy("Cargar datos", "Upload data")], ["/visualization", copy("Visualización", "Visualization")], ["/analysis", copy("Análisis", "Analysis")],
  ];
  return <nav aria-label={copy("Navegación de experimentos", "Experiment navigation")} className="p-4">
    <Link href="/start" className="block rounded border border-info/30 px-3 py-3 text-sm font-semibold text-info" aria-current={path === "/start" ? "page" : undefined}>{copy("Todos los experimentos", "All experiments")}</Link>
    {experiment && <p className="mt-4 text-sm font-semibold">{copy(...experiment.title)}</p>}
    {(experiment || path === "/start") && <ol className="my-4 flex flex-wrap gap-2 md:block md:space-y-2" aria-label={copy("Pasos del experimento", "Experiment steps")}>
      {steps.map((label, index) => <li key={index} aria-current={index === stage ? "step" : undefined} className={cn("flex items-center gap-3 rounded px-3 py-2 text-sm", index === stage ? "bg-white text-black" : "text-muted-foreground")}><span aria-hidden="true" className="font-mono text-xs">{index + 1}</span>{label}</li>)}
    </ol>}
    <details className="mt-4 border-t border-white/10 pt-4">
      <summary className="cursor-pointer text-sm font-medium">{copy("Cambiar experimento", "Change experiment")}</summary>
      <div className="mt-3 grid gap-1">{EXPERIMENTS.map((item) => <Link key={item.id} href={"/start?experiment=" + item.id} className="rounded px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">{copy(...item.title)}</Link>)}</div>
    </details>
    <details className="mt-4 border-t border-white/10 pt-4">
      <summary className="cursor-pointer text-sm font-medium">{copy("Herramientas del investigador", "Researcher tools")}</summary>
      <div className="mt-3 grid gap-1">{researcher.map(([href, label]) => <Link key={href} href={href} aria-current={path === href ? "page" : undefined} className="rounded px-3 py-2 text-sm text-muted-foreground hover:bg-white/5 hover:text-foreground">{label}</Link>)}</div>
    </details>
  </nav>;
}
