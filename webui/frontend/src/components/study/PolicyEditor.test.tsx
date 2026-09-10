import { render, screen, fireEvent } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { FixedLocaleProvider } from "@/lib/i18n";
import type { StudyPayload } from "@/lib/study";
import { PolicyEditor } from "./PolicyEditor";
it("translates consequential policy choices, interruption causes and comparators while retaining codes", () => {
  const payload = {
    study: {
      occasions: [{ key: "pre", instrument: "pvt", locale: "en" }],
      preparation_policy: [
        {
          occasion_key: "pre",
          placement: "before_baseline",
          demonstration_required: false,
          acknowledgement_required: false,
          comprehension: [
            {
              id: "c",
              metric: "comprehension.correct_fraction",
              comparator: "gte",
              threshold: 1,
            },
          ],
          practice: [],
        },
      ],
      repeat_policy: {
        permitted_causes: [],
        selection: "first_finished",
        max_attempts: 2,
      },
      interruption_policy: { available_outcomes: "exclude_attempt" },
    },
    analysis: { eligibility_policy: { hcf_screen_keys: [] } },
  } as unknown as StudyPayload;
  const change = vi.fn();
  render(
    <FixedLocaleProvider locale="es-419">
      <PolicyEditor payload={payload} onChange={change} />
    </FixedLocaleProvider>,
  );
  expect(
    screen.getByRole("option", { name: "Antes de la línea base" }),
  ).toHaveValue("before_baseline");
  expect(
    screen.getByRole("option", { name: "Mayor o igual que (≥)" }),
  ).toHaveValue("gte");
  expect(
    screen.getByRole("option", { name: "Excluir el intento interrumpido" }),
  ).toHaveValue("exclude_attempt");
  expect(
    screen.getByRole("option", { name: "Exigir fuente completa y verificada" }),
  ).toHaveValue("complete_verified");
  fireEvent.click(screen.getByLabelText("Detención por el operador"));
  expect(change).toHaveBeenCalledWith(
    expect.objectContaining({
      study: expect.objectContaining({
        repeat_policy: expect.objectContaining({
          permitted_causes: ["operator_stop"],
        }),
      }),
    }),
  );
});
