"use client";
import React, { useCallback, useEffect, useRef, useState } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { useAppLocale } from "@/lib/i18n";
import {
  areaTraffic,
  geographyCatalog,
  geographyRequest,
  prepareArea,
  type GeographyCatalog,
} from "@/lib/geography/api";
import {
  GEOGRAPHY_LAYERS,
  type Region,
  type GeographyLayer,
  type TrafficFrame,
  type PreparationJob,
} from "@/lib/geography/types";
import { TrafficPanel } from "@/components/mission/presentation/TrafficPanel";
const ColombiaMap = dynamic(() => import("./ColombiaMap"), {
  ssr: false,
  loading: () => <p>Colombia…</p>,
});
const national: Region = {
  id: "national",
  title: "Colombia",
  region: "Colombia",
  lat: 4.5,
  lon: -73.5,
};
export default function ColombiaExplorer() {
  const { simulationLocale: locale, copy } = useAppLocale();
  const [catalog, setCatalog] = useState<GeographyCatalog | null>(null),
    [target, setTarget] = useState(national);
  const [layers, setLayers] = useState<GeographyLayer[]>(GEOGRAPHY_LAYERS),
    [imagery, setImagery] = useState(false),
    [relief, setRelief] = useState(false),
    [live, setLive] = useState(true);
  const [traffic, setTraffic] = useState<TrafficFrame | null>(null),
    [selected, setSelected] = useState<string | null>(null),
    [elapsed, setElapsed] = useState(0);
  const [query, setQuery] = useState({ lat: 4.5, lon: -73.5, radius: 250 }),
    [provider, setProvider] = useState("adsb.lol");
  const [job, setJob] = useState<PreparationJob | null>(null),
    [error, setError] = useState<string | null>(null),
    [feature, setFeature] = useState<Record<string, unknown> | null>(null);
  const [lat, setLat] = useState("4.5000"),
    [lon, setLon] = useState("-73.5000"),
    [title, setTitle] = useState("Colombia");
  const received = useRef(0),
    queryRef = useRef(query);
  queryRef.current = query;
  const refresh = useCallback(
    () =>
      geographyCatalog()
        .then(setCatalog)
        .catch((e) => setError(String(e))),
    [],
  );
  useEffect(() => {
    void refresh();
  }, [refresh]);
  const selectArea = useCallback((site: Region) => {
    setTarget(site);
    setLat(site.lat.toFixed(4));
    setLon(site.lon.toFixed(4));
    setTitle(site.title);
  }, []);
  const changeQuery = useCallback(
    (lat: number, lon: number, radius: number) =>
      setQuery({
        lat: Number(lat.toFixed(2)),
        lon: Number(lon.toFixed(2)),
        radius,
      }),
    [],
  );
  useEffect(() => {
    if (!live) {
      setTraffic(null);
      return;
    }
    const abort = new AbortController();
    let active = true;
    const poll = async () => {
      if (document.hidden) return;
      try {
        const q = queryRef.current;
        const value = await areaTraffic(
          q.lat,
          q.lon,
          q.radius,
          provider,
          abort.signal,
        );
        if (active) {
          received.current = performance.now();
          setElapsed(0);
          setTraffic(value);
        }
      } catch (e) {
        if (active && !abort.signal.aborted) {
          setError(String(e));
          setTraffic((previous) =>
            previous ? { ...previous, status: "unavailable" } : null,
          );
        }
      }
    };
    void poll();
    const timer = setInterval(() => void poll(), 15000),
      clock = setInterval(() => {
        if (!document.hidden)
          setElapsed(Math.max(0, performance.now() - received.current));
      }, 1000);
    const visible = () => {
      if (!document.hidden) void poll();
    };
    document.addEventListener("visibilitychange", visible);
    return () => {
      active = false;
      abort.abort();
      clearInterval(timer);
      clearInterval(clock);
      document.removeEventListener("visibilitychange", visible);
    };
  }, [live, provider, query]);
  useEffect(() => {
    if (!job || !["queued", "running"].includes(job.status)) return;
    let active = true;
    const timer = setInterval(
      () =>
        void geographyRequest<PreparationJob>(`/preparations/${job.id}`)
          .then((value) => {
            if (active) {
              setJob(value);
              if (value.status === "ready") void refresh();
            }
          })
          .catch((e) => {
            if (active) setError(String(e));
          }),
      2000,
    );
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [job, refresh]);
  const selectSceneForMission = (id: string) =>
    sessionStorage.setItem("matb.geography.scene", id);
  const labels: Record<GeographyLayer, string> = {
    roads: copy("Vías", "Roads"),
    rivers: copy("Ríos y aguas", "Rivers and water"),
    settlements: copy("Poblaciones", "Settlements"),
    boundaries: copy("Límites administrativos", "Administrative boundaries"),
    airports: copy("Aeródromos y helipuertos", "Airports and heliports"),
  };
  return (
    <main className="space-y-4 p-4 md:p-6">
      <header>
        <p className="page-kicker">
          MATB · {copy("Contexto geográfico", "Geographic context")}
        </p>
        <h1 className="text-3xl font-semibold">Colombia</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {copy(
            "Explore capas, observe tráfico y prepare un área local para la misión.",
            "Explore layers, observe traffic and prepare a local mission area.",
          )}
        </p>
      </header>
      <div className="grid min-w-0 gap-4 xl:grid-cols-[280px_minmax(0,1fr)]">
        <aside className="space-y-4">
          <section className="mission-panel space-y-3 p-3">
            <label className="block text-sm">
              {copy("Región", "Region")}
              <select
                aria-label={copy("Región", "Region")}
                className="mt-1 w-full bg-background p-2"
                value={target.id}
                onChange={(e) =>
                  selectArea(
                    catalog?.regions.find((r) => r.id === e.target.value) ??
                      (e.target.value === "islands"
                        ? {
                            id: "islands",
                            title: "San Andrés y Providencia",
                            region: "Archipiélago",
                            lat: 12.58,
                            lon: -81.7,
                          }
                        : national),
                  )
                }
              >
                <option value="national">Colombia</option>
                {catalog?.regions.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.region} · {r.title}
                  </option>
                ))}
                <option value="islands">San Andrés y Providencia</option>
                {target.id === "custom" && (
                  <option value="custom">
                    {copy("Área seleccionada", "Selected area")}
                  </option>
                )}
              </select>
            </label>
            <form
              className="space-y-2"
              onSubmit={(e) => {
                e.preventDefault();
                const latitude = Number(lat),
                  longitude = Number(lon);
                if (
                  !Number.isFinite(latitude + longitude) ||
                  latitude < -5 ||
                  latitude > 16 ||
                  longitude < -84 ||
                  longitude > -66
                ) {
                  setError(
                    copy(
                      "Coordenadas fuera del área de Colombia.",
                      "Coordinates outside the Colombia extent.",
                    ),
                  );
                  return;
                }
                selectArea({
                  id: "custom",
                  title: title || "Área local",
                  region: target.region,
                  lat: latitude,
                  lon: longitude,
                });
              }}
            >
              <div className="grid grid-cols-2 gap-2">
                <label className="text-xs">
                  Lat
                  <input
                    aria-label="Latitude"
                    type="number"
                    step="0.0001"
                    value={lat}
                    onChange={(e) => setLat(e.target.value)}
                    className="w-full bg-background p-2"
                  />
                </label>
                <label className="text-xs">
                  Lon
                  <input
                    aria-label="Longitude"
                    type="number"
                    step="0.0001"
                    value={lon}
                    onChange={(e) => setLon(e.target.value)}
                    className="w-full bg-background p-2"
                  />
                </label>
              </div>
              <button className="w-full rounded border border-white/20 p-2 text-sm">
                {copy("Ir a coordenadas", "Go to coordinates")}
              </button>
            </form>
            <p className="text-xs text-muted-foreground">
              {copy(
                "Haga clic en el mapa para centrar el área de 12 × 8 km.",
                "Click the map to center the 12 × 8 km area.",
              )}
            </p>
          </section>
          <fieldset className="mission-panel space-y-2 p-3">
            <legend>{copy("Capas", "Layers")}</legend>
            {GEOGRAPHY_LAYERS.map((layer) => (
              <label key={layer} className="block text-sm">
                <input
                  type="checkbox"
                  checked={layers.includes(layer)}
                  onChange={() =>
                    setLayers((old) =>
                      old.includes(layer)
                        ? old.filter((l) => l !== layer)
                        : [...old, layer],
                    )
                  }
                />{" "}
                {labels[layer]}
              </label>
            ))}
            <label className="block text-sm">
              <input
                type="checkbox"
                checked={relief}
                onChange={(e) => setRelief(e.target.checked)}
              />{" "}
              {copy("Relieve", "Relief")}
            </label>
            <label className="block text-sm">
              <input
                type="checkbox"
                checked={imagery}
                onChange={(e) => setImagery(e.target.checked)}
              />{" "}
              {copy("Imagen satelital · 250 m", "Satellite imagery · 250 m")}
            </label>
            <label className="block text-sm">
              <input
                type="checkbox"
                checked={live}
                onChange={(e) => setLive(e.target.checked)}
              />{" "}
              {copy("Tráfico aéreo en vivo", "Live aircraft traffic")}
            </label>
            {live && (
              <>
                <select
                  aria-label={copy("Proveedor de tráfico", "Traffic provider")}
                  className="w-full bg-background p-2 text-sm"
                  value={provider}
                  onChange={(e) => setProvider(e.target.value)}
                >
                  {(
                    catalog?.providers ?? [{ id: "adsb.lol", available: true }]
                  ).map((p) => (
                    <option key={p.id} value={p.id} disabled={!p.available}>
                      {p.id}
                      {!p.available ? " · OAuth" : ""}
                    </option>
                  ))}
                </select>
                <p className="text-xs text-muted-foreground">
                  {copy(
                    "Línea ámbar: región consultada; cobertura parcial.",
                    "Amber outline: queried region; partial coverage.",
                  )}{" "}
                  {query.radius} NM
                </p>
              </>
            )}
          </fieldset>
          <section className="mission-panel space-y-2 p-3">
            <h2>{copy("Preparar mapa local", "Prepare local map")}</h2>
            <input
              aria-label={copy("Nombre del área", "Area name")}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={80}
              className="w-full bg-background p-2 text-sm"
            />
            <button
              type="button"
              disabled={
                !title.trim() ||
                (!!job && ["queued", "running"].includes(job.status))
              }
              className="w-full rounded bg-info p-2 text-sm text-black disabled:opacity-40"
              onClick={() => {
                setError(null);
                void prepareArea({ ...target, title })
                  .then(setJob)
                  .catch((e) => setError(String(e)));
              }}
            >
              {copy("Preparar área sin conexión", "Prepare offline area")}
            </button>
            <p className="text-xs text-muted-foreground">
              {copy(
                "Preparación con internet; misión local sin conexión. Sentinel-2 10 m y terreno 100 m.",
                "Preparation requires internet; local missions work offline. Sentinel-2 10 m and 100 m terrain.",
              )}
            </p>
            {job && (
              <div role="status" className="text-xs">
                <p>
                  {job.status} · {job.progress}
                </p>
                {job.error && <p>{job.error}</p>}
                {["queued", "running"].includes(job.status) && (
                  <button
                    className="mt-2 underline"
                    onClick={() =>
                      void geographyRequest<PreparationJob>(
                        `/preparations/${job.id}`,
                        { method: "DELETE" },
                      )
                        .then(setJob)
                        .catch((e) => setError(String(e)))
                    }
                  >
                    {copy("Cancelar", "Cancel")}
                  </button>
                )}
              </div>
            )}
          </section>
        </aside>
        <div className="min-w-0 space-y-3">
          <ColombiaMap
            target={target}
            layers={layers}
            imagery={imagery}
            relief={relief}
            traffic={traffic}
            elapsed={elapsed}
            selected={selected}
            onPick={(lat, lon) => {
              if (lat >= -5 && lat <= 16 && lon >= -84 && lon <= -66)
                selectArea({
                  id: "custom",
                  title: "Área local",
                  region: "Colombia",
                  lat,
                  lon,
                });
            }}
            onSelectTraffic={setSelected}
            onQuery={changeQuery}
            onFeature={setFeature}
          />
          <TrafficPanel
            frame={traffic}
            elapsed={elapsed}
            selected={selected}
            onSelect={setSelected}
            locale={locale}
          />
          {feature && (
            <section className="mission-panel p-3 text-sm">
              <button
                className="float-right"
                aria-label="Close feature"
                onClick={() => setFeature(null)}
              >
                ×
              </button>
              <h2 className="font-semibold">
                {String(feature.name ?? feature.ident ?? "")}
              </h2>
              <p>
                {[feature.ident, feature.type, feature.municipality]
                  .filter(Boolean)
                  .join(" · ")}
              </p>
              {Boolean(feature.elevation_ft) && (
                <p>
                  {copy("Elevación publicada", "Published elevation")}:{" "}
                  {String(feature.elevation_ft)} ft
                </p>
              )}
              <p className="mt-1 text-xs text-muted-foreground">
                OurAirports · {catalog?.reference?.acquired_at.slice(0, 10)}
              </p>
            </section>
          )}
        </div>
      </div>
      {error && (
        <p
          role="alert"
          className="rounded border border-warning/40 p-3 text-sm text-warning"
        >
          {error}
        </p>
      )}
      <section>
        <h2 className="mb-3 text-xl">
          {copy("Mapas locales instalados", "Installed local maps")}
        </h2>
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {catalog?.scenes.map((scene) => (
            <article key={scene.id} className="mission-panel p-4">
              <p className="text-xs text-muted-foreground">
                {scene.region ?? "Meta"}
              </p>
              <h3 className="text-lg">{scene.title}</h3>
              <p className="my-2 text-xs">
                12 × 8 km · {scene.origin.lat.toFixed(4)},{" "}
                {scene.origin.lon.toFixed(4)}
              </p>
              <p className="mb-3 text-xs text-muted-foreground">
                {scene.acquired_at?.slice(0, 10)} ·{" "}
                {copy("Nubes muestreadas", "Sampled cloud cover")}:{" "}
                {scene.footprint_cloud_percent?.toFixed(1) ?? "—"}%
              </p>
              <div className="flex gap-4 text-sm text-info">
                <Link
                  href="/mission/test"
                  onClick={() => selectSceneForMission(scene.id)}
                >
                  {copy("Prueba técnica", "Technical test")}
                </Link>
                <Link
                  href="/mission/setup"
                  onClick={() => selectSceneForMission(scene.id)}
                >
                  {copy("Investigación", "Research setup")}
                </Link>
              </div>
            </article>
          ))}
        </div>
      </section>
    </main>
  );
}
