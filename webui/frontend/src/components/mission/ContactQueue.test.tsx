import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ContactQueue } from "./ContactQueue";
import type { ContactSnapshot } from "@/types/simulation";

const contact = {
  contact_id: "CONTACT-01",
  position: { x_mm: 100, y_mm: 100 },
  evidence: "INSPECTABLE",
  workflow: "INSPECTED",
  classification: null,
  priority: null,
} as ContactSnapshot;

describe("ContactQueue", () => {
  it("selects a contact for explicit command choices instead of applying defaults", () => {
    const onSelect = vi.fn();
    const onInspect = vi.fn();
    render(<ContactQueue contacts={[contact]} locale="en" onSelect={onSelect} onInspect={onInspect} />);

    expect(screen.queryByRole("button", { name: /classify contact/i })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /select contact-01/i }));
    expect(onSelect).toHaveBeenCalledWith("CONTACT-01");
    expect(onInspect).not.toHaveBeenCalled();
  });
});
