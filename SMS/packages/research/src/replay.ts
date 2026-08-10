import { parseResearchEvent, parseResearchSession, type ResearchEvent, type ResearchSession } from "./types.js";

export interface ResearchSessionPackage {
  readonly schemaVersion?: string;
  readonly session: ResearchSession;
  readonly events?: readonly ResearchEvent[];
}

const forbiddenKeys = new Set(["operationalUserId", "userId", "operatorId", "personnelNumber", "callSign", "diagnosis", "medicalDiagnosis", "missionRelease", "releaseEligibility", "classified"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`);
  return value.trim();
}

function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void {
  const unknown = Object.keys(value).find((key) => !allowed.includes(key));
  if (unknown !== undefined) throw new TypeError(`research separation boundary rejects field: ${unknown}`);
}

function rejectForbidden(value: unknown, path = "payload"): void {
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (forbiddenKeys.has(key)) throw new TypeError(`research export boundary rejects ${path}.${key}`);
    rejectForbidden(child, `${path}.${key}`);
  }
}

function parsePackage(input: unknown): { schemaVersion: string; session: ResearchSession; events: readonly ResearchEvent[] } {
  if (!isRecord(input)) throw new TypeError("research session package must be an object");
  let sessionInput: unknown = input;
  let eventInput: unknown;
  let schemaVersion = "research-events-v1";
  if (Object.prototype.hasOwnProperty.call(input, "session")) {
    strictKeys(input, ["schemaVersion", "session", "events"]);
    sessionInput = input.session;
    eventInput = input.events;
    schemaVersion = input.schemaVersion === undefined ? schemaVersion : requiredText(input.schemaVersion, "schemaVersion");
  }
  const session = parseResearchSession(sessionInput);
  if (session.nonDispatchable !== true) throw new TypeError("research sessions are non-dispatchable");
  const candidates = eventInput === undefined ? session.events : eventInput;
  if (!Array.isArray(candidates)) throw new TypeError("events must be an array");
  const events = candidates.map((event) => {
    const parsed = parseResearchEvent(event);
    if (parsed.sessionId !== session.id) throw new TypeError("research event session does not match package");
    rejectForbidden(parsed.payload);
    return parsed;
  });
  return { schemaVersion, session, events };
}

/** Replay is deterministic: events are copied, then ordered by sequence, time, and ID. */
export async function* replaySession(input: ResearchSessionPackage | ResearchSession | unknown): AsyncIterable<ResearchEvent> {
  const { schemaVersion, events } = parsePackage(input);
  // Touch the schema version in the generator so a malformed package fails at
  // iteration time, like all other validation errors from an async iterable.
  requiredText(schemaVersion, "schemaVersion");
  const ordered = [...events].sort((left, right) => left.sequence - right.sequence || Date.parse(left.occurredAtUtc) - Date.parse(right.occurredAtUtc) || left.eventId.localeCompare(right.eventId));
  for (const event of ordered) yield event;
}
