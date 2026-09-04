"use client";

import React, { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { CheckCircle2, Radio, ShieldAlert } from "lucide-react";

import { experimentErrorMessage } from "@/lib/experiment-errors";
import { useExecutionPurpose } from "@/lib/execution-purpose";
import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { getStudyContext } from "@/lib/api";
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
  const { copy, locale } = useAppLocale();
  const purpose = useExecutionPurpose();
  const copyRef = useRef(copy);
  copyRef.current = copy;
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
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void getLiftoffReadiness()
      .then(setReadiness)
      .catch((reason: unknown) => setError(experimentErrorMessage(reason, copyRef.current)));
  }, []);

  useEffect(() => {
    let active = true;
    setContext(null);
    if (!participantId) return () => { active = false; };
    setContextLoading(true);
    void getStudyContext(participantId)
      .then((value) => { if (active) setContext(value); })
      .catch((reason: unknown) => { if (active) setError(experimentErrorMessage(reason, copyRef.current)); })
      .finally(() => { if (active) setContextLoading(false); });
    return () => { active = false; };
  }, [participantId]);

  async function prepare(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!participantId || !visitOrdinal || !readiness?.ready) return;
    setBusy(true);
    setError(null);
    try {
      const ready = await getLiftoffReadiness();
      setReadiness(ready);
      if (!ready.ready) throw new Error(copy("No se reciben datos de Liftoff. Abra el simulador y vuelva a comprobar.", "No Liftoff data is arriving. Open the simulator and check again."));
      if (purpose === "study" && !context) throw new Error(copy("Solicite al investigador que asigne su protocolo antes de iniciar.", "Ask the researcher to assign your protocol before starting."));
      const session = await createLiftoffSession({
        execution_purpose: purpose,
        locale,
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
      setError(experimentErrorMessage(reason, copyRef.current));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
    <ExperimentGuide id="liftoff" />
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
          {purpose === "study" && !context && participantId && !contextLoading && <p role="status" className="text-sm text-warning sm:col-span-2">{copy("Falta su protocolo asignado. El investigador debe registrar el contexto del estudio en Participantes.", "Your assigned protocol is missing. The researcher must register the study context in Participants.")}</p>}
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
    </form></>
  );
}
