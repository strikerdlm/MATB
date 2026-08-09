import type { GCSConfiguration, PayloadConfiguration, UASSystem, ConfigurationResult } from "./types.js";
export function evaluateConfiguration(system: UASSystem, payload: PayloadConfiguration, gcs: GCSConfiguration): ConfigurationResult {
  const reasons: string[] = [];
  if (system.configuration === "armed" || system.configuration === "strike") reasons.push("CONFIGURATION_OUT_OF_SCOPE");
  if (!payload.compatibleAircraftIds.includes(system.id)) reasons.push("PAYLOAD_AIRCRAFT_INCOMPATIBLE");
  if (!gcs.compatibleAircraftIds.includes(system.id) || !(system.compatibleGcsIds ?? [gcs.id]).includes(gcs.id)) reasons.push("GCS_AIRCRAFT_INCOMPATIBLE");
  if (payload.configurationHash !== payload.approvedConfigurationHash) reasons.push("PAYLOAD_CONFIGURATION_NOT_APPROVED");
  if (gcs.configurationHash !== gcs.approvedConfigurationHash) reasons.push("GCS_CONFIGURATION_NOT_APPROVED");
  if (system.approvedSoftwareBaseline !== undefined && gcs.softwareBaseline !== system.approvedSoftwareBaseline) reasons.push("SOFTWARE_BASELINE_MISMATCH");
  if (!Number.isFinite(payload.massKg) || payload.massKg < 0 || !Number.isFinite(payload.powerW) || payload.powerW < 0 || !Number.isFinite(payload.thermalLimitC)) reasons.push("PAYLOAD_LIMITS_INVALID");
  const evidenceRefs = [...system.evidenceRefs, ...payload.evidenceRefs, ...gcs.evidenceRefs];
  if (evidenceRefs.length === 0) reasons.push("CONFIGURATION_EVIDENCE_REQUIRED");
  return { status: reasons.length ? "blocked" : "pass", reasons, evidenceRefs };
}
