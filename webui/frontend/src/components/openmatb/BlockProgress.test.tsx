import React from "react";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { BlockProgress } from "./BlockProgress";
import type { OpenMatbSession, OpenMatbReceipt, OpenMatbBlockReceipt } from "@/types/openmatb";
vi.mock("@/lib/i18n", () => ({ useAppLocale: () => ({ copy: (_es: string, en: string) => en }) }));
const ready = { lifecycle: "READY", block_order: ["PRACTICE", "LOW", "MEDIUM", "HIGH"], current_block_index: 0, active_block: null } as OpenMatbSession;
const attempt = { block_instance_id: "first", block_index: 0, profile: "PRACTICE", task_status: "completed", artifact_status: "saved", ratings_status: "not_required" } as OpenMatbBlockReceipt;
const receipt = { attempts: [attempt] } as OpenMatbReceipt;
describe("authoritative OpenMATB block progress", () => {
  it("shows the planned order and current block before a launch", () => {
    render(<BlockProgress session={ready} receipt={null} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
    const first = screen.getAllByRole("listitem")[0];
    expect(first).toHaveAttribute("aria-current", "step");
    expect(first).toHaveTextContent("Ready to start");
    expect(screen.queryByText("Confirmed")).toBeNull();
  });
  it("shows saved prior attempts and the next block between launches", () => {
    render(<BlockProgress session={{ ...ready, lifecycle: "BETWEEN_BLOCKS", current_block_index: 1 }} receipt={receipt} />);
    expect(screen.getAllByRole("listitem")[0]).toHaveTextContent("Confirmed");
    expect(screen.getAllByRole("listitem")[1]).toHaveAttribute("aria-current", "step");
    expect(screen.getAllByRole("listitem")[1]).toHaveTextContent("Ready to start");
  });
  it("retains each practice attempt while a repeat is running", () => {
    const repeated = { ...receipt, attempts: [attempt, { ...attempt, block_instance_id: "second", task_status: "running", artifact_status: "pending" }] };
    render(<BlockProgress session={{ ...ready, lifecycle: "RUNNING", active_block: "PRACTICE", active_block_instance_id: "second" }} receipt={repeated} />);
    const practice = within(screen.getAllByRole("listitem")[0]);
    expect(practice.getByText("Attempt 1")).toBeVisible();
    expect(practice.getByText("Attempt 2")).toBeVisible();
    expect(practice.getByText("In progress")).toBeVisible();
    expect(practice.getByText("Not yet confirmed")).toBeVisible();
  });
  it("shows an unconfirmed current attempt while the receipt still contains only a prior completed practice", () => {
    render(<BlockProgress session={{ ...ready, lifecycle: "STARTING", active_block: "PRACTICE", active_block_instance_id: "second" }} receipt={receipt} />);
    expect(screen.getByText("Attempt 1")).toBeVisible();
    expect(screen.getByText("Confirmed")).toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("Current attempt");
    expect(screen.getByRole("status")).toHaveTextContent("Checking save status for this attempt");
  });
});
