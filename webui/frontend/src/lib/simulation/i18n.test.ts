import { describe, expect, it } from "vitest";
import { STRINGS, t } from "@/lib/simulation/i18n";

describe("simulation translations", () => {
  it("English and es-CO have identical translation keys", () => {
    expect(Object.keys(STRINGS.en).sort()).toEqual(Object.keys(STRINGS["es-CO"]).sort());
  });

  it("translates command labels and replaces variables", () => {
    expect(t("es-CO", "command.return_to_base")).toBe("Regresar a base");
    expect(t("en", "a11y.select_aircraft", { aircraft: "UAS-01" })).toBe("Select UAS-01");
    expect(t("es-CO", "probe.remaining", { time: 12 })).toBe("Quedan 12");
  });
});
