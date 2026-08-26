import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { AppShell } from "../src/app/AppShell.js";
import { routeMode } from "../src/app/routes.js";
import { getLabels } from "../src/i18n/registry.js";

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

  it("renders a fully localized Spanish login surface and keeps locale keys in parity", () => {
    const english = getLabels("en");
    const spanish = getLabels("es");
    const html = renderToStaticMarkup(<AppShell initialLocale="es" />);

    expect(Object.keys(spanish).sort()).toEqual(Object.keys(english).sort());
    expect(html).toMatch(/Iniciar sesión en la consola operativa/);
    expect(html).toMatch(/Identificador de usuario/);
    expect(html).toMatch(/Contraseña/);
    expect(html).not.toMatch(/Sign in to operational console|User ID|Password/);
  });
});
