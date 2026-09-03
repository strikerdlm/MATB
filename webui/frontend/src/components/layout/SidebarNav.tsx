"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, Users, Upload, BarChart3, FlaskConical, Brain, Gamepad2, Radar, SlidersHorizontal } from "lucide-react";
import { cn } from "@/lib/utils";
import { getCapabilities } from "@/lib/api";
import { hasComponent, productRoutes } from "@/lib/capabilities";
import { useAppLocale, type AppTranslationKey } from "@/lib/i18n";
import type { ConsoleCapabilities } from "@/types";

const CORE_ITEMS = [
  { href: "/", labelKey: "nav.tracker" as AppTranslationKey, icon: LayoutGrid, enabled: true },
  { href: "/experiments", labelKey: "nav.designer" as AppTranslationKey, icon: SlidersHorizontal, enabled: true },
  { href: "/participants", labelKey: "nav.participants" as AppTranslationKey, icon: Users, enabled: true },
  { href: "/upload", labelKey: "nav.upload" as AppTranslationKey, icon: Upload, enabled: true },
  { href: "/visualization", labelKey: "nav.visualization" as AppTranslationKey, icon: BarChart3, enabled: true },
  { href: "/analysis", labelKey: "nav.analysis" as AppTranslationKey, icon: FlaskConical, enabled: true },
  { href: "/screen", labelKey: "nav.screen" as AppTranslationKey, icon: Brain, enabled: true },
];

export function SidebarNav() {
  const { tr } = useAppLocale();
  const pathname = usePathname() ?? "/";
  const [capabilities, setCapabilities] = useState<ConsoleCapabilities | null>(null);
  useEffect(() => {
    let active = true;
    void getCapabilities()
      .then((value) => { if (active) setCapabilities(value); })
      .catch(() => { if (active) setCapabilities(null); });
    return () => { active = false; };
  }, []);
  const optionalItems = capabilities ? productRoutes(capabilities).map((route) => ({
    href: route.href,
    labelKey: (route.componentId === "matb-liftoff" ? "nav.liftoff" : "nav.mission") as AppTranslationKey,
    icon: route.componentId === "matb-liftoff" ? Gamepad2 : Radar,
    enabled: true,
  })) : [];
  const technicalItems = capabilities && hasComponent(capabilities, "matb-suas") ? [{
    href: "/mission/test",
    labelKey: "nav.tests" as AppTranslationKey,
    icon: Radar,
    enabled: true,
  }] : [];
  const items = [...CORE_ITEMS, ...optionalItems, ...technicalItems];
  return (
    <nav className="flex gap-2 overflow-x-auto p-3 md:flex-col md:overflow-visible md:p-4">
      {items.map(({ href, labelKey, icon: Icon, enabled }, index) => {
        const label = tr(labelKey);
        const active = pathname === href
          || (href === "/mission/setup" && pathname.startsWith("/mission") && !pathname.startsWith("/mission/test"))
          || (href === "/liftoff/setup" && pathname.startsWith("/liftoff"));
        const base = "group flex shrink-0 items-center gap-3 rounded-[3px] border px-3 py-3 text-xs font-semibold uppercase tracking-[0.12em] transition-all";
        if (!enabled)
          return (
            <span
              key={href}
              className={cn(base, "cursor-not-allowed border-white/5 text-muted-foreground/50")}
              title={tr("nav.coming_soon")}
            >
              <span className="font-mono text-[10px] text-muted-foreground/40">
                {String(index + 1).padStart(2, "0")}
              </span>
              <Icon className="h-4 w-4" /> {label}
              <span className="ml-auto font-mono text-[10px] uppercase tracking-wide">{tr("nav.soon")}</span>
            </span>
          );
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              base,
              active
                ? "border-white bg-white text-black shadow-[0_0_40px_rgb(255_255_255/0.14)]"
                : "border-white/10 text-muted-foreground hover:border-white/30 hover:bg-white/[0.04] hover:text-foreground",
            )}
          >
            <span className={cn("font-mono text-[10px]", active ? "text-black/60" : "text-muted-foreground/50")}>
              {String(index + 1).padStart(2, "0")}
            </span>
            <Icon className="h-4 w-4" /> {label}
          </Link>
        );
      })}
    </nav>
  );
}
