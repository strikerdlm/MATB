import { describe, expect, it } from "vitest";
import {
  evaluateCrewAssignment,
  evaluateDutyAndRest,
  requireOneOperatorPerAircraft,
} from "../src/qualification.js";
import { requireOneOperatorPerAircraft as exportedStaffingCheck } from "../src/index.js";

const policy = {
  policyId: "crew-policy",
  edition: "2026.1",
  maxDutyMinutes: 480,
  minimumRestMinutes: 720,
  maxCumulativeWorkloadMinutes: 300,
  maxScreenExposureMinutes: 240,
  evidenceRefs: ["policy-ev"],
};

const duty = {
  startedAtUtc: "2026-08-09T00:00:00Z",
  previousDutyEndedAtUtc: "2026-08-08T12:00:00Z",
  cumulativeWorkloadMinutes: 300,
  cumulativeScreenExposureMinutes: 240,
  evidenceRefs: ["duty-ev"],
};

const qualification = {
  userId: "U-1",
  role: "operator" as const,
  edition: "2026.1",
  validUntilUtc: "2026-12-01T00:00:00Z",
  recencyValidUntilUtc: "2026-09-01T00:00:00Z",
  evidenceRefs: ["qualification-ev"],
};

const input = {
  assignment: {
    userId: "U-1",
    role: "operator" as const,
    aircraftId: "A-1",
    requiredQualificationEdition: "2026.1",
    evidenceRefs: ["assignment-ev"],
  },
  qualification,
  dutyPeriod: duty,
  dutyPolicy: policy,
  operationalSafetyStatus: "available" as const,
  nowUtc: "2026-08-09T08:00:00Z",
};

describe("crew duty and rest", () => {
  it("allows exact duty, rest, workload, and screen limits", () => {
    expect(evaluateDutyAndRest(duty, policy, "2026-08-09T08:00:00Z")).toEqual({
      status: "available",
      blockers: [],
      evidenceRefs: ["duty-ev", "policy-ev"],
    });
  });

  it("makes excessive duty and insufficient rest unavailable", () => {
    expect(evaluateDutyAndRest(duty, policy, "2026-08-09T08:00:00.001Z").status).toBe("unavailable");
    expect(evaluateDutyAndRest(
      { ...duty, previousDutyEndedAtUtc: "2026-08-08T12:00:00.001Z" },
      policy,
      "2026-08-09T08:00:00Z",
    ).status).toBe("unavailable");
  });

  it("restricts excessive workload and screen exposure", () => {
    expect(evaluateDutyAndRest(
      { ...duty, cumulativeWorkloadMinutes: 301 },
      policy,
      "2026-08-09T07:59:00Z",
    ).status).toBe("restricted");
    expect(evaluateDutyAndRest(
      { ...duty, cumulativeScreenExposureMinutes: 241 },
      policy,
      "2026-08-09T07:59:00Z",
    ).status).toBe("restricted");
  });

  it("returns unknown for malformed time, numeric, or evidence facts", () => {
    expect(evaluateDutyAndRest(duty, policy, "2026-02-30T00:00:00Z").status).toBe("unknown");
    expect(evaluateDutyAndRest(
      { ...duty, cumulativeWorkloadMinutes: Number.NaN },
      policy,
      "2026-08-09T07:59:00Z",
    ).status).toBe("unknown");
    expect(evaluateDutyAndRest(
      { ...duty, evidenceRefs: [] },
      policy,
      "2026-08-09T07:59:00Z",
    ).status).toBe("unknown");
  });

  it("does not apply limits from a malformed policy", () => {
    const result = evaluateDutyAndRest(
      duty,
      { ...policy, policyId: "", maxDutyMinutes: 1 },
      "2026-08-09T08:00:00Z",
    );
    expect(result.status).toBe("unknown");
    expect(result.blockers.map(({ code }) => code)).toEqual(["DUTY_POLICY_INVALID"]);
  });

  it("still detects excessive duty when only the rest timestamp is invalid", () => {
    const result = evaluateDutyAndRest(
      { ...duty, previousDutyEndedAtUtc: "invalid" },
      policy,
      "2026-08-09T08:00:00.001Z",
    );
    expect(result.status).toBe("unavailable");
    expect(result.blockers.map(({ code }) => code)).toEqual([
      "DUTY_TIME_DATA_INVALID",
      "DUTY_LIMIT_EXCEEDED",
    ]);
  });
});

