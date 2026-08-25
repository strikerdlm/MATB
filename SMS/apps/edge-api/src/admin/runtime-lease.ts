import type { EdgeDatabase } from "../db/migrate.js";
import { randomBytes } from "node:crypto";

export interface RuntimeLeaseOptions {
  readonly holderId: string;
  readonly now?: () => string;
  readonly durationMs?: number;
}

export class RuntimeLeaseError extends Error {}

export class RuntimeLease {
  private readonly now: () => string;
  private readonly durationMs: number;
  private readonly leaseId: string;
  private fencingToken?: number;

  public constructor(private readonly database: EdgeDatabase, private readonly options: RuntimeLeaseOptions) {
    if (options.holderId.trim() === "") throw new RuntimeLeaseError("runtime lease holder is required");
    this.now = options.now ?? (() => new Date().toISOString());
    this.durationMs = options.durationMs ?? 30_000;
    this.leaseId = `${options.holderId}:${randomBytes(16).toString("hex")}`;
    if (!Number.isInteger(this.durationMs) || this.durationMs <= 0) throw new RuntimeLeaseError("runtime lease duration must be positive");
  }

  public acquire(): void {
    const sql = this.database.sql();
    const now = this.instant();
    sql.exec("BEGIN IMMEDIATE");
    try {
      const current = sql.prepare("SELECT holder_id, fencing_token, expires_at_utc FROM runtime_lease WHERE singleton = 1").get() as { holder_id: string; fencing_token: number; expires_at_utc: string } | undefined;
      if (current !== undefined && Date.parse(current.expires_at_utc) > now.getTime()) {
        throw new RuntimeLeaseError(`runtime lease is held by ${current.holder_id}`);
      }
      const nextToken = (current?.fencing_token ?? 0) + 1;
      sql.prepare(`INSERT INTO runtime_lease (singleton, holder_id, fencing_token, acquired_at_utc, expires_at_utc)
        VALUES (1, ?, ?, ?, ?) ON CONFLICT(singleton) DO UPDATE SET holder_id = excluded.holder_id,
        fencing_token = excluded.fencing_token, acquired_at_utc = excluded.acquired_at_utc, expires_at_utc = excluded.expires_at_utc`)
        .run(this.leaseId, nextToken, now.toISOString(), new Date(now.getTime() + this.durationMs).toISOString());
      sql.exec("COMMIT");
      this.fencingToken = nextToken;
      this.database.setFencingToken(this.leaseId, nextToken, this.now);
    } catch (error) {
      sql.exec("ROLLBACK");
      throw error;
    }
  }

  public renew(): void {
    const now = this.instant();
    if (this.fencingToken === undefined) throw new RuntimeLeaseError("runtime lease is not owned by this holder");
    const result = this.database.sql().prepare("UPDATE runtime_lease SET expires_at_utc = ? WHERE singleton = 1 AND holder_id = ? AND fencing_token = ? AND expires_at_utc > ?")
      .run(new Date(now.getTime() + this.durationMs).toISOString(), this.leaseId, this.fencingToken, now.toISOString()) as { changes?: number | bigint };
    if (Number(result.changes ?? 0) !== 1) throw new RuntimeLeaseError("runtime lease is not owned by this holder");
  }

  public release(): void {
    const now = this.instant().toISOString();
    this.database.sql().prepare("UPDATE runtime_lease SET expires_at_utc = ? WHERE singleton = 1 AND holder_id = ?").run(now, this.leaseId);
    this.database.clearFencingToken(this.leaseId);
    this.fencingToken = undefined;
  }

  private instant(): Date {
    const value = new Date(this.now());
    if (!Number.isFinite(value.getTime())) throw new RuntimeLeaseError("runtime lease clock is invalid");
    return value;
  }
}
