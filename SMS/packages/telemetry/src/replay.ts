import { createHash } from "node:crypto";
import { canonicalJson } from "@fac-isr/evidence";
import { ReplayGateway } from "./gateway.js";
import type { ReplayFixtureResult, ReplayGatewayOptions } from "./types.js";

export function signReplayFixture(events: readonly unknown[]): string {
  return createHash("sha256").update(canonicalJson(events)).digest("hex");
}

export async function replayFixture(events: readonly unknown[], options: ReplayGatewayOptions): Promise<ReplayFixtureResult> {
  const gateway = new ReplayGateway(options);
  const records = await gateway.replay(events);
  return Object.freeze({ records, retentionRecords: gateway.retentionRecords(), signature: signReplayFixture(events) });
}

export { ReplayGateway } from "./gateway.js";
