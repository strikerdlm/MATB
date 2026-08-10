export const USER_ROLES = [
  "commander",
  "safety-officer",
  "maintainer",
  "operator",
  "observer",
  "reviewer",
  "researcher",
  "administrator",
] as const;

export type UserRole = (typeof USER_ROLES)[number];

export interface AuthorizationSubject {
  readonly userId: string;
  readonly roles: readonly UserRole[];
  readonly missionIds: readonly string[];
  readonly state?: "active" | "locked" | "expired";
  readonly lockedAtUtc?: string;
  readonly requiresReauthentication?: boolean;
}

export interface AuthorizationRequest {
  readonly action: string;
  readonly missionId?: string;
}

export interface AuthorizationResult {
  readonly allowed: boolean;
  readonly reason: string;
  readonly requiredRole?: UserRole;
}

type GateName = "maintenance" | "operator" | "safety" | "commander";

const gateRoles: Record<GateName, UserRole> = {
  maintenance: "maintainer",
  operator: "operator",
  safety: "safety-officer",
  commander: "commander",
};

const gateActionPattern = /^gate:(maintenance|operator|safety|commander):[a-z-]+$/;

function deny(reason: string, requiredRole?: UserRole): AuthorizationResult {
  return requiredRole === undefined
    ? { allowed: false, reason }
    : { allowed: false, reason, requiredRole };
}

function requestFrom(action: string | AuthorizationRequest): AuthorizationRequest | undefined {
  if (typeof action === "string") return { action };
  if (
    action === null
    || typeof action !== "object"
    || typeof action.action !== "string"
  ) return undefined;
  return action;
}

function gateForAction(action: string): GateName | undefined {
  if (!gateActionPattern.test(action)) return undefined;
  return action.split(":")[1] as GateName;
}

export function requiredRoleForAction(action: string): UserRole | undefined {
  const gate = gateForAction(action);
  return gate === undefined ? undefined : gateRoles[gate];
}

export function isUserRole(value: string): value is UserRole {
  return (USER_ROLES as readonly string[]).includes(value);
}

export function authorize(
  subject: AuthorizationSubject,
  action: string | AuthorizationRequest,
): AuthorizationResult {
  const request = requestFrom(action);
  if (request === undefined || subject === null || typeof subject !== "object") {
    return deny("invalid authorization request");
  }
  if (subject.userId.trim() === "") return deny("identity is required");
  if (subject.state === "locked" || subject.lockedAtUtc !== undefined) {
    return deny("session is locked");
  }
  if (subject.state === "expired") return deny("session is expired");
  if (subject.requiresReauthentication === true) return deny("re-authentication is required");

  const gate = gateForAction(request.action);
  if (gate === undefined) {
    if (request.action.startsWith("system:") && subject.roles.includes("administrator")) {
      return { allowed: true, reason: "administrator permission granted" };
    }
    return deny("action is not authorized");
  }

  const requiredRole = gateRoles[gate];
  if (!subject.roles.includes(requiredRole)) {
    return deny(`role ${requiredRole} is required`, requiredRole);
  }
  if (request.missionId === undefined || request.missionId.trim() === "") {
    return deny("mission assignment is required", requiredRole);
  }
  if (!subject.missionIds.includes("*") && !subject.missionIds.includes(request.missionId)) {
    return deny("identity is not assigned to this mission", requiredRole);
  }
  return { allowed: true, reason: `${requiredRole} permission granted`, requiredRole };
}
