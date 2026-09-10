"use client";

import {
  createContext,
  startTransition,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type NavigationRole = "participant" | "researcher";

const STORAGE_KEY = "matb.navigation.role";

function isNavigationRole(value: unknown): value is NavigationRole {
  return value === "participant" || value === "researcher";
}

export function destinationForRole(role: NavigationRole): "/start" | "/tracker" {
  return role === "participant" ? "/start" : "/tracker";
}

export function isRouteActive(pathname: string, href: string): boolean {
  return pathname === href || (href !== "/" && pathname.startsWith(`${href}/`));
}

interface NavigationRoleContextValue {
  role: NavigationRole | null;
  setRole: (role: NavigationRole) => void;
}

const NavigationRoleContext = createContext<NavigationRoleContextValue>({
  role: null,
  setRole: () => undefined,
});

export function NavigationRoleProvider({ children }: { children: ReactNode }) {
  const [role, setRoleState] = useState<NavigationRole | null>(null);

  useEffect(() => {
    try {
      const stored = window.sessionStorage.getItem(STORAGE_KEY);
      if (isNavigationRole(stored)) startTransition(() => setRoleState(stored));
    } catch { /* Workspace navigation still works when tab storage is unavailable. */ }
  }, []);

  const value = useMemo<NavigationRoleContextValue>(() => ({
    role,
    setRole: (nextRole) => {
      try { window.sessionStorage.setItem(STORAGE_KEY, nextRole); } catch { /* Keep this page usable without storage. */ }
      setRoleState(nextRole);
    },
  }), [role]);

  return <NavigationRoleContext.Provider value={value}>{children}</NavigationRoleContext.Provider>;
}

export function useNavigationRole(): NavigationRoleContextValue {
  return useContext(NavigationRoleContext);
}
