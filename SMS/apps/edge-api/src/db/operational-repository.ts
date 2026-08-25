import type { SqlDatabase } from "./schema.js";

export interface NormalizedMissionSnapshot {
  readonly missionId: string;
  readonly persistenceVersion: number;
  readonly revisions: readonly Record<string, unknown>[];
  readonly safetyResults: readonly { readonly envelope: Record<string, unknown>; readonly stale: boolean }[];
  readonly checklistResponses: readonly Record<string, unknown>[];
  readonly approvals: readonly Record<string, unknown>[];
  readonly postflight?: Record<string, unknown>;
  readonly occurrences: readonly Record<string, unknown>[];
}

export class MissionSnapshotConflictError extends Error {
  public constructor() {
    super("mission snapshot changed in another repository instance");
    this.name = "MissionSnapshotConflictError";
  }
}

function parseObject(value: unknown, field: string): Record<string, unknown> {
  const parsed = typeof value === "string" ? JSON.parse(value) as unknown : value;
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error(`${field} is corrupt`);
  return parsed as Record<string, unknown>;
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new Error(`${field} is corrupt`);
  return value;
}

export function writeMissionSnapshot(database: SqlDatabase, snapshot: NormalizedMissionSnapshot): void {
  const currentRevision = snapshot.revisions.reduce((highest, revision) => Math.max(highest, Number(revision.revision)), -1);
  if (!Number.isInteger(currentRevision) || currentRevision < 0) throw new Error("mission snapshot has no valid revision");
  const existing = database.prepare("SELECT state_version FROM missions WHERE mission_id = ?").get(snapshot.missionId) as { state_version: number } | undefined;
  if ((snapshot.persistenceVersion === 0 && existing !== undefined)
    || (snapshot.persistenceVersion > 0 && existing?.state_version !== snapshot.persistenceVersion)) {
    throw new MissionSnapshotConflictError();
  }
  database.prepare("DELETE FROM missions WHERE mission_id = ?").run(snapshot.missionId);
  database.prepare("INSERT INTO missions (mission_id, current_revision, state_version) VALUES (?, ?, ?)").run(snapshot.missionId, currentRevision, snapshot.persistenceVersion + 1);
  for (const revision of snapshot.revisions) {
    database.prepare("INSERT INTO mission_revisions (revision_id, mission_id, revision, revision_json) VALUES (?, ?, ?, ?)")
      .run(requiredText(revision.id, "revision id"), snapshot.missionId, Number(revision.revision), JSON.stringify(revision));
  }
  for (const result of snapshot.safetyResults) {
    database.prepare("INSERT INTO evaluation_envelopes (revision_id, envelope_json, stale) VALUES (?, ?, ?)")
      .run(requiredText(result.envelope.revisionId, "evaluation revision id"), JSON.stringify(result.envelope), result.stale ? 1 : 0);
  }
  for (const response of snapshot.checklistResponses) {
    database.prepare("INSERT INTO checklist_responses (response_id, revision_id, item_id, response_json) VALUES (?, ?, ?, ?)")
      .run(requiredText(response.responseId, "checklist response id"), requiredText(response.revisionId, "checklist revision id"), requiredText(response.itemId, "checklist item id"), JSON.stringify(response));
  }
  for (const approval of snapshot.approvals) {
    const revisionId = requiredText(approval.missionRevisionId, "gate revision id");
    const gate = requiredText(approval.gate, "gate");
    const aircraftScope = typeof approval.aircraftId === "string" ? approval.aircraftId : "";
    database.prepare("INSERT INTO gate_decisions (decision_id, revision_id, gate, aircraft_scope, decision_json) VALUES (?, ?, ?, ?, ?)")
      .run(`${revisionId}:${gate}:${aircraftScope}`, revisionId, gate, aircraftScope, JSON.stringify(approval));
  }
  if (snapshot.postflight !== undefined) {
    database.prepare("INSERT INTO postflight_records (revision_id, record_json) VALUES (?, ?)")
      .run(requiredText(snapshot.postflight.revisionId, "postflight revision id"), JSON.stringify(snapshot.postflight));
  }
  for (const occurrence of snapshot.occurrences) {
    database.prepare("INSERT INTO occurrences (occurrence_id, revision_id, record_json) VALUES (?, ?, ?)")
      .run(requiredText(occurrence.occurrenceId, "occurrence id"), requiredText(occurrence.revisionId, "occurrence revision id"), JSON.stringify(occurrence));
  }
}

export function loadMissionSnapshots(database: SqlDatabase): NormalizedMissionSnapshot[] {
  const missionRows = database.prepare("SELECT mission_id, state_version FROM missions ORDER BY mission_id").all() as { mission_id: string; state_version: number }[];
  return missionRows.map(({ mission_id: missionId, state_version: persistenceVersion }) => {
    const revisions = (database.prepare("SELECT revision_json FROM mission_revisions WHERE mission_id = ? ORDER BY revision").all(missionId) as { revision_json: string }[])
      .map(({ revision_json }) => parseObject(revision_json, "mission revision"));
    const revisionIds = revisions.map((revision) => requiredText(revision.id, "revision id"));
    const inMission = (revisionId: string): boolean => revisionIds.includes(revisionId);
    const safetyResults = (database.prepare("SELECT revision_id, envelope_json, stale FROM evaluation_envelopes ORDER BY revision_id").all() as { revision_id: string; envelope_json: string; stale: number }[])
      .filter(({ revision_id }) => inMission(revision_id))
      .map(({ envelope_json, stale }) => ({ envelope: parseObject(envelope_json, "evaluation envelope"), stale: stale === 1 }));
    const checklistResponses = (database.prepare("SELECT revision_id, response_json FROM checklist_responses ORDER BY response_id").all() as { revision_id: string; response_json: string }[])
      .filter(({ revision_id }) => inMission(revision_id)).map(({ response_json }) => parseObject(response_json, "checklist response"));
    const approvals = (database.prepare("SELECT revision_id, decision_json FROM gate_decisions ORDER BY decision_id").all() as { revision_id: string; decision_json: string }[])
      .filter(({ revision_id }) => inMission(revision_id)).map(({ decision_json }) => parseObject(decision_json, "gate decision"));
    const postflightRow = database.prepare(`SELECT record_json FROM postflight_records WHERE revision_id IN (
      SELECT revision_id FROM mission_revisions WHERE mission_id = ?
    ) LIMIT 1`).get(missionId) as { record_json: string } | undefined;
    const occurrences = (database.prepare("SELECT revision_id, record_json FROM occurrences ORDER BY occurrence_id").all() as { revision_id: string; record_json: string }[])
      .filter(({ revision_id }) => inMission(revision_id)).map(({ record_json }) => parseObject(record_json, "occurrence"));
    return {
      missionId,
      persistenceVersion,
      revisions,
      safetyResults,
      checklistResponses,
      approvals,
      ...(postflightRow === undefined ? {} : { postflight: parseObject(postflightRow.record_json, "postflight record") }),
      occurrences,
    };
  });
}
