"use client";
import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useAppLocale } from "@/lib/i18n";
import { EXPERIMENTS, type ExecutionPurpose, type ExperimentId } from "@/lib/experiments";
import { useExecutionPurpose, withExecutionPurpose } from "@/lib/execution-purpose";

export function ExecutionPurposeBadge({ purpose }: { purpose: ExecutionPurpose }) {
  const { copy } = useAppLocale();
  const practice = purpose === "practice";
  return <div role="note" className={`flex flex-wrap items-center gap-x-3 gap-y-1 rounded border px-3 py-2 text-sm ${practice ? "border-warning/40 bg-warning/10" : "border-info/30 bg-info/5"}`}>
    <span className={`font-semibold ${practice ? "text-warning" : "text-info"}`}>
      {practice ? copy("Práctica", "Practice") : copy("Sesión de estudio", "Study session")}
    </span>
    <span className="text-muted-foreground">{practice
      ? copy("La práctica se guarda por separado y no completa una visita de estudio.", "Practice is saved separately and does not complete a study visit.")
      : copy("Use el código y la visita asignados para este estudio.", "Use the code and visit assigned for this study.")}</span>
  </div>;
}

export function ExperimentGuide({ id }: { id: ExperimentId }) {
  const { copy } = useAppLocale();
  const purpose = useExecutionPurpose();
  const pathname = usePathname() ?? "/start";
  const search = useSearchParams();
  const info = EXPERIMENTS.find((item) => item.id === id)!;
  const currentHref = `${pathname}${search.size ? `?${search.toString()}` : ""}`;
  const catalogHref = purpose
    ? withExecutionPurpose(`/start?experiment=${id}`, purpose)
    : `/start?experiment=${id}`;
  return <section className="rounded-lg border border-info/30 bg-info/5 p-5" aria-label={copy("Guía del experimento", "Experiment guide")}>
    <div className="flex flex-wrap items-start justify-between gap-3">
      {purpose
        ? <ExecutionPurposeBadge purpose={purpose} />
        : <div>
          <h2 className="text-base font-semibold">{copy("Elija cómo participará", "Choose how you will participate")}</h2>
          <p className="mt-1 text-sm text-muted-foreground">{copy("Debe elegir práctica o estudio antes de preparar esta actividad.", "Choose practice or study before preparing this activity.")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link className="rounded border border-warning/50 px-3 py-2 text-sm font-semibold text-warning" href={withExecutionPurpose(currentHref, "practice")}>{copy("Practicar", "Practice")}</Link>
            <Link className="rounded border border-info/50 px-3 py-2 text-sm font-semibold text-info" href={withExecutionPurpose(currentHref, "study")}>{copy("Participar en mi estudio", "Join my study")}</Link>
          </div>
        </div>}
      <Link href={catalogHref} className="text-sm underline underline-offset-4">{copy("Ver experimentos", "View experiments")}</Link>
    </div>
    <p className="mt-3 text-sm leading-6">{copy(...info.actions)}</p>
    {purpose && <p className="mt-2 text-sm text-muted-foreground">{purpose === "practice"
      ? copy("Puede familiarizarse con la tarea antes de iniciar una visita asignada.", "You can become familiar with the task before starting an assigned visit.")
      : copy("La aplicación conserva el orden y los requisitos del protocolo.", "The application preserves the protocol’s order and requirements.")}</p>}
  </section>;
}