describe("crew assignment qualification", () => {
  it("returns a minimal available evaluation for current qualification and duty", () => {
    expect(evaluateCrewAssignment(input)).toEqual({
      status: "available",
      blockers: [],
      evidenceRefs: ["assignment-ev", "qualification-ev", "duty-ev", "policy-ev"],
    });
  });

  it.each([
    ["qualification", { validUntilUtc: "2026-08-09T08:00:00Z" }, "QUALIFICATION_EXPIRED"],
    ["recency", { recencyValidUntilUtc: "2026-08-09T08:00:00Z" }, "RECENCY_EXPIRED"],
  ])("blocks at the exact %s expiry instant", (_name, qualificationChange, code) => {
    const result = evaluateCrewAssignment({
      ...input,
      qualification: { ...qualification, ...qualificationChange },
    });
    expect(result.status).toBe("unavailable");
    expect(result.blockers).toContainEqual(expect.objectContaining({ code }));
  });

  it("returns unknown when qualification or duty facts are absent", () => {
    expect(evaluateCrewAssignment({ ...input, qualification: undefined }).status).toBe("unknown");
    expect(evaluateCrewAssignment({ ...input, dutyPeriod: undefined }).status).toBe("unknown");
    expect(evaluateCrewAssignment({ ...input, dutyPolicy: undefined }).status).toBe("unknown");
  });

  it.each([
    [
      "qualification user mismatch",
      { qualification: { ...qualification, userId: "U-2" } },
      "unavailable",
      "QUALIFICATION_USER_MISMATCH",
    ],
    [
      "qualification role mismatch",
      { qualification: { ...qualification, role: "observer" as const } },
      "unavailable",
      "QUALIFICATION_ROLE_MISMATCH",
    ],
    [
      "operator aircraft missing",
      { assignment: { ...input.assignment, aircraftId: undefined } },
      "unavailable",
      "OPERATOR_AIRCRAFT_ASSIGNMENT_REQUIRED",
    ],
    [
      "qualification edition stale",
      { qualification: { ...qualification, edition: "2025.4" } },
      "unavailable",
      "QUALIFICATION_EDITION_STALE",
    ],
    [
      "qualification evidence missing",
      { qualification: { ...qualification, evidenceRefs: [] } },
      "unknown",
      "QUALIFICATION_EVIDENCE_REQUIRED",
    ],
    [
      "self-declared restriction",
      { operationalSafetyStatus: "restricted" as const },
      "restricted",
      "OPERATIONAL_SAFETY_STATUS_RESTRICTED",
    ],
    [
      "self-declared unavailability",
      { operationalSafetyStatus: "unavailable" as const },
      "unavailable",
      "OPERATIONAL_SAFETY_STATUS_UNAVAILABLE",
    ],
    [
      "self-declared status unknown",
      { operationalSafetyStatus: "unknown" as const },
      "unknown",
      "OPERATIONAL_SAFETY_STATUS_UNKNOWN",
    ],
  ])("handles %s", (_name, change, status, code) => {
    const result = evaluateCrewAssignment({ ...input, ...change });
    expect(result.status).toBe(status);
    expect(result.blockers).toContainEqual(expect.objectContaining({ code }));
  });

  it("returns unknown for invalid qualification timestamps", () => {
    const result = evaluateCrewAssignment({
      ...input,
      qualification: { ...qualification, validUntilUtc: "2026-02-30T00:00:00Z" },
    });
    expect(result.status).toBe("unknown");
    expect(result.blockers).toContainEqual(expect.objectContaining({ code: "QUALIFICATION_TIME_DATA_INVALID" }));
  });

  it("still detects qualification expiry when only recency time is invalid", () => {
    const result = evaluateCrewAssignment({
      ...input,
      qualification: {
        ...qualification,
        validUntilUtc: "2026-08-09T07:59:59.999Z",
        recencyValidUntilUtc: "invalid",
      },
    });
    expect(result.status).toBe("unavailable");
    expect(result.blockers.map(({ code }) => code)).toContain("QUALIFICATION_TIME_DATA_INVALID");
    expect(result.blockers.map(({ code }) => code)).toContain("QUALIFICATION_EXPIRED");
  });

  it("gives a definitive unavailable fact precedence over missing data", () => {
    expect(evaluateCrewAssignment({
      ...input,
      qualification: { ...qualification, validUntilUtc: input.nowUtc },
      dutyPeriod: undefined,
    }).status).toBe("unavailable");
  });

  it("trims and de-duplicates evidence in first-seen order", () => {
    const result = evaluateCrewAssignment({
      ...input,
      assignment: { ...input.assignment, evidenceRefs: [" assignment-ev ", "shared"] },
      qualification: { ...qualification, evidenceRefs: ["shared", "qualification-ev"] },
      dutyPeriod: { ...duty, evidenceRefs: ["duty-ev", "shared"] },
    });
    expect(result.evidenceRefs).toEqual(["assignment-ev", "shared", "qualification-ev", "duty-ev", "policy-ev"]);
  });

  it("does not expose diagnosis or clinical reasoning from runtime input", () => {
    const runtimeInput = { ...input, diagnosis: "private", clinicalReasoning: "private" };
    const serialized = JSON.stringify(evaluateCrewAssignment(runtimeInput));
    expect(serialized).not.toContain("diagnosis");
    expect(serialized).not.toContain("clinicalReasoning");
    expect(serialized).not.toContain("private");
  });

  it("rejects whitespace-wrapped assignment identities", () => {
    const result = evaluateCrewAssignment({
      ...input,
      assignment: { ...input.assignment, userId: " U-1 ", aircraftId: " A-1 " },
      qualification: { ...qualification, userId: " U-1 " },
    });
    expect(result.status).toBe("unknown");
    expect(result.blockers).toContainEqual(expect.objectContaining({ code: "CREW_ASSIGNMENT_INVALID" }));
  });
});

