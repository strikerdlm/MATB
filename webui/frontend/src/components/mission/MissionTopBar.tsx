"use client";

import React, { useState } from "react";
import { Pause, Play, Flag, Radio, ShieldAlert } from "lucide-react";
import type { ConnectionMode, Locale, SessionView } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { consoleProfileStatus } from "@/lib/simulation/console-profile";
import { Button } from "@/components/ui/button";

interface MissionTopBarProps {
  session: SessionView;
  locale: Locale;
  connection: ConnectionMode;
  canControl: boolean;
  onStart: () => void;
  onPause: () => void;
  onResume: () => void;
  onFinish: () => void;
  busy?: boolean;
}

const connectionTone: Record<ConnectionMode, string> = {
  live: "text-success",
  reconnecting: "text-warning",
  paused: "text-warning",
  observer: "text-info",
  disconnected: "text-muted-foreground",
};

export function MissionTopBar({ session, locale, connection, canControl, onStart, onPause, onResume, onFinish, busy = false }: MissionTopBarProps) {
  const [confirmFinish, setConfirmFinish] = useState(false);
  const lifecycleKey = `lifecycle.${session.lifecycle.toLowerCase()}` as never;
  const connectionKey = `connection.${connection}` as never;
  const isPrepared = session.lifecycle === "PREPARED";
  const isRunning = session.lifecycle === "RUNNING";
  const isPaused = session.lifecycle === "PAUSED";
  const protocolGateActive = ["ISA_ACTIVE", "SAGAT_ACTIVE", "POST_BLOCK_ACTIVE"].includes(session.protocol_phase ?? "");
  const readyForNextBlock = isPaused && session.protocol_phase === "READY_FOR_BLOCK";
  const modern = consoleProfileStatus(session.console_profile) === "supported";
  const administrativeButton = modern ? "text-sm normal-case tracking-normal" : undefined;
  const technical = session.record_class === "technical_only";

  return (
    <header className="mission-panel flex min-h-[68px] flex-wrap items-center justify-between gap-3 rounded-none border-x-0 border-t-0 px-4 py-3 lg:px-6">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex h-9 w-9 items-center justify-center border border-success/40 bg-success/10 text-success" aria-hidden="true"><Radio className="h-4 w-4" /></div>
        <div className="min-w-0">
          <div className={`flex flex-wrap items-center gap-2 font-mono text-muted-foreground ${modern ? "text-sm" : "text-[10px] uppercase tracking-[0.18em]"}`}>
            <span>{t(locale, "mission.label")} {session.id}</span><span aria-hidden="true">·</span><span>{session.active_block_id ?? t(locale, "mission.ready")}</span>
          </div>
          <div className={`mt-1 flex flex-wrap items-center gap-3 text-sm font-semibold text-foreground ${modern ? "" : "uppercase tracking-wide"}`}>
            {technical
              ? <><span className="text-warning">{locale === "es-CO" ? (modern ? "Modo técnico" : "MODO TÉCNICO") : (modern ? "Technical mode" : "TECHNICAL MODE")}</span><span>{session.selected_block_id}</span></>
              : <span>{session.participant_id}</span>}
            <span className={connectionTone[connection]} aria-label={t(locale, "a11y.connection", { status: t(locale, connectionKey) })}>
              <span className="mr-1.5 inline-block h-2 w-2 rounded-full bg-current align-middle" aria-hidden="true" />{t(locale, connectionKey)}
            </span>
            <span className={`font-mono text-muted-foreground ${modern ? "text-sm" : "text-xs"}`}>{t(locale, lifecycleKey)}</span>
          </div>
        </div>
      </div>
      <div className="flex items-center gap-2">
        {(isPrepared || readyForNextBlock) && <Button className={administrativeButton} type="button" size="sm" onClick={onStart} disabled={!canControl || busy}><Play className="mr-2 h-3.5 w-3.5" aria-hidden="true" />{t(locale, "lifecycle.start")}</Button>}
        {isRunning && <Button className={administrativeButton} type="button" size="sm" variant="warning" onClick={onPause} disabled={!canControl || busy}><Pause className="mr-2 h-3.5 w-3.5" aria-hidden="true" />{t(locale, "lifecycle.pause")}</Button>}
        {isPaused && !readyForNextBlock && <Button className={administrativeButton} type="button" size="sm" variant="success" onClick={onResume} disabled={!canControl || busy || protocolGateActive}><Play className="mr-2 h-3.5 w-3.5" aria-hidden="true" />{t(locale, "lifecycle.resume")}</Button>}
        {confirmFinish ? (
          <div className="flex items-center gap-1" role="group" aria-label={isPrepared ? (locale === "es-CO" ? "¿Cancelar esta sesión preparada?" : "Cancel this prepared session?") : t(locale, "confirm.finish")}>
            <Button className={administrativeButton} type="button" size="sm" variant="destructive" onClick={() => { setConfirmFinish(false); onFinish(); }} disabled={!canControl || busy}>{t(locale, "common.confirm")}</Button>
            <Button className={administrativeButton} type="button" size="sm" variant="ghost" aria-label={locale === "es-CO" ? "Mantener sesión" : "Keep session"} onClick={() => setConfirmFinish(false)}>×</Button>
          </div>
        ) : (
          <Button className={administrativeButton} type="button" size="sm" variant="outline" onClick={() => setConfirmFinish(true)} disabled={!canControl || busy || ["FINISHED", "ABORTED", "INTERRUPTED"].includes(session.lifecycle)}><Flag className="mr-2 h-3.5 w-3.5" aria-hidden="true" />{isPrepared ? (locale === "es-CO" ? "Cancelar sesión" : "Cancel session") : t(locale, "lifecycle.finish")}</Button>
        )}
        {!canControl && <span className="sr-only"><ShieldAlert />{t(locale, "mission.observer_disabled")}</span>}
      </div>
      {technical && <div className={`w-full border-t border-warning/20 pt-2 font-mono text-warning ${modern ? "text-sm" : "text-[10px] uppercase tracking-wider"}`}>{locale === "es-CO" ? "No apto para análisis de participantes" : "Not eligible for participant analysis"}</div>}
    </header>
  );
}
