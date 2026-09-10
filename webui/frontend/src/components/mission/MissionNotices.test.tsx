import React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { connectionNotice, MissionNotices, type MissionNotice } from "./MissionNotices";

const command: MissionNotice = { severity: "info", source: "command", message: "Command accepted", action: "Acknowledges receipt; it does not evaluate performance.", resolution: "acknowledged" };
it("shows command receipt independently of a connection error and resolves reconnect warning", () => {
  const connection = connectionNotice("reconnecting", "Connection lost", "en")!;
  const { rerender } = render(<MissionNotices modern notices={[command, connection]} />);
  expect(screen.getByRole("status")).toHaveTextContent("does not evaluate performance");
  expect(screen.getByRole("alert")).toHaveAttribute("data-source", "connection");
  expect(screen.getByRole("alert")).toHaveAttribute("data-resolution", "pending");
  expect(connectionNotice("live", null, "en")).toBeNull();
  rerender(<MissionNotices modern notices={[command]} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toBeVisible();
});
describe("versioned notice appearance", () => {
  it.each(["success", "info", "warning", "error"] as const)("renders %s with its own semantic tone", severity => {
    render(<MissionNotices modern notices={[{ ...command, severity }]} />);
    const notice = screen.getByRole(severity === "error" ? "alert" : "status");
    expect(notice).toHaveAttribute("data-severity", severity);
    expect(notice).toHaveClass(severity === "error" ? "text-destructive" : `text-${severity}`);
  });
  it("keeps the historical single warning banner", () => {
    render(<MissionNotices modern={false} notices={[command]} legacyMessage="Command accepted" />);
    expect(screen.getByRole("status")).toHaveClass("text-xs", "text-warning", "font-mono");
    expect(screen.getByRole("status")).not.toHaveTextContent("performance");
  });
  it("provides Spanish reconnect guidance", () => {
    expect(connectionNotice("reconnecting", null, "es-CO")?.action).toBe("Espere la reconexión automática.");
  });
});
