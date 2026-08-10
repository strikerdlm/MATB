import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../src/app/AppShell.js";
import { ResearchProtocolPanel } from "../src/components/ResearchProtocolPanel.js";
import { ResearchSessionPanel } from "../src/components/ResearchSessionPanel.js";

describe("research boundary panels", () => {
  it("keeps research identity controls unavailable in the operational route", () => {
    const html = renderToStaticMarkup(<AppShell initialPath="/missions/1/monitor" />);
    expect(html).not.toMatch(/participant identity/i);
    expect(html).not.toMatch(/NON-DISPATCHABLE RESEARCH/i);
  });

  it("keeps the research-only label and consent gate persistent", () => {
    const html = renderToStaticMarkup(<><ResearchProtocolPanel authorized protocol={{ id: "PROTOCOL-1", version: "1.0.0", title: "Workload study", ethicsApprovalId: "ETHICS-1", status: "current", permittedSensors: ["matb"], permittedInstruments: ["NASA-TLX"] }} /><ResearchSessionPanel authorized session={{ participantCode: "P-001", conditionAssignment: "baseline", startedAtUtc: "2026-08-10T15:00:00.000Z", instrumentProgress: "NASA-TLX · 1/1" }} /></>);
    expect(html).toMatch(/NON-DISPATCHABLE RESEARCH/);
    expect(html).toMatch(/Consent|Ethics/i);
    expect(html).toMatch(/P-001/);
    expect(html).not.toMatch(/mission release|qualification update/i);
  });
});
