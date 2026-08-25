import type { GateApproval, MissionRevision } from "@fac-isr/safety-kernel";

const ROLE_BY_GATE = {
  maintenance: "maintainer",
  operator: "operator",
  safety: "safety",
  commander: "commander",
} as const;

export function validateGateAuthorityScope(revision: MissionRevision, approval: Pick<GateApproval, "gate" | "actorUserId" | "actorRole" | "aircraftId">): void {
  if (approval.actorRole !== ROLE_BY_GATE[approval.gate]) throw new Error(`actor role is not authorized for the ${approval.gate} gate`);
  const crew = revision.crew.find((member) => member.userId === approval.actorUserId && member.role === approval.actorRole);
  if (crew === undefined || !crew.qualified || !crew.recencyCurrent || crew.dutyStatus !== "available") throw new Error(`gate actor ${approval.actorUserId} is not qualified and available`);
  if (approval.gate === "operator" && (approval.aircraftId === undefined || crew.aircraftId !== approval.aircraftId)) throw new Error("operator gate approval must name the actor's assigned aircraft");
  if (approval.gate !== "operator" && approval.aircraftId !== undefined) throw new Error("only operator gate approval may name an aircraft");
}
