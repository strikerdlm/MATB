import type { AuthenticatedPrincipal } from "../auth/http.js";
import type { GateActorContext, ServiceActorContext } from "../services/mission-service.js";

export type SupportedGate = "maintenance" | "operator" | "safety" | "commander";

const gateAuthorization = Object.freeze({
  maintenance: { userRole: "maintainer", actorRole: "maintainer" },
  operator: { userRole: "operator", actorRole: "operator" },
  safety: { userRole: "safety-officer", actorRole: "safety" },
  commander: { userRole: "commander", actorRole: "commander" },
} as const);

export function serviceContext(principal: AuthenticatedPrincipal): ServiceActorContext {
  return Object.freeze({
    actorUserId: principal.userId,
    clientSessionId: principal.sessionId,
    occurredAtUtc: new Date().toISOString(),
  });
}

export function gateContext(principal: AuthenticatedPrincipal, gate: SupportedGate): GateActorContext | undefined {
  const authorization = gateAuthorization[gate];
  if (!principal.roles.includes(authorization.userRole)) return undefined;
  return Object.freeze({ ...serviceContext(principal), actorRole: authorization.actorRole });
}

export function isSupportedGate(value: string): value is SupportedGate {
  return Object.prototype.hasOwnProperty.call(gateAuthorization, value);
}

export function hasMissionAssignment(principal: AuthenticatedPrincipal, missionId: string): boolean {
  return principal.missionIds.includes("*") || principal.missionIds.includes(missionId);
}

export function canManageMission(principal: AuthenticatedPrincipal): boolean {
  return principal.roles.includes("commander") || principal.roles.includes("safety-officer");
}
