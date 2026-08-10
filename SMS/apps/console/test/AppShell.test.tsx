import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../src/app/AppShell.js";
import { routeMode } from "../src/app/routes.js";

describe("console shell", () => {
  it("renders the controlled-data warning and keyboard-visible navigation", () => {
    const html = renderToStaticMarkup(<AppShell initialPath="/missions" />);
    expect(html).toMatch(/unclassified.*controlled safety metadata/i);
    expect(html).toMatch(/aria-label="Mission navigation"/);
    expect(html).toMatch(/Mission safety strip/i);
    expect(html).toMatch(/Read-only telemetry/i);
  });

  it("maps planning, review, and monitoring routes to safe view modes", () => {
    expect(routeMode("/missions/mission-1/plan")).toBe("planning");
    expect(routeMode("/missions/mission-1/review")).toBe("review");
    expect(routeMode("/missions/mission-1/monitor")).toBe("monitoring");
  });
});
