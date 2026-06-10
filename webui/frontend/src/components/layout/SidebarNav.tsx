"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, Users, Upload, BarChart3, FlaskConical, Brain } from "lucide-react";
import { cn } from "@/lib/utils";

const ITEMS = [
  { href: "/", label: "Tracker", icon: LayoutGrid, enabled: true },
  { href: "/participants", label: "Participants", icon: Users, enabled: true },
  { href: "/upload", label: "Upload", icon: Upload, enabled: true },
  { href: "/visualization", label: "Visualization", icon: BarChart3, enabled: true },
  { href: "/analysis", label: "Analysis", icon: FlaskConical, enabled: true },
  { href: "/screen", label: "Screen", icon: Brain, enabled: true },
];

export function SidebarNav() {
  const pathname = usePathname();
  return (
    <nav className="flex gap-2 overflow-x-auto p-3 md:flex-col md:overflow-visible md:p-4">
      {ITEMS.map(({ href, label, icon: Icon, enabled }, index) => {
        const active = pathname === href;
        const base = "group flex shrink-0 items-center gap-3 rounded-[3px] border px-3 py-3 text-xs font-semibold uppercase tracking-[0.12em] transition-all";
        if (!enabled)
          return (
            <span
              key={href}
              className={cn(base, "cursor-not-allowed border-white/5 text-muted-foreground/50")}
              title="Coming soon"
            >
              <span className="font-mono text-[10px] text-muted-foreground/40">
                {String(index + 1).padStart(2, "0")}
              </span>
              <Icon className="h-4 w-4" /> {label}
              <span className="ml-auto font-mono text-[10px] uppercase tracking-wide">soon</span>
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
