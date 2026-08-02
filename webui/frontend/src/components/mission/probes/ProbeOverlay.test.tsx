import React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { IsaProbe } from "./IsaProbe";
import { PostBlockScales } from "./PostBlockScales";
import { ProbeOverlay } from "./ProbeOverlay";
import type { IsaProbePayload, SagatProbePayload } from "@/types/simulation";

const isa: IsaProbePayload = { kind: "ISA", probe_id: "isa-1", question: "Rate your awareness", timeout_ms: 10_000, min: 1, max: 10 };
const sagat: SagatProbePayload = { kind: "SAGAT", probe_id: "sagat-1", sa_level: 1, domain: "perception", question: "How many links are lost?", options: ["0", "1", "Unknown"], timeout_ms: 10_000 };

describe("research probe overlays", () => {
  it("ISA exposes exactly integer values 1 through 10", () => { render(<IsaProbe locale="es-CO" probe={isa} onSubmit={vi.fn()} />); expect(screen.getAllByRole("radio")).toHaveLength(10); });
  it("conceals the operational state for SAGAT", () => { render(<ProbeOverlay locale="en" probe={sagat} onIsa={vi.fn()} onSagat={vi.fn()} onPostBlock={vi.fn()} />); expect(screen.getByRole("dialog", { name: /situation awareness/i })).toHaveFocus(); expect(screen.queryByText(/truth|weapon|engage/i)).not.toBeInTheDocument(); });
  it("requires all TLX fields and Bedford before submission", async () => { const submit = vi.fn(); render(<PostBlockScales locale="en" onSubmit={submit} />); expect(screen.getByRole("button", { name: /submit measures/i })).toBeDisabled(); for (const label of ["mental demand", "physical demand", "temporal demand", "performance", "effort", "frustration"]) fireEvent.change(screen.getByLabelText(label), { target: { value: "5" } }); fireEvent.change(screen.getByLabelText("Bedford"), { target: { value: "5" } }); expect(screen.getByRole("button", { name: /submit measures/i })).toBeEnabled(); });
});
