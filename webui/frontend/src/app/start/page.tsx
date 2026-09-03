"use client";

import Link from "next/link";
import { ArrowRight, MonitorPlay, Radar, UserRoundPlus } from "lucide-react";

import { GuidedSteps } from "@/components/layout/GuidedSteps";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppLocale } from "@/lib/i18n";

export default function StartPage() {
  const { copy } = useAppLocale();

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Guía de inicio", "Getting started")}
        title={copy("¿Qué quiere ejecutar hoy?", "What do you want to run today?")}
        description={copy(
          "Siga estos pasos en orden. La consola le mostrará una sola acción principal en cada etapa.",
          "Follow these steps in order. The console will show one primary action at each stage.",
        )}
        stats={[
          { label: copy("Flujo", "Flow"), value: copy("Guiado", "Guided") },
          { label: copy("Datos", "Data"), value: copy("Locales", "Local") },
          { label: copy("Idioma", "Language"), value: copy("Español", "English") },
        ]}
      />

      <GuidedSteps
        label={copy("Ruta de inicio", "Start path")}
        steps={[
          { title: copy("Preparar", "Prepare"), description: copy("Abra la consola con el acceso 01. Las dependencias y la interfaz se comprueban automáticamente.", "Open the console with launcher 01. Dependencies and the interface are checked automatically."), state: "complete" },
          { title: copy("Registrar", "Register"), description: copy("Cree o seleccione un código seudonimizado, por ejemplo P01.", "Create or select a pseudonymous code, for example P01."), state: "current" },
          { title: copy("Elegir", "Choose"), description: copy("Seleccione OpenMATB clásico o Misión de investigación.", "Choose Classic OpenMATB or Research Mission."), state: "upcoming" },
          { title: copy("Ejecutar", "Run"), description: copy("Siga el botón de acción principal hasta completar la sesión.", "Follow the primary action button until the session is complete."), state: "upcoming" },
        ]}
      />

      <Card className="border-info/30 bg-info/5">
        <CardContent className="flex flex-col items-start justify-between gap-4 pt-6 sm:flex-row sm:items-center">
          <div>
            <div className="font-display text-lg font-semibold uppercase tracking-wide">{copy("Primero: participante", "First: participant")}</div>
            <p className="mt-1 text-sm text-muted-foreground">{copy("Use solamente códigos como P01; nunca nombres, cédulas ni correos.", "Use codes such as P01 only; never names, identity numbers, or email addresses.")}</p>
          </div>
          <Button asChild variant="outline"><Link href="/participants"><UserRoundPlus className="mr-2 h-4 w-4" />{copy("Administrar participantes", "Manage participants")}</Link></Button>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="flex flex-col">
          <CardHeader>
            <MonitorPlay className="mb-3 h-8 w-8 text-info" aria-hidden="true" />
            <CardTitle className="font-display text-2xl uppercase tracking-wide">{copy("OpenMATB clásico", "Classic OpenMATB")}</CardTitle>
            <CardDescription>{copy("Abre la aplicación nativa clásica en la pantalla seleccionada.", "Opens the classic native application on the selected display.")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col justify-between gap-6">
            <ol className="space-y-2 text-sm text-muted-foreground">
              <li><strong className="text-foreground">1.</strong> {copy("Seleccione participante, visita y pantalla.", "Select participant, visit, and display.")}</li>
              <li><strong className="text-foreground">2.</strong> {copy("El participante confirma las instrucciones.", "The participant confirms the instructions.")}</li>
              <li><strong className="text-foreground">3.</strong> {copy("Pulse “Abrir OpenMATB” en el panel del investigador.", "Press “Open OpenMATB” in the researcher console.")}</li>
            </ol>
            <Button asChild size="lg"><Link href="/openmatb/setup">{copy("Iniciar OpenMATB clásico", "Start Classic OpenMATB")}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
          </CardContent>
        </Card>

        <Card className="flex flex-col">
          <CardHeader>
            <Radar className="mb-3 h-8 w-8 text-success" aria-hidden="true" />
            <CardTitle className="font-display text-2xl uppercase tracking-wide">{copy("Misión de investigación", "Research Mission")}</CardTitle>
            <CardDescription>{copy("Ejecuta el simulador sUAS integrado dentro de la consola.", "Runs the integrated sUAS simulator inside the console.")}</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-1 flex-col justify-between gap-6">
            <ol className="space-y-2 text-sm text-muted-foreground">
              <li><strong className="text-foreground">1.</strong> {copy("Seleccione participante y visita.", "Select participant and visit.")}</li>
              <li><strong className="text-foreground">2.</strong> {copy("Confirme el escenario instalado.", "Confirm the installed scenario.")}</li>
              <li><strong className="text-foreground">3.</strong> {copy("Prepare la sesión y luego inicie PRÁCTICA.", "Prepare the session and then start PRACTICE.")}</li>
            </ol>
            <Button asChild size="lg"><Link href="/mission/setup">{copy("Iniciar misión de investigación", "Start Research Mission")}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
