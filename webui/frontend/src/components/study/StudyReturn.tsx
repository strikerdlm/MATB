"use client";
import Link from "next/link";
import type { Attempt } from "@/lib/assessments";
import { useAppLocale } from "@/lib/i18n";
export function StudyReturn({ attempt }: { attempt: Attempt | null }) {
  const preferred = useAppLocale();
  const context = attempt?.assignment_context ?? attempt?.preparation_context;
  const copy = (es: string, en: string) =>
    (context?.locale ?? preferred.locale) === "en" ? en : es;
  return context ? (
    <Link
      className="block underline"
      href={`/study/participant?assignment=${context.assignment_id}`}
    >
      {copy(
        "Continuar visita: siguiente acción",
        "Continue visit: next action",
      )}
    </Link>
  ) : null;
}
