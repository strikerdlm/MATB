import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import { AppLocaleProvider, useAppLocale } from "@/lib/i18n";

function Harness() {
  const { locale, setLocale, tr } = useAppLocale();
  return (
    <>
      <span>{locale}</span>
      <span>{tr("nav.participants")}</span>
      <button onClick={() => setLocale("en")}>English</button>
    </>
  );
}

describe("AppLocaleProvider", () => {
  beforeEach(() => localStorage.clear());

  it("defaults to Latin American Spanish and persists an English selection", async () => {
    const user = userEvent.setup();
    render(
      <AppLocaleProvider>
        <Harness />
      </AppLocaleProvider>,
    );
    expect(screen.getByText("es-419")).toBeInTheDocument();
    expect(screen.getByText("Participantes")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "English" }));
    expect(await screen.findByText("en")).toBeInTheDocument();
    expect(screen.getByText("Participants")).toBeInTheDocument();
    expect(localStorage.getItem("matb-fac.locale")).toBe("en");
  });
});
