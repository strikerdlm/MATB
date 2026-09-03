"use client";

import React from "react";
import type { AircraftSnapshot, AlertSnapshot, Locale, WorldSnapshot } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";

interface FleetPanelProps {
  snapshot: WorldSnapshot | null;
  locale: Locale;
  selectedAircraftId: string | null;
  onSelect: (aircraftId: string) => void;
}

const modeKey = (mode: AircraftSnapshot["mode"]) => `mode.${mode.toLowerCase()}` as never;
const linkKey = (link: AircraftSnapshot["link"]) => `link.${link.toLowerCase()}` as never;

function highestAlert(aircraftId: string, alerts: AlertSnapshot[]): AlertSnapshot | null {
  const rank: Record<AlertSnapshot["severity"], number> = { FATAL: 3, CRITICAL: 2, ADVISORY: 1 };
  return alerts.filter((alert) => alert.entity_ids.includes(aircraftId) && alert.closed_sequence === null).sort((left, right) => (rank[right.severity] - rank[left.severity]) || left.opened_sequence - right.opened_sequence)[0] ?? null;
}

export function FleetPanel({ snapshot, locale, selectedAircraftId, onSelect }: FleetPanelProps) {
  const aircraft = Object.values(snapshot?.aircraft ?? {}).sort((left, right) => left.aircraft_id.localeCompare(right.aircraft_id));
  const alerts = Object.values(snapshot?.alerts ?? {});
  return (
    <aside className="mission-panel flex min-h-0 flex-col" aria-label={t(locale, "fleet.aircraft")}>
      <div className="border-b border-white/10 px-4 py-3"><div className="page-kicker">{t(locale, "mission.fleet")} / {aircraft.length.toString().padStart(2, "0")}</div><h2 className="mt-1 font-display text-lg uppercase tracking-wide">{t(locale, "fleet.aircraft")}</h2></div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2" role="list">
        {aircraft.length === 0 && <p className="p-4 text-sm text-muted-foreground">{t(locale, "mission.start_block_for_telemetry")}</p>}
        {aircraft.map((item) => {
          const alert = highestAlert(item.aircraft_id, alerts);
          return (
            <div key={item.aircraft_id} role="listitem" aria-label={`${item.aircraft_id} ${t(locale, linkKey(item.link))}`}>
              <button type="button" aria-pressed={selectedAircraftId === item.aircraft_id} onClick={() => onSelect(item.aircraft_id)} className={`mb-2 w-full rounded border p-3 text-left transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white ${selectedAircraftId === item.aircraft_id ? "border-white bg-white/[0.08]" : "border-white/10 bg-black/15 hover:border-white/25"}`}>
              <div className="flex items-center justify-between gap-2"><span className="font-mono text-sm font-semibold">{item.aircraft_id}</span><span className={`h-2 w-2 rounded-full ${item.link === "NOMINAL" ? "bg-success" : item.link === "DEGRADED" ? "bg-warning" : "bg-danger"}`} aria-hidden="true" /></div>
              <div className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] uppercase tracking-wide text-muted-foreground">
                <span>{t(locale, "fleet.mode")}</span><span className="text-right text-foreground">{t(locale, modeKey(item.mode))}</span>
                <span>{t(locale, "fleet.link")}</span><span className="text-right text-foreground">{t(locale, linkKey(item.link))}</span>
                <span>{t(locale, "fleet.battery")}</span><span className="text-right text-foreground">{item.energy_units.toLocaleString()}</span>
                <span>{t(locale, "fleet.sector")}</span><span className="text-right text-foreground">{item.assigned_sector_id ?? "—"}</span>
              </div>
              <div className="mt-2 h-1 overflow-hidden rounded bg-white/10"><div className={`h-full ${item.energy_units <= item.predicted_home_reserve_units ? "bg-danger" : "bg-success"}`} style={{ width: `${Math.max(3, Math.min(100, item.energy_units / 1000))}%` }} /></div>
              {alert && <div className="mt-2 font-mono text-[10px] uppercase tracking-wide text-danger">{t(locale, `alert.${alert.severity.toLowerCase()}` as never)} · {t(locale, `alert.${alert.kind.toLowerCase()}` as never)}</div>}
              </button>
            </div>
          );
        })}
      </div>
    </aside>
  );
}
