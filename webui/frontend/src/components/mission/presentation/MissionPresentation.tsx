"use client";
import React, { useRef, useState, useEffect } from "react";
import { TrafficPanel } from "./TrafficPanel";
import dynamic from "next/dynamic";
import { MissionMap, type MissionMapProps } from "../map/MissionMap";
import type { SessionView, WorldSnapshot, Profile } from "@/types/simulation";
import type {
  CameraMode,
  CameraPose,
} from "@/lib/simulation/presentation/contracts";
import {
  sendPresentationEvent,
  getSimulationSession,
} from "@/lib/simulation/api";
import { useSimulationStore } from "@/lib/simulation/store";
const ThreeMissionView = dynamic(() => import("./ThreeMissionView"), {
  ssr: false,
});

export function preflightSnapshot(block: string): WorldSnapshot {
  return {
    block_id: block,
    scenario_id: "presentation-preflight",
    scenario_sha256: "",
    tick: 0,
    simulation_time_ms: 0,
    state_version: 0,
    state_sha256: "",
    title: { en: "", "es-CO": "" },
    description: { en: "", "es-CO": "" },
    terrain: {
      bounds: {
        min_x_mm: 0,
        min_y_mm: 0,
        max_x_mm: 12000000,
        max_y_mm: 8000000,
      },
      polygon: [],
    },
    home: { x_mm: 0, y_mm: 0 },
    initial_view: {
      center: { x_mm: 6000000, y_mm: 4000000 },
      width_mm: 12000000,
      height_mm: 8000000,
    },
    sectors: {},
    restricted_zones: {},
    report_note_codes: {},
    aircraft: {},
    contacts: {},
    alerts: {},
    coverage: {
      grid_cell_mm: 100000,
      origin: { x_mm: 0, y_mm: 0 },
      sectors: {},
    },
  };
}
interface Props extends MissionMapProps {
  session: SessionView;
  frozen?: boolean;
  lease?: string | null;
  replay?: boolean;
  replayCamera?: CameraMode;
  replayPose?: CameraPose;
}
export function MissionPresentation({
  session,
  frozen = false,
  lease,
  replay = false,
  replayCamera,
  replayPose,
  ...map
}: Props) {
  const block = (
    replay
      ? map.snapshot.block_id
      : session.protocol_phase === "READY_FOR_BLOCK" ||
          session.lifecycle === "PREPARED"
        ? (session.next_block_id ?? map.snapshot.block_id)
        : map.snapshot.block_id
  ) as Profile;
  const config = session.presentation;
  const liveTraffic = useSimulationStore((state) => state.traffic);
  const [selectedTrafficId, setSelectedTrafficId] = useState<string | null>(
    null,
  );
  const traffic = replay
    ? map.traffic
    : liveTraffic?.block_id === map.snapshot.block_id
      ? liveTraffic
      : null;
  const elapsed = Math.max(
    0,
    map.snapshot.simulation_time_ms -
      (traffic?.simulation_time_ms ?? map.snapshot.simulation_time_ms),
  );
  const trafficProps = {
    traffic,
    trafficElapsedMs: elapsed,
    selectedTrafficId,
    onSelectTraffic: frozen ? undefined : setSelectedTrafficId,
  };
  const [override, setOverride] = useState<"2d" | "3d" | null>(null),
    [error, setError] = useState<string | null>(null);
  const queue = useRef(Promise.resolve());
  const condition = override ?? config?.blocks[block] ?? "2d";
  const emit = (
    kind: "ready" | "camera" | "render" | "failure" | "fallback",
    camera: CameraMode,
    elapsed?: number,
    pose?: CameraPose,
  ) => {
    if (
      replay ||
      !lease ||
      !["PREPARED", "RUNNING", "PAUSED"].includes(session.lifecycle)
    )
      return;
    const event = {
      event_id: crypto.randomUUID(),
      kind,
      block_id: block,
      state_version: map.snapshot.state_version,
      simulation_time_ms: map.snapshot.simulation_time_ms,
      camera,
      aircraft_id: map.selectedAircraftId ?? null,
      traffic_frame_id: traffic?.frame_id ?? null,
      layers: config?.layers ?? [],
      scene_sha256: config?.scene_sha256 ?? null,
      receipt_to_render_ms: elapsed,
      ...pose,
    };
    queue.current = queue.current
      .then(() => sendPresentationEvent(session.id, lease, event))
      .then(async () => {
        if (kind === "failure")
          useSimulationStore.setState({
            session: await getSimulationSession(session.id),
          });
      })
      .catch((reason) => setError(String(reason)));
  };
  const emitRef = useRef(emit);
  emitRef.current = emit;
  useEffect(() => {
    if (traffic && condition === "2d" && !frozen)
      emitRef.current("render", "overview");
  }, [traffic, condition, frozen]);
  return (
    <div className="flex min-w-0 flex-col gap-2">
      {!replay &&
        session.session_mode === "interactive_technical" &&
        config?.scene_id && (
          <label className="p-2">
            {map.locale === "es-CO" ? "Presentación" : "Presentation"}{" "}
            <select
              className="bg-background p-2"
              value={condition}
              disabled={frozen}
              onChange={(event) => {
                const next = event.target.value as "2d" | "3d";
                setOverride(next);
                if (next === "2d") emit("fallback", "overview");
              }}
            >
              <option value="2d">2D</option>
              <option value="3d">3D</option>
            </select>
          </label>
        )}
      {error && (
        <p role="alert" className="text-warning">
          {error}
        </p>
      )}
      {condition === "3d" && config ? (
        <ThreeMissionView
          key={`${config.scene_sha256}:${block}`}
          {...map}
          {...trafficProps}
          config={config}
          frozen={frozen}
          replayCamera={replayCamera}
          replayPose={replayPose}
          onEvent={emit}
        />
      ) : (
        <MissionMap
          {...map}
          {...trafficProps}
          readOnly={map.readOnly || frozen}
          onSetWaypoint={map.readOnly || frozen ? undefined : map.onSetWaypoint}
        />
      )}
      {config?.traffic?.mode !== "off" && traffic && (
        <TrafficPanel
          frame={traffic}
          elapsed={elapsed}
          locale={map.locale}
          selected={selectedTrafficId}
          onSelect={frozen ? undefined : setSelectedTrafficId}
        />
      )}
    </div>
  );
}
