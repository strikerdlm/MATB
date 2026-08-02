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

  const onKeyDown = (event: React.KeyboardEvent<SVGSVGElement>) => {
    if (event.key === "+" || event.key === "=") { event.preventDefault(); zoomBy(0.25); }
    else if (event.key === "-") { event.preventDefault(); zoomBy(-0.25); }
    else if (event.key === "0") { event.preventDefault(); reset(); }
    else if (event.key === "ArrowLeft") { event.preventDefault(); panBy(40, 0); }
    else if (event.key === "ArrowRight") { event.preventDefault(); panBy(-40, 0); }
    else if (event.key === "ArrowUp") { event.preventDefault(); panBy(0, 40); }
    else if (event.key === "ArrowDown") { event.preventDefault(); panBy(0, -40); }
  };

  const onWheel = (event: React.WheelEvent<SVGSVGElement>) => {
    event.preventDefault();
    zoomBy(event.deltaY > 0 ? -0.12 : 0.12);
  };

  const terrain = projection.polygon(snapshot.terrain.polygon);
  const home = projection.point(snapshot.home);
  const aircraft = Object.values(snapshot.aircraft).sort((left, right) => left.aircraft_id.localeCompare(right.aircraft_id));
  const contacts = Object.values(snapshot.contacts)
    .filter((contact) => layers.contacts && contact.position && contact.evidence !== "NONE")
    .sort((left, right) => left.contact_id.localeCompare(right.contact_id));

  return (
    <section className="mission-panel relative flex min-h-[420px] min-w-0 flex-1 flex-col overflow-hidden" aria-label={t(locale, "map.title")}>
      <MapToolbar locale={locale} layers={layers} onToggleLayer={toggleLayer} onZoomIn={() => zoomBy(0.25)} onZoomOut={() => zoomBy(-0.25)} onReset={reset} />
      <div className="absolute bottom-3 left-3 z-10 rounded border border-white/10 bg-black/65 px-2 py-1 font-mono text-[10px] uppercase tracking-wider text-white/50">
        {snapshot.block_id} · T+{Math.floor(snapshot.simulation_time_ms / 1000).toString().padStart(3, "0")}s
      </div>
      <svg
        role="img"
        aria-label={t(locale, "map.title")}
        data-testid="map-root"
        data-zoom={zoom}
        tabIndex={0}
        viewBox={`0 0 ${VIEWPORT.width} ${VIEWPORT.height}`}
        className="h-full min-h-[420px] w-full outline-none focus-visible:ring-2 focus-visible:ring-white/70"
        onKeyDown={onKeyDown}
        onWheel={onWheel}
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
          {layers.coverage && Object.entries(snapshot.coverage.sectors).sort(([left], [right]) => left.localeCompare(right)).map(([id, sector]) => (
            <g key={`coverage-${id}`} opacity="0.28">
              <text x="16" y={26 + Object.keys(snapshot.coverage.sectors).indexOf(id) * 16} fill="#4ade80" fontSize="10" fontFamily="monospace">{id} {Math.round(sector.coverage_ppm / 10000)}%</text>
              {sector.covered_cells.slice(0, 80).map(([x, y], index) => <rect key={`${id}-${x}-${y}-${index}`} x={16 + (x % 28) * 8} y={VIEWPORT.height - 24 - (y % 14) * 8} width="5" height="5" fill="#4ade80" />)}
            </g>
          ))}
          {layers.routes && aircraft.map((item) => item.route.length > 1 && <polyline key={`route-${item.aircraft_id}`} points={projection.route(item.route)} fill="none" stroke="#fff" strokeOpacity="0.25" strokeDasharray="5 6" strokeWidth="2" />)}
          {layers.sensors && aircraft.map((item) => {
            const point = projection.point(item.position);
            return <circle key={`sensor-${item.aircraft_id}`} cx={point.x} cy={point.y} r="28" fill="#4ade80" fillOpacity="0.035" stroke="#4ade80" strokeOpacity="0.18" strokeDasharray="2 6" />;
          })}
          {layers.contacts && contacts.map((contact) => contact.position && <ContactSymbol key={contact.contact_id} contact={contact} point={projection.point(contact.position)} locale={locale} selected={selectedContactId === contact.contact_id} onSelect={onSelectContact} />)}
          {aircraft.map((item) => <AircraftSymbol key={item.aircraft_id} aircraft={item} point={projection.point(item.position)} locale={locale} selected={selectedAircraftId === item.aircraft_id} onSelect={onSelectAircraft} />)}
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
    </section>
  );
}
