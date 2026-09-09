"use client";
import type { TrafficFrame } from "@/lib/geography/types";
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
      <MissionPresentation
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
        replayCamera={recorded ? camera : undefined}
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
      />
    </div>
  );
}
