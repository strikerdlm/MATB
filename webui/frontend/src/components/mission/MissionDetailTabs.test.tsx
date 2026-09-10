import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MissionDetailTabs } from "./MissionDetailTabs";

describe("mission detail keyboard tabs", () => {
  it.each([true, false])("focuses manually and enters only the active panel (modern %s)", async modern => {
    const user = userEvent.setup();
    render(<MissionDetailTabs locale="en" modern={modern} alerts={<button>Acknowledge</button>} contacts={<button>Inspect</button>} />);
    const alerts = screen.getByRole("tab", { name: "Alerts" });
    const contacts = screen.getByRole("tab", { name: "Contacts" });
    await user.tab();
    expect(alerts).toHaveFocus();
    await user.keyboard("{ArrowRight}");
    expect(contacts).toHaveFocus();
    expect(alerts).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByRole("button", { name: "Inspect" })).not.toBeInTheDocument();
    await user.keyboard("{Enter}");
    expect(contacts).toHaveAttribute("aria-selected", "true");
    await user.tab();
    expect(screen.getByRole("tabpanel")).toHaveFocus();
    expect(screen.getByRole("tabpanel")).toHaveAccessibleName("Contacts");
    await user.tab();
    expect(screen.getByRole("button", { name: "Inspect" })).toHaveFocus();
    await user.tab({ shift: true });
    await user.tab({ shift: true });
    await user.keyboard("{Home}");
    expect(alerts).toHaveFocus();
    expect(contacts).toHaveAttribute("aria-selected", "true");
    await user.keyboard(" ");
    expect(alerts).toHaveAttribute("aria-selected", "true");
    await user.keyboard("{End}");
    expect(contacts).toHaveFocus();
    await user.keyboard("{ArrowLeft}");
    expect(alerts).toHaveFocus();
  });
});
