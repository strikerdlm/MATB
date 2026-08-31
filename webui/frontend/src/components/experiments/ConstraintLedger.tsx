import { AlertTriangle, Check, X } from "lucide-react";
import React from "react";

import { cn } from "@/lib/utils";
import type { TimelineConstraint } from "@/types";

const STATUS = {
  pass: { icon: Check, className: "text-success", label: "PASS" },
  warning: { icon: AlertTriangle, className: "text-warning", label: "WARN" },
  fail: { icon: X, className: "text-danger", label: "FAIL" },
} as const;

export function ConstraintLedger({ constraints }: { constraints: TimelineConstraint[] }) {
  return (
    <section className="border border-white/15 bg-black/30" aria-labelledby="constraint-title">
      <div className="border-b border-white/15 px-4 py-3">
        <h3 id="constraint-title" className="font-display text-sm font-semibold uppercase tracking-[0.08em]">
          Constraint validation
        </h3>
      </div>
      <div className="divide-y divide-white/10">
        {constraints.map((constraint) => {
          const config = STATUS[constraint.status];
          const Icon = config.icon;
          return (
            <div key={constraint.id} className="grid gap-2 px-4 py-3 sm:grid-cols-[1fr_auto] sm:items-center">
              <div>
                <p className="text-sm text-foreground">{constraint.label}</p>
                <p className="mt-1 font-mono text-[10px] text-muted-foreground">{constraint.detail}</p>
              </div>
              <span className={cn("inline-flex items-center gap-2 font-mono text-[10px] font-semibold", config.className)}>
                <Icon className="h-3.5 w-3.5" /> {config.label}
              </span>
            </div>
          );
        })}
      </div>
    </section>
  );
}
