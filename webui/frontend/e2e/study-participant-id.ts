import type { TestInfo } from "@playwright/test";

/** Reserved fixture ranges in the runner's fresh DB, separate from PID-based IDs. */
export function studyParticipantId(
  family: "preparation" | "restore",
  locale: "en" | "es-419",
  info: Pick<TestInfo, "repeatEachIndex" | "retry">,
): string {
  const { repeatEachIndex, retry } = info;
  if (
    !Number.isInteger(repeatEachIndex) ||
    repeatEachIndex < 0 ||
    repeatEachIndex >= 100 ||
    !Number.isInteger(retry) ||
    retry < 0 ||
    retry >= 10
  ) {
    throw new Error("Study participant fixture range exhausted");
  }
  const base = family === "preparation" ? 910000 : 920000;
  return `P${base + repeatEachIndex * 100 + retry * 10 + (locale === "en" ? 1 : 2)}`;
}
