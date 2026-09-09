"use client";
import React, { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MapInstance } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { footprint, displayedTraffic } from "@/lib/geography/coordinates";
import type {
  Region,
  TrafficFrame,
  GeographyLayer,
} from "@/lib/geography/types";
const empty: GeoJSON.FeatureCollection = {
  type: "FeatureCollection",
  features: [],
};
export interface ColombiaMapProps {
  target: Region;
  layers: GeographyLayer[];
  imagery: boolean;
  relief: boolean;
  traffic: TrafficFrame | null;
  selected: string | null;
  elapsed: number;
  onPick: (lat: number, lon: number) => void;
  onSelectTraffic: (id: string) => void;
  onQuery: (lat: number, lon: number, radius: number) => void;
  onFeature: (properties: Record<string, unknown>) => void;
}
export default function ColombiaMap(props: ColombiaMapProps) {
  const host = useRef<HTMLDivElement>(null),
    map = useRef<MapInstance | null>(null),
    current = useRef(props);
  current.current = props;
  const [ready, setReady] = useState(false),
    [error, setError] = useState<string | null>(null);
  const history = useRef(
    new Map<string, { observed: number; points: number[][] }>(),
  );
  useEffect(() => {
    if (!host.current) return;
    maplibregl.setWorkerUrl("/maplibre/maplibre-gl-worker.mjs");
    const viewer = new maplibregl.Map({
      container: host.current,
      style: "https://tiles.openfreemap.org/styles/liberty",
      center: [-73.5, 4.5],
      zoom: 4.4,
      maxZoom: 16,
      minZoom: 3,
      attributionControl: { compact: true },
    });
    map.current = viewer;
    const metrics = () => ({
      observed: viewer.getLayer("observed")
        ? viewer.queryRenderedFeatures({ layers: ["observed"] }).length
        : 0,
      queryOutline: viewer.getLayer("query-area")
        ? viewer.queryRenderedFeatures({ layers: ["query-area"] }).length
        : 0,
      displayed: displayedTraffic(
        current.current.traffic,
        current.current.elapsed,
      ).length,
    });
    const diagnostic =
      new URLSearchParams(window.location.search).get("metrics") === "1";
    if (diagnostic) Reflect.set(window, "__matbGeographyMetrics", metrics);
    viewer.addControl(new maplibregl.NavigationControl(), "top-right");
    let timer: ReturnType<typeof setTimeout>;
    const query = () => {
      clearTimeout(timer);
      timer = setTimeout(() => {
        const c = viewer.getCenter();
        const b = viewer.getBounds();
        const radius = Math.ceil(
          Math.min(
            250,
            Math.max(
              10,
              Math.hypot(
                b.getNorth() - b.getSouth(),
                (b.getEast() - b.getWest()) * Math.cos((c.lat * Math.PI) / 180),
              ) * 30,
            ),
          ),
        );
        if (c.lat >= -5 && c.lat <= 16 && c.lng >= -84 && c.lng <= -66)
          current.current.onQuery(c.lat, c.lng, radius);
      }, 600);
    };
    viewer.on("moveend", query);
    viewer.on("error", () =>
      setError(
        "Some map tiles are unavailable / Algunas teselas no están disponibles",
      ),
    );
    viewer.on("load", async () => {
      viewer.addSource("mission-area", {
        type: "geojson",
        data: footprint(current.current.target.lon, current.current.target.lat),
      });
      viewer.addLayer({
        id: "mission-area",
        type: "line",
        source: "mission-area",
        paint: { "line-color": "#ffbd59", "line-width": 3 },
      });
      viewer.addSource("observed", { type: "geojson", data: empty });
      viewer.addSource("traffic-trails", { type: "geojson", data: empty });
      viewer.addSource("query-area", { type: "geojson", data: empty });
      viewer.addLayer({
        id: "query-area",
        type: "line",
        source: "query-area",
        paint: {
          "line-color": "#d9994b",
          "line-width": 1,
          "line-dasharray": [4, 3],
        },
      });
      viewer.addLayer({
        id: "traffic-trails",
        type: "line",
        source: "traffic-trails",
        paint: {
          "line-color": "#d47313",
          "line-width": 2,
          "line-opacity": 0.6,
        },
      });
      viewer.addLayer({
        id: "observed",
        type: "circle",
        source: "observed",
        paint: {
          "circle-radius": 6,
          "circle-color": ["case", ["get", "selected"], "#ffffff", "#e98420"],
          "circle-stroke-color": "#3b2411",
          "circle-stroke-width": 1,
          "circle-opacity": ["case", ["get", "stale"], 0.45, 1],
        },
      });
      if (viewer.getStyle().glyphs)
        viewer.addLayer({
          id: "observed-labels",
          type: "symbol",
          source: "observed",
          minzoom: 7,
          layout: {
            "text-field": ["get", "callsign"],
            "text-size": 11,
            "text-offset": [0, 1.5],
            "text-font": ["Noto Sans Regular"],
          },
          paint: {
            "text-color": "#683200",
            "text-halo-color": "#fff",
            "text-halo-width": 1,
          },
        });
      viewer.addSource("relief", {
        type: "raster-dem",
        tiles: [
          "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png",
        ],
        encoding: "terrarium",
        tileSize: 256,
        maxzoom: 12,
        attribution: "Terrain: Mapzen / Tilezen, SRTM",
      });
      viewer.addLayer(
        {
          id: "relief",
          type: "hillshade",
          source: "relief",
          layout: { visibility: "none" },
        },
        "mission-area",
      );
      const date = new Date(Date.now() - 2 * 86400000)
        .toISOString()
        .slice(0, 10);
      viewer.addSource("satellite", {
        type: "raster",
        tiles: [
          `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/MODIS_Terra_CorrectedReflectance_TrueColor/default/${date}/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg`,
        ],
        tileSize: 256,
        maxzoom: 9,
        attribution: `NASA GIBS MODIS Terra · ${date} · 250 m`,
      });
      const firstLine = viewer
        .getStyle()
        .layers.find(
          (layer) => layer.type === "line" || layer.type === "symbol",
        )?.id;
      viewer.addLayer(
        {
          id: "satellite",
          type: "raster",
          source: "satellite",
          layout: { visibility: "none" },
        },
        firstLine,
      );
      try {
        const response = await fetch("/geography/airports.json");
        if (!response.ok) throw new Error("airport catalog");
        const airports = await response.json();
        if (map.current !== viewer) return;
        viewer.addSource("colombia-airports", {
          type: "geojson",
          data: airports,
        });
        viewer.addLayer({
          id: "colombia-airports",
          type: "circle",
          source: "colombia-airports",
          paint: {
            "circle-radius": 4,
            "circle-color": "#168195",
            "circle-stroke-width": 1,
            "circle-stroke-color": "white",
          },
        });
      } catch {
        setError(
          "Airport catalog unavailable / Catálogo de aeródromos no disponible",
        );
      }
      if (map.current === viewer) {
        setReady(true);
        query();
      }
    });
    viewer.on("click", (event) => {
      const ids = ["observed", "colombia-airports"].filter((id) =>
        viewer.getLayer(id),
      );
      const feature = viewer.queryRenderedFeatures(event.point, {
        layers: ids,
      })[0];
      if (feature?.layer.id === "observed") {
        current.current.onSelectTraffic(String(feature.properties.id));
        return;
      }
      if (feature) {
        current.current.onFeature(feature.properties);
        return;
      }
      current.current.onPick(event.lngLat.lat, event.lngLat.lng);
    });
    return () => {
      clearTimeout(timer);
      if (
        diagnostic &&
        Reflect.get(window, "__matbGeographyMetrics") === metrics
      )
        Reflect.deleteProperty(window, "__matbGeographyMetrics");
      viewer.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    if (!ready || !map.current) return;
    const viewer = map.current;
    viewer.flyTo({
      center: [props.target.lon, props.target.lat],
      zoom: props.target.id === "national" ? 4.4 : 11,
      duration: 700,
    });
    (viewer.getSource("mission-area") as GeoJSONSource).setData(
      footprint(props.target.lon, props.target.lat),
    );
  }, [props.target, ready]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const viewer = map.current;
    const match: Record<string, string[]> = {
      roads: ["transportation", "transportation_name"],
      rivers: ["waterway", "water_name", "water"],
      settlements: ["place"],
      boundaries: ["boundary"],
      airports: ["aerodrome_label", "aeroway"],
    };
    for (const layer of viewer.getStyle().layers) {
      const sourceLayer =
        "source-layer" in layer ? layer["source-layer"] : null;
      for (const [group, sourceLayers] of Object.entries(match))
        if (sourceLayer && sourceLayers.includes(sourceLayer))
          viewer.setLayoutProperty(
            layer.id,
            "visibility",
            props.layers.includes(group as GeographyLayer) ? "visible" : "none",
          );
    }
    for (const [id, visible] of [
      ["satellite", props.imagery],
      ["relief", props.relief],
      ["colombia-airports", props.layers.includes("airports")],
    ] as const)
      if (viewer.getLayer(id))
        viewer.setLayoutProperty(
          id,
          "visibility",
          visible ? "visible" : "none",
        );
  }, [props.layers, props.imagery, props.relief, ready]);
  useEffect(() => {
    if (!ready || !map.current) return;
    const viewer = map.current;
    const tracks = displayedTraffic(props.traffic, props.elapsed),
      ids = new Set(tracks.map((t) => t.id));
    for (const id of history.current.keys())
      if (!ids.has(id)) history.current.delete(id);
    for (const t of tracks) {
      const previous = history.current.get(t.id);
      if (!previous || previous.observed !== t.observed_at) {
        const points = previous?.points ?? [];
        points.push([t.lon, t.lat]);
        history.current.set(t.id, {
          observed: t.observed_at,
          points: points.slice(-30),
        });
      }
    }
    (viewer.getSource("observed") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: tracks.map((t) => ({
        type: "Feature",
        properties: {
          id: t.id,
          callsign: t.callsign || t.id,
          stale: t.stale,
          selected: t.id === props.selected,
        },
        geometry: { type: "Point", coordinates: [t.lon, t.lat] },
      })),
    });
    (viewer.getSource("traffic-trails") as GeoJSONSource).setData({
      type: "FeatureCollection",
      features: [...history.current.values()]
        .filter((h) => h.points.length > 1)
        .map((h) => ({
          type: "Feature",
          properties: {},
          geometry: { type: "LineString", coordinates: h.points },
        })),
    });
    const q = props.traffic?.query;
    (viewer.getSource("query-area") as GeoJSONSource).setData(
      q
        ? {
            type: "Feature",
            properties: {},
            geometry: {
              type: "Polygon",
              coordinates: [
                Array.from({ length: 65 }, (_, i) => {
                  const a = (i / 64) * Math.PI * 2;
                  return [
                    q.lon +
                      (Math.cos(a) * q.radius_nm) /
                        (60 * Math.cos((q.lat * Math.PI) / 180)),
                    q.lat + (Math.sin(a) * q.radius_nm) / 60,
                  ];
                }),
              ],
            },
          }
        : empty,
    );
  }, [props.traffic, props.elapsed, props.selected, ready]);
  return (
    <div className="relative min-w-0">
      <div
        ref={host}
        className="h-[68vh] min-h-[400px] w-full rounded border border-white/10"
        data-testid="colombia-map"
        data-ready={ready}
      />
      {error && (
        <p
          className="absolute bottom-10 left-2 max-w-[85%] rounded bg-background/90 p-2 text-xs"
          role="status"
        >
          {error}
        </p>
      )}
    </div>
  );
}
