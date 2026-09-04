"use client";

import Link from "next/link";
import { Activity, ArrowRight, CheckCircle2, Clock3, Headphones, MoonStar, Radar, UserRoundPlus } from "lucide-react";

import { InstructionAudio } from "@/components/instructions/InstructionAudio";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useAppLocale } from "@/lib/i18n";

export default function StartPage() {
  const { locale, copy } = useAppLocale();
  const audioLocale = locale === "en" ? "en" : "es";
  const steps = [
    { title: copy("Bienvenida e identificación", "Welcome & Participant ID"), text: copy("Confirme con el investigador su código seudonimizado y la visita de hoy.", "Confirm your pseudonymous code and today’s visit with the researcher."), icon: UserRoundPlus },
    { title: copy("Escala de Somnolencia KSS", "Karolinska Sleepiness Scale"), text: copy("Indique cómo se sintió durante los cinco minutos anteriores.", "Rate how you felt during the previous five minutes."), icon: MoonStar },
    { title: copy("PVT", "PVT"), text: copy("Responda al contador durante 10 minutos para medir vigilancia psicomotora.", "Respond to the counter for 10 minutes to measure psychomotor vigilance."), icon: Clock3 },
    { title: copy("Línea basal Polar H10", "Polar H10 baseline"), text: copy("Permanezca quieto mientras el investigador comprueba la señal y registra la línea basal.", "Remain still while the researcher checks the signal and records the baseline."), icon: Activity },
    { title: copy("Instrucciones de misión", "Mission briefing"), text: copy("Aprenda el mapa, las alertas, los contactos y los controles antes de operar.", "Learn the map, alerts, contacts, and controls before operating."), icon: Headphones },
    { title: copy("Práctica", "Practice"), text: copy("Ensaye selección, asignación de sectores, alertas y reportes sin presión de desempeño.", "Practice selection, sector assignment, alerts, and reports without performance pressure."), icon: Radar },
    { title: copy("Bloques de misión", "Mission blocks"), text: copy("Complete los bloques BAJO, MEDIO y ALTO en el orden que muestre la aplicación.", "Complete LOW, MEDIUM, and HIGH blocks in the order shown by the application."), icon: Radar },
    { title: copy("Preguntas de carga", "Workload questions"), text: copy("Responda ISA durante la misión y NASA-TLX/Bedford después de cada bloque cuando aparezcan.", "Answer ISA during the mission and NASA-TLX/Bedford after each block when prompted."), icon: CheckCircle2 },
    { title: copy("Completar visita", "Complete visit"), text: copy("Espere la confirmación de guardado antes de cerrar la aplicación.", "Wait for the saved confirmation before closing the application."), icon: CheckCircle2 },
  ];

  return (
    <div className="space-y-7">
      <PageHeader
        kicker={copy("Paso 1 de la visita", "Visit step 1")}
        title={copy("Bienvenido a su misión MATB-FAC", "Welcome to your MATB-FAC mission")}
        description={copy(
          "La barra lateral y esta guía muestran las actividades en el orden exacto en que las realizará. No omita pasos.",
          "The sidebar and this guide show the activities in the exact order you will perform them. Do not skip steps.",
        )}
        stats={[
          { label: copy("Secuencia", "Sequence"), value: "9" },
          { label: copy("Idioma", "Language"), value: locale === "en" ? "English" : "Español" },
          { label: copy("Misión principal", "Primary mission"), value: "sUAS" },
        ]}
      />

      <Card className="border-info/30 bg-info/5">
        <CardContent className="flex flex-col items-start justify-between gap-5 pt-6 lg:flex-row lg:items-center">
          <div className="max-w-3xl">
            <div className="font-display text-xl font-semibold uppercase tracking-wide">{copy("Escuche antes de comenzar", "Listen before you begin")}</div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy("El audio explica la secuencia completa. Puede pausarlo o repetirlo. Las mismas instrucciones permanecen visibles en pantalla.", "The audio explains the complete sequence. You may pause or replay it. The same instructions remain visible on screen.")}</p>
          </div>
          <InstructionAudio src={`/audio/instructions/journey-${audioLocale}.mp3`} label={copy("Escuchar guía de la visita", "Listen to visit guide")} unavailableLabel={copy("Audio no disponible", "Audio unavailable")} />
        </CardContent>
      </Card>

      <section aria-labelledby="visit-sequence-heading">
        <div className="mb-4 flex flex-col items-start gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div><p className="page-kicker">01–09</p><h2 id="visit-sequence-heading" className="mt-2 font-display text-2xl font-semibold uppercase">{copy("Su secuencia de actividades", "Your activity sequence")}</h2></div>
          <Button asChild><Link href="/pvt#kss">{copy("Comenzar con KSS", "Begin with KSS")}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
        </div>
        <ol className="grid gap-3 lg:grid-cols-3">
          {steps.map(({ title, text, icon: Icon }, index) => (
            <li key={title} className={`mission-panel p-4 ${index === 0 ? "border-info/40 bg-info/5" : ""}`}>
              <div className="flex items-start gap-3">
                <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full border border-white/15 bg-black/35 font-mono text-xs text-info">{String(index + 1).padStart(2, "0")}</span>
                <div><Icon className="mb-2 h-4 w-4 text-info" /><h3 className="font-semibold">{title}</h3><p className="mt-1 text-sm leading-5 text-muted-foreground">{text}</p></div>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <Card>
        <CardHeader>
          <CardTitle>{copy("Confirmación de identidad", "Identity confirmation")}</CardTitle>
          <CardDescription>{copy("Use solamente códigos como P01. Nunca escriba nombres, documentos de identidad ni correos.", "Use codes such as P01 only. Never enter names, identity documents, or email addresses.")}</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          <Button asChild variant="outline"><Link href="/participants"><UserRoundPlus className="mr-2 h-4 w-4" />{copy("Investigador: administrar códigos", "Researcher: manage codes")}</Link></Button>
          <Button asChild><Link href="/pvt#kss">{copy("Mi código está confirmado", "My code is confirmed")}<ArrowRight className="ml-2 h-4 w-4" /></Link></Button>
        </CardContent>
      </Card>

      <details className="rounded border border-white/10 bg-black/20 p-4 text-sm text-muted-foreground">
        <summary className="cursor-pointer font-semibold text-foreground">{copy("Alternativas administradas por el investigador", "Researcher-managed alternatives")}</summary>
        <p className="mt-3 leading-6">{copy("OpenMATB clásico y Liftoff se conservan como herramientas alternativas del protocolo. La misión sUAS integrada es el flujo principal mostrado al participante.", "Classic OpenMATB and Liftoff remain protocol alternatives managed by the researcher. The integrated sUAS mission is the primary participant flow shown here.")}</p>
      </details>
    </div>
  );
}
