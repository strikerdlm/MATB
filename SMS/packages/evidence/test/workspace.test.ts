import { describe, expect, it } from "vitest";
import { canonicalJson } from "../src/index.js";

describe("evidence workspace", () => {
  it("exports deterministic canonical JSON", () => {
    expect(canonicalJson({ b: 2, a: 1 })).toBe('{"a":1,"b":2}');
  });
});
