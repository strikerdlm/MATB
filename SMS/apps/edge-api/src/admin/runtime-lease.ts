import type { EdgeDatabase } from "../db/migrate.js";

export interface RuntimeLeaseOptions {
  readonly holderId: string;
  readonly now?: () => string;
  readonly durationMs?: number;
}

export class RuntimeLeaseError extends Error {}

export class RuntimeLease {
  private readonly now: () => string;
  private readonly durationMs: number;

  public constructor(private readonly database: EdgeDatabase, private readonly options: RuntimeLeaseOptions) {
    if (options.holderId.trim() === "") throw new RuntimeLeaseError("runtime lease holder is required");
    this.now = options.now ?? (() => new Date().toISOString());
    this.durationMs = options.durationMs ?? 30_000;
    if (!Number.isInteger(this.durationMs) || this.durationMs <= 0) throw new RuntimeLeaseError("runtime lease duration must be positive");
  }

  public acquire(): void {
    const sql = this.database.sql();
    const now = this.instant();
    sql.exec("BEGIN IMMEDIATE");
    try {
      const current = sql.prepare("SELECT holder_id, expires_at_utc FROM runtime_lease WHERE singleton = 1").get() as { holder_id: string; expires_at_utc: string } | undefined;
      if (current !== undefined && current.holder_id !== this.options.holderId && Date.parse(current.expires_at_utc) > now.getTime()) {
        throw new RuntimeLeaseError(`runtime lease is held by ${current.holder_id}`);
      }
      sql.prepare(`INSERT INTO runtime_lease (singleton, holder_id, acquired_at_utc, expires_at_utc)
        VALUES (1, ?, ?, ?) ON CONFLICT(singleton) DO UPDATE SET holder_id = excluded.holder_id,
        acquired_at_utc = excluded.acquired_at_utc, expires_at_utc = excluded.expires_at_utc`)
        .run(this.options.holderId, now.toISOString(), new Date(now.getTime() + this.durationMs).toISOString());
      sql.exec("COMMIT");
    } catch (error) {
      sql.exec("ROLLBACK");
      throw error;
    }
  }

  public renew(): void {
    const now = this.instant();
    const result = this.database.sql().prepare("UPDATE runtime_lease SET expires_at_utc = ? WHERE singleton = 1 AND holder_id = ?")
      .run(new Date(now.getTime() + this.durationMs).toISOString(), this.options.holderId) as { changes?: number | bigint };
    if (Number(result.changes ?? 0) !== 1) throw new RuntimeLeaseError("runtime lease is not owned by this holder");
  }

  public release(): void {
    this.database.sql().prepare("DELETE FROM runtime_lease WHERE singleton = 1 AND holder_id = ?").run(this.options.holderId);
  }

  private instant(): Date {
    const value = new Date(this.now());
    if (!Number.isFinite(value.getTime())) throw new RuntimeLeaseError("runtime lease clock is invalid");
    return value;
  }
}
