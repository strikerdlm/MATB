import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../src/app/AppShell.js";
import { routeMode } from "../src/app/routes.js";

describe("console shell", () => {
  it("renders a genuine login state without production operational fixtures", () => {
    const html = renderToStaticMarkup(<AppShell />);
    expect(html).toMatch(/Sign in to operational console/i);
    expect(html).toMatch(/User ID/i);
    expect(html).not.toMatch(/M24-0518-ISR|FAC-1287|MAP-COLOMBIA-2024Q2|PROTOCOL-MATB-01/);
    expect(html).toMatch(/Sign in to operational console/i);
  });

  it("maps planning, review, and monitoring routes to safe view modes", () => {
    expect(routeMode("/missions/mission-1/plan")).toBe("planning");
    expect(routeMode("/missions/mission-1/review")).toBe("review");
    expect(routeMode("/missions/mission-1/monitor")).toBe("monitoring");
  });
});
