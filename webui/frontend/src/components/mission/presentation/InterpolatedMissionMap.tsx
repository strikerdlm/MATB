"use client";
import { useEffect, useState } from "react";
import { animateSnapshot } from "@/lib/simulation/presentation/interpolation-controller";
import { MissionMap, type MissionMapProps } from "../map/MissionMap";

/** SVG owns its animation state; command controls use the authoritative store. */
export function InterpolatedMissionMap(props: MissionMapProps) {
  const [frame, setFrame] = useState(props.snapshot);
  const enabled = Boolean(props.interpolate && !props.viewLocked && props.viewState?.interpolation_ms !== 0);
  useEffect(() => animateSnapshot(props.previousSnapshot, props.snapshot,
    enabled && !window.matchMedia("(prefers-reduced-motion: reduce)").matches, setFrame),
    [props.previousSnapshot, props.snapshot, enabled]);
  const snapshot = enabled && frame.block_id === props.snapshot.block_id ? frame : props.snapshot;
  const trafficElapsedMs = props.traffic ? Math.max(0, snapshot.simulation_time_ms - (props.traffic.simulation_time_ms ?? snapshot.simulation_time_ms)) : props.trafficElapsedMs;
  return <MissionMap {...props} snapshot={snapshot} trafficElapsedMs={trafficElapsedMs} />;
}
