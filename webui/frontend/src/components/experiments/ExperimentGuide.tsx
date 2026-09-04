"use client";
import Link from "next/link";
import { useAppLocale } from "@/lib/i18n";
import { EXPERIMENTS, type ExperimentId } from "@/lib/experiments";
import { useExecutionPurpose } from "@/lib/execution-purpose";

export function ExperimentGuide({ id }: { id: ExperimentId }) {
  const { copy } = useAppLocale();
  const purpose = useExecutionPurpose();
  const info = EXPERIMENTS.find((item) => item.id === id)!;
  return <section className="rounded-lg border border-info/30 bg-info/5 p-5" aria-label={copy("Guía del experimento", "Experiment guide")}>
    <div className="flex flex-wrap items-center justify-between gap-3">
      <span className="font-semibold text-info">{purpose === "practice" ? copy("Práctica · Familiarización", "Practice · Familiarization") : copy("Sesión de estudio", "Study session")}</span>
      <Link href={`/start?experiment=${id}`} className="text-sm underline underline-offset-4">{copy("Ver experimentos", "View experiments")}</Link>
    </div>
    <p className="mt-3 text-sm leading-6">{copy(...info.actions)}</p>
    <p className="mt-2 text-sm text-muted-foreground">{purpose === "practice"
      ? copy("Puede familiarizarse con la tarea. Esta práctica se guarda por separado y no completa una visita de estudio.", "Familiarize yourself with the task. This practice is saved separately and does not complete a study visit.")
      : copy("Use su código asignado. La aplicación conserva el orden y los requisitos del protocolo.", "Use your assigned code. The application preserves the protocol’s order and requirements.")}</p>
  </section>;
}
