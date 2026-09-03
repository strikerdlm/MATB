"use client";

import { Suspense, useCallback, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { Check, Monitor, Send } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAppLocale } from "@/lib/i18n";
import { acknowledgeOpenMatbInstructions, getOpenMatbSession, readOpenMatbParticipant, submitOpenMatbScales } from "@/lib/openmatb/api";
import type { OpenMatbSession, WorkloadScaleSubmission } from "@/types/openmatb";

const TLX = [
  ["mental_demand", "Demanda mental", "Baja", "Alta"],
  ["physical_demand", "Demanda física", "Baja", "Alta"],
  ["temporal_demand", "Demanda temporal", "Baja", "Alta"],
  ["performance", "Rendimiento", "Bueno", "Deficiente"],
  ["effort", "Esfuerzo", "Bajo", "Alto"],
  ["frustration", "Frustración", "Baja", "Alta"],
] as const;

const BEDFORD = [
  "Carga insignificante.",
  "Carga baja.",
  "Capacidad sobrante suficiente para todas las tareas adicionales deseables.",
  "Capacidad sobrante insuficiente para atender fácilmente tareas adicionales.",
  "Capacidad sobrante reducida; las tareas adicionales no reciben la atención deseada.",
  "Poca capacidad sobrante; el esfuerzo permite poca atención a tareas adicionales.",
  "Muy poca capacidad sobrante, pero se puede mantener el esfuerzo en las tareas principales.",
  "Carga muy alta, casi sin capacidad sobrante; es difícil mantener el esfuerzo.",
  "Carga extremadamente alta, sin capacidad sobrante; existen dudas serias sobre mantener el esfuerzo.",
  "Tareas abandonadas; no fue posible aplicar esfuerzo suficiente.",
];

