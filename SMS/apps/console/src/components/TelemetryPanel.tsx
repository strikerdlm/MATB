import type { JSX } from "react";

export interface TelemetryAircraft {
  readonly aircraftId: string;
  readonly platform: string;
  readonly approvedMinimumReservePercent: number;
}

export interface TelemetrySnapshot {
  readonly capturedAtLocal: string;
  readonly latitude: string;
  readonly longitude: string;
  readonly altitude: string;
  readonly groundspeed: string;
  readonly heading: string;
  readonly verticalRate: string;
  readonly energyPercent: number;
  readonly reservePercent: number;
  readonly batteryHealth: string;
  readonly linkLatencyMs: number;
  readonly linkLossPercent: number;
  readonly gnss: string;
  readonly activeLeg?: string;
  readonly deviation?: string;
}

export interface TelemetryDegraded {
  readonly active: boolean;
  readonly reason?: string;
  readonly sinceLocal?: string;
}

export interface TelemetryPanelProps {
  readonly aircraft: TelemetryAircraft;
  readonly telemetry: TelemetrySnapshot;
  readonly degraded: boolean | TelemetryDegraded;
  readonly locale?: "en" | "es";
}

function isDegraded(value: TelemetryPanelProps["degraded"]): TelemetryDegraded {
  return typeof value === "boolean" ? { active: value } : value;
}

function DataLine({ label, value, mono = false }: { label: string; value: string; mono?: boolean }): JSX.Element {
  return <div><dt>{label}</dt><dd className={mono ? "mono" : ""}>{value}</dd></div>;
}

export function TelemetryPanel({ aircraft, telemetry, degraded, locale = "en" }: TelemetryPanelProps): JSX.Element {
  const health = isDegraded(degraded);
  const degradedLabel = locale === "es" ? "Telemetría degradada" : "Telemetry degraded";
  const reserveLabel = locale === "es" ? "Reserva mínima aprobada" : "Approved minimum reserve";

  return (
    <section className={`rail-panel telemetry-panel ${health.active ? "is-degraded" : ""}`} aria-labelledby="read-only-telemetry-heading">
      <div className="rail-title"><h2 id="read-only-telemetry-heading">{locale === "es" ? "Telemetría de solo lectura" : "Read-only telemetry"}</h2><span>As of {telemetry.capturedAtLocal.slice(12, 17)} local</span></div>
      {health.active && <div className="telemetry-degraded" role="status"><strong>{degradedLabel}</strong><span>{health.reason ?? "Link status is delayed"}{health.sinceLocal === undefined ? "" : ` · since ${health.sinceLocal}`}</span></div>}
      <dl className="telemetry-list"><DataLine label="Aircraft ID" value={aircraft.aircraftId} mono /><DataLine label="Platform" value={aircraft.platform} /><DataLine label="Time (local)" value={telemetry.capturedAtLocal} mono /><DataLine label="Latitude" value={telemetry.latitude} mono /><DataLine label="Longitude" value={telemetry.longitude} mono /><DataLine label="Altitude" value={telemetry.altitude} mono /><DataLine label="Ground speed" value={telemetry.groundspeed} mono /><DataLine label="Heading" value={telemetry.heading} mono /><DataLine label="Vertical rate" value={telemetry.verticalRate} mono /><DataLine label="Active leg" value={telemetry.activeLeg ?? "—"} /><DataLine label="Deviation" value={telemetry.deviation ?? "Within tolerance"} /><DataLine label="Energy" value={`${telemetry.energyPercent}%`} mono /><DataLine label={reserveLabel} value={`${aircraft.approvedMinimumReservePercent}%`} mono /><DataLine label="Reserve margin" value={`${telemetry.reservePercent}%`} mono /><DataLine label="Battery health" value={telemetry.batteryHealth} /><DataLine label="Link latency" value={`${telemetry.linkLatencyMs} ms`} mono /><DataLine label="Link loss" value={`${telemetry.linkLossPercent}%`} mono /><DataLine label="GNSS" value={telemetry.gnss} /></dl>
    </section>
  );
}
