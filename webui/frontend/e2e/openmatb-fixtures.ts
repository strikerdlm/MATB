import type { Page } from "@playwright/test";
import type { OpenMatbSession, OpenMatbReceipt, WorkloadScaleSubmission } from "../src/types/openmatb";

export const SUITE = "aaaaaaaa-0000-4000-8000-000000000001";
export const BLOCK = "bbbbbbbb-0000-4000-8000-000000000001";
export const NEXT_BLOCK = "bbbbbbbb-0000-4000-8000-000000000002";
export const DRAFT = `openmatb.workload-draft.openmatb-workload-v1.${SUITE}.${BLOCK}`;
type Locale = "en" | "es-419";
function session(locale: Locale): OpenMatbSession {
  return {
    id: SUITE, participant_id: "P01", visit_ordinal: 1, visit_code: "T0", scheduled_day: 0,
    execution_purpose: "study", locale, lifecycle: "AWAITING_SCALE", block_order: ["PRACTICE", "LOW", "MEDIUM", "HIGH"], current_block_index: 1,
    active_block: "LOW", active_block_instance_id: BLOCK, evidence_processing: false, native_recovery_required: false,
    preset_id: "matb-fac", preset_version: "1.0.0", preset_sha256: "a".repeat(64),
    instruction_protocol: { protocol_id: "instructions", version: "1.0.0", locale, status: "published", sha256: "b".repeat(64),
      title: "Instructions", steps: ["Read the task instructions."], task_instructions: {}, visit_instructions: {} },
    visit_instruction: "Follow the researcher’s instructions.", visual_theme: "fac_modern", visual_profile_id: "matb-fac-modern", visual_profile_version: "1.0.0",
    visual_profile_schema_version: "openmatb-visual-profile-v1", visual_profile_sha256: "c".repeat(64), display_index: 1,
    scores: {}, active_pid: null, last_error: null, created_at: "2026-09-10T02:00:00Z", started_at: "2026-09-10T02:01:00Z", finished_at: null,
  };
}
function receipt(value: OpenMatbSession): OpenMatbReceipt {
  return { session_id: SUITE, participant_id: value.participant_id, visit_ordinal: value.visit_ordinal, execution_purpose: value.execution_purpose,
    lifecycle: value.lifecycle, historical: false, block_order: value.block_order, attempts: [{
      block_instance_id: BLOCK, block_index: 0, profile: "PRACTICE", execution_purpose: "practice", task_status: "completed",
      started_at: value.started_at!, finished_at: "2026-09-10T02:03:00Z", artifact_status: "saved", artifact_error: null,
      ratings_status: "not_required", ratings_saved_at: null, legacy_import_status: "not_required", legacy_import_error: null,
      evidence_status: "queued", evidence_error: null, capture_id: null, capture_status: null, qualification: null,
    }] };
}
export async function fixture(page: Page, locale: Locale) {
  const state = { current: session(locale), failPoll: false, failSave: false, submissions: [] as WorkloadScaleSubmission[], preparations: [] as Array<Record<string, unknown>>, starts: 0 };
  await page.addInitScript(({ locale, id }) => {
    localStorage.setItem("matb-fac.locale", locale);
    sessionStorage.setItem(`openmatb.participant.${id}`, "test-participant");
    sessionStorage.setItem(`openmatb.controller.${id}`, "test-controller");
  }, { locale, id: SUITE });
  await page.route("**/openmatb/sessions", route => {
    const body = route.request().postDataJSON();
    state.preparations.push(body);
    state.current = { ...state.current, execution_purpose: body.execution_purpose, participant_id: body.participant_id, visit_ordinal: body.visit_ordinal, visit_code: `V${body.visit_ordinal}`, lifecycle: "INSTRUCTIONS", active_block: null, active_block_instance_id: null, current_block_index: 0 };
    return route.fulfill({ json: { session: state.current, controller_lease: "test-controller", participant_token: "test-participant" } });
  });
  await page.route("**/openmatb/sessions/**", async route => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/receipt")) return route.fulfill({ json: receipt(state.current) });
    if (path.endsWith("/scales")) {
      const body = route.request().postDataJSON() as WorkloadScaleSubmission;
      state.submissions.push(body);
      if (state.failSave) return route.fulfill({ status: 503, json: { detail: { code: "unavailable", message: "Save unavailable; retry." } } });
      state.current = { ...state.current, lifecycle: "BETWEEN_BLOCKS", active_block: null, active_block_instance_id: null, current_block_index: 2,
        scores: { LOW: body as unknown as Record<string, unknown> } };
      return route.fulfill({ json: state.current });
    }
    if (path.endsWith("/start")) state.starts++;
    if (state.failPoll) return route.fulfill({ status: 503, json: { detail: { code: "unavailable", message: "Connection interrupted" } } });
    return route.fulfill({ json: state.current });
  });
  await page.route("**/openmatb/displays", route => route.fulfill({ json: [
    { index: 0, label: "Display 1", width: 1920, height: 1080, x: 0, y: 0 },
    { index: 1, label: "Display 2", width: 1366, height: 768, x: 1920, y: 0 },
  ] }));
  await page.route("**/openmatb/readiness", route => route.fulfill({ json: {
    ready: true, platform: "linux", python_executable: "/test/python", openmatb_entrypoint: "/test/openmatb", display_index_default: 1,
    checks: { python: true, runtime_dependencies: true, openmatb: true, questionnaires_es: true, graphical_display: true, native_process_clear: true }, warnings: [],
  } }));
  return state;
}
