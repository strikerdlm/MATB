import { describe, expect, it } from "vitest";
import { createConfig, tlsRequestPolicy } from "../src/config.js";

describe("edge configuration", () => {
  it("defaults to loopback, disabled internet, and normalized local paths", () => {
    const config = createConfig({ databaseUrl: ":memory:" });

    expect(config.bindAddress).toBe("127.0.0.1");
    expect(config.port).toBe(0);
    expect(config.internet).toBe("disabled");
    expect(config.databaseUrl).toBe(":memory:");
    expect(config.packageDirectory).toMatch(/data[\\/]packages$/);
  });

  it("rejects a runtime internet mode other than disabled", () => {
    expect(() => createConfig({ internet: "enabled" })).toThrow(/internet must be disabled/i);
  });

  it("requires both TLS paths when TLS is configured", () => {
    expect(() => createConfig({ tls: { certPath: "cert.pem" } })).toThrow(/both certPath and keyPath/i);
  });

  it("rejects invalid bind addresses and lock timeouts", () => {
    expect(() => createConfig({ bindAddress: "not-an-ip" })).toThrow(/bindAddress/i);
    expect(() => createConfig({ lockTimeoutMs: 0 })).toThrow(/lockTimeoutMs/i);
  });

  it("normalizes an externally provisioned runtime export key path", () => {
    const config = createConfig({ exportKeyPath: "secrets/export-key.pem", exportKeyId: "runtime-export-key-2026" });

    expect(config.exportKeyPath).toMatch(/secrets[\\/]export-key\.pem$/);
    expect(config.exportKeyId).toBe("runtime-export-key-2026");
    expect(() => createConfig({ exportKeyPath: "bad\0key" })).toThrow(/exportKeyPath/i);
    expect(() => createConfig({ exportKeyPath: "key.pem" })).toThrow(/exportKeyId/i);
    expect(() => createConfig({ exportKeyId: "key-id" })).toThrow(/exportKeyPath/i);
  });

  it("resolves Windows-style runtime paths from the configuration location", () => {
    const config = createConfig({
      configDirectory: "C:\\ProgramData\\FAC ISR\\config",
      databaseUrl: "..\\data\\edge.sqlite",
      packageDirectory: "..\\data\\packages",
      consoleDirectory: "..\\app\\console",
    });
    expect(config.databaseUrl).toBe("C:\\ProgramData\\FAC ISR\\data\\edge.sqlite");
    expect(config.packageDirectory).toBe("C:\\ProgramData\\FAC ISR\\data\\packages");
    expect(config.consoleDirectory).toBe("C:\\ProgramData\\FAC ISR\\app\\console");
  });

  it("validates standalone and tactical transport requirements", () => {
    expect(() => createConfig({ deploymentMode: "standalone", bindAddress: "0.0.0.0", tls: { certPath: "cert.pem", keyPath: "key.pem" } })).toThrow(/loopback/i);
    expect(() => createConfig({ deploymentMode: "standalone", bindAddress: "127.0.0.1" })).toThrow(/HTTPS|certificate/i);
    expect(() => createConfig({ deploymentMode: "tactical", bindAddress: "192.168.10.20", tls: { certPath: "cert.pem", keyPath: "key.pem" } })).toThrow(/client CA/i);
    expect(createConfig({ deploymentMode: "tactical", bindAddress: "192.168.10.20", tls: { certPath: "cert.pem", keyPath: "key.pem", clientCaPath: "client-ca.pem" } })).toMatchObject({
      deploymentMode: "tactical",
      tls: { requireClientCertificate: true, rejectUnauthorizedClients: true },
    });
  });

  it("requests allowlisted adapter certificates in standalone without rejecting ordinary HTTPS users", () => {
    expect(() => createConfig({
      deploymentMode: "standalone",
      bindAddress: "127.0.0.1",
      tls: { certPath: "cert.pem", keyPath: "key.pem" },
      telemetryAdapters: [{ fingerprintSha256: "a".repeat(64), adapterId: "adapter-1", aircraftIds: ["aircraft-1"] }],
    })).toThrow(/client CA/i);
    const config = createConfig({
      deploymentMode: "standalone",
      bindAddress: "127.0.0.1",
      tls: { certPath: "cert.pem", keyPath: "key.pem", clientCaPath: "client-ca.pem" },
      telemetryAdapters: [{ fingerprintSha256: "a".repeat(64), adapterId: "adapter-1", aircraftIds: ["aircraft-1"] }],
    });
    expect(tlsRequestPolicy(config)).toEqual({ requestCert: true, rejectUnauthorized: false });
  });
});
