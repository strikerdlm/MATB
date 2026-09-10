import React from "react";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { MISSION_CONSOLE_PROFILE, consoleProfileStatus } from "@/lib/simulation/console-profile";
import { ConsoleProfileProvenance } from "./ConsoleProfileProvenance";

it("does not upgrade historical or unknown replay identity", () => {
  const { rerender } = render(<ConsoleProfileProvenance profile={undefined} locale="en" />);
  expect(screen.getByRole("note")).toHaveTextContent("Historical console: no recorded profile");
  rerender(<ConsoleProfileProvenance profile={MISSION_CONSOLE_PROFILE} locale="en" />);
  expect(screen.getByRole("note")).toHaveTextContent(MISSION_CONSOLE_PROFILE.sha256);
  rerender(<ConsoleProfileProvenance profile={{ ...MISSION_CONSOLE_PROFILE, sha256: "0".repeat(64) }} locale="es-CO" />);
  expect(screen.getByRole("alert")).toHaveTextContent("apariencia registrada sin verificar");
  expect(consoleProfileStatus({ ...MISSION_CONSOLE_PROFILE, version: 2 })).toBe("unsupported");
  expect(consoleProfileStatus(null)).toBe("legacy");
});
