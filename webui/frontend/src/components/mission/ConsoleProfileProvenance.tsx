import React from "react";
import { consoleProfileStatus } from "@/lib/simulation/console-profile";
import type { ConsoleProfile, Locale } from "@/types/simulation";

export function ConsoleProfileProvenance({ profile, locale }: { profile: unknown; locale: Locale }) {
  const status = consoleProfileStatus(profile);
  const es = locale === "es-CO";
  const identity = profile && typeof profile === "object" ? profile as Partial<ConsoleProfile> : null;
  return <div className="text-sm" role={status === "unsupported" ? "alert" : "note"} data-console-profile={status}>
    {status === "legacy" ? (es ? "Consola histórica: sin perfil registrado." : "Historical console: no recorded profile.")
      : status === "supported" ? (es ? "Perfil de consola registrado compatible." : "Recorded console profile supported.")
        : (es ? "Perfil de consola desconocido o incompatible; apariencia registrada sin verificar." : "Unknown or mismatched console profile; recorded appearance unverified.")}
    {identity && <span className="block break-all font-mono">{String(identity.id ?? "?")} · v{String(identity.version ?? "?")} · SHA-256 {String(identity.sha256 ?? "?")}</span>}
  </div>;
}
