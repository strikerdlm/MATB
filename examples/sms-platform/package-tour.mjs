import { createHash } from "node:crypto";

import { calculateMissionEnergy } from "../../SMS/packages/energy/dist/index.js";
import { sha256File } from "../../SMS/packages/evidence/dist/index.js";
import { evaluateCapability } from "../../SMS/packages/fleet/dist/index.js";
import { buildRoute } from "../../SMS/packages/geo/dist/index.js";
import { evaluateOperationalStatus } from "../../SMS/packages/human-performance/dist/index.js";
import {
  createConsentRecord,
  exportDeidentified,
  MatbResearchAdapter,
  openConsentedSession,
  parseResearchSession,
  registerProtocol,
} from "../../SMS/packages/research/dist/index.js";
import { evaluateMission } from "../../SMS/packages/safety-kernel/dist/index.js";
import {
  completeMoc,
  createAuditFinding,
  createCorrectiveAction,
  evaluateErpReadiness,
  evaluateSpi,
  openManagementOfChange,
  promoteMissionHazard,
  verifyCorrectiveAction,
} from "../../SMS/packages/sms/dist/index.js";
import { ReplayGateway } from "../../SMS/packages/telemetry/dist/index.js";

const segment = (id, kind, durationMinutes, payloadPowerW) => ({
  id,
  kind,
  distanceNm: durationMinutes / 120,
  distanceM: (durationMinutes / 120) * 1852,
  durationS: durationMinutes * 60,
  durationMinutes,
  altitudeChangeFt: kind === "climb" ? 500 : 0,
  altitudeChangeM: kind === "climb" ? 152.4 : 0,
  expectedGroundspeedKt: 30,
  expectedGroundspeedMps: 30 * 0.5144444444444445,
  ...(payloadPowerW === undefined ? {} : { payloadPowerW }),
});

const validEnergyInput = {
  aircraftId: "UAS-SYNTH-1",
  battery: {
    serialNumber: "BAT-SYNTH-1",
    aircraftCompatibility: ["UAS-SYNTH-1"],
    chemistry: "li-po",
    nominalCapacityWh: 500,
    nominalEnergyJ: 1_800_000,
    cycles: 10,
    ageDays: 30,
    stateOfChargePercent: 90,
    stateOfHealthPercent: 98,
    status: "released",
  },
  segments: [
    segment("CLIMB-SYNTH-1", "climb", 1),
    segment("CRUISE-SYNTH-1", "cruise", 10),
    segment("WORK-SYNTH-1", "work", 10, 20),
    segment("HOLD-SYNTH-1", "hold", 5),
    segment("RETURN-SYNTH-1", "return", 8),
    segment("DIVERSION-SYNTH-1", "diversion", 4),
    segment("CONTINGENCY-SYNTH-1", "contingency", 5),
  ],
  weather: { windKt: 10, temperatureC: 25, densityAltitudeFt: 1_000 },
  payloadMassKg: 10,
  approvedReserve: {
    recoveryMinimumPercent: 15,
    diversionMinimumPercent: 10,
    contingencyMinimumPercent: 5,
    uncertaintyMethod: "approved-model",
    effectiveFromUtc: "2026-08-01T00:00:00Z",
  },
  modelVersion: "energy-model-SYNTH-v1",
  approvedPerformance: {
    basePowerWBySegment: {
      climb: 300,
      cruise: 180,
      work: 220,
      hold: 160,
      return: 190,
      diversion: 210,
      contingency: 180,
    },
    payloadPowerWPerKg: 2,
    climbEnergyPerMeterJ: 12,
    windPenaltyPercentPerKt: 0.5,
    referenceTemperatureC: 15,
    temperaturePenaltyPercentPerC: 0.3,
    referenceDensityAltitudeFt: 0,
    densityAltitudePenaltyPercentPer1000Ft: 0.1,
    uncertaintyPercent: 8,
    evidenceRefs: ["EV-PERFORMANCE-SYNTH-1"],
  },
};

const evidenceHash = await sha256File(
  new URL("./fixtures/controlled-evidence.txt", import.meta.url),
);
const energyResult = calculateMissionEnergy(validEnergyInput);
const capability = evaluateCapability(
  {
    id: "CAP-SYNTH-1",
    subjectId: "UAS-SYNTH-1",
    capability: "vlos",
    value: true,
    operatingConditions: {},
    evidenceRefs: ["EV-SYNTH-1"],
    confidence: "qualified",
    validFromUtc: "2026-08-01T00:00:00Z",
  },
  {},
  {
    current: true,
    acceptedEvidenceRefs: ["EV-SYNTH-1"],
    approved: true,
    asOfUtc: "2026-08-14T00:00:00Z",
    subjectId: "UAS-SYNTH-1",
  },
);
const route = buildRoute({
  id: "ROUTE-SYNTH-1",
  waypoints: [
    { id: "WP-1", lat: 4.70, lon: -74.10, altitude: 2600, altitudeReference: "MSL", role: "route" },
    { id: "WP-2", lat: 4.80, lon: -74.00, altitude: 2650, altitudeReference: "MSL", role: "recovery" },
  ],
  flightRule: "VFR",
  visualCondition: "VLOS",
  altitudeReference: "MSL",
  sourcePackageIds: ["MAP-SYNTH-1"],
});
const replay = await new ReplayGateway({
  aircraftId: "UAS-SYNTH-1",
  now: () => "2026-08-14T00:00:10.000Z",
  maxDelayMs: 5000,
}).replay([
  {
    eventId: "TEL-SYNTH-1",
    aircraftId: "UAS-SYNTH-1",
    observedAtUtc: "2026-08-14T00:00:01.000Z",
    sourcePackageIds: ["TEL-PKG-SYNTH-1"],
  },
]);

