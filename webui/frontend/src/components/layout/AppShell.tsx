"use client";

import { SidebarNav } from "@/components/layout/SidebarNav";
import { useAppLocale, type AppLocale } from "@/lib/i18n";
import { useConsole } from "@/lib/console-context";

export function AppShell({ children }: { children: React.ReactNode }) {
  const { locale, setLocale, tr, copy } = useAppLocale();
  const { status } = useConsole();
  return (
    <div className="mission-grid flex min-h-screen flex-col text-foreground md:flex-row">
      <aside className="relative z-10 w-full shrink-0 border-b border-white/10 bg-black/75 backdrop-blur md:min-h-screen md:w-72 md:border-b-0 md:border-r">
        <div className="border-b border-white/10 px-5 py-5 md:py-7">
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-muted-foreground">
                {tr("brand.console")}
              </p>
              <h1 className="mt-2 font-display text-3xl font-semibold uppercase leading-none text-white">
                MATB-FAC
              </h1>
            </div>
            <div className="mt-1 h-9 w-9 border border-white/20 bg-white text-center font-display text-xl font-semibold leading-9 text-black">
              M
            </div>
          </div>
          <div className="mt-5 hidden grid-cols-2 gap-2 md:grid font-mono text-[10px] uppercase tracking-[0.16em]">
            <div className="border border-white/10 px-2 py-2 text-muted-foreground">
              {tr("shell.mode")}
              <span className="mt-1 block text-foreground">{tr("shell.operations")}</span>
            </div>
            <div className="border border-white/10 px-2 py-2 text-muted-foreground">
              {tr("shell.link")}
              <span role="status" className={"mt-1 inline-flex items-center gap-1.5 " + (status === "online" ? "text-success" : "text-warning")}>
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
                {status === "online" ? copy("Conectado", "Connected") : status === "checking" ? copy("Comprobando", "Checking") : copy("Sin conexión", "Offline")}
              </span>
            </div>
          </div>
        </div>
        <div className="hidden md:block"><SidebarNav /></div>
        <details className="border-b border-white/10 md:hidden"><summary className="cursor-pointer px-5 py-3 text-sm font-semibold">{copy("Menú de experimentos", "Experiment menu")}</summary><SidebarNav /></details>
        <div className="px-5 pb-6 pt-3">
          <div className="signal-sweep hidden h-px md:block bg-white/10" />
          <p className="mt-4 hidden font-mono text-[10px] md:block uppercase tracking-[0.18em] text-muted-foreground">
            {tr("brand.lab")}
          </p>
          <p className="mt-2 hidden text-[10px] leading-4 md:block text-muted-foreground">{tr("brand.author")}</p>
          <label htmlFor="app-language" className="mt-1 block font-mono md:mt-5 text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
            {tr("language.label")}
          </label>
          <select
            id="app-language"
            value={locale}
            onChange={(event) => setLocale(event.target.value as AppLocale)}
            className="native-select mt-2 w-full"
          >
            <option value="es-419">{tr("language.spanish")}</option>
            <option value="en">{tr("language.english")}</option>
          </select>
        </div>
      </aside>
      <main className="relative min-w-0 flex-1 overflow-auto">
        <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-white/20" />
        <div className="mx-auto max-w-[92rem] px-4 py-5 sm:px-6 md:px-8 md:py-8">{children}</div>
      </main>
    </div>
  );
}
