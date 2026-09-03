"use client";

import { Plus, ShieldCheck } from "lucide-react";
import React, { useMemo, useRef, useState } from "react";

import { ConstraintLedger } from "@/components/experiments/ConstraintLedger";
import { EventInspector } from "@/components/experiments/EventInspector";
import { ExperimentTimeline } from "@/components/experiments/ExperimentTimeline";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { compileExperiment } from "@/lib/api";
import {
  buildExperimentSpec,
  formatTimelineTime,
  INITIAL_EXPERIMENT_EVENTS,
  MAX_EXPERIMENT_DURATION_SECONDS,
  MAX_SAFE_EXPERIMENT_SEED,
  summarizeExperiment,
  validateTimeline,
} from "@/lib/experiment-designer";
import type { CompiledExperiment, ExperimentTimelineEvent } from "@/types";
import { useAppLocale } from "@/lib/i18n";

function nextEventKey(events: ExperimentTimelineEvent[]): string {
  let sequence = events.length + 1;
  while (events.some((event) => event.eventKey === `event-${sequence}`)) sequence += 1;
  return `event-${sequence}`;
}

function HashRow({ label, value }: { label: string; value: string | null }) {
  const { copy } = useAppLocale();
  return (
    <div className="grid gap-2 border-t border-white/10 px-4 py-3 sm:grid-cols-[10rem_1fr] sm:items-center">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{label}</span>
      <code className="min-w-0 break-all bg-black/40 px-3 py-2 font-mono text-[10px] text-foreground">
        {value ?? copy("Compile para materializar", "Compile to materialize")}
      </code>
    </div>
  );
}

