"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { Activity, BatteryMedium, Bluetooth, Clock3, ShieldAlert, Square } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  abortClassicSession,
  getClassicSession,
  getPolarStatus,
  polarPreflight,
  startClassicSession,
} from "@/lib/classic/api";
import type { ClassicSessionView, PolarStatus } from "@/types/classic";

const PHASES = [
  { status: "BASELINE", label: "Baseline", durationSeconds: 300 },
  { status: "TASK", label: "MATB task", durationSeconds: 900 },
  { status: "RECOVERY", label: "Recovery", durationSeconds: 300 },
] as const;
const TERMINAL = new Set(["COMPLETE", "ABORTED", "INTERRUPTED"]);

function reasonMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

function formatClock(seconds: number): string {
  const safe = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(safe / 60)).padStart(2, "0")}:${String(safe % 60).padStart(2, "0")}`;
}

function phaseStart(session: ClassicSessionView, status: string): string | null {
  if (status === "BASELINE") return session.baseline_started_at;
  if (status === "TASK") return session.task_started_at;
  if (status === "RECOVERY") return session.recovery_started_at;
  return null;
}

function phaseOrdinal(status: string | undefined): number {
  if (status === "BASELINE") return 0;
  if (status === "TASK") return 1;
  if (status === "POST_TASK" || status === "RECOVERY") return 2;
  if (status === "FINALIZING" || status === "COMPLETE") return 3;
  return -1;
}

function nanosecondsToMilliseconds(value: string | null | undefined): number | null {
  if (!value) return null;
  try {
    return Number(BigInt(value) / BigInt(1_000_000));
  } catch {
    return null;
  }
}

export function ClassicSessionConsole({ sessionId }: { sessionId: string }) {
  const { push } = useRouter();
  const [session, setSession] = useState<ClassicSessionView | null>(null);
  const [polar, setPolar] = useState<PolarStatus | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [busy, setBusy] = useState<"start" | "abort" | "preflight" | null>(null);
  const [abortReason, setAbortReason] = useState("participant_requested_stop");
  const [error, setError] = useState<string | null>(null);
  const [preflightNotice, setPreflightNotice] = useState<string | null>(null);
  const lease = typeof window === "undefined"
    ? null
    : sessionStorage.getItem(`matb.classic.${sessionId}.lease`);

  useEffect(() => {
    let active = true;
    const refresh = async () => {
      try {
        const [sessionView, polarView] = await Promise.all([
          getClassicSession(sessionId),
          getPolarStatus(),
        ]);
        if (!active) return;
        setSession(sessionView);
        setPolar(polarView);
        if (TERMINAL.has(sessionView.status)) {
          sessionStorage.removeItem(`matb.classic.${sessionId}.lease`);
          push(`/classic/debrief?session=${encodeURIComponent(sessionId)}`);
        }
      } catch (reason: unknown) {
        if (active) setError(reasonMessage(reason, "Session state could not be read."));
      }
    };
    void refresh();
    const poll = window.setInterval(() => void refresh(), 1_000);
    const clock = window.setInterval(() => setNow(Date.now()), 1_000);
    return () => {
      active = false;
      window.clearInterval(poll);
      window.clearInterval(clock);
    };
  }, [push, sessionId]);

  const activePhase = useMemo(
    () => PHASES.find((phase) => phase.status === session?.status) ?? null,
    [session?.status],
  );
  const elapsedSeconds = useMemo(() => {
    if (!session || !activePhase) return 0;
    const started = phaseStart(session, activePhase.status);
    if (!started) return 0;
    return Math.max(0, (now - new Date(started).getTime()) / 1_000);
  }, [activePhase, now, session]);
  const remainingSeconds = activePhase
    ? Math.max(0, activePhase.durationSeconds - elapsedSeconds)
    : 0;
  const progress = activePhase
    ? Math.min(100, elapsedSeconds * 100 / activePhase.durationSeconds)
    : 0;
  const postTaskActive = session?.status === "POST_TASK";
  const postTaskElapsedSeconds = postTaskActive && session?.task_finished_at
    ? Math.max(0, (now - new Date(session.task_finished_at).getTime()) / 1_000)
    : 0;
  const postTaskRemainingSeconds = postTaskActive && session
    ? Math.max(0, session.post_task_timeout_seconds - postTaskElapsedSeconds)
    : 0;
  const preflightMeasuredAtMs = nanosecondsToMilliseconds(polar?.last_rr_at_utc_ns);
  const preflightRemainingSeconds = polar?.preflight_ready && preflightMeasuredAtMs !== null
    ? Math.max(0, 120 - (now - preflightMeasuredAtMs) / 1_000)
    : null;
  const preflightFresh = polar?.preflight_ready === true
    && preflightRemainingSeconds !== null
    && preflightRemainingSeconds > 0;

  async function start() {
    if (!lease) {
      setError("Controller lease is missing. Return to classic MATB setup.");
      return;
    }
    setBusy("start");
    setError(null);
    try {
      setSession(await startClassicSession(sessionId, lease));
      setNow(Date.now());
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Classic MATB protocol could not be started."));
    } finally {
      setBusy(null);
    }
  }

  async function abort() {
    if (!lease) {
      setError("Controller lease is missing. Return to classic MATB setup.");
      return;
    }
    setBusy("abort");
    setError(null);
    try {
      const view = await abortClassicSession(
        sessionId,
        lease,
        abortReason,
      );
      setSession(view);
      sessionStorage.removeItem(`matb.classic.${sessionId}.lease`);
      push(`/classic/debrief?session=${encodeURIComponent(sessionId)}`);
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Session abort could not be recorded."));
    } finally {
      setBusy(null);
    }
  }

  async function refreshPreflight() {
    setBusy("preflight");
    setError(null);
    setPreflightNotice(null);
    try {
      const result = await polarPreflight(8);
      setPolar((current) => current ? {
        ...current,
        preflight_ready: result.ready,
        last_rr_at_utc_ns: result.ready ? result.measured_at_utc_ns : null,
        sensor_contact_detected: result.sensor_contact_detected,
        last_error_code: result.reason_code,
      } : current);
      if (result.ready) {
        setPreflightNotice(`RR preflight refreshed · ${result.heart_rate_bpm ?? "—"} bpm · ${result.rr_count} RR`);
      } else {
        setError(`Polar RR preflight did not pass: ${result.reason_code ?? "live RR unavailable"}.`);
      }
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Polar RR preflight could not be refreshed."));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="mission-grid min-h-screen p-4 sm:p-7">
      <div className="mx-auto max-w-7xl space-y-5">
        <header className="mission-panel flex flex-col gap-5 p-5 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <p className="page-kicker">Classic MATB · synchronized physiology</p>
            <h1 className="page-title mt-2">
              {session ? `${session.participant_id} · ${session.workload_level}` : "Loading session"}
            </h1>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <Badge variant={session?.status === "COMPLETE" ? "success" : "outline"}>
                {session?.status ?? "Loading"}
              </Badge>
              {session?.test_mode ? (
                <Badge variant="danger">TEST MODE · {session.wall_time_scale}× wall time</Badge>
              ) : null}
              {session ? <span className="font-mono text-xs text-muted-foreground">Attempt {session.attempt_number} · visit {session.visit_ordinal}</span> : null}
            </div>
          </div>
          <div className="flex items-end gap-6">
            <div className="text-right">
              <p className="page-kicker">{postTaskActive ? "Questionnaire limit" : "Phase remaining"}</p>
              <p className="mt-1 font-mono text-4xl tabular-nums">
                {activePhase
                  ? formatClock(remainingSeconds)
                  : postTaskActive
                    ? formatClock(postTaskRemainingSeconds)
                    : session?.status === "PREPARED" ? "25:00" : "--:--"}
              </p>
            </div>
            <Activity className={`mb-1 h-8 w-8 ${polar?.recording ? "text-success" : "text-muted-foreground"}`} />
          </div>
        </header>

        <ol className="grid gap-3 md:grid-cols-3" aria-label="Automatic collection phases">
          {PHASES.map((phase, index) => {
            const phaseIndex = phaseOrdinal(session?.status);
            const active = phase.status === session?.status;
            const complete = phaseIndex > index || session?.status === "FINALIZING" || session?.status === "COMPLETE";
            return (
              <li
                key={phase.status}
                className={`mission-panel p-5 ${active ? "border-white shadow-[0_0_50px_rgb(255_255_255/0.08)]" : complete ? "border-success/30" : "border-white/10"}`}
              >
                <div className="flex items-center justify-between gap-3">
                  <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">Phase {index + 1}</p>
                  <span className={`h-2 w-2 rounded-full ${active ? "animate-pulse bg-white" : complete ? "bg-success" : "bg-white/15"}`} />
                </div>
                <p className="mt-3 font-display text-2xl uppercase">{phase.label}</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">{phase.durationSeconds / 60} minutes</p>
                {active ? (
                  <div className="mt-4 h-1 overflow-hidden bg-white/10" aria-label={`${phase.label} progress`}>
                    <div className="h-full bg-white transition-[width]" style={{ width: `${progress}%` }} />
                  </div>
                ) : null}
              </li>
            );
          })}
        </ol>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <section className="mission-panel p-6">
            <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="page-kicker">Operator control</p>
                <h2 className="mt-2 font-display text-3xl uppercase">
                  {session?.status === "PREPARED"
                    ? "Ready to begin"
                    : postTaskActive
                      ? "Post-task questionnaire"
                      : "Automatic phase control is active"}
                </h2>
                <p className="mt-3 max-w-2xl text-sm leading-6 text-muted-foreground">
                  {session?.status === "PREPARED"
                    ? "Start only when the participant is seated, the Polar strap is stable, and the OpenMATB display is ready. Allow up to 35 minutes: a 25-minute collection plus up to 10 minutes for the post-task questionnaire. Phase boundaries are written automatically."
                    : session?.status === "TASK"
                      ? "OpenMATB is running in its native window. Do not close it; performance and synchronized events are being captured."
                      : postTaskActive
                        ? "Task physiology is closed. Complete the post-task questionnaire within the 10-minute response limit; recovery begins immediately afterward."
                      : "RR intervals and clock anchors are being recorded continuously. No manual phase marker is required."}
                </p>
              </div>
              <Clock3 className="h-7 w-7 shrink-0 text-muted-foreground" />
            </div>

            {error ? (
              <p role="alert" className="mt-5 border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p>
            ) : null}
            {preflightNotice ? (
              <p role="status" className="mt-5 border border-success/40 bg-success/10 p-3 text-sm text-success">{preflightNotice}</p>
            ) : null}

            <div className="mt-6 flex flex-wrap gap-3">
              {session?.status === "PREPARED" ? (
                <>
                  <Button onClick={start} disabled={busy !== null}>
                    {busy === "start" ? "Starting acquisition…" : "Start 25-minute collection"}
                  </Button>
                  {!session.performance_only_override ? (
                    <Button variant="outline" onClick={refreshPreflight} disabled={busy !== null || polar?.state !== "connected"}>
                      {busy === "preflight" ? "Checking live RR…" : "Recheck Polar RR"}
                    </Button>
                  ) : null}
                </>
              ) : null}
              {!session || !TERMINAL.has(session.status) ? (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="grid gap-1 font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
                    Abort reason
                    <select
                      className="h-10 border border-white/20 bg-background px-3 text-xs text-foreground"
                      value={abortReason}
                      onChange={(event) => setAbortReason(event.target.value)}
                      disabled={busy !== null}
                    >
                      <option value="participant_requested_stop">Participant requested stop</option>
                      <option value="operator_safety_stop">Operator safety stop</option>
                      <option value="sensor_failure">Sensor failure</option>
                      <option value="software_failure">Software failure</option>
                    </select>
                  </label>
                  <Button variant="destructive" onClick={abort} disabled={busy !== null || !session}>
                    <Square className="mr-2 h-3.5 w-3.5" />
                    {busy === "abort" ? "Recording abort…" : "Abort session"}
                  </Button>
                </div>
              ) : null}
            </div>
          </section>

          <aside className="space-y-4">
            <section aria-label="Polar acquisition status" className="mission-panel p-5">
              <div className="flex items-center justify-between">
                <p className="page-kicker">Polar acquisition</p>
                <Bluetooth className={`h-4 w-4 ${polar?.state === "connected" ? "text-success" : "text-danger"}`} />
              </div>
              <p className="mt-3 truncate font-display text-xl uppercase">{polar?.connected_device_name ?? "No sensor"}</p>
              <dl className="mt-4 grid grid-cols-2 gap-2 text-xs">
                <div className="metric-tile"><dt className="page-kicker">State</dt><dd className="mt-2 font-mono uppercase">{polar?.state ?? "—"}</dd></div>
                <div className="metric-tile"><dt className="page-kicker">Battery</dt><dd className="mt-2 flex items-center gap-1 font-mono"><BatteryMedium className="h-3.5 w-3.5" />{polar?.battery_level ?? "—"}%</dd></div>
                <div className="metric-tile"><dt className="page-kicker">Recording</dt><dd className="mt-2 font-mono uppercase">{polar?.recording ? "Yes" : "No"}</dd></div>
                <div className="metric-tile"><dt className="page-kicker">Reconnects</dt><dd className="mt-2 font-mono">{polar?.reconnect_attempts ?? 0}</dd></div>
                <div className="metric-tile col-span-2">
                  <dt className="page-kicker">RR preflight</dt>
                  <dd className={`mt-2 font-mono uppercase ${preflightFresh ? "text-success" : "text-warning"}`}>
                    {preflightFresh
                      ? `Ready · ${Math.ceil(preflightRemainingSeconds ?? 0)}s remaining`
                      : polar?.preflight_ready ? "Expired · recheck before start" : "Not ready"}
                  </dd>
                </div>
              </dl>
            </section>
            <div className="flex gap-3 border border-warning/30 bg-warning/5 p-4 text-xs leading-5 text-warning">
              <ShieldAlert className="h-5 w-5 shrink-0" />
              Emergency stop preserves the partial attempt and its available RR and MATB evidence.
            </div>
          </aside>
        </div>
      </div>
    </div>
  );
}
