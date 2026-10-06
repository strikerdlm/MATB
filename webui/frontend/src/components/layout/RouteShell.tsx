"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";
import { useNavigationRole } from "@/lib/navigation-role";

/**
 * The operator console owns its viewport.  Keep it outside the research
 * console chrome while leaving every existing route inside AppShell.
 */
export function RouteShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const { role } = useNavigationRole();
  const crewRoute = pathname === "/study/join" || pathname === "/study/run"
    || (pathname === "/study/assignments" && role !== "researcher");
  const isMissionRoute = pathname === "/mission"
    || pathname.startsWith("/mission/debrief")
    || pathname.startsWith("/openmatb/participant")
    || pathname.startsWith("/liftoff/session")
    || pathname.startsWith("/liftoff/debrief");

  if (crewRoute || isMissionRoute) {
    return <div className="min-h-screen bg-background">{children}</div>;
  }

  return <AppShell>{children}</AppShell>;
}
