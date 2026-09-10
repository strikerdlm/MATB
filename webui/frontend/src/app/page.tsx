"use client";

import { useRouter } from "next/navigation";
import { Microscope, UserRound } from "lucide-react";

import { PageHeader } from "@/components/layout/PageHeader";
import { useAppLocale } from "@/lib/i18n";
import { destinationForRole, useNavigationRole, type NavigationRole } from "@/lib/navigation-role";

export default function HomePage() {
  const { copy } = useAppLocale();
  const { setRole } = useNavigationRole();
  const router = useRouter();

  function choose(role: NavigationRole) {
    setRole(role);
    router.push(destinationForRole(role));
  }

  return <div className="mx-auto max-w-5xl space-y-7 py-4 sm:py-8">
    <PageHeader
      kicker="MATB - FAC"
      title={copy("Elija su espacio de trabajo", "Choose your workspace")}
      description={copy("Esta elección organiza la navegación de esta pestaña. No cambia el propósito de una ejecución ni sus credenciales.", "This choice organizes navigation in this tab. It does not change a run's purpose or credentials.")}
    />
    <div className="grid gap-4 md:grid-cols-2">
      <button type="button" onClick={() => choose("participant")} className="rounded-lg border border-info/30 bg-info/5 p-6 text-left hover:border-info focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info">
        <UserRound className="h-7 w-7 text-info" aria-hidden="true" />
        <span className="mt-4 block text-xl font-semibold">{copy("Participante", "Participant")}</span>
        <span className="mt-2 block text-sm leading-6 text-muted-foreground">{copy("Elija una actividad y seleccione práctica o estudio antes de prepararla.", "Choose an activity and select practice or study before preparing it.")}</span>
      </button>
      <button type="button" onClick={() => choose("researcher")} className="rounded-lg border border-white/20 bg-card p-6 text-left hover:border-white/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-info">
        <Microscope className="h-7 w-7 text-info" aria-hidden="true" />
        <span className="mt-4 block text-xl font-semibold">{copy("Investigador", "Researcher")}</span>
        <span className="mt-2 block text-sm leading-6 text-muted-foreground">{copy("Revise participantes, seguimiento, configuración y evidencia.", "Review participants, tracking, configuration, and evidence.")}</span>
      </button>
    </div>
  </div>;
}
