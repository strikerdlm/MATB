import { SidebarNav } from "@/components/layout/SidebarNav";

export function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mission-grid flex min-h-screen flex-col text-foreground md:flex-row">
      <aside className="relative z-10 w-full shrink-0 border-b border-white/10 bg-black/75 backdrop-blur md:min-h-screen md:w-72 md:border-b-0 md:border-r">
        <div className="border-b border-white/10 px-5 py-5 md:py-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
                Research console
              </p>
              <h1 className="mt-2 font-display text-3xl font-semibold uppercase leading-none text-white">
                MATB
              </h1>
            </div>
            <div className="mt-1 h-9 w-9 border border-white/20 bg-white text-center font-display text-xl font-semibold leading-9 text-black">
              M
            </div>
          </div>
          <div className="mt-5 grid grid-cols-2 gap-2 font-mono text-[10px] uppercase tracking-[0.16em]">
            <div className="border border-white/10 px-2 py-2 text-muted-foreground">
              Mode
              <span className="mt-1 block text-foreground">Ops</span>
            </div>
            <div className="border border-white/10 px-2 py-2 text-muted-foreground">
              Link
              <span className="mt-1 inline-flex items-center gap-1.5 text-success">
                <span className="h-1.5 w-1.5 rounded-full bg-success" />
                Live
              </span>
            </div>
          </div>
        </div>
        <SidebarNav />
        <div className="hidden px-5 pb-6 pt-3 md:block">
          <div className="signal-sweep h-px bg-white/10" />
          <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
            Longitudinal human performance lab
          </p>
        </div>
      </aside>
      <main className="relative min-w-0 flex-1 overflow-auto">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/20" />
        <div className="mx-auto max-w-[92rem] px-4 py-5 sm:px-6 md:px-8 md:py-8">{children}</div>
      </main>
    </div>
  );
}
