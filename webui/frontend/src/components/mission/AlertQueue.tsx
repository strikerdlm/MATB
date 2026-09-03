"use client";

import React from "react";
import type { AlertSnapshot, Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { Button } from "@/components/ui/button";

interface AlertQueueProps { alerts: AlertSnapshot[]; locale: Locale; onAcknowledge: (alert: AlertSnapshot) => void; readOnly?: boolean; }
const rank: Record<AlertSnapshot["severity"], number> = { FATAL: 0, CRITICAL: 1, ADVISORY: 2 };
export function sortAlerts(alerts: AlertSnapshot[]): AlertSnapshot[] {
  return [...alerts].sort((left, right) => ((left.acknowledged ? 2 : 0) + rank[left.severity]) - ((right.acknowledged ? 2 : 0) + rank[right.severity]) || left.opened_sequence - right.opened_sequence || left.alert_id.localeCompare(right.alert_id));
}
export function AlertQueue({ alerts, locale, onAcknowledge, readOnly = false }: AlertQueueProps) {
  return <section aria-labelledby="mission-alert-heading" className="flex min-h-0 flex-1 flex-col"><div className="border-b border-white/10 px-4 py-3"><div className="page-kicker">{t(locale, "mission.signals")} / {alerts.filter((alert) => !alert.acknowledged && alert.closed_sequence === null).length.toString().padStart(2, "0")}</div><h2 id="mission-alert-heading" className="mt-1 font-display text-lg uppercase tracking-wide">{t(locale, "mission.alerts")}</h2></div><ol className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">{sortAlerts(alerts).map((alert) => <li key={alert.alert_id} data-alert-id={alert.alert_id} className={`rounded border p-3 ${alert.acknowledged ? "border-white/10 opacity-60" : alert.severity === "CRITICAL" || alert.severity === "FATAL" ? "border-danger/50 bg-danger/5" : "border-warning/40 bg-warning/5"}`}><div className="flex items-start justify-between gap-2"><div><div className="font-mono text-[10px] uppercase tracking-wide text-muted-foreground">{t(locale, `alert.${alert.severity.toLowerCase()}` as never)}</div><div className="mt-1 text-sm font-semibold">{t(locale, `alert.${alert.kind.toLowerCase()}` as never)}</div></div>{!alert.acknowledged && !readOnly && <Button type="button" size="sm" variant="outline" onClick={() => onAcknowledge(alert)}>{t(locale, "command.acknowledge_alert")}</Button>}</div><div className="mt-2 font-mono text-[10px] text-muted-foreground">{alert.entity_ids.join(" · ") || t(locale, "common.system")}</div></li>)}</ol></section>;
}
