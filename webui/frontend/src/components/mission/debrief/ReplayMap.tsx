"use client";
import type { TrafficFrame } from "@/lib/geography/types";
import { resolveExposure, type ExposureEvent } from "@/lib/simulation/presentation/state";
import React, { useState } from "react";
import { MissionPresentation } from "../presentation/MissionPresentation";
import type { ReplayFrame } from "./ReplayTimeline";
import type {
  DebriefView,
  Locale,
  SessionView,
  WorldSnapshot,
} from "@/types/simulation";
import type {
  CameraMode,
  CameraPose,
  PresentationConfig,
} from "@/lib/simulation/presentation/contracts";
export function ReplayMap({
  debrief,
  frame,
  locale,
}: {
  debrief: DebriefView;
  frame: ReplayFrame | null;
  locale: Locale;
}) {
  const [recorded, setRecorded] = useState(true);
  const [exposureSequence, setExposureSequence] = useState<number>(Infinity);
  if (!frame?.snapshot || !frame.snapshot.terrain || !frame.snapshot.aircraft)
    return null;
  const snapshot = frame.snapshot as unknown as WorldSnapshot;
  const events = Array.isArray(debrief.presentation_events)
    ? debrief.presentation_events
    : [];
  const event = events
    .filter(
      (item) =>
        item &&
        typeof item === "object" &&
        !Array.isArray(item) &&
        item.block_id === frame.block_id &&
        typeof item.simulation_time_ms === "number" &&
        item.simulation_time_ms <= frame.simulation_time_ms &&
        (item.kind === "camera" ||
          item.kind === "ready" ||
          item.kind === "render" ||
          item.kind === "fallback"),
    )
    .at(-1);
  const data =
    event && typeof event === "object" && !Array.isArray(event) ? event : {};
  const camera = (data.camera ?? "overview") as CameraMode;
  const exposures = (events as unknown as ExposureEvent[]).filter(e => e && (e.version === 2 || e.version === 3));
  const resolved = resolveExposure(exposures, snapshot.block_id, frame.simulation_time_ms, exposureSequence === Infinity ? Number(frame.presentation_sequence ?? Infinity) : exposureSequence);
  const atTime = exposures.filter(e => e.block_id === frame.block_id && e.simulation_time_ms === frame.simulation_time_ms);
  const config = debrief.presentation as unknown as PresentationConfig | null;
  const trafficFrames = (Array.isArray(debrief.traffic_frames)
    ? debrief.traffic_frames
    : []) as unknown as TrafficFrame[];
  const traffic = trafficFrames
    .filter(
      (t) =>
        t.block_id === snapshot.block_id &&
        (t.simulation_time_ms ?? 0) <= frame.simulation_time_ms,
    )
    .at(-1);
  const session = {
    id: String(debrief.session_id ?? "replay"),
    console_profile: debrief.console_profile,
    presentation:
      config && data.kind === "fallback"
        ? { ...config, blocks: { ...config.blocks, [snapshot.block_id]: "2d" } }
        : config,
    session_mode: "research",
    lifecycle: "FINISHED",
  } as SessionView;
  return (
    <div className="mt-4">
      <label>
        <input
          type="checkbox"
          checked={recorded}
          onChange={(e) => setRecorded(e.target.checked)}
        />
        {locale === "es-CO" ? "Cámara registrada" : "Recorded camera mode"}
      </label>
      {(config?.version ?? 1) < 2 && <p>{locale === "es-CO" ? "Registro v1: capas operativas y selección observada desconocidas." : "V1 recording: operational layers and observed selection are unknown."}</p>}
      {!recorded && <p>{locale === "es-CO" ? "Exploración de reproducción; no representa la vista registrada." : "Replay exploration; this is not the recorded participant view."}</p>}
      {atTime.length > 1 && <select aria-label={locale === "es-CO" ? "Cambio de presentación" : "Presentation change"} value={exposureSequence} onChange={e => setExposureSequence(Number(e.target.value))}>
        <option value={Infinity}>{locale === "es-CO" ? "Último cambio" : "Latest change"}</option>
        {atTime.map(e => <option key={e.sequence} value={e.sequence}>{e.sequence} · {e.kind}</option>)}
      </select>}
      {recorded && resolved?.viewport && <p>{locale === "es-CO" ? "Resolución registrada" : "Recorded viewport"}: {resolved.viewport.width} × {resolved.viewport.height} · DPR {resolved.viewport.dpr}. {locale === "es-CO" ? "Movimiento reconstruido; la densidad de píxeles depende del dispositivo actual." : "Reconstructed motion; pixel density depends on the current device."}</p>}
      {recorded && resolved && resolved.visibility !== "visible" ? <p role="status">{locale === "es-CO" ? "Presentación oculta o no disponible" : "Presentation hidden or unavailable"}</p> : <MissionPresentation
        key={snapshot.block_id}
        session={session}
        snapshot={snapshot}
        locale={locale}
        readOnly
        replay
        traffic={traffic}
        selectedAircraftId={
          typeof data.aircraft_id === "string" ? data.aircraft_id : null
        }
        replayState={recorded ? resolved : undefined}
        replayCamera={recorded ? resolved?.camera ?? camera : undefined}
        replayPose={
          recorded &&
          Array.isArray(data.camera_position) &&
          Array.isArray(data.camera_quaternion)
            ? ({
                camera_position: data.camera_position,
                camera_quaternion: data.camera_quaternion,
              } as unknown as CameraPose)
            : undefined
        }
      />}
    </div>
  );
}
