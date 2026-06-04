// Author: Dr Diego Malpica MD
"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { ES } from "@/components/screen/strings_es";
import { Button } from "@/components/ui/button";
import { genSimpleRtIsis, type RtTrial, type ScreenConfig } from "@/lib/screen";

const STIMULUS_WINDOW_MS = 1500;

type Stage = "instructions" | "practice" | "interstitial" | "scored" | "finished";
type TrialPhase = "waiting" | "stimulus";

export function SimpleRT({
  config,
  rng,
  onDone,
}: {
  config: ScreenConfig;
  rng: () => number;
  onDone: (trials: RtTrial[]) => void;
}) {
  const practiceCount = config.practiceTrials;
  const scoredCount = config.simpleRtTrials;
  const totalTrials = scoredCount + practiceCount;
  // Generate the ISI stream exactly once (rng is stateful). Practice trials
  // consume the first practiceCount entries, scored trials the remainder.
  const isis = useMemo(() => genSimpleRtIsis(totalTrials, rng), [rng, totalTrials]);

  const [stage, setStage] = useState<Stage>("instructions");
  const [showStimulus, setShowStimulus] = useState(false);

  const stageRef = useRef<Stage>("instructions");
  const phaseRef = useRef<TrialPhase>("waiting");
  const shownAtRef = useRef<number>(0);
  const resolvedRef = useRef(true); // true => no live trial awaiting a response
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  const scoredRef = useRef<RtTrial[]>([]);
  // Index into the full ISI stream; practice = [0, practiceCount), scored after.
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

  function recordAndAdvance(trial: RtTrial) {
    const idx = streamIndexRef.current;
    const isScored = idx >= practiceCount;
    if (isScored) scoredRef.current.push(trial);
    const next = idx + 1;
    streamIndexRef.current = next;
    if (next >= totalTrials) {
      stageRef.current = "finished";
      setStage("finished");
      onDoneRef.current(scoredRef.current);
      return;
    }
    if (next === practiceCount) {
      // Practice just finished; pause for the interstitial.
      stageRef.current = "interstitial";
      setStage("interstitial");
      setShowStimulus(false);
      return;
    }
    startWaiting(next);
  }

  // Begin the inter-stimulus wait for stream index idx, then flash the stimulus.
  function startWaiting(idx: number) {
    clearTimers();
    resolvedRef.current = false;
    phaseRef.current = "waiting";
    setShowStimulus(false);
    const isi = isis[idx] ?? 1500;
    timeoutRef.current = setTimeout(() => {
      timeoutRef.current = null;
      setShowStimulus(true);
      // Capture onset after paint. The acceptance gate (phaseRef) opens HERE,
      // together with the onset timestamp — never before it, so a sub-frame
      // keydown is still classified as an anticipation (rt_ms: 0, discarded).
      rafRef.current = requestAnimationFrame(() => {
        rafRef.current = null;
        shownAtRef.current = performance.now();
        phaseRef.current = "stimulus";
        // Arm the no-response timeout from the measured onset.
        timeoutRef.current = setTimeout(() => {
          timeoutRef.current = null;
          if (resolvedRef.current) return;
          resolvedRef.current = true;
          setShowStimulus(false);
          recordAndAdvance({ rt_ms: null, responded: false });
        }, STIMULUS_WINDOW_MS);
      });
    }, isi);
  }

  function startPractice() {
    streamIndexRef.current = 0;
    stageRef.current = "practice";
    setStage("practice");
    startWaiting(0);
  }

  function startScored() {
    stageRef.current = "scored";
    setStage("scored");
    startWaiting(streamIndexRef.current);
  }

  // Single keydown listener; reads refs so it always sees the live trial.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.code !== "Space") return;
      event.preventDefault();
      if (event.repeat) return;
      const stage = stageRef.current;
      if (stage !== "practice" && stage !== "scored") return;
      if (resolvedRef.current) return;
      const now = performance.now();
      resolvedRef.current = true;
      if (phaseRef.current === "waiting") {
        // Anticipation: scoring discards it via the 150 ms rule.
        clearTimers();
        recordAndAdvance({ rt_ms: 0, responded: true });
      } else {
        const rt = now - shownAtRef.current;
        clearTimers();
        setShowStimulus(false);
        recordAndAdvance({ rt_ms: rt, responded: true });
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => clearTimers, []);

  if (stage === "instructions") {
    return (
      <Instructions
        title={ES.simpleRt.title}
        body={ES.simpleRt.instructions}
        onStart={startPractice}
      />
    );
  }

  if (stage === "interstitial") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
        <p className="max-w-md text-sm text-muted-foreground">{ES.common.practiceDone}</p>
        <Button onClick={startScored}>{ES.common.continue}</Button>
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
          {ES.common.practice}
        </p>
      )}
      <div className="flex h-40 w-40 items-center justify-center">
        {showStimulus && (
          <div className="h-24 w-24 rounded-full bg-emerald-500" aria-hidden />
        )}
      </div>
    </div>
  );
}

function Instructions({
  title,
  body,
  onStart,
}: {
  title: string;
  body: string;
  onStart: () => void;
}) {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
      <h3 className="text-xl font-semibold">{title}</h3>
      <p className="max-w-md text-sm leading-relaxed text-muted-foreground">{body}</p>
      <Button onClick={onStart}>{ES.common.start}</Button>
    </div>
  );
}
