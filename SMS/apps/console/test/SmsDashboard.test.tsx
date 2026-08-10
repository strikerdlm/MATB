import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SmsDashboard } from "../src/components/SmsDashboard.js";

describe("SmsDashboard", () => {
  it("shows SMS assurance domains and accountable follow-up", () => {
    const html = renderToStaticMarkup(<SmsDashboard />);
    expect(html).toMatch(/Hazards/);
    expect(html).toMatch(/CAPA/);
    expect(html).toMatch(/SPI|indicator/i);
    expect(html).toMatch(/ERP/);
    expect(html).toMatch(/MOC|change/i);
    expect(html).toMatch(/owner|due/i);
  });
});
