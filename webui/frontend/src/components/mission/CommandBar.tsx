"use client";

import React, { useState } from "react";
import { Crosshair } from "lucide-react";

import { Button } from "@/components/ui/button";
import { t } from "@/lib/simulation/i18n";
import { validCommandsFor } from "@/lib/simulation/store";
import type { AircraftSnapshot, CommandKind, ContactSnapshot, Locale, WorldSnapshot } from "@/types/simulation";

interface CommandBarProps {
  snapshot: WorldSnapshot | null;
  selectedAircraft: AircraftSnapshot | null;
  selectedContact: ContactSnapshot | null;
  locale: Locale;
  readOnly?: boolean;
  pending?: boolean;
  waypointMode?: boolean;
  onWaypointMode?: () => void;
  onCommand: (kind: CommandKind, payload: Record<string, unknown>) => void;
}

export function CommandBar({ snapshot, selectedAircraft, selectedContact, locale, readOnly = false, pending = false, waypointMode = false, onWaypointMode, onCommand }: CommandBarProps) {
  const [confirmReturn, setConfirmReturn] = useState(false);
  const grouped = selectedAircraft && Object.values(snapshot?.swarms ?? {}).some(g => g.members.includes(selectedAircraft.aircraft_id));
  const aircraftKinds = grouped ? [] : validCommandsFor(selectedAircraft);
  const contactKinds = validCommandsFor(selectedContact);
  const disabled = readOnly || pending;
  const es = locale === "es-CO";

  const command = (kind: CommandKind, payload: Record<string, unknown>) => {
    onCommand(kind, payload);
    setConfirmReturn(false);
  };

  return (
    <footer className="mission-panel rounded-none border-x-0 border-b-0 px-4 py-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="page-kicker mr-2">{t(locale, "command.label")}</span>
        {grouped && <span className="text-xs">{es ? "Separe el miembro en Control del enjambre para mando individual." : "Detach this member in Swarm control for individual commands."}</span>}
        {selectedAircraft ? (
          <>
            <span className="mr-1 rounded border border-success/30 bg-success/5 px-2 py-1 font-mono text-xs text-success">{selectedAircraft.aircraft_id}</span>
            {aircraftKinds.includes("ASSIGN_SECTOR") && Object.keys(snapshot?.sectors ?? {}).sort().map((sectorId) => (
              <Button key={sectorId} type="button" size="sm" variant="outline" disabled={disabled} onClick={() => command("ASSIGN_SECTOR", { aircraft_id: selectedAircraft.aircraft_id, sector_id: sectorId })}>
                {t(locale, "command.assign_sector")} {sectorId.toUpperCase()}
              </Button>
            ))}
            {aircraftKinds.includes("SET_WAYPOINT") && (
              <Button type="button" size="sm" variant={waypointMode ? "default" : "outline"} aria-pressed={waypointMode} disabled={disabled} onClick={onWaypointMode}>
                <Crosshair className="mr-2 h-3.5 w-3.5" />{es ? "Fijar punto de ruta" : "Set waypoint"}
              </Button>
            )}
            {aircraftKinds.includes("HOLD") && <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => command("HOLD", { aircraft_id: selectedAircraft.aircraft_id })}>{t(locale, "command.hold")}</Button>}
            {aircraftKinds.includes("RESUME_MISSION") && <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => command("RESUME_MISSION", { aircraft_id: selectedAircraft.aircraft_id })}>{t(locale, "command.resume_mission")}</Button>}
            {aircraftKinds.includes("RETURN_TO_BASE") && (confirmReturn ? (
              <>
                <Button type="button" size="sm" variant="destructive" disabled={disabled} aria-label={t(locale, "command.confirm_return")} onClick={() => command("RETURN_TO_BASE", { aircraft_id: selectedAircraft.aircraft_id })}>{t(locale, "command.confirm_return")}</Button>
                <Button type="button" size="sm" variant="ghost" onClick={() => setConfirmReturn(false)}>×</Button>
              </>
            ) : <Button type="button" size="sm" variant="warning" disabled={disabled} onClick={() => setConfirmReturn(true)}>{t(locale, "command.return_to_base")}</Button>)}
          </>
        ) : selectedContact ? (
          <>
            <span className="mr-1 rounded border border-warning/30 bg-warning/5 px-2 py-1 font-mono text-xs text-warning">{selectedContact.contact_id}</span>
            {contactKinds.includes("INSPECT_CONTACT") && <Button type="button" size="sm" variant="outline" disabled={disabled} onClick={() => command("INSPECT_CONTACT", { contact_id: selectedContact.contact_id })}>{t(locale, "command.inspect_contact")}</Button>}
            {contactKinds.includes("CLASSIFY_CONTACT") && (["routine", "priority", "uncertain"] as const).map((classification) => <Button key={classification} type="button" size="sm" variant="outline" disabled={disabled} onClick={() => command("CLASSIFY_CONTACT", { contact_id: selectedContact.contact_id, classification })}>{es ? "Clasificar" : "Classify"}: {classification.toUpperCase()}</Button>)}
            {contactKinds.includes("SET_CONTACT_PRIORITY") && (["LOW", "MEDIUM", "HIGH"] as const).map((priority) => <Button key={priority} type="button" size="sm" variant="outline" disabled={disabled} onClick={() => command("SET_CONTACT_PRIORITY", { contact_id: selectedContact.contact_id, priority })}>{es ? "Prioridad" : "Priority"}: {priority}</Button>)}
            {contactKinds.includes("REPORT_CONTACT") && Object.keys(snapshot?.report_note_codes ?? { GENERAL: {} }).sort().map((noteCode) => <Button key={noteCode} type="button" size="sm" variant="outline" disabled={disabled} onClick={() => command("REPORT_CONTACT", { contact_id: selectedContact.contact_id, note_code: noteCode })}>{es ? "Reportar" : "Report"}: {snapshot?.report_note_codes[noteCode]?.[locale] ?? noteCode}</Button>)}
          </>
        ) : (
          <span className="text-sm text-muted-foreground">{t(locale, "command.select_target")}</span>
        )}
        {pending && <span role="status" className="ml-auto font-mono text-[10px] uppercase text-warning">{t(locale, "command.pending")}</span>}
      </div>
    </footer>
  );
}
