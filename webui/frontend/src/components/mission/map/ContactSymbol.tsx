"use client";

import React from "react";
import type { ContactSnapshot, Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import type { ProjectedPoint } from "./projection";

export interface ContactSymbolProps {
  contact: ContactSnapshot;
  point: ProjectedPoint;
  locale: Locale;
  selected?: boolean;
  onSelect?: (contactId: string) => void;
}

export function ContactSymbol({ contact, point, locale, selected = false, onSelect }: ContactSymbolProps) {
  const state = contact.workflow.toLowerCase();
  const label = `${contact.contact_id} — ${t(locale, `contact.workflow_${state}` as never)}`;
  const activate = () => onSelect?.(contact.contact_id);
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
      data-contact-id={contact.contact_id}
      transform={`translate(${point.x} ${point.y})`}
      onClick={activate}
      onKeyDown={onKeyDown}
      className="cursor-pointer outline-none"
    >
      <title>{label}</title>
      <circle r={selected ? 13 : 11} fill="#fbbf24" fillOpacity="0.18" stroke={selected ? "#fff" : "#fbbf24"} strokeWidth={selected ? 2 : 1.5} />
      <path d="M 0 -7 L 7 0 L 0 7 L -7 0 Z" fill="#fbbf24" stroke="#17120a" strokeWidth="1.5" />
      <text x="11" y="4" fill="#f5f5f5" fontSize="10" fontFamily="monospace" paintOrder="stroke" stroke="#050608" strokeWidth="3">
        {contact.contact_id}
      </text>
    </g>
  );
}
