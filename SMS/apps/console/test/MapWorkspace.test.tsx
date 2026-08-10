import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MapWorkspace } from "../src/components/MapWorkspace.js";

describe("MapWorkspace", () => {
  it("renders a local map source without a remote tile URL", () => {
    const html = renderToStaticMarkup(
      <MapWorkspace
        packageDirectory={{ packageId: "MAP-COLOMBIA-2024Q2", version: "1.2.0", manifestHash: "sha256:deadbeef2024", freshness: "Current · 18 May 2024 09:25" }}
        route={{ routeId: "ISR_SWEEP_120", distanceNm: 214, waypoints: [{ id: "WP01", label: "Puerto Santander", x: 20, y: 65 }, { id: "WP02", label: "Tibú", x: 280, y: 118 }, { id: "WP03", label: "La Gabarra", x: 398, y: 158 }] }}
        findings={[{ id: "F-01", label: "Wildlife strike risk", severity: "high", x: 398, y: 158 }]}
        mode="review"
      />,
    );

    expect(html).toMatch(/data-testid="map-canvas"/);
    expect(html).toMatch(/data-map-source="local-package"/);
    expect(html).toMatch(/MAP-COLOMBIA-2024Q2/);
    expect(html).toMatch(/sha256:deadbeef2024/);
    expect(html).toMatch(/Wildlife strike risk/);
    expect(html).not.toMatch(/https?:\/\//);
  });

  it("keeps route mode and overlay labels visible for review", () => {
    const html = renderToStaticMarkup(
      <MapWorkspace
        packageDirectory={{ packageId: "MAP-COLOMBIA-2024Q2", version: "1.2.0", manifestHash: "sha256:deadbeef2024", freshness: "Current · 18 May 2024 09:25" }}
        route={{ routeId: "ISR_SWEEP_120", distanceNm: 214, waypoints: [{ id: "WP01", label: "Puerto Santander", x: 20, y: 65 }] }}
        findings={[]}
        mode="planning"
      />,
    );

    expect(html).toMatch(/Planning mode/);
    expect(html).toMatch(/Route/);
    expect(html).toMatch(/214 NM/);
    expect(html).toMatch(/Offline tiles/);
    expect(html).toMatch(/Source freshness/);
  });
});