const safetyResult = evaluateMission({
  mission: {
    id: "MR-SYNTH-1",
    missionId: "MISSION-SYNTH-1",
    revision: 1,
    profileId: "fac-state-aviation",
    state: "Planned",
    aircraft: [
      {
        aircraftId: "UAS-SYNTH-1",
        aircraftClass: "IC",
        configuration: "unarmed-isr",
        operatorUserId: "OP-SYNTH-1",
      },
    ],
    flightRule: "VFR",
    visualCondition: "VLOS",
    configuration: "unarmed-isr",
    route: {
      areaId: "AREA-SYNTH-1",
      routeHash: route.segments[0].geometryHash,
      terrainStatus: "pass",
      obstacleStatus: "pass",
      airspaceStatus: "pass",
      notamStatus: "pass",
      visualConditionStatus: "pass",
    },
    crew: [
      {
        userId: "OP-SYNTH-1",
        role: "operator",
        aircraftId: "UAS-SYNTH-1",
        qualified: true,
        recencyCurrent: true,
        dutyStatus: "available",
      },
    ],
    evidenceSnapshotId: "EV-SNAPSHOT-SYNTH-1",
    dataSnapshots: [],
    riskAssessment: {
      hazardIds: [],
      mitigationIds: [],
      status: "complete",
    },
  },
  requirements: [
    {
      requirementId: "REQ-SYNTH-EVIDENCE-1",
      sourceRefs: [],
      Spanish: "Requisito sintético pendiente de evidencia controlada",
      EnglishControlled: "Synthetic requirement pending controlled evidence",
      applicabilityExpression: "state_aviation",
      severity: "hard",
      evidenceRequired: true,
      effectiveFromUtc: "2026-08-01T00:00:00Z",
      interpretationStatus: "approved",
      reviewerIds: ["REVIEWER-SYNTH-1"],
    },
  ],
  policy: {
    packageId: "POLICY-SYNTH-1",
    version: "1.0.0",
    status: "approved",
    freshness: {
      aip: { maxAgeMinutes: 60, critical: true },
      notam: { maxAgeMinutes: 60, critical: true },
      weather: { maxAgeMinutes: 60, critical: true },
      terrain: { maxAgeMinutes: 60, critical: true },
      airspace: { maxAgeMinutes: 60, critical: true },
      policy: { maxAgeMinutes: 60, critical: true },
      regulation: { maxAgeMinutes: 60, critical: true },
    },
    delegatedAuthorities: [],
  },
  nowUtc: "2026-08-14T00:00:00Z",
});
if (safetyResult.status !== "blocked") {
  throw new Error("Capability tour must remain fail-closed");
}

const hazard = promoteMissionHazard({
  missionHazard: {
    id: "MH-SYNTH-1",
    title: "Synthetic wildlife activity",
    description: "Training-only scenario",
    causes: ["synthetic seasonal activity"],
    consequences: ["exercise interruption"],
    residualRiskId: "RISK-SYNTH-1",
  },
  organizationalOwnerId: "SMS-SYNTH-OWNER",
  promotedAtUtc: "2026-08-14T00:00:00Z",
});
const spi = evaluateSpi(
  { value: 4, unit: "synthetic-events/100-hours" },
  { alertAt: 3, actionAt: 5 },
);

let auditStatus = "blocked";
try {
  createAuditFinding({
    id: "AUDIT-SYNTH-1",
    criterion: "Synthetic controlled evidence",
    scope: "training-only",
    evidenceRefs: [],
    ownerId: "SMS-SYNTH-OWNER",
    dueAtUtc: "2026-09-01T00:00:00Z",
    status: "open",
  });
  auditStatus = "unexpectedly-created";
} catch {
  auditStatus = "blocked";
}
const correctiveAction = createCorrectiveAction({
  id: "CAPA-SYNTH-1",
  ownerId: "SMS-SYNTH-OWNER",
  dueAtUtc: "2026-09-01T00:00:00Z",
  evidence: [],
});
const capa = verifyCorrectiveAction(correctiveAction, {});
const erp = evaluateErpReadiness({
  ownerId: "SMS-SYNTH-OWNER",
  contactPlan: "synthetic exercise contact plan",
  aircraftContingencies: ["synthetic recovery exercise"],
  crewContingencies: ["synthetic relief exercise"],
  routeContingencies: ["synthetic alternate area"],
  currentAtUtc: "2026-08-14T00:00:00Z",
});
const moc = openManagementOfChange({
  id: "MOC-SYNTH-1",
  changeDescription: "Synthetic training change",
  affectedHazards: [hazard.hazard.id],
  affectedRequirements: ["REQ-SYNTH-EVIDENCE-1"],
  approvals: [],
  status: "open",
});
let mocStatus = "incomplete";
try {
  completeMoc(moc, []);
  mocStatus = "unexpectedly-complete";
} catch {
  mocStatus = "incomplete";
}

