"use client";
import React, { useEffect, useRef, useState } from "react";
import type { MissionMapProps } from "../map/MissionMap";
import type {
  PresentationConfig,
  CameraMode,
  CameraPose,
} from "@/lib/simulation/presentation/contracts";
import { loadScene } from "@/lib/simulation/presentation/contracts";
import {
  createMissionScene,
  type SceneOptions,
} from "@/lib/simulation/presentation/scene";

export interface ThreeMissionViewProps extends MissionMapProps {
  config: PresentationConfig;
  frozen: boolean;
  onEvent?: (
    kind: "ready" | "camera" | "render" | "failure",
    camera: CameraMode,
    elapsed?: number,
    pose?: CameraPose,
  ) => void;
  replayCamera?: CameraMode;
  replayPose?: CameraPose;
}
export default function ThreeMissionView(props: ThreeMissionViewProps) {
  const host = useRef<HTMLDivElement>(null),
    current = useRef(props);
  current.current = props;
  const controller = useRef<Awaited<
    ReturnType<typeof createMissionScene>
  > | null>(null);
  const [error, setError] = useState<string | null>(null),
    [ready, setReady] = useState(false),
    [camera, setCamera] = useState<CameraMode>(props.config.camera);
  const [layers, setLayers] = useState({
    routes: true,
    coverage: true,
    contacts: true,
  });
  const lastLog = useRef(0),
    revision = useRef(0);
  const es = props.locale === "es-CO";
  const activeCamera = props.replayCamera ?? camera;
  const selected = props.selectedAircraftId
    ? props.snapshot.aircraft[props.selectedAircraftId]
    : Object.values(props.snapshot.aircraft)[0];
  const feedUnavailable =
    activeCamera === "drone" &&
    selected &&
    (selected.link === "LOST" || selected.sensor === "OFFLINE");
  const options = useRef<SceneOptions>({
    ...props,
    cameraMode: activeCamera,
    frozen: props.frozen,
    layers,
    geographicLayers: props.config.layers ?? [
      "roads",
      "rivers",
      "settlements",
      "boundaries",
      "airports",
    ],
    onFailure: () => {},
  });
  options.current = {
    ...props,
    cameraMode: activeCamera,
    layers,
    geographicLayers: props.config.layers ?? [
      "roads",
      "rivers",
      "settlements",
      "boundaries",
      "airports",
    ],
    onFailure: () => {
      setError(
        es
          ? "Se perdió la vista 3D. Recargue para verificarla antes de reanudar."
          : "3D view lost. Reload to verify it before resuming.",
      );
      setReady(false);
      current.current.onEvent?.("failure", activeCamera);
    },
    onRender: (_elapsed, pose) => {
      if (performance.now() - lastLog.current > 2000) {
        lastLog.current = performance.now();
        current.current.onEvent?.(
          "render",
          activeCamera,
          Math.max(0, performance.now() - revision.current),
          pose,
        );
      }
    },
  };
  useEffect(() => {
    const abort = new AbortController();
    let active = true;
    setError(null);
    setReady(false);
    void loadScene(current.current.config, abort.signal)
      .then(async (assets) => {
        if (!active || !host.current) return;
        const scene = await createMissionScene(
          host.current,
          assets,
          options.current,
        );
        if (!active) {
          scene.dispose();
          return;
        }
        controller.current = scene;
        if (new URLSearchParams(window.location.search).get("metrics") === "1")
          Object.assign(window, { __matbPresentationMetrics: scene.metrics });
        revision.current = performance.now();
        scene.update(options.current);
        setReady(true);
        current.current.onEvent?.("ready", options.current.cameraMode);
      })
      .catch((reason) => {
        if (active) {
          setError(reason instanceof Error ? reason.message : String(reason));
          current.current.onEvent?.("failure", options.current.cameraMode);
        }
      });
    return () => {
      active = false;
      abort.abort();
      controller.current?.dispose();
      controller.current = null;
      Reflect.deleteProperty(window, "__matbPresentationMetrics");
    };
  }, [props.config.scene_id, props.config.scene_sha256]); // Scene ownership changes only with its immutable package.
  useEffect(() => {
    revision.current = performance.now();
    try {
      controller.current?.update(options.current);
    } catch (reason) {
      setError(String(reason));
      setReady(false);
      current.current.onEvent?.("failure", activeCamera);
    }
  }, [
    props.snapshot,
    props.traffic,
    props.trafficElapsedMs,
    props.selectedTrafficId,
    props.selectedAircraftId,
    props.selectedContactId,
    props.readOnly,
    props.waypointAircraftId,
    props.frozen,
    props.replayPose,
    activeCamera,
    layers,
  ]);
  return (
    <section
      className="mission-panel flex min-w-0 flex-col"
      aria-label={es ? "Presentación geográfica" : "Geographic presentation"}
    >
      <div className="flex flex-wrap items-center gap-2 p-2">
        <label>
          {es ? "Cámara" : "Camera"}{" "}
          <select
            value={activeCamera}
            disabled={
              props.frozen || !ready || props.replayCamera !== undefined
            }
            onChange={(event) => {
              const value = event.target.value as CameraMode;
              setCamera(value);
              props.onEvent?.("camera", value);
            }}
            className="bg-background p-2"
          >
            <option value="overview">{es ? "General" : "Overview"}</option>
            <option value="follow">{es ? "Seguimiento" : "Follow"}</option>
            <option value="drone">
              {es ? "Cámara del dron" : "Drone camera"}
            </option>
          </select>
        </label>
        <button
          type="button"
          disabled={!ready || props.frozen}
          onClick={() => {
            setCamera("overview");
            controller.current?.reset();
            props.onEvent?.("camera", "overview");
          }}
        >
          {es ? "Restablecer" : "Reset"}
        </button>
        {(["routes", "coverage", "contacts"] as const).map((name) => (
          <label key={name} className="text-xs">
            <input
              type="checkbox"
              checked={layers[name]}
              disabled={props.frozen}
              onChange={() =>
                setLayers((previous) => ({
                  ...previous,
                  [name]: !previous[name],
                }))
              }
            />
            {es
              ? {
                  routes: "Rutas",
                  coverage: "Cobertura",
                  contacts: "Contactos",
                }[name]
              : name}
          </label>
        ))}
      </div>
      {!ready && !error && (
        <p role="status" className="p-3">
          {es
            ? "Verificando escena local y renderizador…"
            : "Verifying local scene and renderer…"}
        </p>
      )}
      {feedUnavailable && (
        <p role="status" className="p-3">
          {es
            ? "Cámara no disponible: enlace o sensor fuera de servicio."
            : "Camera unavailable: link or sensor offline."}
        </p>
      )}
      {error && (
        <p role="alert" className="p-3 text-warning">
          {error}
        </p>
      )}
      <div
        ref={host}
        className="relative min-h-[520px] flex-1 overflow-hidden"
        style={{
          height: 520,
          visibility: error || feedUnavailable ? "hidden" : "visible",
        }}
        data-testid="mission-three-view"
      />
      <p className="px-3 text-xs text-muted-foreground">
        {es
          ? "Imagen satelital de 10 m · Altura ilustrativa sobre terreno · Flechas: desplazar; +/−: zoom; 0: restablecer."
          : "10 m satellite imagery · Illustrative height above terrain · Arrows: pan; +/−: zoom; 0: reset."}
      </p>
      <p className="p-3 text-xs text-muted-foreground">
        Contains modified Copernicus Sentinel data. Terrain: Mapzen / Tilezen,
        SRTM. Geographic overlays: © OpenStreetMap contributors / OpenFreeMap /
        OurAirports.{" "}
        <a
          href="https://github.com/tilezen/joerd/blob/master/docs/attribution.md"
          target="_blank"
          rel="noreferrer"
        >
          {es ? "Atribución" : "Attribution"}
        </a>
      </p>
    </section>
  );
}
