"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { getApiBase } from "@/lib/runtime-config";
import type { CatalogEntry } from "@/lib/experiments";

interface ConsoleState { catalog: CatalogEntry[]; status: "checking" | "online" | "offline"; refresh: () => void; }
const Context = createContext<ConsoleState>({ catalog: [], status: "checking", refresh: () => undefined });
export function ConsoleProvider({ children }: { children: ReactNode }) {
  const [catalog, setCatalog] = useState<CatalogEntry[]>([]);
  const [status, setStatus] = useState<ConsoleState["status"]>("checking");
  const [revision, setRevision] = useState(0);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);
  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let active = true;
    void getApiBase().then((base) => fetch(`${base}/experiments/catalog`, { signal: controller.signal }))
      .then(async (response) => {
        if (!response.ok) throw new Error("catalog_unavailable");
        const result = await response.json() as { experiments: CatalogEntry[] };
        if (active) { setCatalog(result.experiments); setStatus("online"); }
      }).catch(() => { if (active) setStatus("offline"); })
      .finally(() => clearTimeout(timeout));
    return () => { active = false; clearTimeout(timeout); controller.abort(); };
  }, [revision]);
  useEffect(() => {
    const interval = setInterval(() => { if (!document.hidden) refresh(); }, 30000);
    const visible = () => { if (!document.hidden) refresh(); };
    document.addEventListener("visibilitychange", visible);
    return () => { clearInterval(interval); document.removeEventListener("visibilitychange", visible); };
  }, [refresh]);
  return <Context.Provider value={{ catalog, status, refresh }}>{children}</Context.Provider>;
}
export const useConsole = () => useContext(Context);
