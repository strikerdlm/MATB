import { describe, expect, it } from "vitest";
import { errorLabel, operatorLabel } from "../src/app/operator-labels.js";
import { getLabels } from "../src/i18n/registry.js";

describe("operator-visible API localization", () => {
  it("exhaustively localizes non-ready mission and operational enums in Spanish", () => {
    const labels = getLabels("es");
    expect([
      operatorLabel(labels, "UnderReview"), operatorLabel(labels, "ReadyForRelease"), operatorLabel(labels, "conditional"),
      operatorLabel(labels, "blocked"), operatorLabel(labels, "degraded"), operatorLabel(labels, "not-applicable"), operatorLabel(labels, "safe-mode"),
    ]).toEqual(["En revisión", "Lista para liberación", "condicional", "bloqueada", "degradada", "no aplica", "modo seguro"]);
  });

  it("localizes stable server error codes without leaking raw English messages", () => {
    const labels = getLabels("es");
    expect(errorLabel(labels, "SAFE_MODE_DATABASE_FAILURE")).toBe("Modo seguro de solo lectura");
    expect(errorLabel(labels, "AUTHORIZATION_FORBIDDEN")).toBe("Prohibido para este rol");
    expect(errorLabel(labels, "UNKNOWN_SERVER_FAILURE")).toBe("La solicitud falló");
  });
});
