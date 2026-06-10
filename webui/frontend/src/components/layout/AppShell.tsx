import { SidebarNav } from "@/components/layout/SidebarNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground md:flex-row">
      <aside className="w-full shrink-0 border-b border-border bg-card/95 md:w-60 md:border-b-0 md:border-r">
        <div className="border-b border-border px-4 py-4 md:py-5">
          <h1 className="font-serif text-sm font-semibold tracking-tight">MATB Research Console</h1>
          <p className="text-xs uppercase tracking-[0.14em] text-muted-foreground">Longitudinal lab</p>
        </div>
        <SidebarNav />
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 md:py-8">{children}</div>
      </main>
    </div>
  );
}
