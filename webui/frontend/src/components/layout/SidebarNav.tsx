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
    <nav className="flex gap-1 overflow-x-auto p-3 md:flex-col md:overflow-visible">
      {ITEMS.map(({ href, label, icon: Icon, enabled }) => {
        const active = pathname === href;
        const base = "flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors";
        if (!enabled)
          return (
            <span key={href} className={cn(base, "cursor-not-allowed text-muted-foreground/50")} title="Coming soon">
              <Icon className="h-4 w-4" /> {label}
              <span className="ml-auto text-[10px] uppercase tracking-wide">soon</span>
            </span>
          );
        return (
          <Link key={href} href={href}
            className={cn(base, active ? "bg-primary text-primary-foreground" : "text-foreground hover:bg-accent hover:text-accent-foreground")}>
            <Icon className="h-4 w-4" /> {label}
          </Link>
        );
      })}
    </nav>
  );
}
