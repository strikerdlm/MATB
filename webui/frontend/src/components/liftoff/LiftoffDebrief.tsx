"use client";

import React, { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { sealLiftoffSession, submitLiftoffQuestionnaires, submitLiftoffResults } from "@/lib/liftoff/api";
import type { LiftoffDebriefView } from "@/types/liftoff";

export function LiftoffDebrief({ sessionId }: { sessionId: string }) {
  const [lapTimes, setLapTimes] = useState("");
  const [invalidLaps, setInvalidLaps] = useState("0");
  const [restarts, setRestarts] = useState("0");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [debrief, setDebrief] = useState<LiftoffDebriefView | null>(null);

  async function seal(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const lease = sessionStorage.getItem(`matb.liftoff.${sessionId}.lease`);
    if (!lease || !screenshot) { setError("Controller lease and result screenshot are required."); return; }
    const validLapTimes = lapTimes.split(",").map((value) => Number(value.trim())).filter((value) => Number.isFinite(value) && value > 0);
    setBusy(true);
    setError(null);
    try {
      await submitLiftoffResults(sessionId, lease, {
        valid_lap_times_s: validLapTimes,
        invalid_laps: Number(invalidLaps),
        observer_restart_count: Number(restarts),
      }, screenshot);
      await submitLiftoffQuestionnaires(sessionId, lease, {
        kss: 4,
        mental_demand: 50,
        physical_demand: 20,
        temporal_demand: 50,
        performance: 50,
        effort: 50,
        frustration: 20,
      });
      setDebrief(await sealLiftoffSession(sessionId, lease));
      sessionStorage.removeItem(`matb.liftoff.${sessionId}.lease`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Session seal failed.");
    } finally {
      setBusy(false);
    }
  }

  if (debrief) {
    return <div className="mission-panel p-6"><p className="page-kicker">Sealed evidence</p><h1 className="page-title mt-2">{debrief.validity}</h1><p className="mt-3 text-sm text-muted-foreground">Telemetry quality: {debrief.quality?.validity ?? "recorded"}. Component outcomes remain separate.</p></div>;
  }

  return (
    <form onSubmit={seal} className="mission-panel space-y-5 p-6">
      <div><p className="page-kicker">Visible-result verification</p><h1 className="page-title mt-2">Debrief and seal</h1></div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="space-y-2 md:col-span-3"><Label htmlFor="lap-times">Valid lap times (seconds, comma-separated)</Label><Input id="lap-times" aria-label="Valid lap times" value={lapTimes} onChange={(event) => setLapTimes(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="invalid-laps">Invalid laps</Label><Input id="invalid-laps" type="number" min="0" value={invalidLaps} onChange={(event) => setInvalidLaps(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="restart-count">Observer restarts</Label><Input id="restart-count" type="number" min="0" value={restarts} onChange={(event) => setRestarts(event.target.value)} /></div>
        <div className="space-y-2"><Label htmlFor="result-screen">Result screenshot</Label><Input id="result-screen" aria-label="Result screenshot" type="file" accept="image/png,image/jpeg" onChange={(event) => setScreenshot(event.target.files?.[0] ?? null)} /></div>
      </div>
      {error ? <p role="alert" className="text-sm text-danger">{error}</p> : null}
      <Button disabled={busy || !screenshot}>{busy ? "Sealing evidence…" : "Seal session"}</Button>
    </form>
  );
}
