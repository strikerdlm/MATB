import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface PageHeaderStat {
  label: string;
  value: ReactNode;
}

interface PageHeaderProps {
  kicker: string;
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  stats?: PageHeaderStat[];
  className?: string;
}

export function PageHeader({
  kicker,
  title,
  description,
  actions,
  stats,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cn(
        "mission-panel animate-telemetry-in px-5 py-5 sm:px-6",
        "flex flex-col gap-5 xl:flex-row xl:items-end xl:justify-between",
        className,
      )}
    >
      <div className="min-w-0 space-y-2">
        <p className="page-kicker">{kicker}</p>
        <h2 className="page-title">{title}</h2>
        {description && (
          <p className="max-w-3xl text-sm leading-6 text-muted-foreground">{description}</p>
        )}
      </div>
      {(actions || stats?.length) && (
        <div className="flex shrink-0 flex-col gap-3 sm:flex-row sm:items-end">
          {stats?.length ? (
            <div className="grid grid-cols-3 gap-2 sm:min-w-[21rem]">
              {stats.map((stat) => (
                <div key={stat.label} className="metric-tile min-w-0">
                  <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                    {stat.label}
                  </p>
                  <p className="mt-1 whitespace-nowrap font-display text-sm font-semibold leading-none text-foreground sm:text-2xl">
                    {stat.value}
                  </p>
                </div>
              ))}
            </div>
          ) : null}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
      )}
    </header>
  );
}
