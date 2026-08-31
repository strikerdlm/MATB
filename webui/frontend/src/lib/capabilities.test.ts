import { describe, expect, it } from "vitest";

import { activeComponentIds, productRoutes } from "@/lib/capabilities";
import type { ConsoleCapabilities } from "@/types";

function response(ids: string[]): ConsoleCapabilities {
  return {
    schema_version: "1.0",
    components: ids.map((component_id) => ({
      schema_version: "1.0",
      component_id,
      component_version: "0.1.0-alpha.1",
      component_kind: "console",
      stability: "candidate",
      distribution: component_id.startsWith("matb-") ? "core" : "optional",
      capabilities: [],
      requires: [],
      python_entrypoint: null,
      license_expression: "MIT",
    })),
  };
}

describe("console capabilities", () => {
  it("keeps optional routes absent when the backend exports only research core", () => {
    const capabilities = response(["matb-console", "matb-contracts", "matb-research"]);

    expect(productRoutes(capabilities)).toEqual([]);
    expect(activeComponentIds(capabilities)).toEqual([
      "matb-console",
      "matb-contracts",
      "matb-research",
    ]);
  });

  it("maps installed optional components to their operator routes", () => {
    const capabilities = response([
      "matb-console",
      "matb-contracts",
      "matb-liftoff",
      "matb-research",
      "matb-suas",
    ]);

    expect(productRoutes(capabilities)).toEqual([
      { componentId: "matb-liftoff", href: "/liftoff/setup", label: "Liftoff" },
      { componentId: "matb-suas", href: "/mission/setup", label: "Mission" },
    ]);
  });
});
