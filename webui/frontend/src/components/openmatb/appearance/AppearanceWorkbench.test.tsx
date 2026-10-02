import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppearanceWorkbench } from "./AppearanceWorkbench";
import type { OpenMatbVisualProfile, OpenMatbVisualProfileDocument } from "@/types/openmatb";

const mocks = vi.hoisted(() => ({
  list: vi.fn(),
  previewStatus: vi.fn(),
  clone: vi.fn(),
  update: vi.fn(),
  validate: vi.fn(),
  publish: vi.fn(),
  importProfile: vi.fn(),
  exportProfile: vi.fn(),
  startPreview: vi.fn(),
  abortPreview: vi.fn(),
}));

vi.mock("@/lib/openmatb/api", () => ({
  listOpenMatbVisualProfiles: mocks.list,
  getOpenMatbVisualPreview: mocks.previewStatus,
  cloneOpenMatbVisualProfile: mocks.clone,
  updateOpenMatbVisualProfile: mocks.update,
  validateOpenMatbVisualProfile: mocks.validate,
  publishOpenMatbVisualProfile: mocks.publish,
  importOpenMatbVisualProfile: mocks.importProfile,
  exportOpenMatbVisualProfile: mocks.exportProfile,
  startOpenMatbVisualPreview: mocks.startPreview,
  abortOpenMatbVisualPreview: mocks.abortPreview,
}));

const payload: OpenMatbVisualProfileDocument = {
  schema_version: "openmatb-visual-profile-v1",
  profile_id: "matb-fac-modern",
  version: "1.0.0",
  label: "MATB - FAC Modern",
  geometry_policy: "preserve_openmatb_v1",
  palette: {
    app_background: "#F7F9FC", panel_background: "#FFFFFF", instrument_background: "#FFFFFF",
    panel_header: "#FFFFFF", panel_header_text: "#0B4EA2", control_background: "#1E63D6",
    control_foreground: "#FFFFFF", text: "#222222", muted_text: "#667085", border: "#61758A",
    grid: "#D9E1EB", accent: "#1E63D6", safe: "#238B45", warning: "#C58A00",
    critical: "#D92D20", disabled: "#D9E1EB",
  },
  metrics: { line_width: 2, panel_radius: 12, corner_mark_ratio: 0.035 },
  modules: {
    tracking: { panel: "#FFFFFF", axis: "#286EF3", grid: "#D9E1EB", target: "#286EF3", target_fill: "#FFFFFF", cursor: "#165CD6", cursor_outside: "#D92D20", show_panel: true, show_grid: true, closed_target_border: true },
    system_monitoring: { panel: "#FFFFFF", lamp_1: "#FFD60A", lamp_2: "#FFD60A", lamp_3: "#FFD60A", lamp_4: "#FFD60A", lamp_off: "#E6F0FF", lamp_border: "#8A9CB0", lamp_shape: "circle", scale: "#8A9CB0", pointer: "#165CD6", feedback_positive: "#238B45", feedback_negative: "#D92D20" },
    communications: { panel: "#FFFFFF", display_background: "#F7F9FC", display_border: "#D9E1EB", active: "#1E63D6", inactive: "#8A9CB0", positive: "#238B45", negative: "#D92D20", show_display_bezel: true },
    resource_management: { panel: "#FFFFFF", tank_1: "#FFFFFF", tank_2: "#FFFFFF", tank_3: "#FFFFFF", tank_4: "#FFFFFF", tank_5: "#FFFFFF", tank_6: "#FFFFFF", fluid: "#1683E8", pipe_on: "#238B45", pipe_off: "#8B92A0", pump_on: "#238B45", pump_off: "#D9E1EB", pump_failure: "#D92D20", tolerance: "#C58A00", meter: "#165CD6", show_pump_ring: true },
    workload: { panel: "#FFFFFF", scale: "#8A9CB0", marker: "#1E63D6" },
  },
};

function makeProfile(status: "draft" | "published" = "published"): OpenMatbVisualProfile {
  return {
    profile_id: payload.profile_id,
    version: payload.version,
    label: payload.label,
    status,
    schema_version: payload.schema_version,
    sha256: "a".repeat(64),
    payload: JSON.parse(JSON.stringify(payload)) as OpenMatbVisualProfileDocument,
    validation: { valid: true, publishable: true, errors: [], warnings: [], unacknowledged_warning_codes: [] },
    warning_acknowledgements: [],
    bundled: status === "published",
    created_at: "2026-09-04T00:00:00Z",
    published_at: status === "published" ? "2026-09-04T00:00:00Z" : null,
  };
}

describe("AppearanceWorkbench", () => {
  beforeEach(() => {
    Object.values(mocks).forEach((mock) => mock.mockReset());
    mocks.list.mockResolvedValue([makeProfile()]);
    mocks.previewStatus.mockResolvedValue({ lifecycle: "IDLE", profile_id: null, profile_version: null, profile_sha256: null, pid: null, artifact_root: null, last_error: null });
  });

  it("loads the modern published profile as immutable", async () => {
    render(<AppearanceWorkbench />);
    expect(await screen.findByRole("heading", { name: "MATB - FAC" })).toBeInTheDocument();
    expect(screen.getByText("Published: clone to edit.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /save draft/i })).toBeDisabled();
    expect(screen.getByText(/Participant CVD/).closest("div")).toHaveTextContent("Not enabled");
  });

  it("prefers the approved daylight profile when both bundled profiles are available", async () => {
    const daylight = makeProfile();
    daylight.profile_id = "matb-daylight-avionics";
    daylight.payload.profile_id = daylight.profile_id;
    daylight.label = "MATB — Daylight Avionics";
    daylight.payload.palette.app_background = "#EFF3F7";
    mocks.list.mockResolvedValue([makeProfile(), daylight]);
    render(<AppearanceWorkbench />);
    await screen.findByRole("heading", { name: "MATB - FAC" });
    await waitFor(() => expect(screen.getByLabelText("Application")).toHaveValue("#EFF3F7"));
  });

  it("clones before editing and saves the resulting draft", async () => {
    const user = userEvent.setup();
    const cloned = makeProfile("draft");
    cloned.profile_id = "matb-fac-modern-custom";
    cloned.payload.profile_id = cloned.profile_id;
    cloned.bundled = false;
    mocks.clone.mockResolvedValue(cloned);
    mocks.update.mockImplementation(async (profile: OpenMatbVisualProfile) => profile);

    render(<AppearanceWorkbench />);
    await screen.findByRole("heading", { name: "MATB - FAC" });
    await user.click(screen.getByRole("button", { name: /^clone$/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /create draft/i }));
    await waitFor(() => expect(mocks.clone).toHaveBeenCalledWith(
      expect.objectContaining({ profile_id: "matb-fac-modern" }),
      expect.objectContaining({ profile_id: "matb-fac-modern-custom" }),
    ));

    const appColor = screen.getByLabelText("Application") as HTMLInputElement;
    await user.clear(appColor);
    await user.type(appColor, "#101820");
    await user.click(screen.getByRole("button", { name: /save draft/i }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    expect(mocks.update.mock.calls[0][0].payload.palette.app_background).toBe("#101820");
  });
});
