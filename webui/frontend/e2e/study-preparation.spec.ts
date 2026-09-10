import { test, expect } from "@playwright/test";
import { approveStudyFixture, baseOccasion, post } from "./study-fixtures";
const base = "http://127.0.0.1:8000";
for (const locale of ["en", "es-419"] as const) {
  test(`measured preparation and exact PVT return in ${locale}`, async ({
    page,
    request,
  }) => {
    const participant = `P${((process.pid % 8000) + 1) * 60 + (locale === "en" ? 51 : 52)}`;
    await post(request, "/participants", {
      id: participant,
      enrollment_date: "2026-09-10",
    });
    const occasion = {
      ...(await baseOccasion(request)),
      key: "baseline",
      locale,
    };
    const assignment = await approveStudyFixture(
      request,
      participant,
      [occasion],
      undefined,
      (payload) => {
        payload.study.preparation_policy = [
          {
            occasion_key: "baseline",
            placement: "before_baseline",
            demonstration_required: true,
            acknowledgement_required: true,
            comprehension: [
              {
                id: "browser-comprehension",
                rationale: "Software-only fixture",
                metric: "comprehension.correct_fraction",
                comparator: "eq",
                threshold: 1,
              },
            ],
            practice: [
              {
                id: "browser-practice",
                rationale: "Software-only fixture",
                metric: "pvt.lapses",
                comparator: "gte",
                threshold: 0,
              },
            ],
            rationale:
              "Browser workflow fixture; no scientific threshold claim.",
          },
        ];
      },
    );
    await page.goto(`/study/participant?assignment=${assignment.id}`);
    const en = locale === "en";
    await page
      .getByRole("button", { name: en ? "Help" : "Ayuda", exact: true })
      .focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByText(
        en ? /Ask the researcher for help/ : /Pida ayuda al investigador/,
      ),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: en ? "Prepare · baseline" : "Preparar · baseline",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name: en ? /Prepare: demonstration/ : /Preparar: demostración/,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", {
        name: en ? "Stop preparation" : "Detener preparación",
        exact: true,
      })
      .focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByText(en ? /Preparation stopped/ : /Preparación detenida/),
    ).toBeVisible();
    const stopped = await (
      await request.get(
        `${base}/study/assignments/${assignment.id}/preparation`,
      )
    ).json();
    expect(stopped.preparations[0].next_action).toBe("stopped");
    expect(
      stopped.preparations[0].events.map(
        (event: { stage: string }) => event.stage,
      ),
    ).toEqual(["stopped"]);
    await page.reload();
    await page
      .getByRole("button", {
        name: en ? "Prepare · baseline" : "Preparar · baseline",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("button", {
        name: en ? "Continue" : "Continuar",
        exact: true,
      }),
    ).toHaveCount(0);
    await page
      .getByRole("button", {
        name: en
          ? "Explicitly restart preparation"
          : "Reiniciar preparación explícitamente",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name: en ? /Prepare: demonstration/ : /Preparar: demostración/,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: en ? "Continue" : "Continuar", exact: true })
      .click();
    await expect(
      page.getByRole("heading", {
        name: en ? /Understand: acknowledge/ : /Entender: confirmar/,
      }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: en ? "Continue" : "Continuar", exact: true })
      .click();
    await page.getByRole("textbox").fill("wrong");
    await page
      .getByRole("button", { name: en ? "Continue" : "Continuar", exact: true })
      .click();
    await expect(page.getByRole("textbox")).toHaveValue("");
    await page.getByRole("textbox").fill("SPACE");
    await page
      .getByRole("button", { name: en ? "Continue" : "Continuar", exact: true })
      .click();
    await page
      .getByRole("button", {
        name: en ? "Perform practice" : "Realizar práctica",
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(/\/pvt\?purpose=practice&attempt=/);
    const practiceUrl = new URL(page.url());
    const attempt = practiceUrl.searchParams.get("attempt")!;
    practiceUrl.searchParams.set("fast", "1");
    await page.goto(practiceUrl.toString());
    await page
      .getByRole("button", {
        name: en ? "Continue to KSS" : "Continuar a KSS",
        exact: true,
      })
      .click();
    await page.getByRole("radio").nth(4).check();
    await page
      .getByRole("button", {
        name: en ? /Confirm KSS and view/ : /Confirmar KSS y ver/,
      })
      .click();
    await page
      .getByRole("button", {
        name: en ? "I am ready" : "Estoy listo",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", {
        name: en ? /Start PVT practice/ : /Iniciar práctica PVT/,
      })
      .click();
    for (let i = 0; i < 14; i++) {
      await page.keyboard.press("Space");
      await page.waitForTimeout(1000);
    }
    await expect(
      page.getByRole("heading", {
        name: en ? "KSS and PVT complete" : "KSS y PVT completadas",
        exact: true,
      }),
    ).toBeVisible();
    await page
      .getByRole("link", {
        name: en
          ? "Continue visit: next action"
          : "Continuar visita: siguiente acción",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", {
        name: en ? "Prepare · baseline" : "Preparar · baseline",
        exact: true,
      })
      .click();
    await page
      .getByRole("button", {
        name: new RegExp(
          `${en ? "Evaluate observations" : "Evaluar observaciones"}.*${attempt.slice(0, 8)}`,
        ),
      })
      .click();
    await expect(
      page.getByRole("button", {
        name: en ? "Perform assessment" : "Realizar evaluación",
        exact: true,
      }),
    ).toBeVisible();
    const prep = await (
      await request.get(
        `${base}/study/assignments/${assignment.id}/preparation`,
      )
    ).json();
    expect(prep.preparations).toHaveLength(2);
    expect(
      prep.preparations.find(
        (run: { next_action: string }) => run.next_action === "stopped",
      ).events,
    ).toHaveLength(1);
    const events = prep.preparations.find(
      (run: { practice_attempt_ids: string[] }) =>
        run.practice_attempt_ids.includes(attempt),
    ).events;
    expect(
      events
        .filter((e: { stage: string }) => e.stage === "comprehension")
        .map((e: { passed: boolean }) => e.passed),
    ).toEqual([false, true]);
    expect(
      events.find((e: { stage: string }) => e.stage === "practice").attempt_id,
    ).toBe(attempt);
    await page
      .getByRole("button", {
        name: en ? "Perform assessment" : "Realizar evaluación",
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(/purpose=study&attempt=/);
    await page
      .getByRole("button", {
        name: en ? "Continue to KSS" : "Continuar a KSS",
        exact: true,
      })
      .click();
    await expect(
      page.getByRole("heading", {
        name: en
          ? "Karolinska Sleepiness Scale"
          : "Escala de Somnolencia de Karolinska",
        exact: true,
      }),
    ).toBeVisible();
  });
}

// Native transport is software-only: exercise the real assigned pages and exact
// questionnaire UI while the native-process lifecycle is represented by the fixture.
for (const locale of ["en", "es-419"] as const) {
  test(`assigned native release and exact ratings navigation in ${locale}`, async ({
    page,
    request,
  }) => {
    const { fixture, SUITE, BLOCK } = await import("./openmatb-fixtures");
    const native = await fixture(page, locale);
    const en = locale === "en",
      assignment = "assigned-native-fixture";
    native.current = {
      ...native.current,
      study_assignment_id: assignment,
      lifecycle: "RUNNING",
      active_block: "HIGH",
      active_block_instance_id: BLOCK,
      block_order: ["HIGH"],
      current_block_index: 0,
    };
    const base = await baseOccasion(request);
    const task = {
      ...base,
      key: "task",
      order: 1,
      instrument: "openmatb",
      locale,
      config: {},
    };
    const rating = {
      ...base,
      key: "rating",
      order: 2,
      instrument: "questionnaire",
      locale,
      target_key: "task",
      config: {},
    };
    const taskAttempt = {
      id: "exact-task",
      occasion_id: "task-occasion",
      ordinal: 1,
      execution_purpose: "study",
      acquisition_state: "created",
      sources: [{ source_table: "openmatb_suite_session", source_id: SUITE }],
    };
    const questionnaire = {
      id: "exact-questionnaire",
      occasion_id: "rating-occasion",
      target_attempt_id: taskAttempt.id,
      ordinal: 1,
      execution_purpose: "study",
      acquisition_state: "created",
      sources: [],
    };
    const detail = {
      assignment: {
        id: assignment,
        participant_id: "P01",
        visit_id: 1,
        version_id: "frozen-fixture",
      },
      version: {
        study: {
          title: "Software navigation fixture",
          occasions: [task, rating],
        },
      },
      occasions: { task: "task-occasion", rating: "rating-occasion" },
      attempts: { task: [taskAttempt], rating: [questionnaire] },
    };
    await page.route(`**/study/assignments/${assignment}`, (route) =>
      route.fulfill({ json: detail }),
    );
    await page.route(
      `**/study/assignments/${assignment}/preparation`,
      (route) =>
        route.fulfill({
          json: { requirements: { task: [], rating: [] }, preparations: [] },
        }),
    );
    await page.route("**/assessments/attempts/exact-task", (route) =>
      route.fulfill({ json: taskAttempt }),
    );
    await page.route(
      `**/assessments/sources/openmatb_block_attempt/${BLOCK}*`,
      (route) => route.fulfill({ json: questionnaire }),
    );
    await page.route(
      "**/assessments/occasions/rating-occasion/attempts",
      (route) => route.fulfill({ json: [questionnaire] }),
    );
    await page.route(`**/openmatb/sessions/${SUITE}/scales`, async (route) => {
      const body = route.request().postDataJSON();
      native.submissions.push(body);
      questionnaire.acquisition_state = "finished";
      native.current = {
        ...native.current,
        lifecycle: "COMPLETE",
        active_block: null,
        active_block_instance_id: null,
        scores: { rating: body },
        current_block_index: 1,
      };
      await route.fulfill({ json: native.current });
    });
    await page.goto(`/study/participant?assignment=${assignment}`);
    await page
      .getByRole("button", {
        name: en ? "Perform assessment" : "Realizar evaluación",
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(
      new RegExp(`/openmatb/participant\\?session=${SUITE}`),
    );
    expect(native.starts).toBe(1);
    taskAttempt.acquisition_state = "finished";
    native.current = { ...native.current, lifecycle: "AWAITING_SCALE" };
    await page.goto(`/study/participant?assignment=${assignment}`);
    await page
      .getByRole("button", {
        name: en ? "Answer ratings" : "Responder valoraciones",
        exact: true,
      })
      .click();
    await expect(page).toHaveURL(/questionnaire=exact-questionnaire/);
    await expect(
      page.getByLabel(
        en
          ? "Questionnaire attempt for this task"
          : "Intento de cuestionario para esta tarea",
      ),
    ).toHaveValue("exact-questionnaire");
    const defaults = page.getByRole("button", {
      name: en ? /Use 50 for/ : /Usar 50 para/,
    });
    await expect(defaults).toHaveCount(6);
    for (let index = 0; index < 6; index++) await defaults.first().click();
    await expect(defaults).toHaveCount(0);
    await page.getByRole("radio").first().check();
    await page
      .getByRole("button", {
        name: en ? "Save ratings and continue" : "Guardar escalas y continuar",
        exact: true,
      })
      .click();
    await expect.poll(() => native.submissions.length).toBe(1);
    expect(native.submissions[0]).toMatchObject({
      block_instance_id: BLOCK,
      questionnaire_attempt_id: "exact-questionnaire",
    });
    await page
      .getByRole("link", {
        name: en
          ? "Continue visit: next action"
          : "Continuar visita: siguiente acción",
        exact: true,
      })
      .click();
    await expect(
      page.getByText(
        en
          ? /Assessments performed.*close visit collection/
          : /Evaluaciones realizadas.*cerrar la recolección/,
      ),
    ).toBeVisible();
  });
}

test("historical unknown exposure and exact immutable classification history", async ({
  page,
}) => {
  const historyA = {
    classifications: [{ id: "history-A", reason: "Old A classification" }],
  };
  const historyB = {
    classifications: [{ id: "history-B", reason: "Original B classification" }],
  };
  await page.addInitScript(() => localStorage.setItem("matb-fac.locale", "en"));
  await page.route("**/study/participants/HISTORY/exposure", (route) =>
    route.fulfill({
      json: [
        {
          attempt_id: "historical-attempt",
          instrument: "pvt",
          purpose: "unknown",
          duration_seconds: null,
          outcome: "unknown",
          competence: null,
        },
      ],
    }),
  );
  await page.route("**/assessments/occasions?participant_id=HISTORY", (route) =>
    route.fulfill({
      json: [
        { id: "A", origin: "legacy", instrument: "pvt" },
        { id: "B", origin: "legacy", instrument: "pvt" },
      ],
    }),
  );
  let releaseA!: () => void;
  await page.route(
    "**/assessments/occasions/A/classifications",
    async (route) => {
      await new Promise<void>((resolve) => {
        releaseA = resolve;
      });
      await route.fulfill({ json: historyA });
    },
  );
  const posted: unknown[] = [];
  await page.route("**/assessments/occasions/B/classifications", (route) => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON();
      posted.push(body);
      return route.fulfill({
        json: {
          classifications: [
            ...historyB.classifications,
            { id: "B-new", ...body },
          ],
        },
      });
    }
    return route.fulfill({ json: historyB });
  });
  await page.goto("/study/history?participant=HISTORY");
  await expect(
    page.getByRole("cell", { name: "Unknown", exact: true }).first(),
  ).toBeVisible();
  await page
    .getByRole("combobox", { name: "Historical occasion", exact: true })
    .selectOption("A");
  await expect.poll(() => Boolean(releaseA)).toBe(true);
  await page
    .getByRole("combobox", { name: "Historical occasion", exact: true })
    .selectOption("B");
  await expect(page.getByText(/Original B classification/)).toBeVisible();
  releaseA();
  await expect(page.getByText(/Old A classification/)).toHaveCount(0);
  await page.getByLabel("Reviewer", { exact: true }).fill("Dr History");
  await page
    .getByLabel("Reason and references", { exact: true })
    .fill("Reviewed source record");
  await page.getByLabel("Visit ID", { exact: true }).fill("7");
  await page.getByLabel("Phase", { exact: true }).fill("baseline");
  await page.getByLabel("Order", { exact: true }).fill("1");
  await page
    .getByRole("button", { name: "Record classification", exact: true })
    .click();
  await expect(page.getByText(/B-new/)).toBeVisible();
  expect(posted).toEqual([
    {
      reviewer: "Dr History",
      reason: "Reviewed source record",
      visit_id: 7,
      phase: "baseline",
      order: 1,
      supporting_references: [],
    },
  ]);
  await expect(page.getByText(/Original B classification/)).toBeVisible();
});

// Failure paths remain unresolved until both native abort and the durable stop write succeed.
for (const locale of ["en", "es-419"] as const) {
  test(`native preparation stop preserves abort uncertainty and write failures in ${locale}`, async ({
    page,
  }) => {
    const { fixture, SUITE } = await import("./openmatb-fixtures");
    const native = await fixture(page, locale);
    const en = locale === "en";
    native.current = { ...native.current, lifecycle: "PREFLIGHT_HELD" };
    const assignment = "native-stop-fixture";
    const preparation = {
      id: "native-stop-preparation",
      occasion_key: "task",
      next_action: "acknowledgement",
      presentation: { locale, instrument: "openmatb", items: [] },
      events: [
        { stage: "native_presentation", session_id: SUITE, passed: true },
      ],
      practice_attempt_ids: [],
    };
    const detail = {
      assignment: {
        id: assignment,
        participant_id: "P01",
        visit_id: 1,
        version_id: "frozen-fixture",
      },
      version: {
        study: {
          title: "Software stop fixture",
          occasions: [
            { key: "task", instrument: "openmatb", locale, order: 1 },
          ],
        },
      },
      occasions: { task: "task-occasion" },
      attempts: { task: [] },
    };
    await page.route(`**/study/assignments/${assignment}`, (route) =>
      route.fulfill({ json: detail }),
    );
    await page.route(
      `**/study/assignments/${assignment}/preparation`,
      (route) =>
        route.fulfill({
          json: {
            requirements: {
              task: [{ occasion_key: "task", state: "required" }],
            },
            preparations: [preparation],
          },
        }),
    );
    const calls: string[] = [];
    let abortFailed = false,
      writeFailed = false;
    await page.route(`**/openmatb/sessions/${SUITE}/abort`, (route) => {
      if (!abortFailed) {
        abortFailed = true;
        calls.push("abort-unconfirmed");
        return route.fulfill({
          status: 409,
          json: {
            detail: {
              code: "openmatb_stop_unconfirmed",
              message: "Native stop unconfirmed",
            },
          },
        });
      }
      calls.push("abort-confirmed");
      native.current = { ...native.current, lifecycle: "ABORTED" };
      return route.fulfill({ json: native.current });
    });
    await page.route(
      "**/study/preparation/native-stop-preparation/stop",
      (route) => {
        if (!writeFailed) {
          writeFailed = true;
          calls.push("stop-write-failed");
          return route.fulfill({
            status: 500,
            json: { detail: "Stop evidence write unavailable" },
          });
        }
        calls.push("stop-written");
        preparation.next_action = "stopped";
        preparation.events.push({
          stage: "stopped",
          session_id: "",
          passed: false,
        });
        return route.fulfill({ json: preparation });
      },
    );
    await page.goto(`/study/participant?assignment=${assignment}`);
    await page
      .getByRole("button", {
        name: en ? "Prepare · task" : "Preparar · task",
        exact: true,
      })
      .click();
    const stop = page.getByRole("button", {
      name: en ? "Stop preparation" : "Detener preparación",
      exact: true,
    });
    const stoppedMessage = page.getByText(
      en
        ? /Preparation stopped. Prior records/
        : /Preparación detenida. Los registros/,
    );
    await stop.focus();
    await page.keyboard.press("Enter");
    await expect(
      page.getByRole("alert").filter({ hasText: "Native stop unconfirmed" }),
    ).toBeVisible();
    await expect.poll(() => calls).toEqual(["abort-unconfirmed"]);
    await expect(stoppedMessage).toHaveCount(0);
    await stop.focus();
    await page.keyboard.press("Enter");
    await expect
      .poll(() => calls)
      .toEqual(["abort-unconfirmed", "abort-confirmed", "stop-write-failed"]);
    await expect(
      page
        .getByRole("alert")
        .filter({ hasText: "Stop evidence write unavailable" }),
    ).toBeVisible();
    await expect(stoppedMessage).toHaveCount(0);
    await stop.focus();
    await page.keyboard.press("Enter");
    await expect(stoppedMessage).toBeVisible();
    expect(calls).toEqual([
      "abort-unconfirmed",
      "abort-confirmed",
      "stop-write-failed",
      "stop-written",
    ]);
    expect(native.current.lifecycle).toBe("ABORTED");
    expect(preparation.events[0]).toMatchObject({
      stage: "native_presentation",
      session_id: SUITE,
    });
    expect(preparation.next_action).toBe("stopped");
  });
}
