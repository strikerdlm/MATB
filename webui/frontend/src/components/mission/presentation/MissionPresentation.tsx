"use client";
import { usePresentation } from "@/lib/simulation/presentation/use-presentation";
import { DEFAULT_CONTROLS, type ResolvedPresentation, type Entity } from "@/lib/simulation/presentation/state";
import { ContactNavigator } from "./ContactNavigator";
import { displayedTraffic } from "@/lib/geography/coordinates";
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
  replayState?: ResolvedPresentation;
}
export function MissionPresentation(props: Props) {
  const session = props.session;
  const block = props.replay ? props.snapshot.block_id :
    session.protocol_phase === "READY_FOR_BLOCK" || session.lifecycle === "PREPARED"
      ? session.next_block_id ?? props.snapshot.block_id : props.snapshot.block_id;
  return <MissionPresentationBlock key={`${session.id}:${block}:${!!props.replay}`} {...props} />;
}
function MissionPresentationBlock({
  session,
  frozen = false,
  lease,
  replay = false,
  replayCamera,
  replayPose,
  replayState,
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
  const view = usePresentation({ sessionId: session.id, block, lease, config, replay,
    time: map.snapshot.simulation_time_ms, stateVersion: map.snapshot.state_version,
    trafficFrame: traffic?.frame_id, active: ["PREPARED", "RUNNING", "PAUSED"].includes(session.lifecycle) });
  const resolved = replayState ?? view.state;
  const controls = config?.version === 2 ? config.controls ?? DEFAULT_CONTROLS : { ...DEFAULT_CONTROLS, adjustable_layers: true };
  const locked = frozen || !!view.error || !!replayState || (replay && replayCamera !== undefined) || (!replay && config?.version === 2 && !lease);
  const selectEntity = (entity: Entity, navigation = false) => {
    if (locked) return;
    view.dispatch({ type: "selection", entity }, navigation ? "navigate" : "selection");
    if (entity.category === "aircraft") map.onSelectAircraft?.(entity.id);
    if (entity.category === "contact") map.onSelectContact?.(entity.id);

  };
  const selectedTrafficId = resolved.observed_id;
  const setSelectedTrafficId = (id: string) => selectEntity({ category: "observed", id });
  const viewRef = useRef(view); viewRef.current = view;
  useEffect(() => {
    if (replay || frozen) return;
    const view = viewRef.current, focus = view.latest.current.focus;
    if (!focus || view.latest.current.camera !== "overview") return;
    const valid = focus.category === "observed" ? displayedTraffic(traffic, elapsed).some(t => t.id === focus.id)
      : focus.category === "aircraft" ? !!map.snapshot.aircraft[focus.id]
        : !!map.snapshot.contacts[focus.id]?.position && map.snapshot.contacts[focus.id]?.evidence !== "NONE";
    if (!valid) view.dispatch({ type: "resolved", patch: { focus: null, observed_id: null,
      ...(focus.category === "contact" ? { contact_id: null } : {}) } }, "selection");
  }, [traffic, elapsed, map.snapshot, replay, frozen]);
  useEffect(() => {
    const view = viewRef.current;
    if (replayState) return;
    const aircraft_id = map.selectedAircraftId ?? null, contact_id = map.selectedContactId ?? null;
    if (aircraft_id !== view.latest.current.aircraft_id || contact_id !== view.latest.current.contact_id)
      view.dispatch({ type: "resolved", patch: { aircraft_id, contact_id } }, "selection");
  }, [map.selectedAircraftId, map.selectedContactId, replayState]);
  const trafficProps = {
    traffic,
    trafficElapsedMs: elapsed,
    selectedTrafficId,
    onSelectTraffic: locked ? undefined : setSelectedTrafficId,
  };
  const [override, setOverride] = useState<"2d" | "3d" | null>(null),
    [error, setError] = useState<string | null>(null);
  const queue = useRef(Promise.resolve());
  const condition = replayState?.condition ?? override ?? resolved.condition;
  const emit = (
    kind: "ready" | "camera" | "render" | "failure" | "fallback",
    camera: CameraMode,
    elapsed?: number,
    pose?: CameraPose,
  ) => {
    if (config?.version === 2) {
      if (pose) view.dispatch({ type: "resolved", patch: { pose } }, kind);
      else if (kind === "failure") view.dispatch({ type: "resolved", patch: { visibility: "unavailable" } }, kind);
      else view.record(kind);
      return;
    }
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
      ...(pose ? { camera_position: pose.camera_position, camera_quaternion: pose.camera_quaternion } : {}),
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
                view.dispatch({ type: "resolved", patch: { condition: next } });
                if (next === "2d") emit("fallback", "overview");
              }}
            >
              <option value="2d">2D</option>
              <option value="3d">3D</option>
            </select>
          </label>
        )}
      {controls.adjustable_layers && config?.layers && <fieldset disabled={locked} className="flex flex-wrap gap-3 p-2">
        <legend>{map.locale === "es-CO" ? "Capas geográficas" : "Geographic layers"}</legend>
        {config.layers.map(layer => <label key={layer}><input type="checkbox" checked={resolved.geographic_layers.includes(layer)} onChange={() => view.dispatch({ type: "geography", layers: resolved.geographic_layers.includes(layer) ? resolved.geographic_layers.filter(l => l !== layer) : [...resolved.geographic_layers, layer] })} />
          {map.locale === "es-CO" ? { roads: "Vías", rivers: "Ríos", settlements: "Poblaciones", boundaries: "Límites", airports: "Aeródromos" }[layer] : layer}
        </label>)}
      </fieldset>}
      {view.error && <p role="alert">{view.error}</p>}
      {controls.contact_cycling && <ContactNavigator snapshot={map.snapshot} traffic={traffic} elapsed={elapsed} locale={map.locale} focus={resolved.focus} disabled={locked} category={resolved.navigation_category} onCategory={category => view.dispatch({ type: "resolved", patch: { navigation_category: category } }, "navigation_filter")} onSelect={entity => selectEntity(entity, true)} />}
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
          selectedAircraftId={replayState ? replayState.aircraft_id : map.selectedAircraftId}
          selectedContactId={replayState ? replayState.contact_id : map.selectedContactId}
          config={config}
          frozen={locked}
          replayCamera={replayCamera}
          replayPose={replayState?.pose ?? replayPose}
          viewState={resolved}
          onViewAction={view.dispatch}
          onSelectAircraft={locked ? undefined : id => selectEntity({ category: "aircraft", id })}
          onSelectContact={locked ? undefined : id => selectEntity({ category: "contact", id })}
          onEvent={emit}
        />
      ) : (
        <MissionMap
          {...map}
          {...trafficProps}
          selectedAircraftId={replayState ? replayState.aircraft_id : map.selectedAircraftId}
          selectedContactId={replayState ? replayState.contact_id : map.selectedContactId}
          viewState={resolved}
          onViewAction={view.dispatch}
          viewLocked={locked}
          layersLocked={!controls.adjustable_layers || locked}
          onSelectAircraft={locked ? undefined : id => selectEntity({ category: "aircraft", id })}
          onSelectContact={locked ? undefined : id => selectEntity({ category: "contact", id })}
          readOnly={map.readOnly || locked}
          onSetWaypoint={map.readOnly || frozen ? undefined : map.onSetWaypoint}
        />
      )}
      {config?.traffic?.mode !== "off" && traffic && (
        <TrafficPanel
          frame={traffic}
          elapsed={elapsed}
          locale={map.locale}
          selected={selectedTrafficId}
          onSelect={locked ? undefined : setSelectedTrafficId}
        />
      )}
    </div>
  );
}
