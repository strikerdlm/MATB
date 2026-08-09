import { describe, expect, it } from "vitest";
import {
  evaluateCrewAssignment,
  evaluateDutyAndRest,
  requireOneOperatorPerAircraft,
  type CrewAssignmentInput,
  type DutyPeriod,
  type DutyPolicy,
} from "../src/qualification.js";

const nowUtc = "2026-08-09T12:00:00Z";
const validDutyPolicy: DutyPolicy = {
  maxDutyMinutes: 480,
  minimumRestMinutes: 30,
  maxCumulativeWorkloadMinutes: 300,
  maxScreenExposureMinutes: 360,
  requireSafetyDeclaration: true,
  evidenceRefs: ["policy-duty-1"],
};
const validDutyPeriod: DutyPeriod = {
  id: "duty-1",
  userId: "operator-1",
  startUtc: "2026-08-09T08:00:00Z",
  priorDutyEndUtc: "2026-08-09T07:00:00Z",
  cumulativeWorkloadMinutes: 60,
  screenExposureMinutes: 120,
  selfDeclaredSafetyStatus: "able",
  evidenceRefs: ["duty-1"],
};
const validInput: CrewAssignmentInput = {
  userId: "operator-1",
  aircraftId: "aircraft-1",
  role: "operator",
  nowUtc,
  requiredQualificationEdition: "FAC-UAS-2026",
  qualification: {
    id: "qualification-1",
    edition: "FAC-UAS-2026",
    validFromUtc: "2026-01-01T00:00:00Z",
    expiresAtUtc: "2027-01-01T00:00:00Z",
    evidenceRefs: ["qualification-1"],
  },
  recency: {
    validUntilUtc: "2026-12-01T00:00:00Z",
    evidenceRefs: ["recency-1"],
  },
  dutyPeriod: validDutyPeriod,
  dutyPolicy: validDutyPolicy,
  evidenceRefs: ["assignment-1"],
};

describe("crew qualification and staffing", () => {
  it("requires an independent qualified operator for each active aircraft", () => {
    expect(requireOneOperatorPerAircraft([
      { aircraftId: "A-1", role: "operator", userId: "U-1", qualified: true },
      { aircraftId: "A-2", role: "operator", userId: "U-1", qualified: true },
    ])).toContainEqual(expect.objectContaining({ code: "OPERATOR_ASSIGNED_TO_MULTIPLE_AIRCRAFT" }));
  });

  it("returns available when qualification, recency, duty, and self-declaration are current", () => {
    expect(evaluateCrewAssignment(validInput)).toMatchObject({ status: "available", blockers: [] });
  });

  it("fails closed at qualification and duty expiry boundaries", () => {
    expect(evaluateCrewAssignment({
      ...validInput,
      nowUtc: validInput.qualification.expiresAtUtc,
    }).status).toBe("unavailable");

    expect(evaluateDutyAndRest(
      { ...validDutyPeriod, startUtc: "2026-08-09T04:00:00Z", priorDutyEndUtc: "2026-08-09T03:00:00Z" },
      validDutyPolicy,
      nowUtc,
    ).status).toBe("unavailable");
  });

  it("restricts an operator when required rest or screen exposure is exceeded", () => {
    expect(evaluateDutyAndRest(
      { ...validDutyPeriod, priorDutyEndUtc: "2026-08-09T07:45:00Z" },
      validDutyPolicy,
      nowUtc,
    ).status).toBe("restricted");
    expect(evaluateCrewAssignment({
      ...validInput,
      dutyPeriod: { ...validDutyPeriod, screenExposureMinutes: 361 },
    }).status).toBe("restricted");
  });

  it("does not expose medical diagnosis in operational output", () => {
    const inputWithMedicalNote = {
      ...validInput,
      medicalNote: "diagnosis: intentionally excluded",
    };
    const result = evaluateCrewAssignment(inputWithMedicalNote);
    expect(JSON.stringify(result)).not.toContain("diagnosis");
    expect(Object.keys(result)).not.toContain("medicalNote");
  });

  it("returns unknown when required evidence or timestamps cannot be trusted", () => {
    expect(evaluateCrewAssignment({
      ...validInput,
      evidenceRefs: [],
    }).status).toBe("unknown");
    expect(evaluateDutyAndRest(
      { ...validDutyPeriod, startUtc: "2026-02-30T00:00:00Z" },
      validDutyPolicy,
      nowUtc,
    ).status).toBe("unknown");
  });
});
