import { SidebarNav } from "@/components/layout/SidebarNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen bg-background text-foreground">
      <aside className="w-60 shrink-0 border-r border-border bg-card/95">
        <div className="px-4 py-5 border-b border-border">
          <h1 className="font-serif text-sm font-semibold tracking-tight">MATB Research Console</h1>
          <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Longitudinal lab</p>
        </div>
        <SidebarNav />
      </aside>
      <main className="flex-1 overflow-auto">
        <div className="mx-auto max-w-7xl px-6 py-8">{children}</div>
      </main>
    </div>
  );
}
