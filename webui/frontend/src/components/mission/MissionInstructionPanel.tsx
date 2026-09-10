"use client";

import React from "react";
import { AlertTriangle, Crosshair, Headphones, MousePointer2 } from "lucide-react";

import { consoleProfileStatus } from "@/lib/simulation/console-profile";
import { InstructionAudio } from "@/components/instructions/InstructionAudio";
import type { AircraftSnapshot, ContactSnapshot, Locale, SessionView } from "@/types/simulation";

function instructions(session: SessionView, locale: Locale): { eyebrow: string; title: string; items: string[] } {
  const es = locale === "es-CO";
  if (["ISA_ACTIVE", "SAGAT_ACTIVE", "POST_BLOCK_ACTIVE"].includes(session.protocol_phase ?? "")) {
    return {
      eyebrow: es ? "Acción requerida" : "Action required",
      title: es ? "Responda el instrumento" : "Answer the prompt",
      items: es
        ? ["Detenga los comandos.", "Lea la pregunta completa.", "Seleccione una respuesta y envíela para continuar."]
        : ["Stop issuing commands.", "Read the full question.", "Select and submit one answer to continue."],
    };
  }
  if (session.lifecycle === "PREPARED") {
    return {
      eyebrow: es ? "Qué hacer ahora" : "What to do now",
      title: es ? "Escuche y comience PRÁCTICA" : "Listen, then start PRACTICE",
      items: es
        ? ["Escuche las instrucciones una vez.", "Ubique aeronaves, sectores, contactos y alertas.", "Pulse INICIAR cuando el investigador lo indique."]
        : ["Listen to the instructions once.", "Locate aircraft, sectors, contacts, and alerts.", "Press START when the researcher tells you to begin."],
    };
  }
  if (session.lifecycle === "RUNNING") {
    return {
      eyebrow: es ? "Qué hacer ahora" : "What to do now",
      title: es ? "Mantenga la misión estable" : "Keep the mission stable",
      items: es
        ? ["Seleccione una aeronave en el mapa o en la flota.", "Use los botones inferiores para asignar, mantener o regresar.", "Revise alertas y procese contactos detectados."]
        : ["Select an aircraft on the map or in the fleet.", "Use the bottom buttons to assign, hold, or return.", "Monitor alerts and process detected contacts."],
    };
  }
  if (session.lifecycle === "PAUSED" && session.protocol_phase === "READY_FOR_BLOCK") {
    return {
      eyebrow: es ? "Siguiente bloque" : "Next block",
      title: es ? `Prepare ${session.next_block_id ?? "el siguiente bloque"}` : `Prepare ${session.next_block_id ?? "the next block"}`,
      items: es
        ? ["Compruebe que entiende el siguiente nivel.", "Descanse las manos hasta recibir la indicación.", "Pulse INICIAR para continuar."]
        : ["Confirm you understand the next level.", "Rest your hands until instructed.", "Press START to continue."],
    };
  }
  return {
    eyebrow: es ? "Misión en pausa" : "Mission paused",
    title: es ? "Espere la indicación" : "Wait for instruction",
    items: es ? ["No emita comandos.", "Mantenga visible esta pantalla.", "Reanude solamente cuando se le indique."] : ["Do not issue commands.", "Keep this screen visible.", "Resume only when instructed."],
  };
}
export function MissionInstructionPanel({ session, locale, selectedAircraft, selectedContact }: { session: SessionView; locale: Locale; selectedAircraft: AircraftSnapshot | null; selectedContact: ContactSnapshot | null }) {
  const content = instructions(session, locale);
  const modern = consoleProfileStatus(session.console_profile) === "supported";
  const es = locale === "es-CO";
  return (
    <section className="mission-panel border-info/25 p-4" aria-labelledby="mission-instruction-title">
      <div className="flex items-start justify-between gap-3">
        <div><p className={modern ? "text-sm text-info" : "page-kicker text-info"}>{content.eyebrow}</p><h2 id="mission-instruction-title" className={`mt-2 font-display text-xl font-semibold leading-tight ${modern ? "" : "uppercase"}`}>{content.title}</h2></div>
        <Headphones className="h-5 w-5 shrink-0 text-info" />
      </div>
      <ol className="mt-4 space-y-2">
        {content.items.map((item, index) => <li key={item} className="flex gap-2 text-sm leading-5"><span className="font-mono text-info">{index + 1}</span><span>{modern ? item.replace("INICIAR", "Iniciar").replace("START", "Start") : item}</span></li>)}
      </ol>
      <div className={`mt-4 border-t border-white/10 pt-4 ${modern ? "[&_button]:text-sm [&_button]:normal-case [&_button]:tracking-normal" : ""}`}>
        <InstructionAudio src={`/audio/instructions/mission-${es ? "es" : "en"}.mp3`} label={es ? "Escuchar instrucciones" : "Listen to instructions"} unavailableLabel={es ? "Audio no disponible" : "Audio unavailable"} />
      </div>
      <div className={`mt-4 rounded border border-white/10 bg-black/25 p-3 text-muted-foreground ${modern ? "text-sm" : "text-xs"}`}>
        {selectedAircraft ? <span className="flex items-center gap-2"><Crosshair className="h-3.5 w-3.5 text-success" />{es ? "Aeronave seleccionada" : "Selected aircraft"}: <strong className="text-foreground">{selectedAircraft.aircraft_id}</strong></span> : selectedContact ? <span className="flex items-center gap-2"><AlertTriangle className="h-3.5 w-3.5 text-warning" />{es ? "Contacto seleccionado" : "Selected contact"}: <strong className="text-foreground">{selectedContact.contact_id}</strong></span> : <span className="flex items-center gap-2"><MousePointer2 className="h-3.5 w-3.5" />{es ? "Seleccione un símbolo para mostrar comandos válidos." : "Select a symbol to reveal valid commands."}</span>}
      </div>
    </section>
  );
}
