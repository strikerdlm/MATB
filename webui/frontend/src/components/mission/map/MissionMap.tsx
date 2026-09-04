"use client";

import React, { useCallback, useMemo, useState } from "react";
import type { ContactSnapshot, Locale, WorldSnapshot } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { AircraftSymbol } from "./AircraftSymbol";
import { ContactSymbol } from "./ContactSymbol";
import { MapToolbar, type MapLayerState } from "./MapToolbar";
import { createProjection } from "./projection";

const VIEWPORT = { width: 1200, height: 800 } as const;
const MIN_ZOOM = 0.75;
const MAX_ZOOM = 6;

export interface MissionMapProps {
  snapshot: WorldSnapshot;
  locale: Locale;
  selectedAircraftId?: string | null;
  selectedContactId?: string | null;
  onSelectAircraft?: (aircraftId: string) => void;
  onSelectContact?: (contactId: string) => void;
  readOnly?: boolean;
  waypointAircraftId?: string | null;
  onSetWaypoint?: (aircraftId: string, waypoint: { x_mm: number; y_mm: number }) => void;
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value));
}

function statusLabel(locale: Locale, contact: ContactSnapshot) {
  const key = `contact.workflow_${contact.workflow.toLowerCase()}` as never;
  return t(locale, key);
}

