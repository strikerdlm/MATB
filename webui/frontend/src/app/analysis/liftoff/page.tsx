"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/button";
import { getApiBase } from "@/lib/runtime-config";
import { useAppLocale } from "@/lib/i18n";

interface Analysis { status: string; analysis_version: string; continuous: Record<string, { status: string; n_participants?: number; n_observations?: number }>; counts: Record<string, unknown>; }
export default function LiftoffAnalysisPage() {
  const { copy } = useAppLocale();
  const [result, setResult] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  async function run() {
    controller.current?.abort();
    const pending = new AbortController(); controller.current = pending;
    setBusy(true); setError(false);
    try {
      const response = await fetch((await getApiBase()) + "/analysis/liftoff/run", { method: "POST", signal: pending.signal });
      if (!response.ok) throw new Error("analysis_unavailable");
      setResult(await response.json());
    } catch { if (!pending.signal.aborted) setError(true); }
    finally { if (!pending.signal.aborted) setBusy(false); }
  }
  return <div className="space-y-6">
    <PageHeader kicker={copy("Herramientas del investigador", "Researcher tools")} title={copy("Análisis de Liftoff", "Liftoff analysis")} description={copy("Resultados de vuelo por visita con el modelo estadístico registrado. Las prácticas se excluyen; las familias de experimentos se analizan por separado.", "Flight outcomes by visit using the registered statistical model. Practice is excluded; experiment families are analyzed separately.")} />
    <div className="flex flex-wrap gap-4"><Button onClick={() => void run()} disabled={busy}>{busy ? copy("Calculando…", "Calculating…") : copy("Calcular análisis de Liftoff", "Run Liftoff analysis")}</Button><Link className="self-center underline" href="/analysis">{copy("Análisis de OpenMATB", "OpenMATB analysis")}</Link></div>
    {error && <p role="alert">{copy("No se pudo calcular. Compruebe que Liftoff esté habilitado y que la consola esté conectada.", "Could not calculate. Check that Liftoff is enabled and the console is connected.")}</p>}
    {result && <section className="space-y-4"><p role="status">{result.status === "insufficient_data" ? copy("Datos insuficientes: se requieren al menos tres participantes con dos visitas elegibles cada uno.", "Insufficient data: at least three participants with two eligible visits each are required.") : copy("Análisis calculado. Revise elegibilidad, datos faltantes y convergencia de cada modelo antes de interpretar.", "Analysis calculated. Review eligibility, missing data, and convergence for each model before interpreting.")}</p>
      <details className="rounded border border-white/15 p-4"><summary>{copy("Modelos, estimaciones y comprobaciones", "Models, estimates, and checks")} · {result.analysis_version}</summary><pre className="mt-4 overflow-auto text-xs">{JSON.stringify(result, null, 2)}</pre></details>
    </section>}
  </div>;
}
