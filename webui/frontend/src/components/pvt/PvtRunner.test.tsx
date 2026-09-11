import { act, fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { PvtRunner } from "./PvtRunner";
vi.mock("@/lib/i18n", () => ({
  useAppLocale: () => ({ copy: (_es: string, en: string) => en }),
}));
it("awaits start admission and exposes rejection before any task begins", async () => {
  let reject!: (error: Error) => void;
  const admission = new Promise<void>((_resolve, r) => {
    reject = r;
  });
  const onComplete = vi.fn();
  render(<PvtRunner onStart={() => admission} onComplete={onComplete} />);
  fireEvent.click(screen.getByRole("button", { name: "Start 10-minute PVT" }));
  expect(
    screen.getByRole("button", { name: "Start 10-minute PVT" }),
  ).toBeDisabled();
  expect(
    screen.queryByText("Stop and save incomplete recording"),
  ).not.toBeInTheDocument();
  await act(async () => {
    reject(new Error("Station owns a heavy job"));
  });
  expect(screen.getByRole("alert")).toHaveTextContent(
    "Station owns a heavy job",
  );
  expect(onComplete).not.toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "Start 10-minute PVT" }),
  ).toBeEnabled();
});
