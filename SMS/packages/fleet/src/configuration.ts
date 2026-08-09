import type { BatteryInput, ConfigurationEvidence, GCSConfiguration, PayloadConfiguration, UASSystem, ConfigurationResult } from "./types.js";
export function evaluateConfiguration(system: UASSystem, payload: PayloadConfiguration, gcs: GCSConfiguration, battery: BatteryInput, evidence: ConfigurationEvidence): ConfigurationResult {
  const reasons: string[] = [];
  if (system.configuration === "armed" || system.configuration === "strike") reasons.push("CONFIGURATION_OUT_OF_SCOPE");
  if (!payload.compatibleAircraftIds.includes(system.id)) reasons.push("PAYLOAD_AIRCRAFT_INCOMPATIBLE");
  if (!gcs.compatibleAircraftIds.includes(system.id) || !(system.compatibleGcsIds ?? [gcs.id]).includes(gcs.id)) reasons.push("GCS_AIRCRAFT_INCOMPATIBLE");
  if (payload.configurationHash !== payload.approvedConfigurationHash) reasons.push("PAYLOAD_CONFIGURATION_NOT_APPROVED");
  if (gcs.configurationHash !== gcs.approvedConfigurationHash) reasons.push("GCS_CONFIGURATION_NOT_APPROVED");
  if (system.approvedSoftwareBaseline !== undefined && gcs.softwareBaseline !== system.approvedSoftwareBaseline) reasons.push("SOFTWARE_BASELINE_MISMATCH");
  if (system.approvedConfigurationId !== payload.approvedConfigurationId || system.approvedConfigurationId !== gcs.approvedConfigurationId) reasons.push("APPROVED_CONFIGURATION_MISMATCH");
  if (!system.batteryId || battery.serialNumber !== system.batteryId || !battery.aircraftCompatibility.includes(system.id) || battery.status !== "released") reasons.push("BATTERY_INCOMPATIBLE_OR_UNRELEASED");
  if (!Number.isFinite(payload.massKg) || payload.massKg < 0 || !Number.isFinite(payload.powerW) || payload.powerW < 0 || !Number.isFinite(payload.thermalLimitC)) reasons.push("PAYLOAD_LIMITS_INVALID");
  if (payload.massKg > payload.approvedMassKg || payload.powerW > payload.approvedPowerW || payload.thermalLimitC > payload.approvedThermalLimitC) reasons.push("PAYLOAD_APPROVED_LIMIT_EXCEEDED");
  const evidenceRefs = [...system.evidenceRefs, ...payload.evidenceRefs, ...gcs.evidenceRefs];
  if (!evidence.current || !evidence.approved) return { status: "unknown", reasons: ["CONFIGURATION_EVIDENCE_NOT_CURRENT_OR_APPROVED"], evidenceRefs: [...evidence.evidenceRefs] };
  const requiredRefs = [...system.evidenceRefs, ...payload.evidenceRefs, ...gcs.evidenceRefs];
  if (evidence.evidenceRefs.length === 0 || !requiredRefs.every((ref) => evidence.evidenceRefs.includes(ref)) || !requiredRefs.every((ref) => evidence.acceptedEvidenceRefs.includes(ref))) reasons.push("CONFIGURATION_EVIDENCE_NOT_ACCEPTED");
  if (evidenceRefs.length === 0) reasons.push("CONFIGURATION_EVIDENCE_REQUIRED");
  return { status: reasons.length ? "blocked" : "pass", reasons, evidenceRefs };
}
