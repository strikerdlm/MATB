// Author: Dr Diego Malpica MD
"use client";

import { ArrowLeft, ArrowRight } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useScreenStrings } from "@/components/screen/strings";
import { Button } from "@/components/ui/button";
import { genChoiceSides, type ChoiceTrial, type ScreenConfig } from "@/lib/screen";

const RESPONSE_WINDOW_MS = 2000;
const ISI_MS = 800;

type Stage = "instructions" | "practice" | "interstitial" | "scored" | "finished";
type TrialPhase = "isi" | "stimulus";
type Side = "left" | "right";

export function ChoiceRT({
  config,
  rng,
  onDone,
}: {
  config: ScreenConfig;
  rng: () => number;
  onDone: (trials: ChoiceTrial[]) => void;
}) {
  const strings = useScreenStrings();
  const practiceCount = config.practiceTrials;
  const scoredCount = config.choiceRtTrials;
  const totalTrials = scoredCount + practiceCount;
  // Generate the side stream exactly once (rng is stateful).
  const sides = useMemo(() => genChoiceSides(totalTrials, rng), [rng, totalTrials]);

  const [stage, setStage] = useState<Stage>("instructions");
  const [shownSide, setShownSide] = useState<Side | null>(null);

  const stageRef = useRef<Stage>("instructions");
  const phaseRef = useRef<TrialPhase>("isi");
  const sideRef = useRef<Side | null>(null);
  const shownAtRef = useRef<number>(0);
  const resolvedRef = useRef(true);
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  const scoredRef = useRef<ChoiceTrial[]>([]);
  const streamIndexRef = useRef(0);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  function clearTimers() {
    if (timeoutRef.current !== null) {
      clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }

  function recordAndAdvance(trial: ChoiceTrial) {
    const idx = streamIndexRef.current;
    if (idx >= practiceCount) scoredRef.current.push({ ...trial, stimulus_side: sideRef.current ?? undefined });
    const next = idx + 1;
    streamIndexRef.current = next;
    if (next >= totalTrials) {
      stageRef.current = "finished";
      setStage("finished");
      onDoneRef.current(scoredRef.current);
      return;
    }
    if (next === practiceCount) {
      stageRef.current = "interstitial";
      setStage("interstitial");
      setShownSide(null);
      return;
    }
    startTrial(next);
  }

  // Fixed ISI (blank), then show the arrow and arm the response timeout.
  function startTrial(idx: number) {
    clearTimers();
    resolvedRef.current = false;
    phaseRef.current = "isi";
    setShownSide(null);
    timeoutRef.current = setTimeout(() => {
      timeoutRef.current = null;
      const side = sides[idx];
      sideRef.current = side;
      setShownSide(side);
      // Acceptance gate opens with the measured onset (see SimpleRT) — a
      // sub-frame keydown is ignored by the phase guard instead of computing
      // an RT against a stale onset.
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        shownAtRef.current = performance.now();
        phaseRef.current = "stimulus";
        timeoutRef.current = setTimeout(() => {
          timeoutRef.current = null;
          if (resolvedRef.current) return;
          resolvedRef.current = true;
          setShownSide(null);
          recordAndAdvance({ rt_ms: null, responded: false, correct: false });
        }, RESPONSE_WINDOW_MS);
      });
    }, ISI_MS);
  }

  function startPractice() {
    streamIndexRef.current = 0;
    stageRef.current = "practice";
    setStage("practice");
    startTrial(0);
  }

  function startScored() {
    stageRef.current = "scored";
    setStage("scored");
    startTrial(streamIndexRef.current);
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.code !== "ArrowLeft" && event.code !== "ArrowRight") return;
      event.preventDefault();
      if (event.repeat) return;
      const stage = stageRef.current;
      if (stage !== "practice" && stage !== "scored") return;
      // Only accept a response while the arrow is on screen.
      if (phaseRef.current !== "stimulus") return;
      if (resolvedRef.current) return;
      const now = performance.now();
      resolvedRef.current = true;
      const pressed: Side = event.code === "ArrowLeft" ? "left" : "right";
      const rt = now - shownAtRef.current;
      clearTimers();
      setShownSide(null);
      recordAndAdvance({
        rt_ms: rt,
        responded: true,
        correct: pressed === sideRef.current,
        response_side: pressed,
      });
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => clearTimers, []);

  if (stage === "instructions") {
    return (
      <Instructions
        title={strings.choiceRt.title}
        body={strings.choiceRt.instructions}
        onStart={startPractice}
        startLabel={strings.common.start}
      />
    );
  }

  if (stage === "interstitial") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
        <p className="max-w-md text-sm text-muted-foreground">{strings.common.practiceDone}</p>
        <Button onClick={startScored}>{strings.common.continue}</Button>
      </div>
    );
  }

  if (stage === "finished") {
    return <div className="min-h-[60vh]" />;
  }

  const inPractice = stage === "practice";

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-8">
      {inPractice && (
        <p className="text-xs uppercase tracking-wide text-muted-foreground">
          {strings.common.practice}
        </p>
      )}
      <div className="flex h-40 w-40 items-center justify-center">
        {shownSide === "left" && <ArrowLeft size={96} aria-hidden />}
        {shownSide === "right" && <ArrowRight size={96} aria-hidden />}
      </div>
    </div>
  );
}

function Instructions({
  title,
  body,
  onStart,
  startLabel,
}: {
  title: string;
  body: string;
  onStart: () => void;
  startLabel: string;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
      <h3 className="text-xl font-semibold">{title}</h3>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{body}</p>
      <Button onClick={onStart}>{startLabel}</Button>
    </div>
  );
}
