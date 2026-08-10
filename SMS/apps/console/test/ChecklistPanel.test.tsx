import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { ChecklistPanel } from "../src/components/ChecklistPanel.js";

describe("ChecklistPanel", () => {
  it("renders each checklist item with accountable response metadata", () => {
    const html = renderToStaticMarkup(
      <ChecklistPanel
        items={[
          { itemId: "safety-01", prompt: "Configuration is within approved scope", responseOptions: ["yes", "no", "not-applicable"], response: "no", accountableUserId: "safety-17", occurredAtUtc: "2024-05-18T14:25:00Z", evidenceRef: "EV-SAF-00077", reason: "configuration out of scope" },
          { itemId: "safety-02", prompt: "Wildlife strike mitigation is briefed", responseOptions: ["yes", "no"], response: undefined },
        ]}
        onRespond={vi.fn()}
      />,
    );

    expect(html).toMatch(/Configuration is within approved scope/);
    expect(html).toMatch(/safety-01/);
    expect(html).toMatch(/safety-17/);
    expect(html).toMatch(/EV-SAF-00077/);
    expect(html).toMatch(/configuration out of scope/);
    expect(html).toMatch(/Wildlife strike mitigation is briefed/);
  });

  it("does not render a check-all control", () => {
    const html = renderToStaticMarkup(
      <ChecklistPanel
        items={[{ itemId: "safety-01", prompt: "Configuration is within approved scope", responseOptions: ["yes", "no"] }]}
        onRespond={() => undefined}
      />,
    );

    expect(html).not.toMatch(/check all|complete all/i);
    expect(html).toMatch(/Respond to item/);
  });
});
