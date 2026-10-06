"use client";

import React from "react";
import { Check, Circle } from "lucide-react";

import { consoleProfileStatus } from "@/lib/simulation/console-profile";
import type { Locale, SessionView } from "@/types/simulation";
import type { ParticipantJourneyStep } from "@/types";

function currentStep(session: SessionView): number {
  if (["FINISHED", "ABORTED", "INTERRUPTED"].includes(session.lifecycle)) return 8;
  if (["ISA_ACTIVE", "SAGAT_ACTIVE", "POST_BLOCK_ACTIVE"].includes(session.protocol_phase ?? "")) return 7;
  const block = session.active_block_id ?? session.next_block_id;
  if (block === "PRACTICE") return session.lifecycle === "PREPARED" ? 4 : 5;
  if (block && ["LOW", "MEDIUM", "HIGH"].includes(block)) return 6;
  return 4;
}

export function MissionJourneyRail({ session, locale, steps }: { session: SessionView; locale: Locale; steps?: ParticipantJourneyStep[] | null }) {
  const modern = consoleProfileStatus(session.console_profile) === "supported";
  const spanish = locale === "es-CO";
  const inferredActive = currentStep(session);
  const active = steps?.filter(step => step.id !== "polar").findIndex((step) => step.status === "current") ?? -1;
  const activeNumber = active >= 0 ? active + 1 : inferredActive;
  const labels = spanish
    ? ["Identificación", "KSS", "PVT", "Instrucciones", "Práctica", "Bloques", "Preguntas", "Completar"]
    : ["Participant ID", "KSS", "PVT", "Briefing", "Practice", "Mission blocks", "Questions", "Complete"];

  return (
    <section className="mission-panel p-3" aria-label={spanish ? "Secuencia de la visita" : "Visit sequence"}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className={modern ? "text-sm text-info" : "page-kicker text-info"}>{spanish ? "Su secuencia" : "Your sequence"}</h2>
        <span className={`font-mono text-muted-foreground ${modern ? "text-sm" : "text-[9px]"}`}>{activeNumber}/{labels.length}</span>
      </div>
      <ol className="space-y-1">
        {labels.map((label, index) => {
          const number = index + 1;
          const aggregate = steps?.find((step) => step.id === ["welcome", "kss", "pvt", "briefing", "practice", "blocks", "workload", "complete"][index]);
          const complete = aggregate ? aggregate.complete : number < inferredActive;
          const current = aggregate ? aggregate.status === "current" : number === inferredActive;
          return (
            <li key={label} aria-current={current ? "step" : undefined} className={`flex items-center gap-2 rounded border px-2 py-2 ${modern ? "text-sm" : "text-[11px]"} ${current ? "border-white bg-white text-black" : complete ? "border-success/15 bg-success/5 text-success" : "border-transparent text-muted-foreground"}`}>
              <span className={`grid h-5 w-5 shrink-0 place-items-center rounded-full border border-current/30 font-mono ${modern ? "text-sm" : "text-[8px]"}`}>{complete ? <Check className="h-3 w-3" /> : current ? number : <Circle className="h-2 w-2" />}</span>
              <span className="leading-tight">{label}</span>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
