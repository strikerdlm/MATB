import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../src/app/AppShell.js";
import { renderConcepts } from "../src/i18n/registry.js";

describe("console accessibility and locale contracts", () => {
  it("keeps Spanish and English decision concepts structurally identical", () => {
    expect(renderConcepts("es").length).toBe(renderConcepts("en").length);
    expect(renderConcepts("es")).toEqual(["Franja de seguridad de misión", "Mantenimiento", "Operador", "Seguridad", "Comandante"]);
  });

  it("keeps landmarks and labels available in the mobile continuation", () => {
    const html = renderToStaticMarkup(<AppShell initialPath="/missions/mission-1/monitor" initialLocale="es" />);
    expect(html).toMatch(/aria-label="Mission navigation"/);
    expect(html).toMatch(/Espacio cartográfico sin conexión/);
    expect(html).toMatch(/Telemetría de solo lectura/);
  });
});
