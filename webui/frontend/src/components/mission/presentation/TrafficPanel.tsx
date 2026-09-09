"use client";
import React from "react";
import type { Locale } from "@/types/simulation";
import type { TrafficFrame } from "@/lib/geography/types";
import { displayedTraffic } from "@/lib/geography/coordinates";
export function TrafficPanel({
  frame,
  elapsed = 0,
  locale,
  selected,
  onSelect,
}: {
  frame: TrafficFrame | null | undefined;
  elapsed?: number;
  locale: Locale;
  selected?: string | null;
  onSelect?: (id: string) => void;
}) {
  const es = locale === "es-CO",
    tracks = displayedTraffic(frame, elapsed),
    track = tracks.find((t) => t.id === selected);
  if (!frame) return null;
  const status: Record<string, string> = {
    live: es ? "Observaciones recientes" : "Recent observations",
    empty: es ? "Sin observaciones recibidas" : "No observations received",
    unavailable: es ? "Fuente no disponible" : "Source unavailable",
    throttled: es ? "Límite del proveedor" : "Provider rate limit",
  };
  return (
    <section
      aria-label={es ? "Tráfico observado" : "Observed traffic"}
      className="mission-panel space-y-2 p-3 text-sm"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <strong>
          {es ? "Tráfico observado" : "Observed traffic"} · {tracks.length}
        </strong>
        <span>
          {frame.provider} · {status[frame.status] ?? frame.status}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        {es
          ? "Posiciones estimadas hasta 15 s; antiguas después de 15 s; retiradas a los 60 s. Cobertura parcial."
          : "Positions estimated up to 15 s; stale after 15 s; removed at 60 s. Partial coverage."}
      </p>
      <div className="flex max-h-28 flex-wrap gap-1 overflow-auto">
        {tracks.slice(0, 100).map((t) => (
          <button
            type="button"
            key={t.id}
            onClick={() => onSelect?.(t.id)}
            aria-pressed={selected === t.id}
            className="rounded border border-amber-400/40 px-2 py-1 text-xs text-amber-200"
          >
            {t.callsign || t.id} · {Math.round(t.age_s)} s {t.stale ? "◷" : ""}
          </button>
        ))}
      </div>
      {track && (
        <dl className="grid grid-cols-2 gap-1 text-xs">
          <dt>{es ? "Identificación" : "Identifier"}</dt>
          <dd>{track.id}</dd>
          <dt>{es ? "Altitud geométrica" : "Geometric altitude"}</dt>
          <dd>
            {track.geometric_altitude_m === null
              ? "—"
              : `${Math.round(track.geometric_altitude_m)} m`}
          </dd>
          <dt>{es ? "Altitud barométrica" : "Barometric altitude"}</dt>
          <dd>
            {track.barometric_altitude_m === null
              ? "—"
              : `${Math.round(track.barometric_altitude_m)} m`}
          </dd>
          <dt>{es ? "Velocidad sobre el suelo" : "Ground speed"}</dt>
          <dd>
            {track.speed_mps === null
              ? "—"
              : `${Math.round(track.speed_mps * 1.94384)} kt`}
          </dd>
          <dt>{es ? "Última posición" : "Last position"}</dt>
          <dd>{new Date(track.observed_at * 1000).toISOString()}</dd>
        </dl>
      )}
      <p className="text-xs text-muted-foreground">{frame.attribution}</p>
    </section>
  );
}
