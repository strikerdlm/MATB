import type { EdgeDatabase } from "./migrate.js";

interface WatermarkRow {
  readonly adapter_id: string;
  readonly aircraft_id: string;
  readonly last_sequence: number;
}

export class TelemetrySequenceRepository {
  private readonly watermarks = new Map<string, number>();

  public constructor(private readonly database: EdgeDatabase) {
    const rows = database.sql().prepare(
      "SELECT adapter_id, aircraft_id, last_sequence FROM telemetry_sequence_watermarks",
    ).all() as WatermarkRow[];
    for (const row of rows) this.watermarks.set(key(row.adapter_id, row.aircraft_id), row.last_sequence);
  }

  public claim(adapterId: string, aircraftId: string, sequence: number): boolean {
    requireIdentifier(adapterId, "adapterId");
    requireIdentifier(aircraftId, "aircraftId");
    if (!Number.isSafeInteger(sequence) || sequence < 0) throw new Error("telemetry sequence is invalid");
    if ((this.watermarks.get(key(adapterId, aircraftId)) ?? -1) >= sequence) return false;

    const sql = this.database.sql();
    sql.exec("BEGIN IMMEDIATE");
    try {
      this.database.assertFencingToken();
      const result = sql.prepare(`INSERT INTO telemetry_sequence_watermarks (adapter_id, aircraft_id, last_sequence)
        VALUES (?, ?, ?)
        ON CONFLICT (adapter_id, aircraft_id) DO UPDATE SET last_sequence = excluded.last_sequence
        WHERE telemetry_sequence_watermarks.last_sequence < excluded.last_sequence`).run(adapterId, aircraftId, sequence) as { changes?: number };
      const accepted = result.changes === 1;
      sql.exec("COMMIT");
      if (accepted) this.watermarks.set(key(adapterId, aircraftId), sequence);
      else {
        const row = sql.prepare("SELECT last_sequence FROM telemetry_sequence_watermarks WHERE adapter_id = ? AND aircraft_id = ?")
          .get(adapterId, aircraftId) as { last_sequence: number } | undefined;
        if (row !== undefined) this.watermarks.set(key(adapterId, aircraftId), row.last_sequence);
      }
      return accepted;
    } catch (error) {
      sql.exec("ROLLBACK");
      throw error;
    }
  }
}

function key(adapterId: string, aircraftId: string): string {
  return `${adapterId}\0${aircraftId}`;
}

function requireIdentifier(value: string, field: string): void {
  if (value.trim() === "" || value !== value.trim() || value.includes("\0") || value.length > 256) throw new Error(`${field} is invalid`);
}
