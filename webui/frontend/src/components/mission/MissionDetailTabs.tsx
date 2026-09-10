"use client";

import React from "react";
import * as Tabs from "@radix-ui/react-tabs";
import type { Locale } from "@/types/simulation";
import { t } from "@/lib/simulation/i18n";

/** Keyboard behavior changes only inside the tab list; task shortcuts stay local. */
export function MissionDetailTabs({ locale, modern, alerts, contacts }: {
  locale: Locale; modern: boolean; alerts: React.ReactNode; contacts: React.ReactNode;
}) {
  return <Tabs.Root defaultValue="alerts" activationMode="manual" className="mission-panel flex min-h-[15rem] flex-1 flex-col">
    <Tabs.List className="grid grid-cols-2 border-b border-white/10" aria-label={t(locale, "mission.detail_views")}>
      {(["alerts", "contacts"] as const).map(value => <Tabs.Trigger key={value} value={value} id={`mission-${value}-tab`} className={`border-b-2 border-transparent px-3 font-mono text-muted-foreground data-[state=active]:border-white data-[state=active]:text-foreground ${modern ? "h-[41px] text-sm normal-case" : "py-3 text-[10px] uppercase tracking-wider"}`}>{t(locale, `mission.${value}`)}</Tabs.Trigger>)}
    </Tabs.List>
    <Tabs.Content value="alerts" aria-labelledby="mission-alerts-tab" className="min-h-0 flex-1">{alerts}</Tabs.Content>
    <Tabs.Content value="contacts" aria-labelledby="mission-contacts-tab" className="min-h-0 flex-1">{contacts}</Tabs.Content>
  </Tabs.Root>;
}
