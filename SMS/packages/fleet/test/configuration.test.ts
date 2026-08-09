import { describe, expect, it } from "vitest";
import { evaluateConfiguration } from "../src/configuration.js";
const system = { id: "uas-1", manufacturer: "Example", model: "X", aircraftClass: "IC" as const, mtowKg: 15 as never, configuration: "unarmed-isr" as const, approvedConfigurationId: "cfg-1", approvedSoftwareBaseline: "sw-1", compatibleGcsIds: ["gcs-1"], batteryId: "bat-1", evidenceRefs: ["sys-ev"] };
const payload = { id: "payload-1", compatibleAircraftIds: ["uas-1"], massKg: 1, powerW: 20, thermalLimitC: 60, approvedMassKg: 2, approvedPowerW: 30, approvedThermalLimitC: 70, configurationHash: "pay-hash", approvedConfigurationHash: "pay-hash", approvedConfigurationId: "cfg-1", evidenceRefs: ["payload-ev"] };
const gcs = { id: "gcs-1", compatibleAircraftIds: ["uas-1"], configurationHash: "gcs-hash", approvedConfigurationHash: "gcs-hash", approvedConfigurationId: "cfg-1", softwareBaseline: "sw-1", evidenceRefs: ["gcs-ev"] };
const battery = { serialNumber: "bat-1", aircraftCompatibility: ["uas-1"], status: "released" as const };
const evidence = { current: true, approved: true, evidenceRefs: ["sys-ev", "payload-ev", "gcs-ev"], acceptedEvidenceRefs: ["sys-ev", "payload-ev", "gcs-ev"] };
describe("configuration compatibility", () => {
  it("hard-blocks armed and strike configurations", () => {
    expect(evaluateConfiguration({ ...system, configuration: "armed" }, payload, gcs, battery, evidence).status).toBe("blocked");
    expect(evaluateConfiguration({ ...system, configuration: "strike" }, payload, gcs, battery, evidence).status).toBe("blocked");
  });
  it("passes compatible approved configuration and blocks mismatched IDs/hashes", () => {
    expect(evaluateConfiguration(system, payload, gcs, battery, evidence)).toMatchObject({ status: "pass", evidenceRefs: ["sys-ev", "payload-ev", "gcs-ev"] });
    expect(evaluateConfiguration(system, { ...payload, compatibleAircraftIds: ["other"] }, gcs, battery, evidence).status).toBe("blocked");
    expect(evaluateConfiguration(system, payload, { ...gcs, softwareBaseline: "old" }, battery, evidence).status).toBe("blocked");
    expect(evaluateConfiguration(system, payload, gcs, { ...battery, aircraftCompatibility: ["other"] }, evidence).status).toBe("blocked");
    expect(evaluateConfiguration(system, payload, gcs, battery, { ...evidence, current: false }).status).toBe("unknown");
    expect(evaluateConfiguration(system, payload, gcs, battery, { ...evidence, acceptedEvidenceRefs: ["sys-ev"] }).status).toBe("blocked");
  });
});
