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
}

const LINK_COLORS: Record<AircraftSnapshot["link"], string> = {
  NOMINAL: "#4ade80",
  DEGRADED: "#fbbf24",
  LOST: "#fb7185",
};

export function AircraftSymbol({ aircraft, point, locale, selected = false, onSelect }: AircraftSymbolProps) {
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
      <path d="M 0 -12 L 8 10 L 0 6 L -8 10 Z" fill={LINK_COLORS[aircraft.link]} stroke="#050608" strokeWidth="2" />
      <circle cy={-1} r="2.5" fill="#050608" />
      <text x="13" y="4" fill="#f5f5f5" fontSize="11" fontFamily="monospace" paintOrder="stroke" stroke="#050608" strokeWidth="3">
        {aircraft.aircraft_id}
      </text>
    </g>
  );
}
