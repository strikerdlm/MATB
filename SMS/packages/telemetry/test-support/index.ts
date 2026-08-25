import { createHash } from "node:crypto";
import { canonicalJson } from "@fac-isr/evidence";
import { ReplayGateway } from "./gateway.js";
import type { ReplayFixtureResult, ReplayGatewayOptions } from "./types.js";

export * from "./gateway.js";
export * from "./types.js";

function signReplayFixture(events: readonly unknown[]): string {
  return createHash("sha256").update(canonicalJson(events)).digest("hex");
}

export async function replayFixture(events: readonly unknown[], options: ReplayGatewayOptions): Promise<ReplayFixtureResult> {
  const gateway = new ReplayGateway(options);
  return Object.freeze({ records: await gateway.replay(events), retentionRecords: gateway.retentionRecords(), signature: signReplayFixture(events) });
}
