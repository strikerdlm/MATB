"use client";

import React from "react";
import { usePathname } from "next/navigation";
import { AppShell } from "@/components/layout/AppShell";

/**
 * The operator console owns its viewport.  Keep it outside the research
 * console chrome while leaving every existing route inside AppShell.
 */
export function RouteShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname() ?? "/";
  const isMissionRoute = pathname === "/mission" || pathname.startsWith("/mission/debrief");

  if (isMissionRoute) {
    return <div className="min-h-screen bg-background">{children}</div>;
  }

  return <AppShell>{children}</AppShell>;
}
