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
import { useAppLocale } from "@/lib/i18n";

export function LiftoffSetupForm({
  participants,
  protocol,
}: {
  participants: Participant[];
  protocol: StudyProtocol;
}) {
  const { copy } = useAppLocale();
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
      .catch((reason: unknown) => setError(reason instanceof Error ? reason.message : copy("No se pudo consultar la preparación de la telemetría.", "Telemetry readiness could not be read.")));
  }, [copy]);

  useEffect(() => {
    let active = true;
    setContext(null);
    if (!participantId) return () => { active = false; };
    setContextLoading(true);
    void getStudyContext(participantId)
      .then((value) => { if (active) setContext(value); })
      .catch((reason: unknown) => { if (active) setError(reason instanceof Error ? reason.message : copy("No se pudo consultar el contexto del estudio.", "Study context could not be read.")); })
      .finally(() => { if (active) setContextLoading(false); });
    return () => { active = false; };
  }, [copy, participantId]);

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
      setError(reason instanceof Error ? reason.message : copy("Falló la preparación de la sesión.", "Session preparation failed."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={prepare} className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
      <Card>
        <CardHeader>
          <p className="page-kicker">{copy("Recolección FPV manual", "Manual FPV collection")}</p>
          <CardTitle className="font-display uppercase tracking-wide">{copy("Fijar la configuración de la ejecución", "Freeze the run configuration")}</CardTitle>
          <CardDescription>{copy("El participante, la visita, la versión del simulador, el controlador y el modo de fisiología quedan inmutables al preparar.", "Participant, visit, simulator build, controller, and physiology mode become immutable at preparation.")}</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-5 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="liftoff-participant">{copy("Participante", "Participant")}</Label>
            <select id="liftoff-participant" aria-label={copy("Participante", "Participant")} className="native-select w-full" value={participantId} onChange={(event) => setParticipantId(event.target.value)}>
              <option value="">{copy("Seleccionar…", "Select…")}</option>
              {participants.map((participant) => <option key={participant.id} value={participant.id}>{participant.id}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="liftoff-visit">{copy("Visita", "Visit")}</Label>
            <select id="liftoff-visit" aria-label={copy("Visita", "Visit")} className="native-select w-full" value={visitOrdinal} onChange={(event) => setVisitOrdinal(event.target.value)}>
              <option value="">{copy("Seleccionar…", "Select…")}</option>
              {protocol.visits.map((visit) => <option key={visit.ordinal} value={visit.ordinal}>{visit.code} · {copy("día", "day")} {visit.scheduled_day}</option>)}
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="liftoff-build">{copy("Versión de Liftoff", "Liftoff build")}</Label>
            <Input id="liftoff-build" value={build} onChange={(event) => setBuild(event.target.value)} />
          </div>
          <div className="space-y-2">
            <Label htmlFor="controller-firmware">{copy("Firmware del controlador", "Controller firmware")}</Label>
            <Input id="controller-firmware" value={controllerFirmware} onChange={(event) => setControllerFirmware(event.target.value)} />
          </div>
          {!context && participantId && !contextLoading ? (
            <div className="grid gap-4 border border-white/10 bg-white/[0.02] p-4 sm:col-span-2 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="task-sequence">{copy("Secuencia de tareas", "Task sequence")}</Label>
                <select id="task-sequence" className="native-select w-full" value={taskSequence} onChange={(event) => setTaskSequence(event.target.value as typeof taskSequence)}>
                  <option value="MATB_LIFTOFF">MATB → Liftoff</option>
                  <option value="LIFTOFF_MATB">Liftoff → MATB</option>
                </select>
              </div>
              <div className="space-y-2"><Label htmlFor="fpv-hours">{copy("Horas FPV previas", "Prior FPV hours")}</Label><Input id="fpv-hours" type="number" min="0" value={priorFpvHours} onChange={(event) => setPriorFpvHours(event.target.value)} /></div>
              <div className="space-y-2"><Label htmlFor="gaming-hours">{copy("Horas de videojuegos/semana", "Gaming hours/week")}</Label><Input id="gaming-hours" type="number" min="0" value={gamingHours} onChange={(event) => setGamingHours(event.target.value)} /></div>
            </div>
          ) : null}
          <label className="flex items-center gap-3 border border-white/10 p-3 text-sm sm:col-span-2">
            <input type="checkbox" checked={polarConfirmed} onChange={(event) => setPolarConfirmed(event.target.checked)} />
            {copy("La grabación del Polar H10 está activa", "Polar H10 recording is running")}
          </label>
          {!polarConfirmed ? <div className="space-y-2 sm:col-span-2"><Label htmlFor="performance-reason">{copy("Razón para registrar solo desempeño", "Performance-only reason")}</Label><Input id="performance-reason" value={performanceReason} onChange={(event) => setPerformanceReason(event.target.value)} /></div> : null}
          {error ? <p role="alert" className="text-sm text-danger sm:col-span-2">{error}</p> : null}
          <Button className="sm:col-span-2" disabled={busy || contextLoading || !participantId || !visitOrdinal || !readiness?.ready || !build || !controllerFirmware}>
            {busy ? copy("Preparando…", "Preparing…") : copy("Preparar sesión de Liftoff", "Prepare Liftoff session")}
          </Button>
        </CardContent>
      </Card>
      <aside aria-label={copy("Preparación de Liftoff", "Liftoff readiness")} className="space-y-4">
        <div className={`mission-panel p-5 ${readiness?.ready ? "border-success/40" : "border-warning/40"}`}>
          <div className="flex items-center gap-2">
            {readiness?.ready ? <CheckCircle2 className="h-5 w-5 text-success" /> : <Radio className="h-5 w-5 text-warning" />}
            <p className="font-display text-lg uppercase">{readiness?.ready ? copy("Telemetría lista", "Telemetry ready") : copy("Esperando telemetría", "Waiting for telemetry")}</p>
          </div>
          <p className="mt-2 font-mono text-xs text-muted-foreground">{readiness?.valid_packets ?? 0} / 20 {copy("paquetes válidos", "valid packets")}</p>
        </div>
        <div className="flex gap-3 border border-warning/30 bg-warning/5 p-4 text-sm text-warning">
          <ShieldAlert className="h-5 w-5 shrink-0" /> {copy("Exclusivamente instrumento de investigación. No produce decisiones de aptitud ni preparación operacional.", "Research instrument only. No readiness or fitness decision is produced.")}
        </div>
      </aside>
    </form>
  );
}
