"use client";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { useAppLocale } from "@/lib/i18n";
import type { ReactNode } from "react";

export function CrewFrame({ children, step = 2 }: { children: ReactNode; step?: 2 | 3 }) {
  const { copy } = useAppLocale();
  return <div className="crew-page">
    <header className="crew-header"><Link href="/start" className="crew-brand">MATB · ASTRA</Link><Link href="/start">{copy("Cambiar actividad", "Change activity")}</Link></header>
    <main className="crew-main">
      <ol className="crew-steps" aria-label={copy("Pasos", "Steps")}>
        {[copy("Actividad", "Activity"), copy("Tripulante", "Crew member"), copy("Prueba", "Test")].map((label, index) =>
          <li key={label} aria-current={index + 1 === step ? "step" : undefined}><span aria-hidden="true">{index + 1}</span>{label}</li>)}
      </ol>
      {children}
      <Link href="/start" className="crew-back"><ArrowLeft aria-hidden="true" size={20} />{copy("Volver a actividades", "Back to activities")}</Link>
    </main>
  </div>;
}
