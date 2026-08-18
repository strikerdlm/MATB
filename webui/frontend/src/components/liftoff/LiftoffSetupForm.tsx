"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Radio, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { createStudyContext, getStudyContext } from "@/lib/api";
import { createLiftoffSession, getLiftoffReadiness } from "@/lib/liftoff/api";
import type { Participant, StudyParticipantContext, StudyProtocol } from "@/types";

export function LiftoffSetupForm({
  participants,
  protocol,
}: {
  participants: Participant[];
  protocol: StudyProtocol;
}) {
  const router = useRouter();
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [build, setBuild] = useState("freeze-before-collection");
  const [controllerFirmware, setControllerFirmware] = useState("record-at-setup");
  const [polarConfirmed, setPolarConfirmed] = useState(true);
  const [performanceReason, setPerformanceReason] = useState("polar_unavailable");
  const [readiness, setReadiness] = useState<{ ready: boolean; valid_packets: number } | null>(null);
  const [context, setContext] = useState<StudyParticipantContext | null>(null);
  const [contextLoading, setContextLoading] = useState(false);
  const [taskSequence, setTaskSequence] = useState<"MATB_LIFTOFF" | "LIFTOFF_MATB">("MATB_LIFTOFF");
  const [priorFpvHours, setPriorFpvHours] = useState("0");
  const [gamingHours, setGamingHours] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getLiftoffReadiness()
      .then(setReadiness)
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : "Telemetry readiness could not be read."));
  }, []);

  useEffect(() => {
    let active = true;
    setContext(null);
    if (!participantId) return () => { active = false; };
    setContextLoading(true);
    void getStudyContext(participantId)
      .then((value) => { if (active) setContext(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : "Study context could not be read."); })
      .finally(() => { if (active) setContextLoading(false); });
    return () => { active = false; };
  }, [participantId]);

  async function prepare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!participantId || !visitOrdinal || !readiness?.ready) return;
    setBusy(true);
    setError(null);
    try {
      if (!context) {
        const created = await createStudyContext(participantId, {
          task_sequence: taskSequence,
          prior_fpv_hours: Number(priorFpvHours),
          gaming_hours_per_week: Number(gamingHours),
        });
        setContext(created);
      }
      const session = await createLiftoffSession({
        participant_id: participantId,
        visit_ordinal: Number(visitOrdinal),
        configuration: {
          liftoff_build: build,
          track_id: "astra-neutral-time-trial-v1",
          drone_id: "astra-standard-quad-v1",
          flight_mode: "acro",
          camera_angle_deg: 25,
          fov_deg: 110,
          rates_profile: "astra-v1",
          controller_model: "research-rc",
          controller_firmware: controllerFirmware,
          resolution: "1920x1080",
          refresh_rate_hz: 120,
          graphics_preset: "medium",
          damage_enabled: false,
          battery_enabled: false,
          telemetry_profile: "liftoff-telemetry-all-v1",
        },
        polar_recording_confirmed: polarConfirmed,
        performance_only_reason: polarConfirmed ? null : performanceReason,
      });
      sessionStorage.setItem(`matb.liftoff.${session.id}.lease`, session.controller_lease);
      router.push(`/liftoff/session?session=${encodeURIComponent(session.id)}`);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "Session preparation failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={prepare} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Card>
        <CardHeader>
          <p className="page-kicker">Manual FPV collection</p>
          <CardTitle className="font-display uppercase tracking-wide">Freeze the run configuration</CardTitle>
          <CardDescription>Participant, visit, simulator build, controller, and physiology mode become immutable at preparation.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="liftoff-participant">Participant</Label>
            <select id="liftoff-participant" aria-label="Participant" className="native-select w-full" value={participantId} onChange={(event) => setParticipantId(event.target.value)}>
              <option value="">Select…</option>
              {participants.map((participant) => <option key={participant.id} value={participant.id}>{participant.id}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="liftoff-visit">Visit</Label>
            <select id="liftoff-visit" aria-label="Visit" className="native-select w-full" value={visitOrdinal} onChange={(event) => setVisitOrdinal(event.target.value)}>
              <option value="">Select…</option>
              {protocol.visits.map((visit) => <option key={visit.ordinal} value={visit.ordinal}>{visit.code} · day {visit.scheduled_day}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="liftoff-build">Liftoff build</Label>
            <Input id="liftoff-build" value={build} onChange={(event) => setBuild(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="controller-firmware">Controller firmware</Label>
            <Input id="controller-firmware" value={controllerFirmware} onChange={(event) => setControllerFirmware(event.target.value)} />
          </div>
          {!context && participantId && !contextLoading ? (
            <div className="grid gap-4 border border-white/10 bg-white/[0.02] p-4 sm:col-span-2 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="task-sequence">Task sequence</Label>
                <select id="task-sequence" className="native-select w-full" value={taskSequence} onChange={(event) => setTaskSequence(event.target.value as typeof taskSequence)}>
                  <option value="MATB_LIFTOFF">MATB → Liftoff</option>
                  <option value="LIFTOFF_MATB">Liftoff → MATB</option>
                </select>
              </div>
              <div className="space-y-2"><Label htmlFor="fpv-hours">Prior FPV hours</Label><Input id="fpv-hours" type="number" min="0" value={priorFpvHours} onChange={(event) => setPriorFpvHours(event.target.value)} /></div>
              <div className="space-y-2"><Label htmlFor="gaming-hours">Gaming hours/week</Label><Input id="gaming-hours" type="number" min="0" value={gamingHours} onChange={(event) => setGamingHours(event.target.value)} /></div>
            </div>
          ) : null}
          <label className="flex items-center gap-3 border border-white/10 p-3 text-sm sm:col-span-2">
            <input type="checkbox" checked={polarConfirmed} onChange={(event) => setPolarConfirmed(event.target.checked)} />
            Polar H10 recording is running
          </label>
          {!polarConfirmed ? <div className="space-y-2 sm:col-span-2"><Label htmlFor="performance-reason">Performance-only reason</Label><Input id="performance-reason" value={performanceReason} onChange={(event) => setPerformanceReason(event.target.value)} /></div> : null}
          {error ? <p role="alert" className="text-sm text-danger sm:col-span-2">{error}</p> : null}
          <Button className="sm:col-span-2" disabled={busy || contextLoading || !participantId || !visitOrdinal || !readiness?.ready || !build || !controllerFirmware}>
            {busy ? "Preparing…" : "Prepare Liftoff session"}
          </Button>
        </CardContent>
      </Card>
      <aside aria-label="Liftoff readiness" className="space-y-4">
        <div className={`mission-panel p-5 ${readiness?.ready ? "border-success/40" : "border-warning/40"}`}>
          <div className="flex items-center gap-2">
            {readiness?.ready ? <CheckCircle2 className="h-5 w-5 text-success" /> : <Radio className="h-5 w-5 text-warning" />}
            <p className="font-display text-lg uppercase">{readiness?.ready ? "Telemetry ready" : "Waiting for telemetry"}</p>
          </div>
          <p className="mt-2 font-mono text-xs text-muted-foreground">{readiness?.valid_packets ?? 0} / 20 valid packets</p>
        </div>
        <div className="flex gap-3 border border-warning/30 bg-warning/5 p-4 text-sm text-warning">
          <ShieldAlert className="h-5 w-5 shrink-0" /> Research instrument only. No readiness or fitness decision is produced.
        </div>
      </aside>
    </form>
  );
}
