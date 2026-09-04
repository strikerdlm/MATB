"use client";

import React from "react";
import type { AircraftSnapshot, Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import type { ProjectedPoint } from "./projection";

export interface AircraftSymbolProps {
  aircraft: AircraftSnapshot;
  point: ProjectedPoint;
  locale: Locale;
  selected?: boolean;
  onSelect?: (aircraftId: string) => void;
  labelOffset?: ProjectedPoint;
}

const LINK_COLORS: Record<AircraftSnapshot["link"], string> = {
  NOMINAL: "#4ade80",
  DEGRADED: "#fbbf24",
  LOST: "#fb7185",
};

export function AircraftSymbol({ aircraft, point, locale, selected = false, onSelect, labelOffset = { x: 22, y: -22 } }: AircraftSymbolProps) {
  const label = `${aircraft.label || aircraft.aircraft_id} — ${t(locale, `link.${aircraft.link.toLowerCase()}` as never)}`;
  const activate = () => onSelect?.(aircraft.aircraft_id);
  const onKeyDown = (event: React.KeyboardEvent<SVGGElement>) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      activate();
    }
  };

  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={label}
      data-aircraft-id={aircraft.aircraft_id}
      transform={`translate(${point.x} ${point.y})`}
      onClick={activate}
      onKeyDown={onKeyDown}
      className="cursor-pointer outline-none"
    >
      <title>{label}</title>
      <circle r={selected ? 18 : 15} fill="none" stroke={selected ? "#fff" : "#fff"} strokeOpacity={selected ? 0.9 : 0.26} strokeWidth={selected ? 2 : 1} />
      <path d="M 0 -12 L 8 10 L 0 6 L -8 10 Z" transform={`rotate(${aircraft.heading_mdeg / 1000})`} fill={LINK_COLORS[aircraft.link]} stroke="#050608" strokeWidth="2" />
      <circle cy={-1} r="2.5" fill="#050608" />
      <line x1={labelOffset.x > 0 ? 10 : -10} y1="0" x2={labelOffset.x} y2={labelOffset.y} stroke="#f5f5f5" strokeOpacity="0.35" strokeWidth="1" />
      <g transform={`translate(${labelOffset.x} ${labelOffset.y - 10})`}>
        <rect x={labelOffset.x > 0 ? 0 : -76} y="0" width="76" height="20" rx="3" fill="#050608" fillOpacity="0.88" stroke={selected ? "#fff" : LINK_COLORS[aircraft.link]} strokeOpacity={selected ? 0.9 : 0.55} />
        <text x={labelOffset.x > 0 ? 7 : -69} y="14" fill="#f5f5f5" fontSize="11" fontWeight="600" fontFamily="monospace">
          {aircraft.aircraft_id}
        </text>
      </g>
    </g>
  );
}
