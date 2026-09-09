import { GEOGRAPHY_LAYERS, type GeographyLayer } from "@/lib/geography/types";
import type { CameraMode, CameraPose, PresentationConfig } from "./contracts";
import { interpolatePose } from "./camera-controller";

export type Entity = { category: "aircraft" | "contact" | "observed"; id: string };
export type OperationalLayers = { routes: boolean; coverage: boolean; contacts: boolean; sensors: boolean; labels: boolean };
export interface ResolvedPresentation {
  version: 2;
  condition: "2d" | "3d";
  camera: CameraMode;
  focus: Entity | null;
  aircraft_id: string | null;
  contact_id: string | null;
  observed_id: string | null;
  navigation_category: Entity["category"];
  operational_layers: OperationalLayers;
  geographic_layers: GeographyLayer[];
  pose: CameraPose | null;
  map_view: { zoom: number; pan: { x: number; y: number } };
  viewport: { width: number; height: number; dpr: number } | null;
  visibility: "visible" | "hidden" | "concealed" | "unavailable";
  transition_ms: number;
  visual_profile: "standard-v1";
  model_version: "schematic-drone-v1-scale12";
  scene_sha256: string | null;
  capture_sha256: string | null;
}
export type PresentationAction =
  | { type: "camera"; camera: CameraMode; focus?: Entity | null }
  | { type: "selection"; entity: Entity | null }
  | { type: "layers"; layers: OperationalLayers }
  | { type: "geography"; layers: GeographyLayer[] }
  | { type: "resolved"; patch: Partial<ResolvedPresentation> };
export const DEFAULT_CONTROLS = { smooth_camera: false, contact_cycling: false, adjustable_layers: false };
export function initialPresentation(config: PresentationConfig | null | undefined, block: string, reducedMotion = false): ResolvedPresentation {
  return {
    version: 2, condition: config?.blocks[block as keyof PresentationConfig["blocks"]] ?? "2d",
    camera: config?.camera ?? "overview", focus: null, aircraft_id: null, contact_id: null, observed_id: null, navigation_category: "aircraft",
    operational_layers: { routes: true, coverage: true, contacts: true, sensors: true, labels: true },
    geographic_layers: [...(config?.layers ?? GEOGRAPHY_LAYERS)], pose: null,
    map_view: { zoom: 1, pan: { x: 0, y: 0 } }, viewport: null, visibility: "visible",
    transition_ms: config?.version === 2 && config.controls?.smooth_camera && !reducedMotion ? 600 : 0,
    visual_profile: "standard-v1", model_version: "schematic-drone-v1-scale12",
    scene_sha256: config?.scene_sha256 ?? null, capture_sha256: config?.traffic?.recording_sha256 ?? null,
  };
}
export function presentationReducer(state: ResolvedPresentation, action: PresentationAction): ResolvedPresentation {
  switch (action.type) {
    case "camera": return { ...state, camera: action.camera, focus: action.focus === undefined ? state.focus : action.focus };
    case "layers": return { ...state, operational_layers: action.layers };
    case "geography": return { ...state, geographic_layers: action.layers };
    case "selection": {
      const entity = action.entity;
      return { ...state, focus: entity,
        camera: entity && ((state.camera === "drone" && entity.category !== "aircraft") || (state.camera === "follow" && entity.category === "contact")) ? "overview" : state.camera,
        ...(entity?.category === "aircraft" ? { aircraft_id: entity.id } : {}),
        ...(entity?.category === "contact" ? { contact_id: entity.id } : {}),
        observed_id: entity?.category === "observed" ? entity.id : null };
    }
    case "resolved": return { ...state, ...action.patch };
  }
}
export function cycleEntity(ids: string[], selected: string | null, direction: -1 | 1): string | null {
  const ordered = [...new Set(ids)].sort();
  if (!ordered.length) return null;
  const index = selected === null ? -1 : ordered.indexOf(selected);
  return ordered[index < 0 ? (direction === 1 ? 0 : ordered.length - 1) : (index + direction + ordered.length) % ordered.length];
}
export interface ExposureEvent {
  version?: number; block_id: string; simulation_time_ms: number; sequence?: number;
  client_time_ms?: number; resolved?: ResolvedPresentation; kind?: string;
}
/** Full snapshots make backward seeks independent of the previously displayed block. */
export function resolveExposure(events: ExposureEvent[], block: string, time: number, sequence = Infinity): ResolvedPresentation | undefined {
  const ordered = events.filter(e => e.version === 2 && e.block_id === block)
    .sort((a, b) => a.simulation_time_ms - b.simulation_time_ms || (a.sequence ?? 0) - (b.sequence ?? 0));
  const previous = ordered.filter(e => e.simulation_time_ms <= time &&
    (e.simulation_time_ms < time || (e.sequence ?? 0) <= sequence))
    .at(-1);
  const next = ordered.find(e => e.simulation_time_ms > time);
  const state = previous?.resolved;
  if (!state || !previous || previous.simulation_time_ms === time || !next?.resolved) return state;
  const later = next.resolved;
  if (state.visibility !== "visible" || later.visibility !== "visible" || !state.pose || !later.pose ||
      state.camera !== later.camera || JSON.stringify(state.focus) !== JSON.stringify(later.focus) ||
      state.condition !== later.condition || !["render", "transition_end"].includes(next.kind ?? "")) return state;
  return { ...state, pose: interpolatePose(state.pose, later.pose,
    (time - previous.simulation_time_ms) / (next.simulation_time_ms - previous.simulation_time_ms)) };
}
