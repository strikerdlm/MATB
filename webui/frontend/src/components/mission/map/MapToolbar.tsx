"use client";

import React from "react";
import { Minus, Plus, RotateCcw } from "lucide-react";
import type { Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";
import { Button } from "@/components/ui/button";

export interface MapLayerState {
  routes: boolean;
  sensors: boolean;
  coverage: boolean;
  contacts: boolean;
  labels: boolean;
}

interface MapToolbarProps {
  disabled?: boolean;
  layersDisabled?: boolean;
  locale: Locale;
  layers: MapLayerState;
  onToggleLayer: (layer: keyof MapLayerState) => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onReset: () => void;
}

export function MapToolbar({ disabled, layersDisabled, locale, layers, onToggleLayer, onZoomIn, onZoomOut, onReset }: MapToolbarProps) {
  const layerLabels: Array<[keyof MapLayerState, string]> = [
    ["routes", t(locale, "map.routes")],
    ["sensors", t(locale, "map.sensors")],
    ["coverage", t(locale, "map.coverage")],
    ["contacts", t(locale, "map.contacts")],
    ["labels", t(locale, "map.labels")],
  ];

  return (
    <div className="absolute left-3 top-3 z-10 flex max-w-[calc(100%-1.5rem)] flex-wrap items-center gap-1 rounded border border-white/10 bg-black/75 p-1 backdrop-blur" aria-label={t(locale, "map.title")}>
      {layerLabels.map(([layer, label]) => (
        <button
          key={layer}
          disabled={disabled || layersDisabled}
          type="button"
          aria-pressed={layers[layer]}
          onClick={() => onToggleLayer(layer)}
          className={`rounded px-2 py-1 font-mono text-[10px] uppercase tracking-wider transition ${layers[layer] ? "bg-white text-black" : "text-white/60 hover:bg-white/10 hover:text-white"}`}
        >
          {label}
        </button>
      ))}
      <span className="mx-1 h-4 w-px bg-white/15" aria-hidden="true" />
      <Button disabled={disabled} type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(locale, "map.zoom_out")} onClick={onZoomOut}>
        <Minus className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
      <Button disabled={disabled} type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(locale, "map.zoom_in")} onClick={onZoomIn}>
        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
      <Button disabled={disabled} type="button" variant="ghost" size="icon" className="h-7 w-7" aria-label={t(locale, "map.reset_view")} onClick={onReset}>
        <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
      </Button>
    </div>
  );
}
