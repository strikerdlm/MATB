import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../src/app/AppShell.js";

describe("console shell", () => {
  it("renders the controlled-data warning and keyboard-visible navigation", () => {
    const html = renderToStaticMarkup(<AppShell initialPath="/missions" />);
    expect(html).toMatch(/unclassified.*controlled safety metadata/i);
    expect(html).toMatch(/aria-label="Mission navigation"/);
    expect(html).toMatch(/Mission safety strip/i);
    expect(html).toMatch(/Read-only telemetry/i);
  });
});
