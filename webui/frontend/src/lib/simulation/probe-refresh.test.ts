import { expect, it } from "vitest";
import { reconcileProbeRefresh } from "./probe-refresh";
import type {
  ActiveProbePayload,
  IsaProbePayload,
  SagatProbePayload,
  SessionView,
} from "@/types/simulation";

const isa: IsaProbePayload = {
  kind: "ISA",
  probe_id: "isa-1",
  timeout_ms: 60000,
};
const sagat: SagatProbePayload = {
  kind: "SAGAT",
  probe_id: "sa-1",
  sa_level: 1,
  domain: "perception",
  question: "Aircraft count?",
  options: ["2", "Unknown"],
  timeout_ms: 15000,
};
const running = {
  lifecycle: "RUNNING",
  protocol_phase: "BLOCK_RUNNING",
  active_probe: null,
} as SessionView;

it("clears the completed post-block gate even if its remaining scales were streamed", () => {
  const answered = {
    kind: "POST_BLOCK",
    scales: ["NASA_TLX", "BEDFORD"],
  } as ActiveProbePayload;
  const update = {
    kind: "POST_BLOCK",
    scales: ["BEDFORD"],
  } as ActiveProbePayload;
  expect(
    reconcileProbeRefresh(update, answered, {
      ...running,
      protocol_phase: "COMPLETE",
    }).activeProbe,
  ).toBeNull();
});

it("keeps a streamed SAGAT concealed when the previous ISA response arrives late", () => {
  const result = reconcileProbeRefresh(sagat, isa, running);
  expect(result.activeProbe).toBe(sagat);
  expect(result.concealOperationalState).toBe(true);
  expect(result.session.protocol_phase).toBe("SAGAT_ACTIVE");
  expect(result.session.lifecycle).toBe("PAUSED");
});

it("uses the next gate in REST and clears only the answered gate", () => {
  expect(
    reconcileProbeRefresh(isa, isa, { ...running, active_probe: sagat })
      .activeProbe,
  ).toBe(sagat);
  expect(reconcileProbeRefresh(sagat, sagat, running).activeProbe).toBeNull();
  expect(
    reconcileProbeRefresh(sagat, sagat, running).concealOperationalState,
  ).toBe(false);
});
