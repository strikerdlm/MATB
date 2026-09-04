"use client";

import React, { useCallback, useEffect, useRef, useState } from "react";

import {
  PVT_PROTOCOL_DURATION_MS,
  PVT_RESPONSE_TIMEOUT_MS,
  classifyPvtResponse,
  randomPvtWait,
  type PvtTrial,
} from "@/lib/pvt";
import { useAppLocale } from "@/lib/i18n";

type Phase = "ready" | "waiting" | "stimulus" | "feedback" | "complete";

export function PvtRunner({
  durationMs = PVT_PROTOCOL_DURATION_MS,
  onComplete,
}: {
  durationMs?: number;
  onComplete: (result: { durationMs: number; trials: PvtTrial[] }) => void;
}) {
  const { copy } = useAppLocale();
  const [phase, setPhase] = useState<Phase>("ready");
  const [displayMs, setDisplayMs] = useState(0);
  const [feedback, setFeedback] = useState("");
  const [remainingMs, setRemainingMs] = useState(durationMs);
  const phaseRef = useRef<Phase>("ready");
  const startRef = useRef(0);
  const stimulusRef = useRef<number | null>(null);
  const waitRef = useRef(0);
  const trialsRef = useRef<PvtTrial[]>([]);
  const timerRef = useRef<number | null>(null);
  const completeRef = useRef(false);
  const scheduleRef = useRef<(feedbackMs?: number) => void>(() => undefined);

  const setCurrentPhase = useCallback((value: Phase) => {
    phaseRef.current = value;
    setPhase(value);
  }, []);

  const elapsed = useCallback(() => Math.max(0, performance.now() - startRef.current), []);

  const finish = useCallback(() => {
    if (completeRef.current) return;
    completeRef.current = true;
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
    setCurrentPhase("complete");
    onComplete({ durationMs, trials: [...trialsRef.current] });
  }, [durationMs, onComplete, setCurrentPhase]);

  const scheduleStimulus = useCallback((feedbackMs = 0) => {
    if (completeRef.current) return;
    const waitMs = randomPvtWait();
    waitRef.current = waitMs;
    stimulusRef.current = null;
    setDisplayMs(0);
    const arm = () => {
      if (completeRef.current) return;
      setFeedback("");
      setCurrentPhase("waiting");
      timerRef.current = window.setTimeout(() => {
        if (completeRef.current) return;
        stimulusRef.current = elapsed();
        setCurrentPhase("stimulus");
        timerRef.current = window.setTimeout(() => {
          if (phaseRef.current !== "stimulus" || completeRef.current) return;
          trialsRef.current.push({
            index: trialsRef.current.length,
            wait_ms: waitRef.current,
            stimulus_at_ms: stimulusRef.current,
            response_at_ms: null,
            rt_ms: null,
            outcome: "timeout",
          });
          setFeedback(copy("Sin respuesta", "No response"));
          setCurrentPhase("feedback");
          scheduleRef.current(1_000);
        }, PVT_RESPONSE_TIMEOUT_MS);
      }, Math.max(0, waitMs - feedbackMs));
    };
    if (feedbackMs > 0) timerRef.current = window.setTimeout(arm, feedbackMs);
    else arm();
  }, [copy, elapsed, setCurrentPhase]);
  scheduleRef.current = scheduleStimulus;

  const respond = useCallback(() => {
    if (completeRef.current || phaseRef.current === "ready" || phaseRef.current === "feedback") return;
    const responseAt = elapsed();
    if (phaseRef.current === "waiting" || stimulusRef.current === null) {
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      trialsRef.current.push({
        index: trialsRef.current.length,
        wait_ms: waitRef.current,
        stimulus_at_ms: null,
        response_at_ms: responseAt,
        rt_ms: null,
        outcome: "false_start",
      });
      setFeedback(copy("Demasiado pronto", "Too soon"));
    } else {
      const rtMs = Math.max(0, responseAt - stimulusRef.current);
      if (timerRef.current !== null) window.clearTimeout(timerRef.current);
      const outcome = classifyPvtResponse(rtMs);
      trialsRef.current.push({
        index: trialsRef.current.length,
        wait_ms: waitRef.current,
        stimulus_at_ms: stimulusRef.current,
        response_at_ms: responseAt,
        rt_ms: rtMs,
        outcome,
      });
      setFeedback(outcome === "false_start" ? copy("Demasiado pronto", "Too soon") : `${Math.round(rtMs)} ms`);
    }
    setCurrentPhase("feedback");
    scheduleRef.current(1_000);
  }, [copy, elapsed, setCurrentPhase]);

  function start() {
    startRef.current = performance.now();
    trialsRef.current = [];
    completeRef.current = false;
    scheduleStimulus();
  }

  useEffect(() => {
    if (phase === "ready" || phase === "complete") return;
    const interval = window.setInterval(() => {
      const elapsedMs = elapsed();
      setRemainingMs(Math.max(0, durationMs - elapsedMs));
      if (phaseRef.current === "stimulus" && stimulusRef.current !== null) {
        setDisplayMs(Math.max(0, elapsedMs - stimulusRef.current));
      }
      if (elapsedMs >= durationMs) finish();
    }, 16);
    return () => window.clearInterval(interval);
  }, [durationMs, elapsed, finish, phase]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.repeat) return;
      event.preventDefault();
      respond();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [respond]);

  useEffect(() => () => {
    if (timerRef.current !== null) window.clearTimeout(timerRef.current);
  }, []);

  if (phase === "ready") {
    return (
      <button type="button" onClick={start} className="mx-auto min-h-14 rounded bg-white px-8 py-4 font-display text-lg font-semibold uppercase tracking-wide text-black focus-visible:outline-none focus-visible:ring-4 focus-visible:ring-info">
        {copy("Iniciar PVT de 10 minutos", "Start 10-minute PVT")}
      </button>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col items-center gap-6">
      <div className="font-mono text-xs uppercase tracking-[0.2em] text-muted-foreground" aria-live="polite">
        {copy("Tiempo restante", "Time remaining")} {Math.ceil(remainingMs / 1000)} s
      </div>
      <button
        type="button"
        onPointerDown={respond}
        disabled={phase === "complete"}
        aria-label={copy("Área de respuesta PVT. Presione al ver el contador.", "PVT response area. Press when the counter appears.")}
        className="grid min-h-[360px] w-full touch-manipulation place-items-center rounded-xl border border-white/15 bg-black shadow-[inset_0_0_80px_rgb(255_255_255/0.035)] outline-none focus-visible:ring-4 focus-visible:ring-info"
      >
        {phase === "stimulus" ? (
          <span className="font-mono text-7xl font-bold tabular-nums text-white sm:text-8xl">{Math.round(displayMs)}</span>
        ) : phase === "feedback" ? (
          <span className="font-mono text-3xl font-semibold text-info">{feedback}</span>
        ) : phase === "complete" ? (
          <span className="font-display text-3xl uppercase">{copy("PVT completada", "PVT complete")}</span>
        ) : (
          <span className="sr-only">{copy("Espere el contador", "Wait for the counter")}</span>
        )}
      </button>
      <p className="max-w-2xl text-center text-sm text-muted-foreground">
        {copy("Mantenga un dedo sobre la barra espaciadora o el botón. Responda apenas aparezca el contador; no se anticipe.", "Keep a finger on the space bar or button. Respond as soon as the counter appears; do not anticipate it.")}
      </p>
    </div>
  );
}
