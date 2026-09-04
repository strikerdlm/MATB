"use client";

import React, { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity, BarChart3, Check, ClipboardCheck, Clock3, FileQuestion,
  FlaskConical, Gamepad2, LayoutGrid, MonitorPlay, MoonStar, Radar,
  SlidersHorizontal, Upload, UserRound, Users,
} from "lucide-react";

import { getCapabilities } from "@/lib/api";
import { hasComponent } from "@/lib/capabilities";
import { useAppLocale } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type { ConsoleCapabilities } from "@/types";

interface JourneyItem {
  id: string;
  href: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  enabled: boolean;
}

export function SidebarNav() {
  const { copy } = useAppLocale();
  const pathname = usePathname() ?? "/";
  const [hash, setHash] = useState("");
  const [capabilities, setCapabilities] = useState<ConsoleCapabilities | null>(null);

  useEffect(() => {
    const sync = () => setHash(window.location.hash);
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [pathname]);

  useEffect(() => {
    let active = true;
    void getCapabilities()
      .then((value) => { if (active) setCapabilities(value); })
      .catch(() => { if (active) setCapabilities(null); });
    return () => { active = false; };
  }, []);

  const hasMission = Boolean(capabilities && hasComponent(capabilities, "matb-suas"));
  const hasPolar = Boolean(capabilities && hasComponent(capabilities, "matb-physiology"));
  const participantItems = useMemo<JourneyItem[]>(() => [
    { id: "welcome", href: "/start", label: copy("Bienvenida e identificación", "Welcome & Participant ID"), icon: UserRound, enabled: true },
    { id: "kss", href: "/pvt#kss", label: copy("Escala de Somnolencia KSS", "Karolinska Sleepiness Scale"), icon: MoonStar, enabled: true },
    { id: "pvt", href: "/pvt#pvt", label: copy("PVT · Vigilancia psicomotora", "PVT · Psychomotor vigilance"), icon: Clock3, enabled: true },
    { id: "polar", href: "/physiology/polar-h10", label: copy("Línea basal Polar H10", "Polar H10 baseline"), icon: Activity, enabled: hasPolar },
    { id: "briefing", href: "/mission/setup#briefing", label: copy("Instrucciones de misión", "Mission briefing"), icon: ClipboardCheck, enabled: hasMission },
    { id: "practice", href: "/mission/setup#practice", label: copy("Práctica", "Practice"), icon: Gamepad2, enabled: hasMission },
    { id: "blocks", href: "/mission/setup#blocks", label: copy("Bloques de misión", "Mission blocks"), icon: Radar, enabled: hasMission },
    { id: "workload", href: "/mission/setup#workload", label: copy("Preguntas de carga", "Workload questions"), icon: FileQuestion, enabled: hasMission },
    { id: "complete", href: "/mission/setup#complete", label: copy("Completar visita", "Complete visit"), icon: Check, enabled: hasMission },
  ], [copy, hasMission, hasPolar]);

  const researcherItems = [
    { href: "/", label: copy("Seguimiento", "Tracker"), icon: LayoutGrid },
    { href: "/participants", label: copy("Participantes", "Participants"), icon: Users },
    { href: "/experiments", label: copy("Diseñador", "Designer"), icon: SlidersHorizontal },
    { href: "/upload", label: copy("Cargar datos", "Upload data"), icon: Upload },
    { href: "/visualization", label: copy("Visualización", "Visualization"), icon: BarChart3 },
    { href: "/analysis", label: copy("Análisis", "Analysis"), icon: FlaskConical },
    ...(capabilities && hasComponent(capabilities, "matb-openmatb") ? [{ href: "/openmatb/setup", label: copy("OpenMATB clásico", "Classic OpenMATB"), icon: MonitorPlay }] : []),
    ...(capabilities && hasComponent(capabilities, "matb-liftoff") ? [{ href: "/liftoff/setup", label: "Liftoff", icon: Gamepad2 }] : []),
    ...(hasMission ? [{ href: "/mission/test", label: copy("Pruebas técnicas MATB-FAC", "MATB-FAC technical tests"), icon: Radar }] : []),
  ];

  function journeyActive(item: JourneyItem): boolean {
    if (item.id === "welcome") return pathname === "/start";
    if (item.id === "kss") return pathname === "/pvt" && hash !== "#pvt";
    if (item.id === "pvt") return pathname === "/pvt" && hash === "#pvt";
    if (item.id === "polar") return pathname.startsWith("/physiology/polar-h10");
    if (["briefing", "practice", "blocks", "workload", "complete"].includes(item.id)) {
      return pathname.startsWith("/mission/setup") && hash === `#${item.id}`;
    }
    return false;
  }

  return (
    <nav aria-label={copy("Orden del flujo", "Workflow order")} className="p-3 md:p-4">
      <div className="mb-3 flex items-center justify-between px-1">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-info">{copy("Secuencia del participante", "Participant sequence")}</span>
        <span className="font-mono text-[9px] text-muted-foreground">01–09</span>
      </div>
      <ol className="flex gap-2 overflow-x-auto pb-2 md:block md:space-y-1 md:overflow-visible md:pb-0">
        {participantItems.map((item, index) => {
          const active = journeyActive(item);
          const Icon = item.icon;
          const content = <><span className={cn("grid h-6 w-6 shrink-0 place-items-center rounded-full border font-mono text-[9px]", active ? "border-black/25 bg-black text-white" : "border-white/20 bg-black/30 text-muted-foreground")}>{index + 1}</span><Icon className="h-3.5 w-3.5 shrink-0" /><span className="leading-tight">{item.label}</span></>;
          const classes = cn("relative flex min-w-[14rem] items-center gap-2 rounded border px-2.5 py-2.5 text-left text-[11px] font-medium transition md:min-w-0 md:w-full", active ? "border-white bg-white text-black shadow-[0_0_32px_rgb(255_255_255/0.12)]" : "border-white/10 text-muted-foreground hover:border-white/30 hover:bg-white/[0.04] hover:text-foreground", !item.enabled && "cursor-not-allowed opacity-45");
          return <li key={item.id} className="relative">{index < participantItems.length - 1 && <span aria-hidden="true" className="absolute left-[1.35rem] top-10 hidden h-3 border-l border-white/15 md:block" />}{item.enabled ? <Link href={item.href} aria-current={active ? "step" : undefined} className={classes}>{content}</Link> : <span className={classes} title={copy("Componente no instalado", "Component not installed")}>{content}</span>}</li>;
        })}
      </ol>

      <details className="mt-5 border-t border-white/10 pt-4">
        <summary className="cursor-pointer list-none px-1 font-mono text-[10px] font-semibold uppercase tracking-[0.2em] text-muted-foreground">{copy("Herramientas del investigador", "Researcher tools")}</summary>
        <div className="mt-3 grid gap-1">
          {researcherItems.map(({ href, label, icon: Icon }) => {
            const active = pathname === href || (href !== "/" && pathname.startsWith(href));
            return <Link key={href} href={href} aria-current={active ? "page" : undefined} className={cn("flex items-center gap-3 rounded border px-3 py-2 text-[11px] uppercase tracking-[0.08em] transition", active ? "border-info/40 bg-info/10 text-info" : "border-transparent text-muted-foreground hover:border-white/15 hover:text-foreground")}><Icon className="h-3.5 w-3.5" />{label}</Link>;
          })}
        </div>
      </details>
    </nav>
  );
}
