import { describe, expect, it } from "vitest";
import { evaluateConfiguration } from "../src/configuration.js";
const system = { id: "uas-1", manufacturer: "Example", model: "X", aircraftClass: "IC" as const, mtowKg: 15 as never, configuration: "unarmed-isr" as const, approvedConfigurationId: "cfg-1", approvedSoftwareBaseline: "sw-1", compatibleGcsIds: ["gcs-1"], batteryId: "bat-1", evidenceRefs: ["sys-ev"] };
const payload = { id: "payload-1", compatibleAircraftIds: ["uas-1"], massKg: 1, powerW: 20, thermalLimitC: 60, configurationHash: "pay-hash", approvedConfigurationHash: "pay-hash", evidenceRefs: ["payload-ev"] };
const gcs = { id: "gcs-1", compatibleAircraftIds: ["uas-1"], configurationHash: "gcs-hash", approvedConfigurationHash: "gcs-hash", softwareBaseline: "sw-1", evidenceRefs: ["gcs-ev"] };
describe("configuration compatibility", () => {
  it("hard-blocks armed and strike configurations", () => {
    expect(evaluateConfiguration({ ...system, configuration: "armed" }, payload, gcs).status).toBe("blocked");
    expect(evaluateConfiguration({ ...system, configuration: "strike" }, payload, gcs).status).toBe("blocked");
  });
  it("passes compatible approved configuration and blocks mismatched IDs/hashes", () => {
    expect(evaluateConfiguration(system, payload, gcs)).toMatchObject({ status: "pass", evidenceRefs: ["sys-ev", "payload-ev", "gcs-ev"] });
    expect(evaluateConfiguration(system, { ...payload, compatibleAircraftIds: ["other"] }, gcs).status).toBe("blocked");
    expect(evaluateConfiguration(system, payload, { ...gcs, softwareBaseline: "old" }).status).toBe("blocked");
  });
});
