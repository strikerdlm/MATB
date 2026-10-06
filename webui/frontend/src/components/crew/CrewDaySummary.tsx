"use client";
import Link from "next/link";
import { Check } from "lucide-react";
import { crewHref, type CrewActivity, type CrewProgress } from "@/lib/crew-workflow";
import { useAppLocale } from "@/lib/i18n";

export const activityNames: Record<CrewActivity, readonly [string, string]> = {
  openmatb: ["OpenMATB · Cuatro tareas", "OpenMATB · Four tasks"],
  suas: ["Misión sUAS · Supervisión", "sUAS mission · Supervision"],
  screen: ["Pruebas", "Tests"], pvt: ["KSS + PVT", "KSS + PVT"],
};

export function testDate(value: string, locale: string): string {
  // An explicit noon UTC avoids shifting a calendar date with the browser's timezone.
  return new Intl.DateTimeFormat(locale === "en" ? "en-US" : "es-CO", {
    day: "numeric", month: "long", timeZone: "America/Bogota",
  }).format(new Date(`${value}T12:00:00Z`));
}

export function CrewDaySummary({ person }: { person: CrewProgress }) {
  const { copy, locale } = useAppLocale();
  return <div className="crew-day-summary">
    {person.next_test_date && <p className="crew-next-date">
      {person.state === "scheduled" ? copy("Tu próxima jornada", "Your next test day") : (person.days_until_next ?? 0) < 0 ? copy("Después de esta, continúa con la jornada pendiente del", "After this, continue with the overdue test day of") : copy("Después de esta jornada, vuelve", "After this test day, return")}:
      {" "}<strong>{testDate(person.next_test_date, locale)}</strong>
      {person.days_until_next !== null && person.days_until_next > 0 && <span>{" · "}{copy(`en ${person.days_until_next} ${person.days_until_next === 1 ? "día" : "días"}`, `in ${person.days_until_next} ${person.days_until_next === 1 ? "day" : "days"}`)}</span>}.
    </p>}
    <p className="crew-note">{copy("Completa todas las pruebas de esta jornada.", "Complete every test in this test day.")}</p>
    <ul className="crew-activities" aria-label={copy("Pruebas de la jornada", "Tests for this day")}>
      {person.activities.map(item => <li key={item.instrument}>
        <Link href={crewHref(item.instrument, person.callsign)}>
          <span>{copy(...activityNames[item.instrument])}</span>
          <span className={item.complete ? "crew-saved" : "crew-muted"}>{item.complete ? <><Check size={16} aria-hidden="true" />{copy("Guardada", "Saved")}</> : copy("Pendiente", "Pending")}</span>
        </Link>
      </li>)}
    </ul>
    <p className="crew-note">{copy("Tres jornadas en misión, cada cuatro días, y una postmisión.", "Three mission test days, four days apart, and one post-mission test day.")}</p>
    <ol className="crew-calendar" aria-label={copy("Tus fechas de prueba", "Your test dates")}>
      {person.schedule.map(day => <li key={day.label}><span>{day.label}</span><span>{testDate(day.date, locale)}{day.complete && <Check size={14} aria-label={copy("Completada", "Complete")} />}</span></li>)}
    </ol>
  </div>;
}
