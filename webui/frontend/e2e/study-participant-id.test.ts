import { expect, test } from "vitest";
import { PARTICIPANT_ID_PATTERN } from "../src/lib/participant-id";
import { studyParticipantId } from "./study-participant-id";

test("preparation and restore remain distinct in the same worker across locales and attempts", () => {
  const ids = new Set<string>();
  for (const family of ["preparation", "restore"] as const) {
    for (const locale of ["en", "es-419"] as const) {
      for (let repeatEachIndex = 0; repeatEachIndex < 100; repeatEachIndex++) {
        for (let retry = 0; retry < 10; retry++) {
          const id = studyParticipantId(family, locale, {
            repeatEachIndex,
            retry,
          });
          expect(id).toMatch(PARTICIPANT_ID_PATTERN);
          expect(ids.has(id)).toBe(false);
          // Existing PID-based fixtures use lower ranges; predictability uses P89000x.
          expect(Number(id.slice(1))).toBeGreaterThanOrEqual(910000);
          ids.add(id);
        }
      }
    }
  }
  expect(ids.size).toBe(4000);
});

test.each([
  { repeatEachIndex: 100, retry: 0 },
  { repeatEachIndex: -1, retry: 0 },
  { repeatEachIndex: 0.5, retry: 0 },
  { repeatEachIndex: 0, retry: 10 },
  { repeatEachIndex: 0, retry: -1 },
  { repeatEachIndex: 0, retry: 0.5 },
])("rejects exhausted or invalid fixture slots: %j", (info) => {
  expect(() => studyParticipantId("restore", "en", info)).toThrow(
    "range exhausted",
  );
});
