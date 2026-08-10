import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AlertTimeline } from "../src/components/AlertTimeline.js";
import { GateStatus } from "../src/components/GateStatus.js";
import { MissionSafetyStrip } from "../src/components/MissionSafetyStrip.js";

const blockedMissionProps = {
  mission: {
    missionId: "M24-0518-ISR",
    phase: "UnderReview",
    aircraftClass: "IA",
    flightRule: "VFR",
    visualCondition: "VLOS",
    configuration: "unarmed-isr",
    lastUpdatedLocal: "18 May 2024 09:28",
    freshness: { telemetry: "09:25", evidence: "09:25" },
    operatorState: "Assigned · current",
  },
  safetyResult: {
    status: "blocked",
    blockers: [{ code: "CONFIGURATION_OUT_OF_SCOPE", explanation: "configuration out of scope", severity: "hard" }],
  },
  gates: [
    { gate: "maintenance", decision: "accept", requiredRole: "maintainer", label: "Maintenance" },
    { gate: "operator", decision: "accept", requiredRole: "operator", label: "Operator" },
    { gate: "safety", decision: "block", requiredRole: "safety", label: "Safety" },
    { gate: "commander", decision: "pending", requiredRole: "commander", label: "Commander" },
  ],
  locale: "en",
} as const;

describe("MissionSafetyStrip", () => {
  it("shows phase, class, flight rule, four gates, highest blocker, freshness, and operator state", () => {
    const html = renderToStaticMarkup(<MissionSafetyStrip {...blockedMissionProps} />);

    expect(html).toMatch(/UnderReview/);
    expect(html).toMatch(/IA/);
    expect(html).toMatch(/VFR/);
    expect(html).toMatch(/VLOS/);
    expect(html).toMatch(/configuration out of scope/i);
    expect(html).toMatch(/Highest blocker/i);
    expect(html).toMatch(/Data freshness/i);
    expect(html).toMatch(/Assigned · current/);
    expect((html.match(/role="status"/g) ?? []).length).toBe(4);
  });

  it("renders governing requirement and evidence details for a selected gate", () => {
    const html = renderToStaticMarkup(
      <GateStatus
        gate={{ gate: "safety", decision: "block", requiredRole: "safety", label: "Safety" }}
        reviewerRole="safety"
        kernelBlocked
        governingRequirement={{
          title: "Configuration out of scope",
          sourceExcerptEs: "La configuración declarada no está dentro del alcance autorizado.",
          translationEn: "The declared configuration is outside the authorized scope.",
          sourceEdition: "FAC ISR SMS 2024.2",
          sourceSection: "§ 4.3.1",
          freshness: "Current · 18 May 2024 09:25",
          evidenceHash: "sha256:ev-saf-00077",
          reviewerStatus: "Safety review required",
        }}
      />,
    );

    expect(html).toMatch(/Configuration out of scope/);
    expect(html).toMatch(/La configuración declarada/);
    expect(html).toMatch(/sha256:ev-saf-00077/);
    expect(html).toMatch(/Safety review required/);
    expect(html).toMatch(/disabled/);
  });
});

describe("AlertTimeline", () => {
  it("labels degraded and blocker alerts with explicit status text", () => {
    const html = renderToStaticMarkup(
      <AlertTimeline
        alerts={[
          { id: "a-1", occurredAtUtc: "2024-05-18T14:25:00Z", severity: "blocker", title: "Safety evaluation blocked", detail: "Configuration out of scope" },
          { id: "a-2", occurredAtUtc: "2024-05-18T14:20:00Z", severity: "degraded", title: "Telemetry degraded", detail: "Read-only link dropout" },
        ]}
      />,
    );

    expect(html).toMatch(/BLOCKER/);
    expect(html).toMatch(/DEGRADED/);
    expect(html).toMatch(/Safety evaluation blocked/);
    expect(html).toMatch(/Read-only link dropout/);
  });
});
