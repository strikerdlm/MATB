import { describe, expect, it } from "vitest";

import {
  resolveExecutionPurpose,
  resolveSessionExecutionPurpose,
  withExecutionPurpose,
} from "@/lib/execution-purpose";

describe("execution purpose", () => {
  it("requires an explicit valid preparation choice", () => {
    expect(resolveExecutionPurpose(new URLSearchParams())).toBeNull();
    expect(resolveExecutionPurpose(new URLSearchParams("purpose=preview"))).toBeNull();
    expect(resolveExecutionPurpose(new URLSearchParams("purpose=practice"))).toBe("practice");
    expect(resolveExecutionPurpose(new URLSearchParams("purpose=study"))).toBe("study");
  });

  it("keeps fast verification in practice", () => {
    expect(resolveExecutionPurpose(new URLSearchParams("purpose=study&fast=1"))).toBe("practice");
  });

  it("uses only an existing session's stored purpose and never its active block", () => {
    expect(resolveSessionExecutionPurpose("study")).toBe("study");
    expect(resolveSessionExecutionPurpose("practice")).toBe("practice");
    expect(resolveSessionExecutionPurpose("PRACTICE")).toBeNull();
  });

  it("preserves navigation state while changing purpose", () => {
    expect(withExecutionPurpose("/start?experiment=screen#details", "study"))
      .toBe("/start?experiment=screen&purpose=study#details");
    expect(withExecutionPurpose("/pvt?fast=1&participant=P01", "study"))
      .toBe("/pvt?participant=P01&purpose=study");
  });
});
