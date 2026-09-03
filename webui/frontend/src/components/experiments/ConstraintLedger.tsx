"use client";

import { AlertTriangle, Check, X } from "lucide-react";
import React from "react";

import { cn } from "@/lib/utils";
import type { TimelineConstraint } from "@/types";
import { useAppLocale } from "@/lib/i18n";

const STATUS = {
  pass: { icon: Check, className: "text-success", label: "PASS" },
  warning: { icon: AlertTriangle, className: "text-warning", label: "WARN" },
  fail: { icon: X, className: "text-danger", label: "FAIL" },
} as const;

export function ConstraintLedger({ constraints }: { constraints: TimelineConstraint[] }) {
  const { copy, locale } = useAppLocale();
  const spanish = (constraint: TimelineConstraint): { label: string; detail: string } => {
    const count = constraint.detail.match(/\d+/)?.[0] ?? "0";
    const translations: Record<string, { label: string; detail: string }> = {
      "integer-precision": { label: "Los valores del navegador conservan nanosegundos enteros exactos", detail: constraint.status === "pass" ? "Todos los valores de tiempo y semilla son enteros seguros" : "Se detectó un valor de tiempo o semilla inseguro o fraccionario" },
      "seed-range": { label: "La semilla del experimento es un entero seguro no negativo", detail: constraint.status === "pass" ? "La semilla se representa sin pérdida" : "La semilla debe estar entre 0 y Number.MAX_SAFE_INTEGER" },
      "timeline-boundary": { label: "Todos los eventos permanecen dentro de la duración del experimento", detail: constraint.status === "pass" ? `${count} eventos verificados` : `${count} eventos fuera de la duración o con duración inválida` },
      "openmatb-delimiters": { label: "Los campos de tarea y comando usan delimitadores seguros", detail: constraint.status === "pass" ? "No hay tokens de comando ambiguos" : `${count} comandos inseguros` },
      "runtime-semantics": { label: "El compilador de ejecución puede representar los eventos sin pérdida", detail: constraint.status === "pass" ? "Se verificaron comandos, ciclos de vida y ventanas de evidencia" : constraint.detail },
      "sysmon-denominator": { label: "SYSMON tiene oportunidades explícitas sin objetivo", detail: constraint.detail.replace("non-target", "sin objetivo").replace("target", "objetivo") },
      "workload-claim": { label: "Las etiquetas de carga permanecen como preajustes de ingeniería", detail: "Este editor no infiere evidencia de calibración humana" },
    };
    return translations[constraint.id] ?? { label: constraint.label, detail: constraint.detail };
  };
  return (
    <section className="border border-white/15 bg-black/30" aria-labelledby="constraint-title">
      <div className="border-b border-white/15 px-4 py-3">
        <h3 id="constraint-title" className="font-display text-sm font-semibold uppercase tracking-[0.08em]">
          {copy("Validación de restricciones", "Constraint validation")}
        </h3>
      </div>
      <div className="divide-y divide-white/10">
        {constraints.map((constraint) => {
          const config = STATUS[constraint.status];
          const content = locale === "en" ? constraint : spanish(constraint);
          const Icon = config.icon;
          return (
            <div key={constraint.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div>
                <p className="text-sm text-foreground">{content.label}</p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">{content.detail}</p>
              </div>
              <span className={cn("inline-flex items-center gap-2 font-mono text-[10px] font-semibold", config.className)}>
                <Icon className="h-3.5 w-3.5" /> {constraint.status === "pass" ? copy("OK", config.label) : constraint.status === "warning" ? copy("AVISO", config.label) : copy("FALLA", config.label)}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
