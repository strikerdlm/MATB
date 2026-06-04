import { describe, it, expect } from "vitest";
import { fmtP, fmtNum, fmtCi } from "@/lib/format";

describe("format", () => {
  it("fmtP clamps tiny p-values and rounds", () => {
    expect(fmtP(0.0000004)).toBe("<0.001");
    expect(fmtP(0.0432)).toBe("0.043");
    expect(fmtP(null)).toBe("—");
  });
  it("fmtNum rounds to 3 decimals", () => {
    expect(fmtNum(1.65321)).toBe("1.653");
    expect(fmtNum(null)).toBe("—");
  });
  it("fmtCi renders an interval", () => {
    expect(fmtCi([1.2345, 2.3456])).toBe("[1.234, 2.346]");
    expect(fmtCi(null)).toBe("—");
  });
});
