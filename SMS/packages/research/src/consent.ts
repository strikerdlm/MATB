import type { ConsentRecord, ParticipantCode } from "./types.js";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function requiredText(value: unknown, field: string): string {
  if (typeof value !== "string" || value.trim() === "") throw new TypeError(`${field} is required`);
  return value.trim();
}

function utc(value: unknown, field: string): string {
  const text = requiredText(value, field);
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z$/.test(text) || !Number.isFinite(Date.parse(text))) {
    throw new TypeError(`${field} must be UTC`);
  }
  return text;
}

function strictKeys(value: Record<string, unknown>, allowed: readonly string[]): void {
  const unknown = Object.keys(value).find((key) => !allowed.includes(key));
  if (unknown !== undefined) throw new TypeError(`research separation boundary rejects field: ${unknown}`);
}

function freeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const child of Object.values(value as Record<string, unknown>)) freeze(child);
  }
  return value;
}

export function createConsentRecord(input: unknown): ConsentRecord {
  if (!isRecord(input)) throw new TypeError("consent must be an object");
  strictKeys(input, ["id", "protocolId", "participantCode", "consentVersion", "consentedAtUtc", "withdrawnAtUtc", "withdrawalReason"]);
  const consentedAtUtc = utc(input.consentedAtUtc, "consentedAtUtc");
  const withdrawnAtUtc = input.withdrawnAtUtc === undefined ? undefined : utc(input.withdrawnAtUtc, "withdrawnAtUtc");
  if (withdrawnAtUtc !== undefined && Date.parse(withdrawnAtUtc) < Date.parse(consentedAtUtc)) throw new TypeError("withdrawal cannot precede consent");
  const withdrawalReason = input.withdrawalReason === undefined ? undefined : requiredText(input.withdrawalReason, "withdrawalReason");
  return freeze({
    id: requiredText(input.id, "id"),
    protocolId: requiredText(input.protocolId, "protocolId"),
    participantCode: requiredText(input.participantCode, "participantCode") as ParticipantCode,
    consentVersion: requiredText(input.consentVersion, "consentVersion"),
    consentedAtUtc,
    ...(withdrawnAtUtc === undefined ? {} : { withdrawnAtUtc }),
    ...(withdrawalReason === undefined ? {} : { withdrawalReason }),
  });
}

export function withdrawConsent(consent: ConsentRecord, withdrawnAtUtc: string, withdrawalReason?: string): ConsentRecord {
  if (!isRecord(consent)) throw new TypeError("consent is required");
  const normalized = createConsentRecord(consent);
  if (normalized.withdrawnAtUtc !== undefined) throw new TypeError("consent is already withdrawn");
  const withdrawalTime = utc(withdrawnAtUtc, "withdrawnAtUtc");
  if (Date.parse(withdrawalTime) < Date.parse(normalized.consentedAtUtc)) throw new TypeError("withdrawal cannot precede consent");
  const reason = withdrawalReason === undefined ? undefined : requiredText(withdrawalReason, "withdrawalReason");
  return freeze({
    ...normalized,
    withdrawnAtUtc: withdrawalTime,
    ...(reason === undefined ? {} : { withdrawalReason: reason }),
  });
}