export function MissionMap({
  snapshot,
  locale,
  selectedAircraftId = null,
  selectedContactId = null,
  onSelectAircraft,
  onSelectContact,
  waypointAircraftId = null,
  onSetWaypoint,
}: MissionMapProps) {
  const [zoom, setZoom] = useState(1);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [layers, setLayers] = useState<MapLayerState>({ routes: true, sensors: true, coverage: true, contacts: true, labels: true });
  const projection = useMemo(() => createProjection(snapshot.terrain.bounds, VIEWPORT), [snapshot.terrain.bounds]);

  const reset = useCallback(() => {
    setZoom(1);
    setPan({ x: 0, y: 0 });
  }, []);
  const zoomBy = useCallback((amount: number) => setZoom((value) => clamp(Number((value + amount).toFixed(2)), MIN_ZOOM, MAX_ZOOM)), []);
  const toggleLayer = useCallback((layer: keyof MapLayerState) => setLayers((current) => ({ ...current, [layer]: !current[layer] })), []);
  const panBy = useCallback((dx: number, dy: number) => {
    setPan((value) => ({ x: clamp(value.x + dx, -500, 500), y: clamp(value.y + dy, -500, 500) }));
  }, []);

  const onKeyDown = (event: React.KeyboardEvent<HTMLElement>) => {
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomBy(0.25); }
    else if (event.key === "-") { event.preventDefault(); zoomBy(-0.25); }
    else if (event.key === "0") { event.preventDefault(); reset(); }
    else if (event.key === "ArrowLeft") { event.preventDefault(); panBy(40, 0); }
    else if (event.key === "ArrowRight") { event.preventDefault(); panBy(-40, 0); }
    else if (event.key === "ArrowUp") { event.preventDefault(); panBy(0, 40); }
    else if (event.key === "ArrowDown") { event.preventDefault(); panBy(0, -40); }
  };

  const onWheel = (event: React.WheelEvent<HTMLElement>) => {
    event.preventDefault();
    zoomBy(event.deltaY > 0 ? -0.12 : 0.12);
  };

  const terrain = projection.polygon(snapshot.terrain.polygon);
  const home = projection.point(snapshot.home);
  const aircraft = Object.values(snapshot.aircraft).sort((left, right) => left.aircraft_id.localeCompare(right.aircraft_id));
  const contacts = Object.values(snapshot.contacts)
    .filter((contact) => layers.contacts && contact.position && contact.evidence !== "NONE")
    .sort((left, right) => left.contact_id.localeCompare(right.contact_id));
  const projectedAircraft = aircraft.map((item) => ({ item, point: projection.point(item.position) }));
  const labelOffsets = new Map<string, { x: number; y: number }>();
  projectedAircraft.forEach(({ item, point }, index) => {
    const neighbors = projectedAircraft
      .slice(0, index + 1)
      .filter(({ point: other }) => Math.hypot(point.x - other.x, point.y - other.y) < 70);
    const lane = Math.max(0, neighbors.length - 1);
    const right = lane % 8 < 4;
    labelOffsets.set(item.aircraft_id, {
      x: right ? 24 : -24,
      y: -38 + (lane % 4) * 25,
    });
  });
  const coverageCellMm = snapshot.coverage.grid_cell_mm ?? 0;
  const coverageCellPx = Math.max(2, projection.missionDistanceToPixels(coverageCellMm));
  const coverageOrigin = snapshot.coverage.origin ?? {
    x_mm: snapshot.terrain.bounds.min_x_mm,
    y_mm: snapshot.terrain.bounds.min_y_mm,
  };

  const onMapClick = (event: React.MouseEvent<SVGSVGElement>) => {
    if (!waypointAircraftId || !onSetWaypoint) return;
    if ((event.target as Element).closest("[data-aircraft-id], [data-contact-id]")) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    const rawX = (event.clientX - bounds.left) * VIEWPORT.width / bounds.width;
    const rawY = (event.clientY - bounds.top) * VIEWPORT.height / bounds.height;
    const projected = {
      x: (rawX - VIEWPORT.width / 2 - pan.x) / zoom + VIEWPORT.width / 2,
      y: (rawY - VIEWPORT.height / 2 - pan.y) / zoom + VIEWPORT.height / 2,
    };
    const waypoint = projection.inverse(projected);
    const terrainBounds = snapshot.terrain.bounds;
    onSetWaypoint(waypointAircraftId, {
      x_mm: Math.round(clamp(waypoint.x_mm, terrainBounds.min_x_mm, terrainBounds.max_x_mm)),
      y_mm: Math.round(clamp(waypoint.y_mm, terrainBounds.min_y_mm, terrainBounds.max_y_mm)),
    });
  };

  return (
    <section className="mission-panel relative flex min-h-[520px] min-w-0 flex-1 flex-col overflow-hidden" aria-label={t(locale, "map.title")} tabIndex={0} onKeyDown={onKeyDown} onWheel={onWheel}>
      <MapToolbar locale={locale} layers={layers} onToggleLayer={toggleLayer} onZoomIn={() => zoomBy(0.25)} onZoomOut={() => zoomBy(-0.25)} onReset={reset} />
      <div data-testid="mission-clock" className="absolute bottom-3 left-3 z-10 rounded border border-white/10 bg-black/65 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-white/50">
        {snapshot.block_id} · T+{Math.floor(snapshot.simulation_time_ms / 1000).toString().padStart(3, "0")}s
      </div>
      <svg
        role="group"
        aria-label={t(locale, "map.title")}
        data-testid="map-root"
        data-zoom={zoom}
        data-waypoint-mode={waypointAircraftId ? "active" : "inactive"}
        viewBox={`0 0 ${VIEWPORT.width} ${VIEWPORT.height}`}
        onClick={onMapClick}
        className={`h-full min-h-[520px] w-full outline-none focus-visible:ring-2 focus-visible:ring-white/70 ${waypointAircraftId ? "cursor-crosshair" : ""}`}
      >
        <defs>
          <pattern id="mission-grid" width="48" height="48" patternUnits="userSpaceOnUse">
            <path d="M 48 0 L 0 0 0 48" fill="none" stroke="#fff" strokeOpacity="0.08" strokeWidth="1" />
          </pattern>
          <filter id="mission-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
          </filter>
        </defs>
        <rect width={VIEWPORT.width} height={VIEWPORT.height} fill="#07090c" />
        <rect width={VIEWPORT.width} height={VIEWPORT.height} fill="url(#mission-grid)" />
        <g transform={`translate(${VIEWPORT.width / 2 + pan.x} ${VIEWPORT.height / 2 + pan.y}) scale(${zoom}) translate(${-VIEWPORT.width / 2} ${-VIEWPORT.height / 2})`}>
          <polygon points={terrain} fill="#0b1c1c" stroke="#63d3a0" strokeOpacity="0.8" strokeWidth="2" />
          {Object.entries(snapshot.restricted_zones).sort(([left], [right]) => left.localeCompare(right)).map(([id, points]) => (
            <polygon key={id} points={projection.polygon(points)} fill="#fb7185" fillOpacity="0.08" stroke="#fb7185" strokeDasharray="6 6" strokeOpacity="0.7" strokeWidth="2" />
          ))}
          {Object.entries(snapshot.sectors).sort(([left], [right]) => left.localeCompare(right)).map(([id, points]) => {
            const center = projection.point(points[0] ?? snapshot.home);
            return <g key={id}><polygon points={projection.polygon(points)} fill="#22d3ee" fillOpacity="0.04" stroke="#22d3ee" strokeOpacity="0.35" strokeDasharray="3 5" strokeWidth="1.5" />{layers.labels && <text x={center.x} y={center.y} fill="#67e8f9" fontSize="12" fontFamily="monospace" opacity="0.75">{id}</text>}</g>;
          })}
          {layers.coverage && coverageCellMm > 0 && Object.entries(snapshot.coverage.sectors).sort(([left], [right]) => left.localeCompare(right)).map(([id, sector]) => (
            <g key={`coverage-${id}`} opacity="0.38" data-coverage-sector={id}>
              {sector.covered_cells.map(([x, y]) => {
                const center = projection.point({
                  x_mm: coverageOrigin.x_mm + x * coverageCellMm + coverageCellMm / 2,
                  y_mm: coverageOrigin.y_mm + y * coverageCellMm + coverageCellMm / 2,
                });
                return <rect key={`${id}-${x}-${y}`} x={center.x - coverageCellPx / 2} y={center.y - coverageCellPx / 2} width={coverageCellPx} height={coverageCellPx} fill="#4ade80" />;
              })}
            </g>
          ))}
          {layers.routes && aircraft.map((item) => item.route.length > 1 && <polyline key={`route-${item.aircraft_id}`} points={projection.route(item.route)} fill="none" stroke="#fff" strokeOpacity="0.25" strokeDasharray="5 6" strokeWidth="2" />)}
          {layers.sensors && aircraft.map((item) => {
            const point = projection.point(item.position);
            return <circle key={`sensor-${item.aircraft_id}`} cx={point.x} cy={point.y} r="28" fill="#4ade80" fillOpacity="0.035" stroke="#4ade80" strokeOpacity="0.18" strokeDasharray="2 6" />;
          })}
          {layers.contacts && contacts.map((contact) => contact.position && <ContactSymbol key={contact.contact_id} contact={contact} point={projection.point(contact.position)} locale={locale} selected={selectedContactId === contact.contact_id} onSelect={onSelectContact} />)}
          {projectedAircraft.map(({ item, point }) => <AircraftSymbol key={item.aircraft_id} aircraft={item} point={point} locale={locale} selected={selectedAircraftId === item.aircraft_id} onSelect={onSelectAircraft} labelOffset={labelOffsets.get(item.aircraft_id)} />)}
          <g aria-label={t(locale, "map.home")} transform={`translate(${home.x} ${home.y})`} filter="url(#mission-glow)">
            <circle r="12" fill="#f5f5f5" fillOpacity="0.1" stroke="#f5f5f5" strokeWidth="1.5" />
            <path d="M 0 -8 L 8 0 L 0 8 L -8 0 Z" fill="#f5f5f5" />
            {layers.labels && <text x="14" y="4" fill="#f5f5f5" fontSize="11" fontFamily="monospace">BASE</text>}
          </g>
        </g>
      </svg>
      <div className="pointer-events-none absolute right-3 top-3 rounded border border-white/10 bg-black/65 px-2 py-1 font-mono text-[10px] text-white/60" aria-live="polite">
        Z {zoom.toFixed(2)} · {aircraft.length} UAS · {contacts.length} {contacts.length === 1 ? statusLabel(locale, contacts[0]!) : t(locale, "map.contacts")}
      </div>
      {layers.coverage && <div className="pointer-events-none absolute bottom-3 right-3 max-w-[48%] rounded border border-success/20 bg-black/75 px-3 py-2 font-mono text-[10px] text-success">{Object.entries(snapshot.coverage.sectors).sort(([left], [right]) => left.localeCompare(right)).map(([id, sector]) => <span key={id} className="mr-3 inline-block">{id.toUpperCase()} {Math.round(sector.coverage_ppm / 10_000)}%</span>)}</div>}
      {waypointAircraftId && <div role="status" className="pointer-events-none absolute left-1/2 top-14 z-10 -translate-x-1/2 rounded border border-info/40 bg-black/90 px-4 py-2 text-center text-xs font-semibold text-info">{locale === "es-CO" ? `Haga clic en el mapa para fijar la ruta de ${waypointAircraftId}` : `Click the map to set ${waypointAircraftId}'s route`}</div>}
    </section>
  );
}
