"use client";
import React, { useEffect, useState, useRef } from "react";
import Link from "next/link";
import { trafficRecordings } from "@/lib/geography/api";
import { GEOGRAPHY_LAYERS, type TrafficRecording } from "@/lib/geography/types";
import { listPresentationScenes } from "@/lib/simulation/api";
import type {
  PresentationConfig,
  SceneManifest,
} from "@/lib/simulation/presentation/contracts";
import type { Locale, Profile } from "@/types/simulation";
export function PresentationSetup({
  locale,
  value,
  onChange,
  allowLive = false,
  profiles = ["PRACTICE", "LOW", "MEDIUM", "HIGH"],
}: {
  allowLive?: boolean;
  locale: Locale;
  value?: PresentationConfig;
  onChange: (value: PresentationConfig | undefined) => void;
  profiles?: Profile[];
}) {
  const changeRef = useRef(onChange);
  changeRef.current = onChange;
  const [recordings, setRecordings] = useState<TrafficRecording[]>([]);
  const [scenes, setScenes] = useState<SceneManifest[]>([]);
  useEffect(() => {
    let active = true;
    void listPresentationScenes()
      .then((items) => {
        if (active) {
          setScenes(items);
          const id = sessionStorage.getItem("matb.geography.scene");
          const selected = items.find((item) => item.id === id);
          if (selected) {
            sessionStorage.removeItem("matb.geography.scene");
            changeRef.current({
              version: 2,
              scene_id: selected.id,
              scene_sha256: selected.sha256!,
              camera: "overview",
              blocks: { PRACTICE: "3d", LOW: "3d", MEDIUM: "3d", HIGH: "3d" },
              traffic: { mode: "off", provider: "adsb.lol" },
            });
          }
        }
      })
      .catch(() => {});
    void trafficRecordings()
      .then((items) => {
        if (active) setRecordings(items);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);
  const es = locale === "es-CO";
  return (
    <fieldset className="mission-panel space-y-2 p-4">
      <legend>
        {es
          ? "Condición de presentación por bloque"
          : "Presentation condition per block"}
      </legend>
      <Link href="/colombia" className="block text-info underline">
        {es
          ? "Explorar Colombia y preparar un área"
          : "Explore Colombia and prepare an area"}
      </Link>
      <label>
        {es ? "Escena local" : "Local scene"}{" "}
        <select
          className="bg-background p-2"
          value={value?.scene_id ?? ""}
          onChange={(e) => {
            const scene = scenes.find((s) => s.id === e.target.value);
            onChange(
              scene
                ? {
                    version: 2,
                    scene_id: scene.id,
                    scene_sha256: scene.sha256!,
                    camera: "overview",
                    blocks: {},
                  }
                : undefined,
            );
          }}
        >
          <option value="">{es ? "Mapa 2D" : "2D map"}</option>
          {scenes.map((scene) => (
            <option key={scene.id} value={scene.id}>
              {scene.title}
            </option>
          ))}
        </select>
      </label>
      {value?.version === 2 && <div className="flex flex-wrap gap-3">
        {(["smooth_camera", "contact_cycling", "adjustable_layers"] as const).map(name => <label key={name}>
          <input type="checkbox" checked={value.controls?.[name] ?? false} onChange={event => onChange({ ...value, controls: { smooth_camera: false, contact_cycling: false, adjustable_layers: false, ...value.controls, [name]: event.target.checked } })} />
          {es ? { smooth_camera: "Transiciones de cámara", contact_cycling: "Navegación de contactos", adjustable_layers: "Capas ajustables" }[name] : { smooth_camera: "Camera transitions", contact_cycling: "Contact navigation", adjustable_layers: "Adjustable layers" }[name]}
        </label>)}
      </div>}
      {value && (
        <div className="flex flex-wrap gap-3">
          {profiles.map((profile) => (
            <label key={profile}>
              {profile}{" "}
              <select
                className="bg-background p-2"
                value={value.blocks[profile] ?? "2d"}
                onChange={(e) =>
                  onChange({
                    ...value,
                    blocks: {
                      ...value.blocks,
                      [profile]: e.target.value as "2d" | "3d",
                    },
                  })
                }
              >
                <option value="2d">2D</option>
                <option value="3d">3D</option>
              </select>
            </label>
          ))}
        </div>
      )}
      {value && (
        <div className="space-y-3 border-t border-white/10 pt-3">
          <label className="block">
            {es ? "Tráfico observado" : "Observed traffic"}{" "}
            <select
              aria-label={es ? "Modo de tráfico" : "Traffic mode"}
              className="bg-background p-2"
              value={value.traffic?.mode ?? "off"}
              onChange={(e) => {
                const mode = e.target.value as "off" | "live" | "recorded";
                const recording = recordings.find(
                  (r) =>
                    r.scene_id === value.scene_id &&
                    r.scene_sha256 === value.scene_sha256,
                );
                onChange({
                  ...value,
                  traffic: {
                    mode,
                    provider: value.traffic?.provider ?? "adsb.lol",
                    recording_id: mode === "recorded" ? recording?.id : null,
                    recording_sha256:
                      mode === "recorded" ? recording?.sha256 : null,
                  },
                });
              }}
            >
              <option value="off">{es ? "Desactivado" : "Off"}</option>
              {allowLive && (
                <option value="live">{es ? "En vivo" : "Live"}</option>
              )}
              <option
                value="recorded"
                disabled={
                  !recordings.some(
                    (r) =>
                      r.scene_id === value.scene_id &&
                      r.scene_sha256 === value.scene_sha256,
                  )
                }
              >
                {es ? "Grabación de tráfico real" : "Recorded real traffic"}
              </option>
            </select>
          </label>
          {value.traffic?.mode === "live" && (
            <label>
              {es ? "Proveedor" : "Provider"}{" "}
              <select
                className="bg-background p-2"
                value={value.traffic.provider}
                onChange={(e) =>
                  onChange({
                    ...value,
                    traffic: {
                      ...value.traffic!,
                      provider: e.target.value as "adsb.lol" | "opensky",
                    },
                  })
                }
              >
                <option value="adsb.lol">adsb.lol</option>
                <option value="opensky">OpenSky (OAuth)</option>
              </select>
            </label>
          )}
          {value.traffic?.mode === "recorded" && (
            <label>
              {es ? "Grabación" : "Recording"}{" "}
              <select
                className="bg-background p-2"
                value={value.traffic.recording_id ?? ""}
                onChange={(e) => {
                  const r = recordings.find((r) => r.id === e.target.value)!;
                  onChange({
                    ...value,
                    traffic: {
                      mode: "recorded",
                      provider: r.provider as "adsb.lol" | "opensky",
                      recording_id: r.id,
                      recording_sha256: r.sha256,
                    },
                  });
                }}
              >
                {recordings
                  .filter(
                    (r) =>
                      r.scene_id === value.scene_id &&
                      r.scene_sha256 === value.scene_sha256,
                  )
                  .map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.title} · {Math.round(r.duration_ms / 1000)} s
                    </option>
                  ))}
              </select>
            </label>
          )}
          <div className="flex flex-wrap gap-3">
            {GEOGRAPHY_LAYERS.map((layer) => (
              <label key={layer}>
                <input
                  type="checkbox"
                  checked={(value.layers ?? GEOGRAPHY_LAYERS).includes(layer)}
                  onChange={() => {
                    const current = value.layers ?? GEOGRAPHY_LAYERS;
                    onChange({
                      ...value,
                      layers: current.includes(layer)
                        ? current.filter((l) => l !== layer)
                        : [...current, layer],
                    });
                  }}
                />{" "}
                {es
                  ? {
                      roads: "Vías",
                      rivers: "Ríos",
                      settlements: "Poblaciones",
                      boundaries: "Límites",
                      airports: "Aeródromos",
                    }[layer]
                  : layer}
              </label>
            ))}
          </div>
          {!allowLive && (
            <p className="text-xs text-muted-foreground">
              {es
                ? "Los bloques de investigación usan grabaciones verificadas; capture tráfico en modo técnico."
                : "Research blocks use verified recordings; capture traffic in technical mode."}
            </p>
          )}
        </div>
      )}
      {!scenes.length && (
        <p className="text-xs">
          {es
            ? "No hay paquetes geográficos verificados instalados."
            : "No verified geographic packages are installed."}
        </p>
      )}
    </fieldset>
  );
}
