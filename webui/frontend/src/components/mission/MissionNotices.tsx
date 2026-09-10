"use client";

import React from "react";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import type { ConnectionMode, Locale } from "@/types/simulation";

export interface MissionNotice {
  severity: "success" | "info" | "warning" | "error";
  source: "command" | "lifecycle" | "connection" | "profile";
  message: string;
  action: string | null;
  resolution: "acknowledged" | "pending" | "resolved";
}

export function connectionNotice(connection: ConnectionMode, error: string | null, locale: Locale): MissionNotice | null {
  const es = locale === "es-CO";
  if (error) return { severity: "error", source: "connection", message: error, action: es ? "Espere la reconexión antes de enviar comandos." : "Wait for reconnection before sending commands.", resolution: "pending" };
  if (connection === "reconnecting" || connection === "disconnected") return { severity: "warning", source: "connection", message: es ? "Conexión no disponible." : "Connection unavailable.", action: es ? "Espere la reconexión automática." : "Wait for automatic reconnection.", resolution: "pending" };
  return null;
}

const tones = {
  success: "border-success/30 bg-success/5 text-success",
  info: "border-info/30 bg-info/5 text-info",
  warning: "border-warning/30 bg-warning/5 text-warning",
  error: "border-destructive/30 bg-destructive/5 text-destructive",
};
const icons = { success: CheckCircle2, info: Info, warning: AlertTriangle, error: XCircle };

export function MissionNotices({ notices, modern, legacyMessage }: { notices: MissionNotice[]; modern: boolean; legacyMessage?: string | null }) {
  if (!modern) return legacyMessage ? <div role="status" aria-live="polite" className="flex items-center gap-2 border-b border-warning/30 bg-warning/5 px-4 py-2 font-mono text-xs text-warning"><AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />{legacyMessage}</div> : null;
  return <>{notices.map(notice => {
    const Icon = icons[notice.severity];
    return <div key={notice.source} role={notice.severity === "error" ? "alert" : "status"} data-source={notice.source} data-severity={notice.severity} data-resolution={notice.resolution} className={`flex items-center gap-2 border-b px-4 py-2 text-sm ${tones[notice.severity]}`}>
      <Icon className="h-4 w-4 shrink-0" aria-hidden="true" /><span>{notice.message}{notice.action && <> {notice.action}</>}</span>
    </div>;
  })}</>;
}
