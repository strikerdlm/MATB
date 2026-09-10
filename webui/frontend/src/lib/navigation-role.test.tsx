import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  NavigationRoleProvider,
  destinationForRole,
  isRouteActive,
  useNavigationRole,
} from "@/lib/navigation-role";

function RoleControl() {
  const { role, setRole } = useNavigationRole();
  return <button onClick={() => setRole("researcher")}>{role ?? "choose"}</button>;
}

describe("navigation role", () => {
  beforeEach(() => window.sessionStorage.clear());

  it("stores the explicit choice only for the current tab", async () => {
    const user = userEvent.setup();
    render(<NavigationRoleProvider><RoleControl /></NavigationRoleProvider>);
    expect(screen.getByRole("button", { name: "choose" })).toBeInTheDocument();
    await user.click(screen.getByRole("button"));
    expect(screen.getByRole("button", { name: "researcher" })).toBeInTheDocument();
    expect(window.sessionStorage.getItem("matb.navigation.role")).toBe("researcher");
  });

  it("routes each role to its workspace and matches nested routes", () => {
    expect(destinationForRole("participant")).toBe("/start");
    expect(destinationForRole("researcher")).toBe("/tracker");
    expect(isRouteActive("/analysis/liftoff", "/analysis")).toBe(true);
    expect(isRouteActive("/start", "/tracker")).toBe(false);
  });

  it("keeps workspace navigation usable when tab storage is unavailable", async () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("storage blocked"); });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("storage blocked"); });
    render(<NavigationRoleProvider><RoleControl /></NavigationRoleProvider>);
    await userEvent.click(screen.getByRole("button", { name: "choose" }));
    expect(screen.getByRole("button", { name: "researcher" })).toBeInTheDocument();
  });
});
