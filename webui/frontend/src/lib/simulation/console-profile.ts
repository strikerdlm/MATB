import type { ConsoleProfile } from "@/types/simulation";

/** Exact identity of console-profile.v1.json; changing chrome requires a new version. */
export const MISSION_CONSOLE_PROFILE: Readonly<ConsoleProfile> = Object.freeze({
  id: "mission-console",
  version: 1,
  sha256: "55df7b7b1ea4b48cbc6c0a70412bc01c3e8436a26a8c6968676d76c3df7314b9",
});

export function consoleProfileStatus(profile: unknown): "legacy" | "supported" | "unsupported" {
  if (profile === null || profile === undefined) return "legacy";
  if (typeof profile !== "object") return "unsupported";
  const candidate = profile as Partial<ConsoleProfile>;
  if (candidate.id === "mission-swarm-console" && candidate.version === 1 && candidate.sha256 === "4ba0331866765885dbc01f0a25600b7565a1d23c7d54e640b7d95897ed9e81ba") return "supported";
  return candidate.id === MISSION_CONSOLE_PROFILE.id
    && candidate.version === MISSION_CONSOLE_PROFILE.version
    && candidate.sha256 === MISSION_CONSOLE_PROFILE.sha256 ? "supported" : "unsupported";
}
