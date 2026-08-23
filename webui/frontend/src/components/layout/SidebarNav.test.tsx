import { describe, expect, it, vi } from "vitest";
import React from "react";
import { render, screen } from "@testing-library/react";

import { SidebarNav } from "@/components/layout/SidebarNav";

vi.mock("next/navigation", () => ({ usePathname: () => "/classic/setup" }));

describe("SidebarNav", () => {
  it("exposes classic MATB acquisition and marks every classic route active", () => {
    render(<SidebarNav />);

    const link = screen.getByRole("link", { name: /classic/i });
    expect(link).toHaveAttribute("href", "/classic/setup");
    expect(link).toHaveAttribute("aria-current", "page");
  });
});
