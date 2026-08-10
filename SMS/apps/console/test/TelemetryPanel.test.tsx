import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { TelemetryPanel } from "../src/components/TelemetryPanel.js";

const droppedLinkProps = {
  aircraft: { aircraftId: "FAC-1287", platform: "ISR-1", approvedMinimumReservePercent: 30 },
  telemetry: { capturedAtLocal: "18 May 2024 09:25:31", latitude: "08° 23.456′ N", longitude: "072° 45.789′ W", altitude: "FL098", groundspeed: "210 KT", heading: "123°", verticalRate: "+500 FPM", energyPercent: 62, batteryHealth: "NOMINAL", linkLatencyMs: 480, linkLossPercent: 14, gnss: "3D FIX", reservePercent: 38 },
  degraded: { active: true, reason: "Read-only link dropout", sinceLocal: "09:21" },
} as const;

describe("TelemetryPanel", () => {
  it("shows degraded telemetry and preserves the approved reserve", () => {
    const html = renderToStaticMarkup(<TelemetryPanel {...droppedLinkProps} />);

    expect(html).toMatch(/Telemetry degraded/i);
    expect(html).toMatch(/Read-only link dropout/);
    expect(html).toMatch(/Approved minimum reserve/);
    expect(html).toMatch(/30%/);
    expect(html).toMatch(/38%/);
    expect(html).toMatch(/480 ms/);
    expect(html).toMatch(/14%/);
  });

  it("renders read-only cards without command controls", () => {
    const html = renderToStaticMarkup(
      <TelemetryPanel
        aircraft={{ aircraftId: "FAC-1287", platform: "ISR-1", approvedMinimumReservePercent: 30 }}
        telemetry={{ capturedAtLocal: "18 May 2024 09:25:31", latitude: "08° 23.456′ N", longitude: "072° 45.789′ W", altitude: "FL098", groundspeed: "210 KT", heading: "123°", verticalRate: "+500 FPM", energyPercent: 62, batteryHealth: "NOMINAL", linkLatencyMs: 70, linkLossPercent: 0, gnss: "3D FIX", reservePercent: 38 }}
        degraded={false}
      />,
    );

    expect(html).not.toMatch(/<button/);
    expect(html).not.toMatch(/\b(sendCommand|arm|launch|redirect)\b/i);
  });
});