describe("operator staffing", () => {
  it("blocks one operator assigned to multiple aircraft", () => {
    expect(requireOneOperatorPerAircraft([
      { aircraftId: "A-1", role: "operator", userId: "U-1", qualified: true },
      { aircraftId: "A-2", role: "operator", userId: "U-1", qualified: true },
    ])).toContainEqual(expect.objectContaining({ code: "OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT" }));
  });

  it("blocks missing, multiple, and unqualified operator coverage", () => {
    const assignments = [
      { aircraftId: "A-1", role: "observer" as const, userId: "O-1", qualified: true },
      { aircraftId: "A-2", role: "operator" as const, userId: "U-1", qualified: false },
      { aircraftId: "A-3", role: "operator" as const, userId: "U-2", qualified: true },
      { aircraftId: "A-3", role: "operator" as const, userId: "U-3", qualified: true },
    ];
    expect(requireOneOperatorPerAircraft(
      assignments,
      ["A-1", "A-2", "A-3", "A-4"],
    ).map(({ code }) => code)).toEqual([
      "OPERATOR_ASSIGNMENT_MISSING",
      "QUALIFIED_OPERATOR_REQUIRED",
      "MULTIPLE_OPERATORS_ASSIGNED_TO_AIRCRAFT",
      "OPERATOR_ASSIGNMENT_MISSING",
    ]);
  });

  it("detects every duplicate operator assignment across distinct aircraft", () => {
    const userIds = ["U-1", "U-2", "U-3"];
    const aircraftPairs = [["A-1", "A-2"], ["A-1", "A-3"], ["A-2", "A-3"]] as const;
    for (const userId of userIds) {
      for (const [firstAircraftId, secondAircraftId] of aircraftPairs) {
        const blockers = requireOneOperatorPerAircraft([
          { aircraftId: firstAircraftId, role: "operator", userId, qualified: true },
          { aircraftId: secondAircraftId, role: "operator", userId, qualified: true },
        ]);
        expect(blockers).toContainEqual(expect.objectContaining({
          code: "OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT",
        }));
      }
    }
  });

  it("accepts one different qualified operator for each required aircraft through the package export", () => {
    expect(exportedStaffingCheck([
      { aircraftId: "A-1", role: "operator", userId: "U-1", qualified: true },
      { aircraftId: "A-2", role: "operator", userId: "U-2", qualified: true },
    ], ["A-1", "A-2"])).toEqual([]);
  });

  it("reports malformed assignment identities before coverage blockers", () => {
    const blockers = requireOneOperatorPerAircraft([
      { aircraftId: " ", role: "operator", userId: "U-1", qualified: true },
      { aircraftId: "A-1", role: "operator", userId: " ", qualified: true },
    ], ["A-1"]);
    expect(blockers[0]).toEqual(expect.objectContaining({ code: "CREW_ASSIGNMENT_INVALID" }));
    expect(blockers[1]).toEqual(expect.objectContaining({ code: "CREW_ASSIGNMENT_INVALID" }));
  });

  it("rejects whitespace-wrapped assignment identities instead of normalizing them", () => {
    const blockers = requireOneOperatorPerAircraft([
      { aircraftId: " A-1 ", role: "operator", userId: "U-1", qualified: true },
      { aircraftId: "A-2", role: "operator", userId: " U-1 ", qualified: true },
    ], ["A-1", "A-2"]);
    expect(blockers.slice(0, 2).map(({ code }) => code)).toEqual([
      "CREW_ASSIGNMENT_INVALID",
      "CREW_ASSIGNMENT_INVALID",
    ]);
  });

  it("reports malformed required-aircraft identities", () => {
    expect(requireOneOperatorPerAircraft([], [" "])).toContainEqual(
      expect.objectContaining({ code: "CREW_ASSIGNMENT_INVALID" }),
    );
  });
});
