"use client";
import { useEffect, useState } from "react";
import { getApiBase } from "@/lib/runtime-config";
import { useAppLocale } from "@/lib/i18n";
import type { CatalogEntry } from "@/lib/experiments";

const checks: Record<string, [string, string]> = {
  python: ["Python compatible", "Compatible Python"],
  runtime_dependencies: ["Dependencias nativas", "Native dependencies"],
  openmatb: ["Aplicación OpenMATB", "OpenMATB application"],
  questionnaires_es: ["Cuestionarios en español", "Spanish questionnaires"],
  graphical_display: ["Pantalla gráfica", "Graphical display"],
};
export function ReadinessNote({ entry }: { entry: CatalogEntry }) {
  const { copy } = useAppLocale();
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setResult(null); setFailed(false);
    if (!entry.component_available || !entry.readiness_url) return;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    let active = true;
    void getApiBase().then((base) => fetch(base + entry.readiness_url, { signal: controller.signal }))
      .then(async (response) => { if (!response.ok) throw new Error("readiness"); return response.json(); })
      .then((data: Record<string, unknown>) => { if (active) setResult(data); })
      .catch(() => { if (active) setFailed(true); }).finally(() => clearTimeout(timeout));
    return () => { active = false; controller.abort(); clearTimeout(timeout); };
  }, [entry.component_available, entry.readiness_url]);
  if (!entry.component_available || !entry.readiness_url) return null;
  const missing = result?.checks && typeof result.checks === "object"
    ? Object.entries(result.checks).filter(([, ok]) => ok === false).map(([key]) => checks[key] ? copy(...checks[key]) : key.replaceAll("_", " ")) : [];
  const ready = result?.ready === true || result?.connected === true;
  return <div role="status" className="mt-4 rounded border border-white/15 p-4 text-sm">
    {failed ? copy("No se pudieron comprobar los requisitos. Abra Preparar y vuelva a comprobar la conexión.", "Requirements could not be checked. Open Prepare and check the connection again.")
      : !result ? copy("Comprobando los requisitos de esta actividad…", "Checking this activity’s requirements…")
      : ready ? copy("El componente responde. Confirme el equipo al preparar la sesión.", "The component is responding. Confirm the equipment when preparing the session.")
      : missing.length ? copy("Falta: ", "Missing: ") + missing.join(", ")
      : entry.id === "physiology" ? copy("Falta conectar el Polar H10. Abra Preparar para buscarlo y conectarlo.", "Polar H10 is not connected. Open Prepare to find and connect it.")
      : copy("No se recibe telemetría de Liftoff. Abra el simulador y siga la preparación.", "No Liftoff telemetry is arriving. Open the simulator and follow the preparation steps.")}
  </div>;
}
