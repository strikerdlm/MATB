import { describe, expect, it } from "vitest";
import { resolveContainedRuntimePath } from "../src/runtime/paths.js";

describe("portable runtime paths", () => {
  it("contains Windows static asset paths without relying on POSIX separators or prefix lookalikes", () => {
    expect(resolveContainedRuntimePath("C:\\Program Files\\FAC ISR\\console", "assets\\app.js")).toBe("C:\\Program Files\\FAC ISR\\console\\assets\\app.js");
    expect(() => resolveContainedRuntimePath("C:\\Program Files\\FAC ISR\\console", "..\\secret.txt")).toThrow(/contained/i);
    expect(() => resolveContainedRuntimePath("C:\\Program Files\\FAC ISR\\console", "C:\\Program Files\\FAC ISR\\console-evil\\app.js")).toThrow(/contained/i);
  });

  it("contains POSIX static asset paths", () => {
    expect(resolveContainedRuntimePath("/opt/fac-isr-sms/console", "assets/app.js")).toBe("/opt/fac-isr-sms/console/assets/app.js");
    expect(() => resolveContainedRuntimePath("/opt/fac-isr-sms/console", "../secret.txt")).toThrow(/contained/i);
  });
});
