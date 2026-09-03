export const PARTICIPANT_ID_PATTERN = /^P[0-9]{2,6}$/;

/** Normalize the common shorthand p1 to the protocol pseudonym P01. */
export function normalizeParticipantId(value: string): string {
  const candidate = value.trim().toUpperCase();
  const shorthand = /^P([0-9]{1,6})$/.exec(candidate);
  if (!shorthand) return candidate;
  return `P${shorthand[1].padStart(2, "0")}`;
}

export function isParticipantId(value: string): boolean {
  return PARTICIPANT_ID_PATTERN.test(value);
}
