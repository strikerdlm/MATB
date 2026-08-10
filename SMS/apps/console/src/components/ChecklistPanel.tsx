import type { JSX } from "react";

export interface ChecklistItem {
  readonly itemId: string;
  readonly prompt: string;
  readonly responseOptions: readonly string[];
  readonly response?: string;
  readonly accountableUserId?: string;
  readonly occurredAtUtc?: string;
  readonly evidenceRef?: string;
  readonly reason?: string;
}

export interface ChecklistResponseEvent {
  readonly itemId: string;
  readonly response: string;
  readonly occurredAtUtc: string;
  readonly accountableUserId?: string;
  readonly evidenceRef?: string;
  readonly reason?: string;
}

export interface ChecklistPanelProps {
  readonly items: readonly ChecklistItem[];
  readonly onRespond: (event: ChecklistResponseEvent) => void;
  readonly nowUtc?: () => string;
}

function optionLabel(option: string): string {
  return option.replaceAll("-", " ").replace(/\b\w/g, (character) => character.toUpperCase());
}

export function ChecklistPanel({ items, onRespond, nowUtc = () => new Date().toISOString() }: ChecklistPanelProps): JSX.Element {
  return (
    <section className="checklist-panel" aria-labelledby="checklist-panel-heading">
      <div className="rail-title"><h2 id="checklist-panel-heading">Checklist responses</h2><span>One item at a time</span></div>
      <div className="checklist-list">
        {items.map((item) => (
          <fieldset className="checklist-item" key={item.itemId} data-item-id={item.itemId}>
            <legend><span className="mono">{item.itemId}</span> {item.prompt}</legend>
            <div className="checklist-options" aria-label={`Respond to item ${item.itemId}`}>
              {item.responseOptions.map((option) => (
                <button type="button" key={option} className={item.response === option ? "is-selected" : ""} aria-pressed={item.response === option} onClick={() => onRespond({ itemId: item.itemId, response: option, occurredAtUtc: nowUtc(), ...(item.accountableUserId === undefined ? {} : { accountableUserId: item.accountableUserId }), ...(item.evidenceRef === undefined ? {} : { evidenceRef: item.evidenceRef }), ...(item.reason === undefined ? {} : { reason: item.reason }) })}>
                  {optionLabel(option)}
                </button>
              ))}
            </div>
            {(item.accountableUserId !== undefined || item.occurredAtUtc !== undefined || item.evidenceRef !== undefined || item.reason !== undefined) && (
              <dl className="checklist-meta">
                {item.accountableUserId !== undefined && <div><dt>Accountable</dt><dd>{item.accountableUserId}</dd></div>}
                {item.occurredAtUtc !== undefined && <div><dt>Recorded (UTC)</dt><dd className="mono">{item.occurredAtUtc}</dd></div>}
                {item.evidenceRef !== undefined && <div><dt>Evidence</dt><dd className="mono">{item.evidenceRef}</dd></div>}
                {item.reason !== undefined && <div><dt>Reason</dt><dd>{item.reason}</dd></div>}
              </dl>
            )}
          </fieldset>
        ))}
      </div>
    </section>
  );
}
