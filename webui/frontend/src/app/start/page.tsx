"use client";
import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Activity, ArrowRight, Brain, Clock3, Gamepad2, MonitorPlay, Radar } from "lucide-react";
import { ReadinessNote } from "@/components/experiments/ReadinessNote";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { EXPERIMENTS, type ExperimentId, type ExecutionPurpose } from "@/lib/experiments";
import { useConsole } from "@/lib/console-context";
import { resolveExecutionPurpose, withExecutionPurpose } from "@/lib/execution-purpose";

const icons = { openmatb: MonitorPlay, suas: Radar, liftoff: Gamepad2, screen: Brain, pvt: Clock3, physiology: Activity };
export default function StartPage() { return <Suspense><Catalog /></Suspense>; }
function Catalog() {
  const search = useSearchParams();
  const { copy } = useAppLocale();
  const { catalog, status, refresh } = useConsole();
  const [selected, setSelected] = useState<ExperimentId | null>(null);
  const [purpose, setPurpose] = useState<ExecutionPurpose | null>(() => resolveExecutionPurpose(search));
  useEffect(() => {
    const candidate = search.get("experiment");
    setSelected(EXPERIMENTS.some((item) => item.id === candidate) ? candidate as ExperimentId : null);
    setPurpose(resolveExecutionPurpose(search));
  }, [search]);
  const info = EXPERIMENTS.find((item) => item.id === selected);
  const entry = catalog.find((item) => item.id === selected);
  const available = status === "online" && entry?.component_available;
  function choose(id: ExperimentId) {
    setSelected(id);
    const href = purpose
      ? withExecutionPurpose(`/start?experiment=${id}`, purpose)
      : `/start?experiment=${id}`;
    window.history.replaceState(null, "", href);
    requestAnimationFrame(() => document.getElementById("experiment-details")?.focus());
  }
  function choosePurpose(nextPurpose: ExecutionPurpose) {
    setPurpose(nextPurpose);
    window.history.replaceState(null, "", withExecutionPurpose(
      `/start${selected ? `?experiment=${selected}` : ""}`,
      nextPurpose,
    ));
  }
  const destination = selected === "suas" && purpose === "practice" ? "/mission/test" : info?.route;
  return <div className="space-y-7">
    <PageHeader kicker={copy("Comenzar aquí", "Start here")} title={copy("Elija su experimento", "Choose your experiment")}
      description={copy("Explore una actividad, conozca sus pasos y elija práctica o una sesión de su estudio.", "Explore an activity, learn its steps, and choose practice or a session in your study.")} />
    {status !== "online" && <div role="status" className="flex flex-wrap items-center justify-between gap-3 rounded border border-warning/30 p-4 text-sm">
      <span>{status === "checking" ? copy("Comprobando los experimentos disponibles…", "Checking available experiments…") : copy("No se pudo conectar con la consola. Inicie el servicio local y vuelva a comprobar.", "Could not connect to the console. Start the local service and check again.")}</span>
      {status === "offline" && <Button variant="outline" onClick={refresh}>{copy("Volver a comprobar", "Check again")}</Button>}
    </div>}
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3" aria-label={copy("Experimentos", "Experiments")}>
      {EXPERIMENTS.map((item) => {
        const Icon = icons[item.id];
        const active = item.id === selected;
        const installed = catalog.find((row) => row.id === item.id)?.component_available;
        return <button key={item.id} type="button" aria-pressed={active} onClick={() => choose(item.id)}
          className={"min-h-44 rounded-lg border p-5 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info " + (active ? "border-info bg-info/10" : "border-white/15 bg-black/25 hover:border-white/40")}>
          <Icon className="mb-3 h-6 w-6 text-info" aria-hidden="true" />
          <span className="block text-base font-semibold">{copy(...item.title)}</span>
          <span className="mt-2 block text-sm leading-6 text-muted-foreground">{copy(...item.summary)}</span>
          {status === "online" && !installed && <span className="mt-3 block text-xs text-warning">{copy("Requiere habilitar el componente", "Component must be enabled")}</span>}
        </button>;
      })}
    </div>
    {info && <section id="experiment-details" tabIndex={-1} aria-labelledby="experiment-title" className="rounded-lg border border-info/30 bg-card p-5 outline-none sm:p-7">
      <h2 id="experiment-title" className="font-display text-2xl font-semibold">{copy(...info.title)}</h2>
      <dl className="mt-5 grid gap-5 md:grid-cols-2">
        {([
          [copy("Qué mide", "What it measures"), info.summary],
          [copy("Qué hará", "What you will do"), info.actions],
          [copy("Duración", "Duration"), info.duration],
          [copy("Equipo necesario", "Equipment needed"), info.equipment],
          [copy("Cómo leer el resultado", "Reading your result"), info.results],
        ] as const).map(([label, value]) => <div key={label}><dt className="font-semibold">{label}</dt><dd className="mt-1 text-sm leading-6 text-muted-foreground">{copy(...value)}</dd></div>)}
      </dl>
      {entry && <ReadinessNote entry={entry} />}
      <fieldset className="mt-6 border-t border-white/10 pt-5">
        <legend className="px-1 font-semibold">{copy("Cómo desea participar", "How you want to participate")}</legend>
        <div className="mt-2 grid gap-3 sm:grid-cols-2">
          {(["practice", "study"] as const).map((mode) => <label key={mode} className={"flex cursor-pointer items-start gap-3 rounded border p-4 " + (purpose === mode ? "border-info bg-info/5" : "border-white/15")}>
            <input type="radio" name="execution-purpose" value={mode} checked={purpose === mode} onChange={() => choosePurpose(mode)} className="mt-1 accent-cyan-400" />
            <span><strong>{mode === "practice" ? copy("Practicar", "Practice") : copy("Participar en mi estudio", "Join my study")}</strong><span className="mt-1 block text-sm text-muted-foreground">{mode === "practice" ? copy("Familiarícese con los controles. Los resultados se guardan aparte del estudio.", "Learn the controls. Results are saved separately from the study.") : copy("Use su código y visita asignados. Se conserva la secuencia del protocolo.", "Use your assigned code and visit. The protocol sequence is preserved.")}</span></span>
          </label>)}
        </div>
      </fieldset>
      <div className="mt-5 flex flex-wrap items-center gap-4">
        {available && destination && purpose ? <Button asChild><Link href={withExecutionPurpose(destination, purpose)}>{copy("Preparar experimento", "Prepare experiment")}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
          : available && destination ? <p role="status" className="text-sm text-warning">{copy("Elija práctica o estudio para continuar.", "Choose practice or study to continue.")}</p>
          : <p className="text-sm text-warning">{status !== "online" ? copy("Conecte la consola para preparar esta actividad.", "Connect the console to prepare this activity.") : copy("Este componente no está habilitado. Solicite al investigador que lo active y revise el equipo indicado arriba.", "This component is not enabled. Ask the researcher to enable it and check the equipment listed above.")}</p>}
        <span className="text-sm text-muted-foreground">{copy("Antes de iniciar se verifican los requisitos del experimento.", "Experiment requirements are checked before starting.")}</span>
      </div>
    </section>}
  </div>;
}
