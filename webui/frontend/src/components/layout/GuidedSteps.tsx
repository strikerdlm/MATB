import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

export type GuidedStepState = "complete" | "current" | "upcoming";

export interface GuidedStep {
  title: string;
  description: string;
  state: GuidedStepState;
}

export function GuidedSteps({ label, steps }: { label: string; steps: GuidedStep[] }) {
  return (
    <ol aria-label={label} className="grid gap-3 md:grid-cols-4">
      {steps.map((step, index) => (
        <li
          key={`${index}-${step.title}`}
          aria-current={step.state === "current" ? "step" : undefined}
          className={cn(
            "min-h-28 border p-4",
            step.state === "current" && "border-white bg-white text-black shadow-[0_0_32px_rgb(255_255_255/0.12)]",
            step.state === "complete" && "border-success/40 bg-success/5",
            step.state === "upcoming" && "border-white/10 bg-black/20 text-muted-foreground",
          )}
        >
          <div className="flex items-center justify-between font-mono text-[10px] uppercase tracking-[0.16em] opacity-70">
            <span>{String(index + 1).padStart(2, "0")}</span>
            {step.state === "complete" && <Check className="h-4 w-4 text-success" aria-hidden="true" />}
          </div>
          <div className="mt-2 font-display text-base font-semibold uppercase tracking-wide">{step.title}</div>
          <p className="mt-2 text-xs leading-relaxed opacity-75">{step.description}</p>
        </li>
      ))}
    </ol>
  );
}
