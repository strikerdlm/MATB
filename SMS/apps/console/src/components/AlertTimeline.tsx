import type { JSX } from "react";

export type AlertSeverity = "info" | "warning" | "degraded" | "blocker";

export interface AlertTimelineItem {
  readonly id: string;
  readonly occurredAtUtc: string;
  readonly severity: AlertSeverity;
  readonly title: string;
  readonly detail: string;
}

export interface AlertTimelineProps {
  readonly alerts: readonly AlertTimelineItem[];
}

function severityLabel(severity: AlertSeverity): string {
  return severity.toUpperCase();
}

export function AlertTimeline({ alerts }: AlertTimelineProps): JSX.Element {
  return (
    <section className="alert-timeline" aria-labelledby="alert-timeline-heading">
      <div className="rail-title"><h2 id="alert-timeline-heading">Alert timeline</h2><span>{alerts.length} events</span></div>
      <ol>
        {alerts.map((alert) => (
          <li key={alert.id} className={`alert-${alert.severity}`}>
            <span className="alert-marker" role="status" aria-label={severityLabel(alert.severity)}>{severityLabel(alert.severity)}</span>
            <div><strong>{alert.title}</strong><p>{alert.detail}</p><time dateTime={alert.occurredAtUtc} className="mono">{alert.occurredAtUtc}</time></div>
          </li>
        ))}
      </ol>
    </section>
  );
}
