import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ExperimentGuide } from "@/components/experiments/ExperimentGuide";
import { AppLocaleProvider } from "@/lib/i18n";

const pathname = "/screen";
let search = new URLSearchParams("participant=P01");
vi.mock("next/navigation", () => ({
  usePathname: () => pathname,
  useSearchParams: () => search,
}));

describe("ExperimentGuide", () => {
  it("offers explicit purpose choices when the URL has no valid purpose", () => {
    render(<AppLocaleProvider><ExperimentGuide id="screen" /></AppLocaleProvider>);
    expect(screen.getByRole("heading", { name: /Elija cómo participará/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Practicar" }))
      .toHaveAttribute("href", "/screen?participant=P01&purpose=practice");
    expect(screen.getByRole("link", { name: "Participar en mi estudio" }))
      .toHaveAttribute("href", "/screen?participant=P01&purpose=study");
  });

  it("keeps the selected purpose in the catalog link and explains practice separation", () => {
    search = new URLSearchParams("purpose=practice&participant=P01");
    render(<AppLocaleProvider><ExperimentGuide id="screen" /></AppLocaleProvider>);
    expect(screen.getByText(/no completa una visita de estudio/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Ver experimentos" }))
      .toHaveAttribute("href", "/start?experiment=screen&purpose=practice");
  });
});