const humanPerformance = evaluateOperationalStatus(
  {
    userId: "OP-SYNTH-1",
    role: "operator",
    dutyPeriodId: "DUTY-SYNTH-1",
    qualificationStatus: "current",
    fatigueSelfDeclaration: "able",
    screenExposureMinutes: 45,
    workloadLevel: "moderate",
    alertLoad: 2,
    status: "available",
    evidenceRefs: ["EV-HF-SYNTH-1"],
  },
  { maxScreenExposureMinutes: 120, maxAlertLoad: 4, policyVersion: "HF-SYNTH-1" },
);

const protocol = registerProtocol({
  id: "PROTOCOL-SYNTH-1",
  version: "1.0.0",
  title: "Synthetic MATB tour",
  investigatorId: "INV-SYNTH-1",
  ethicsApprovalId: "ETHICS-SYNTH-1",
  permittedInstruments: ["NASA-TLX"],
  permittedSensors: ["matb"],
  retentionDays: 30,
  status: "approved",
});
const consent = createConsentRecord({
  id: "CONSENT-SYNTH-1",
  protocolId: protocol.id,
  participantCode: "SYNTH-P01",
  consentVersion: "v1",
  consentedAtUtc: "2026-08-14T00:00:00.000Z",
});
const researchSession = openConsentedSession({
  protocol,
  ethicsApproval: {
    id: "ETHICS-SYNTH-1",
    protocolId: protocol.id,
    status: "current",
    approvedFromUtc: "2026-08-01T00:00:00.000Z",
    expiresAtUtc: "2027-08-01T00:00:00.000Z",
  },
  consent,
  participantCode: "SYNTH-P01",
  conditionAssignment: "training-baseline",
  startedAtUtc: "2026-08-14T00:00:01.000Z",
  endedAtUtc: "2026-08-14T00:01:00.000Z",
  sessionId: "SESSION-SYNTH-1",
});
const adapter = new MatbResearchAdapter([
  {
    eventId: "MATB-SYNTH-1",
    occurredAtUtc: "2026-08-14T00:00:02.000Z",
    type: "response",
    payload: { responseCode: 1, workloadRating: 42 },
  },
]);
const abortSignal = new AbortController().signal;
await adapter.connect(researchSession, abortSignal);
const researchEvent = await adapter.readEvent(abortSignal);
await adapter.close();
if (researchEvent === null || researchEvent.nonDispatchable !== true) {
  throw new Error("Research tour must remain non-dispatchable");
}
const exportedResearch = JSON.parse(exportDeidentified(
  parseResearchSession({ ...researchSession, events: [researchEvent] }),
  "json",
));

const summary = {
  evidence: {
    status: "hashed",
    sha256: evidenceHash,
  },
  energy: {
    status: energyResult.status,
    reservePercent: energyResult.predictedAtRecoveryPercent,
  },
  fleet: {
    capabilityStatus: capability.status,
  },
  geo: {
    routeSegmentCount: route.segments.length,
    routeSegmentHash: route.segments[0].geometryHash,
  },
  telemetry: {
    recordStatuses: replay.map((record) => record.status),
  },
  safetyKernel: {
    status: safetyResult.status,
    blockerCodes: safetyResult.blockers.map((blocker) => blocker.code),
  },
  sms: {
    capabilities: [
      "hazard-promotion",
      "safety-performance-indicator",
      "audit-finding",
      "corrective-and-preventive-action",
      "emergency-response-plan",
      "management-of-change",
    ],
    hazard: { status: hazard.hazard.status },
    spi: { level: spi.level },
    audit: { status: auditStatus },
    capa: { status: capa.status },
    erp: { status: erp.status },
    moc: { status: mocStatus },
  },
  humanPerformance: {
    status: humanPerformance.status,
    workloadLevel: humanPerformance.workloadLevel,
  },
  research: {
    nonDispatchable: researchSession.nonDispatchable && researchEvent.nonDispatchable,
    dataDomain: researchEvent.dataDomain,
    eventCount: exportedResearch.events.length,
    exportSchemaVersion: exportedResearch.schemaVersion,
    exportSha256: createHash("sha256")
      .update(JSON.stringify(exportedResearch))
      .digest("hex"),
  },
};

process.stdout.write(`${JSON.stringify(summary, null, 2)}\n`);
