"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  BatteryMedium,
  Bluetooth,
  CheckCircle2,
  History,
  Radio,
  ShieldAlert,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  connectPolar,
  disconnectPolar,
  getClassicHistory,
  getClassicScenarios,
  getPolarStatus,
  polarPreflight,
  prepareClassicSession,
  scanPolar,
} from "@/lib/classic/api";
import type { Participant, StudyProtocol } from "@/types";
import type {
  ClassicScenario,
  ClassicSessionView,
  PolarDevice,
  PolarPreflight,
  PolarStatus,
  WorkloadLevel,
} from "@/types/classic";

type BusyAction = "scan" | "connect" | "disconnect" | "preflight" | "prepare" | null;

function reasonMessage(reason: unknown, fallback: string): string {
  return reason instanceof Error ? reason.message : fallback;
}

function statusVariant(ready: boolean): "success" | "warning" {
  return ready ? "success" : "warning";
}

export function ClassicSetupConsole({
  participants,
  protocol,
}: {
  participants: Participant[];
  protocol: StudyProtocol;
}) {
  const router = useRouter();
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [workload, setWorkload] = useState<WorkloadLevel>("LOW");
  const [scenarios, setScenarios] = useState<ClassicScenario[]>([]);
  const [polarStatus, setPolarStatus] = useState<PolarStatus | null>(null);
  const [preflight, setPreflight] = useState<PolarPreflight | null>(null);
  const [devices, setDevices] = useState<PolarDevice[]>([]);
  const [history, setHistory] = useState<ClassicSessionView[]>([]);
  const [performanceOnly, setPerformanceOnly] = useState(false);
  const [overrideReason, setOverrideReason] = useState("");
  const [busy, setBusy] = useState<BusyAction>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void Promise.all([getPolarStatus(), getClassicScenarios()])
      .then(([status, availableScenarios]) => {
        if (!active) return;
        setPolarStatus(status);
        setScenarios(availableScenarios);
      })
      .catch((reason: unknown) => {
        if (active) setError(reasonMessage(reason, "Classic MATB readiness could not be loaded."));
      });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    let active = true;
    if (!participantId || !visitOrdinal) {
      setHistory([]);
      return () => { active = false; };
    }
    void getClassicHistory(participantId, Number(visitOrdinal))
      .then((attempts) => { if (active) setHistory(attempts); })
      .catch((reason: unknown) => {
        if (active) setError(reasonMessage(reason, "Attempt history could not be loaded."));
      });
    return () => { active = false; };
  }, [participantId, visitOrdinal]);

  const scenario = useMemo(
    () => scenarios.find((candidate) => candidate.workload_level === workload),
    [scenarios, workload],
  );
  const physiologyReady = preflight?.ready === true || polarStatus?.preflight_ready === true;
  const exceptionReady = performanceOnly && overrideReason.trim().length > 0;
  const canPrepare = Boolean(
    participantId
    && visitOrdinal
    && scenario
    && (performanceOnly ? exceptionReady : physiologyReady)
    && busy === null,
  );

  async function scan() {
    setBusy("scan");
    setError(null);
    setDevices([]);
    try {
      setDevices(await scanPolar(5));
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Bluetooth scan failed."));
    } finally {
      setBusy(null);
    }
  }

  async function connect(device: PolarDevice) {
    setBusy("connect");
    setError(null);
    setPreflight(null);
    try {
      setPolarStatus(await connectPolar(device.device_token));
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Polar H10 connection failed."));
    } finally {
      setBusy(null);
    }
  }

  async function disconnect() {
    setBusy("disconnect");
    setError(null);
    try {
      setPolarStatus(await disconnectPolar());
      setPreflight(null);
      setDevices([]);
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Polar H10 disconnect failed."));
    } finally {
      setBusy(null);
    }
  }

  async function verifySignal() {
    setBusy("preflight");
    setError(null);
    try {
      const result = await polarPreflight(8);
      setPreflight(result);
      if (!result.ready) setError(result.reason_code ?? "A live RR interval was not received.");
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Live RR preflight failed."));
    } finally {
      setBusy(null);
    }
  }

  async function prepare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canPrepare || !scenario) return;
    setBusy("prepare");
    setError(null);
    try {
      const prepared = await prepareClassicSession({
        participant_id: participantId,
        visit_ordinal: Number(visitOrdinal),
        workload_level: workload,
        scenario_name: scenario.name,
        performance_only_override: performanceOnly,
        override_reason_code: performanceOnly ? overrideReason.trim() : null,
      });
      sessionStorage.setItem(`matb.classic.${prepared.id}.lease`, prepared.controller_lease);
      router.push(`/classic/session?session=${encodeURIComponent(prepared.id)}`);
    } catch (reason: unknown) {
      setError(reasonMessage(reason, "Classic MATB session preparation failed."));
      setBusy(null);
    }
  }

  return (
    <form onSubmit={prepare} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_25rem]">
      <div className="space-y-6">
        <Card>
          <CardHeader>
            <p className="page-kicker">Protocol configuration</p>
            <CardTitle className="font-display uppercase tracking-wide">Freeze the classic MATB attempt</CardTitle>
            <CardDescription>
              Participant, visit, workload scenario, and physiology mode become immutable when prepared.
            </CardDescription>
          </CardHeader>
          <CardContent className="grid gap-5 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="classic-participant">Participant</Label>
              <select
                id="classic-participant"
                aria-label="Participant"
                className="native-select w-full"
                value={participantId}
                onChange={(event) => setParticipantId(event.target.value)}
              >
                <option value="">Select…</option>
                {participants.map((participant) => (
                  <option key={participant.id} value={participant.id}>{participant.id}</option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="classic-visit">Visit</Label>
              <select
                id="classic-visit"
                aria-label="Visit"
                className="native-select w-full"
                value={visitOrdinal}
                onChange={(event) => setVisitOrdinal(event.target.value)}
              >
                <option value="">Select…</option>
                {protocol.visits.map((visit) => (
                  <option key={visit.ordinal} value={visit.ordinal}>
                    {visit.code} · day {visit.scheduled_day}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="classic-workload">Workload</Label>
              <select
                id="classic-workload"
                aria-label="Workload"
                className="native-select w-full"
                value={workload}
                onChange={(event) => setWorkload(event.target.value as WorkloadLevel)}
              >
                {(["LOW", "MEDIUM", "HIGH"] as const).map((level) => (
                  <option key={level} value={level}>{level}</option>
                ))}
              </select>
            </div>
            <div className="sm:col-span-3 border border-white/10 bg-white/[0.025] p-4">
              <p className="page-kicker">Scenario contract</p>
              <p className="mt-2 break-all font-mono text-sm text-foreground">
                {scenario?.name ?? "Loading allowlisted scenarios…"}
              </p>
              <p className="mt-2 text-xs leading-5 text-muted-foreground">
                Automatic sequence: 5 min baseline → 15 min classic MATB → up to 10 min post-task questionnaire → 5 min recovery. Allow up to 35 minutes total.
              </p>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <p className="page-kicker">Exception control</p>
            <CardTitle className="font-display uppercase tracking-wide">Physiology requirement</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <label className="flex items-start gap-3 border border-warning/30 bg-warning/5 p-4 text-sm">
              <input
                aria-label="Performance-only exception"
                type="checkbox"
                className="mt-1"
                checked={performanceOnly}
                onChange={(event) => setPerformanceOnly(event.target.checked)}
              />
              <span>
                <span className="block font-semibold text-warning">Use a performance-only exception</span>
                <span className="mt-1 block leading-5 text-muted-foreground">
                  No HRV metrics will be available. Use only when the sensor cannot be collected and retain the reason in the audit trail.
                </span>
              </span>
            </label>
            {performanceOnly ? (
              <div className="space-y-2">
                <Label htmlFor="classic-override-reason">Exception reason code</Label>
                <Input
                  id="classic-override-reason"
                  aria-label="Exception reason code"
                  placeholder="sensor_unavailable"
                  pattern={"[a-z0-9][a-z0-9_\\-]{0,63}"}
                  value={overrideReason}
                  onChange={(event) => setOverrideReason(event.target.value)}
                />
              </div>
            ) : null}
          </CardContent>
        </Card>

        {error ? (
          <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p>
        ) : null}
        <Button className="w-full sm:w-auto" disabled={!canPrepare}>
          {busy === "prepare" ? "Preparing immutable attempt…" : "Prepare classic MATB"}
        </Button>
      </div>

      <aside className="space-y-5">
        <section aria-label="Polar H10 acquisition" className="mission-panel p-5">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="page-kicker">Polar H10 acquisition</p>
              <h3 className="mt-2 font-display text-2xl uppercase">Signal link</h3>
            </div>
            <Badge variant={statusVariant(physiologyReady)}>
              {physiologyReady ? "RR verified" : polarStatus?.state ?? "Loading"}
            </Badge>
          </div>

          <div className="mt-5 grid grid-cols-2 gap-2">
            <div className="metric-tile">
              <p className="page-kicker">Heart rate</p>
              <p className="mt-2 font-display text-2xl">{preflight?.heart_rate_bpm ?? "—"}<span className="ml-1 text-xs text-muted-foreground">BPM</span></p>
            </div>
            <div className="metric-tile">
              <p className="page-kicker">Battery</p>
              <p className="mt-2 flex items-center gap-2 font-display text-2xl"><BatteryMedium className="h-4 w-4" />{preflight?.battery_level ?? polarStatus?.battery_level ?? "—"}%</p>
            </div>
          </div>

          <div className="mt-4 space-y-2">
            <Button type="button" variant="outline" className="w-full" onClick={scan} disabled={busy !== null || polarStatus?.state === "connected"}>
              <Bluetooth className="mr-2 h-4 w-4" />
              {busy === "scan" ? "Scanning BLE…" : "Scan for Polar H10"}
            </Button>
            {devices.map((device) => (
              <Button
                key={device.device_token}
                type="button"
                variant="secondary"
                className="h-auto w-full justify-between py-3"
                onClick={() => void connect(device)}
                disabled={busy !== null}
                aria-label={`Connect ${device.display_name}`}
              >
                <span className="truncate">Connect {device.display_name}</span>
                <span className="ml-3 font-mono text-[10px] text-muted-foreground">{device.rssi ?? "—"} dBm</span>
              </Button>
            ))}
            {polarStatus?.state === "connected" ? (
              <>
                <Button type="button" variant="success" className="w-full" onClick={verifySignal} disabled={busy !== null}>
                  <Radio className="mr-2 h-4 w-4" />
                  {busy === "preflight" ? "Waiting for live beat…" : "Verify live RR signal"}
                </Button>
                <Button type="button" variant="outline" className="w-full" onClick={disconnect} disabled={busy !== null}>
                  {busy === "disconnect" ? "Disconnecting…" : "Disconnect / switch sensor"}
                </Button>
              </>
            ) : null}
          </div>

          <div className="mt-4 border-t border-white/10 pt-4 text-xs leading-5 text-muted-foreground">
            {physiologyReady ? (
              <p className="flex gap-2 text-success"><CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" /> Live RR interval received; strap contact is acceptable.</p>
            ) : (
              <p className="flex gap-2"><Radio className="mt-0.5 h-4 w-4 shrink-0 text-warning" /> Wet the electrodes, wear the strap firmly, then verify a live RR notification.</p>
            )}
          </div>
        </section>

        <section aria-label="Prior attempts" className="mission-panel p-5">
          <div className="flex items-center gap-2">
            <History className="h-4 w-4 text-muted-foreground" />
            <p className="page-kicker">Prior attempts</p>
          </div>
          {!participantId || !visitOrdinal ? (
            <p className="mt-3 text-sm text-muted-foreground">Select a participant and visit to inspect retained retakes.</p>
          ) : history.length === 0 ? (
            <p className="mt-3 text-sm text-muted-foreground">No classic MATB attempts recorded for this visit.</p>
          ) : (
            <ol className="mt-3 space-y-2">
              {history.map((attempt) => (
                <li key={attempt.id} className="flex items-center justify-between border border-white/10 px-3 py-2 text-xs">
                  <span>Attempt {attempt.attempt_number} · {attempt.workload_level}</span>
                  <span className="font-mono text-muted-foreground">{attempt.status}</span>
                </li>
              ))}
            </ol>
          )}
        </section>

        <div className="flex gap-3 border border-warning/30 bg-warning/5 p-4 text-sm text-warning">
          <ShieldAlert className="h-5 w-5 shrink-0" />
          Research instrument only. HRV is descriptive and does not provide a diagnosis, readiness, or fitness decision.
        </div>
      </aside>
    </form>
  );
}