function ParticipantContent() {
  const params = useSearchParams();
  const { copy } = useAppLocale();
  const id = params.get("session");
  const [token, setToken] = useState<string | null>(null);
  const [session, setSession] = useState<OpenMatbSession | null>(null);
  const [tlx, setTlx] = useState<Record<string, number>>({});
  const [bedford, setBedford] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    const fragment = new URLSearchParams(window.location.hash.replace(/^#/, ""));
    const supplied = fragment.get("token") ?? readOpenMatbParticipant(id);
    if (supplied) { sessionStorage.setItem(`openmatb.participant.${id}`, supplied); setToken(supplied); history.replaceState(null, "", window.location.pathname + window.location.search); }
  }, [id]);

  const refresh = useCallback(async () => { if (!id) return; try { setSession(await getOpenMatbSession(id)); } catch (reason) { setError(reason instanceof Error ? reason.message : copy("No se pudo consultar la sesión.", "Session could not be loaded.")); } }, [copy, id]);
  useEffect(() => { void refresh(); const timer = window.setInterval(() => void refresh(), 1000); return () => window.clearInterval(timer); }, [refresh]);
  useEffect(() => { setTlx({}); setBedford(null); }, [session?.active_block]);

  const scaleComplete = useMemo(() => TLX.every(([key]) => typeof tlx[key] === "number") && bedford !== null, [bedford, tlx]);

  async function acknowledge() {
    if (!id || !token) return;
    setBusy(true); setError(null);
    try { setSession(await acknowledgeOpenMatbInstructions(id, token)); } catch (reason) { setError(reason instanceof Error ? reason.message : copy("No se pudo confirmar.", "Acknowledgement failed.")); } finally { setBusy(false); }
  }

  async function submit() {
    if (!id || !token || !scaleComplete || bedford === null) return;
    setBusy(true); setError(null);
    try { setSession(await submitOpenMatbScales(id, token, { nasa_tlx: tlx as WorkloadScaleSubmission["nasa_tlx"], bedford })); } catch (reason) { setError(reason instanceof Error ? reason.message : copy("No se pudieron guardar las escalas.", "Scales could not be saved.")); } finally { setBusy(false); }
  }

  if (!session) return <main className="grid min-h-screen place-items-center bg-background p-8 text-muted-foreground">{error ?? copy("Cargando…", "Loading…")}</main>;

  return <main className="min-h-screen bg-background p-5 sm:p-8"><div className="mx-auto max-w-5xl space-y-6">
    <header className="border-b border-white/15 pb-5"><div className="font-mono text-xs uppercase tracking-[0.18em] text-muted-foreground">MATB-FAC · {session.visit_code} · {session.participant_id}</div><h1 className="mt-2 font-display text-3xl font-semibold uppercase tracking-wide">{session.lifecycle === "INSTRUCTIONS" ? session.instruction_protocol.title : session.lifecycle === "AWAITING_SCALE" ? "Carga de trabajo percibida" : "Sesión MATB-FAC"}</h1></header>
    {error && <p role="alert" className="border border-danger/40 bg-danger/10 p-3 text-danger">{error}</p>}

    {session.lifecycle === "INSTRUCTIONS" && <section className="space-y-6"><div className="border border-info/40 bg-info/5 p-4"><div className="font-mono text-xs uppercase text-info">{session.visit_code} · Día {session.scheduled_day}</div><p className="mt-2 text-lg leading-7">{session.visit_instruction}</p></div><ol className="space-y-3">{session.instruction_protocol.steps.map((step, index) => <li key={`${index}-${step}`} className="flex gap-4 border-b border-white/10 pb-3"><span className="font-mono text-sm text-info">{String(index + 1).padStart(2, "0")}</span><span className="text-lg leading-7">{step}</span></li>)}</ol><div className="grid gap-3 sm:grid-cols-2">{Object.entries(session.instruction_protocol.task_instructions).map(([task, text]) => <div key={task} className="mission-panel p-4"><h2 className="font-display text-xl font-semibold">{task}</h2><p className="mt-2 text-sm leading-6 text-muted-foreground">{text}</p></div>)}</div><Button size="lg" disabled={!token || busy} onClick={() => void acknowledge()}><Check className="mr-2 h-4 w-4" />He leído y comprendido las instrucciones</Button></section>}

    {["READY", "BETWEEN_BLOCKS"].includes(session.lifecycle) && <section className="grid min-h-[45vh] place-items-center text-center"><div><Monitor className="mx-auto h-12 w-12 text-info" /><h2 className="mt-5 font-display text-3xl uppercase">Listo para continuar</h2><p className="mt-3 text-muted-foreground">Espere la indicación del investigador. El siguiente bloque se abrirá en esta pantalla.</p></div></section>}
    {["STARTING", "RUNNING", "PAUSED"].includes(session.lifecycle) && <section className="grid min-h-[45vh] place-items-center text-center"><div><Monitor className="mx-auto h-12 w-12 text-success" /><h2 className="mt-5 font-display text-3xl uppercase">OpenMATB {session.lifecycle === "PAUSED" ? "en pausa" : "en ejecución"}</h2><p className="mt-3 text-muted-foreground">Utilice únicamente los controles de la tarea. Esta pantalla volverá al terminar el bloque.</p></div></section>}

    {session.lifecycle === "AWAITING_SCALE" && <section className="space-y-8"><div><h2 className="font-display text-2xl uppercase">NASA-TLX</h2><p className="mt-2 text-sm text-muted-foreground">Califique cada dimensión de 0 a 100. Esta es la medida principal de carga percibida.</p></div><div className="grid gap-5 sm:grid-cols-2">{TLX.map(([key, label, low, high]) => <label key={key} className="mission-panel block p-4"><span className="font-semibold">{label}</span><input aria-label={label} className="mt-4 w-full accent-white" type="range" min={0} max={100} step={5} value={tlx[key] ?? 50} onChange={(event) => setTlx((current) => ({ ...current, [key]: Number(event.target.value) }))} /><span className="mt-2 flex justify-between font-mono text-xs text-muted-foreground"><span>{low}</span><strong className="text-lg text-foreground">{tlx[key] ?? "—"}</strong><span>{high}</span></span></label>)}</div><fieldset><legend className="font-display text-2xl uppercase">Bedford</legend><p className="mt-2 text-sm text-warning">Medida secundaria exploratoria; traducción no validada localmente.</p><div className="mt-4 grid gap-2">{BEDFORD.map((text, index) => { const value = index + 1; return <label key={value} className="flex cursor-pointer gap-3 border border-white/10 p-3 hover:border-white/40"><input type="radio" name="bedford" value={value} checked={bedford === value} onChange={() => setBedford(value)} /><strong className="w-6 font-mono">{value}</strong><span>{text}</span></label>; })}</div></fieldset><Button size="lg" disabled={!token || busy || !scaleComplete} onClick={() => void submit()}><Send className="mr-2 h-4 w-4" />Guardar escalas y continuar</Button></section>}

    {session.lifecycle === "COMPLETE" && <section className="grid min-h-[45vh] place-items-center text-center"><div><Check className="mx-auto h-14 w-14 text-success" /><h2 className="mt-5 font-display text-4xl uppercase">Visita completada</h2><p className="mt-3 text-muted-foreground">Las respuestas y los archivos de la sesión quedaron guardados. Avise al investigador.</p></div></section>}
    {["ABORTED", "FAILED", "INTERRUPTED"].includes(session.lifecycle) && <section className="grid min-h-[45vh] place-items-center text-center"><div><h2 className="font-display text-3xl uppercase text-warning">Sesión detenida</h2><p className="mt-3 text-muted-foreground">Avise al investigador y no cierre esta ventana hasta recibir indicaciones.</p></div></section>}
  </div></main>;
}

export default function OpenMatbParticipantPage() {
  return <Suspense fallback={<main className="grid min-h-screen place-items-center bg-background">Cargando…</main>}><ParticipantContent /></Suspense>;
}