export function ExperimentDesigner() {
  const { copy } = useAppLocale();
  const [events, setEvents] = useState<ExperimentTimelineEvent[]>(() => (
    INITIAL_EXPERIMENT_EVENTS.map((event) => ({ ...event }))
  ));
  const [durationSeconds, setDurationSeconds] = useState(60);
  const [seed, setSeed] = useState(42);
  const [selectedKey, setSelectedKey] = useState<string | null>("sysmon-nontarget-1");
  const [compiled, setCompiled] = useState<CompiledExperiment | null>(null);
  const [compileError, setCompileError] = useState<string | null>(null);
  const [isCompiling, setIsCompiling] = useState(false);
  const designRevision = useRef(0);
  const compileRequest = useRef(0);

  const summary = useMemo(
    () => summarizeExperiment(events, durationSeconds),
    [durationSeconds, events],
  );
  const constraints = useMemo(
    () => validateTimeline(events, durationSeconds, seed),
    [durationSeconds, events, seed],
  );
  const selected = events.find((event) => event.eventKey === selectedKey) ?? null;
  const hasFailure = constraints.some((constraint) => constraint.status === "fail");

  const invalidateCompiledDesign = () => {
    designRevision.current += 1;
    setCompiled(null);
    setCompileError(null);
  };

  const addEvent = () => {
    const created: ExperimentTimelineEvent = {
      eventKey: nextEventKey(events),
      atSeconds: Math.min(durationSeconds - 1, 30),
      durationSeconds: 2,
      task: "sysmon",
      command: "open_nontarget_opportunity",
    };
    setEvents((current) => [...current, created]);
    setSelectedKey(created.eventKey);
    invalidateCompiledDesign();
  };

  const updateEvent = (updated: ExperimentTimelineEvent) => {
    setEvents((current) => current.map((event) => (
      event.eventKey === updated.eventKey ? updated : event
    )));
    invalidateCompiledDesign();
  };

  const removeEvent = (eventKey: string) => {
    setEvents((current) => current.filter((event) => event.eventKey !== eventKey));
    setSelectedKey(null);
    invalidateCompiledDesign();
  };

  const compile = async () => {
    const requestId = compileRequest.current + 1;
    compileRequest.current = requestId;
    const requestedRevision = designRevision.current;
    setCompileError(null);
    setIsCompiling(true);
    try {
      const result = await compileExperiment(buildExperimentSpec(events, durationSeconds, seed));
      if (compileRequest.current !== requestId) return;
      if (designRevision.current !== requestedRevision) {
        setCompiled(null);
        setCompileError(copy("El diseño cambió durante la compilación; vuelva a compilar.", "Design changed during compilation; compile again."));
        return;
      }
      setCompiled(result);
    } catch (error) {
      if (compileRequest.current !== requestId) return;
      setCompiled(null);
      setCompileError(
        designRevision.current !== requestedRevision
          ? copy("El diseño cambió durante la compilación; vuelva a compilar.", "Design changed during compilation; compile again.")
          : error instanceof Error
            ? error.message
            : copy("Falló la compilación del experimento", "Experiment compilation failed"),
      );
    } finally {
      if (compileRequest.current === requestId) setIsCompiling(false);
    }
  };

  return (
    <div className="space-y-5 animate-telemetry-in">
      <header className="border border-white/15 bg-black/35">
        <div className="flex flex-col gap-5 px-5 py-5 xl:flex-row xl:items-start xl:justify-between">
          <div>
            <h2 className="font-display text-3xl font-semibold leading-none text-white sm:text-4xl">
              {copy("Diseñador de experimentos", "Experiment Designer")}
            </h2>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-muted-foreground">
              {copy("Construya una especificación canónica del experimento, inspeccione la demanda de las tareas y compile únicamente eventos OpenMATB sin pérdida.", "Build a canonical experiment specification, inspect task demand, and compile only lossless OpenMATB events.")}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button type="button" variant="outline" onClick={addEvent}>
              <Plus className="mr-2 h-4 w-4" /> {copy("Agregar evento", "Add event")}
            </Button>
            <Button type="button" variant="destructive" disabled={hasFailure} onClick={() => void compile()}>
              <ShieldCheck className="mr-2 h-4 w-4" />
              {isCompiling ? copy("Compilando la versión actual…", "Compile latest…") : copy("Compilar y validar", "Compile & validate")}
            </Button>
          </div>
        </div>
        <div className="grid border-t border-white/15 sm:grid-cols-2 xl:grid-cols-4">
          {[
            [copy("Duración", "Duration"), formatTimelineTime(durationSeconds)],
            [copy("Tasa de estímulos/oportunidades/min", "Stimulus/opportunity rate/min"), summary.stimulusOpportunityRatePerMinute.toFixed(1)],
            [copy("Tasa de comandos fuente/min", "Source command rate/min"), summary.sourceCommandRatePerMinute.toFixed(1)],
            [copy("Oportunidades SYSMON", "SYSMON opportunities"), `${summary.sysmonNontargetOpportunities} N / ${summary.sysmonTargetOpportunities} T`],
            [copy("Superposición de eventos", "Event overlap"), `${summary.overlapCount} (${summary.overlapPercent.toFixed(1)}%)`],
          ].map(([label, value]) => (
            <div key={label} className="border-b border-white/10 px-5 py-4 sm:border-r xl:border-b-0 last:border-r-0">
              <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{label}</p>
              <p className="mt-2 font-display text-2xl font-semibold text-white">{value}</p>
            </div>
          ))}
        </div>
      </header>

      <section className="grid gap-3 border border-white/15 bg-black/30 p-4 sm:grid-cols-2 xl:grid-cols-4" aria-label={copy("Configuración del experimento", "Experiment settings")}>
        <div className="space-y-2">
          <label htmlFor="experiment-duration" className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{copy("Duración (segundos)", "Duration (seconds)")}</label>
          <Input id="experiment-duration" type="number" min={10} max={MAX_EXPERIMENT_DURATION_SECONDS} step={1} value={durationSeconds} onChange={(event) => { setDurationSeconds(Number(event.target.value)); invalidateCompiledDesign(); }} />
        </div>
        <div className="space-y-2">
          <label htmlFor="experiment-seed" className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{copy("Semilla determinista", "Deterministic seed")}</label>
          <Input id="experiment-seed" type="number" min={0} max={MAX_SAFE_EXPERIMENT_SEED} step={1} value={seed} onChange={(event) => { setSeed(Number(event.target.value)); invalidateCompiledDesign(); }} />
        </div>
        <div className="xl:col-span-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">{copy("Límite científico", "Scientific boundary")}</p>
          <p className="mt-2 text-sm leading-6 text-muted-foreground">
            {copy("LOW / MEDIUM / HIGH permanecen como preajustes de ingeniería hasta que la evidencia de calibración humana se apruebe de forma independiente.", "LOW / MEDIUM / HIGH remain engineering presets until human calibration evidence passes independently.")}
          </p>
        </div>
      </section>

      <div className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_19rem]">
        <ExperimentTimeline
          events={events}
          durationSeconds={durationSeconds}
          selectedKey={selectedKey}
          onSelect={setSelectedKey}
        />
        <EventInspector event={selected} onChange={updateEvent} onRemove={removeEvent} />
      </div>

      {compileError ? (
        <p role="alert" className="border border-danger/50 bg-danger/10 px-4 py-3 text-sm text-danger">{compileError}</p>
      ) : null}

      <div className="grid gap-4 xl:grid-cols-[1fr_1.1fr]">
        <ConstraintLedger constraints={constraints} />
        <section className="border border-white/15 bg-black/30" aria-labelledby="provenance-title">
          <div className="border-b border-white/15 px-4 py-3">
            <h3 id="provenance-title" className="font-display text-sm font-semibold uppercase tracking-[0.08em]">{copy("Procedencia", "Provenance")}</h3>
          </div>
          <HashRow label="Spec SHA-256" value={compiled?.manifest.spec.sha256 ?? null} />
          <HashRow label="Scenario SHA-256" value={compiled?.manifest.scenario.sha256 ?? null} />
          <HashRow label={copy("Commit fuente", "Source commit")} value={compiled?.manifest.source_commit ?? null} />
          <HashRow label={copy("Árbol fuente", "Source tree")} value={compiled ? (compiled.manifest.source_dirty === null ? copy("no verificado", "unverified") : compiled.manifest.source_dirty ? copy("con cambios", "dirty") : copy("limpio", "clean")) : null} />
          <HashRow label={copy("Estado de procedencia", "Provenance status")} value={compiled?.manifest.provenance_status ?? null} />
          {compiled && compiled.manifest.provenance_status !== "complete" ? (
            <p role="status" className="border-t border-warning/40 bg-warning/10 px-4 py-3 text-xs leading-5 text-warning">
              {copy("Artefacto provisional: la procedencia de la fuente está incompleta. No trate esta vista previa como un registro de versión.", "Provisional artifact: source provenance is incomplete. Do not treat this preview as a release record.")}
            </p>
          ) : null}
          <div className="border-t border-white/10 px-4 py-3 text-xs leading-5 text-muted-foreground">
            {compiled?.manifest.claim_boundary ?? copy("La compilación materializa hashes; nunca eleva la calidad de la evidencia empírica.", "Compilation materializes hashes; it never upgrades empirical evidence.")}
          </div>
        </section>
      </div>

      {compiled ? (
        <details className="border border-white/15 bg-black/30">
          <summary className="cursor-pointer px-4 py-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
            {copy("Escenario OpenMATB compilado", "Compiled OpenMATB scenario")}
          </summary>
          <pre className="max-h-80 overflow-auto border-t border-white/10 p-4 font-mono text-[11px] leading-5 text-foreground">
            {compiled.scenario_text}
          </pre>
        </details>
      ) : null}
    </div>
  );
}
