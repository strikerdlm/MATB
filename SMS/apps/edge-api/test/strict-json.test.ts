import { describe, expect, it } from "vitest";
import { parseStrictJson, StrictJsonError } from "../src/runtime/strict-json.js";

describe("strict bounded JSON numbers", () => {
  it("rejects positive and negative numeric overflow at the root and in nested contexts", () => {
    for (const source of ["1e9999", "-1e9999", '{"nested":[0,{"positive":1e9999,"negative":-1e9999}]}']) {
      expect(() => parseStrictJson(source)).toThrow(StrictJsonError);
    }
  });

  it("retains large finite JSON numbers", () => {
    expect(parseStrictJson('{"positive":1e308,"negative":-1e308}')).toEqual({ positive: 1e308, negative: -1e308 });
  });
});
