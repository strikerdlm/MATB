import { describe, expect, it } from "vitest";
import { createConfig } from "../src/config.js";

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
    const config = createConfig({ exportKeyPath: "secrets/export-key.pem" });

    expect(config.exportKeyPath).toMatch(/secrets[\\/]export-key\.pem$/);
    expect(() => createConfig({ exportKeyPath: "bad\0key" })).toThrow(/exportKeyPath/i);
  });
});
