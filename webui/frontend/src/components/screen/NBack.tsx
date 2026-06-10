// Author: Dr Diego Malpica MD
"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { ES } from "@/components/screen/strings_es";
import { Button } from "@/components/ui/button";
import { genNbackSequence, type NbackTrial, type ScreenConfig } from "@/lib/screen";

const LETTER_VISIBLE_MS = 500;

type Stage = "instructions" | "practice" | "interstitial" | "scored" | "finished";

export function NBack({
  config,
  rng,
  onDone,
}: {
  config: ScreenConfig;
  rng: () => number;
  onDone: (trials: NbackTrial[]) => void;
}) {
  const soaMs = config.nbackSoaMs;
  // Two independent sequences, generated once (rng is stateful). Practice uses
  // a short separate sequence (config.practiceTrials + 2, single target).
  const practiceSeq = useMemo(
    () => genNbackSequence(config.practiceTrials + 2, 1, rng),
    [rng, config.practiceTrials],
  );
  const scoredSeq = useMemo(
    () => genNbackSequence(config.nbackTrials, config.nbackTargets, rng),
    [rng, config.nbackTrials, config.nbackTargets],
  );

  const [stage, setStage] = useState<Stage>("instructions");
  const [letter, setLetter] = useState<string | null>(null);

  const stageRef = useRef<Stage>("instructions");
  // Which sequence the current block iterates over.
  const seqRef = useRef(practiceSeq);
  const indexRef = useRef(0);
  // Per-trial accumulators.
  const respondedRef = useRef(false);
  const shownAtRef = useRef<number>(0);
  const trialsRef = useRef<NbackTrial[]>([]);
  const letterTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const soaTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  function clearTimers() {
    if (letterTimeoutRef.current !== null) {
      clearTimeout(letterTimeoutRef.current);
      letterTimeoutRef.current = null;
    }
    if (soaTimeoutRef.current !== null) {
      clearTimeout(soaTimeoutRef.current);
      soaTimeoutRef.current = null;
    }
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }

  // Show the letter for one trial, then blank to the SOA boundary, recording
  // the post-paint onset timestamp and whether a response arrived in window.
  function runTrial(idx: number) {
    clearTimers();
    const seq = seqRef.current;
    respondedRef.current = false;
    setLetter(seq.letters[idx]);
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = null;
      // Post-paint letter onset; the server derives gaps from these onsets.
      shownAtRef.current = performance.now();
      letterTimeoutRef.current = setTimeout(() => {
        letterTimeoutRef.current = null;
        setLetter(null);
      }, LETTER_VISIBLE_MS);
      soaTimeoutRef.current = setTimeout(() => {
        soaTimeoutRef.current = null;
        finishTrial(idx, seq.isTarget[idx]);
      }, soaMs);
    });
  }

  function finishTrial(idx: number, isTarget: boolean) {
    const isScored = stageRef.current === "scored";
    if (isScored) {
      trialsRef.current.push({
        is_target: isTarget,
        responded: respondedRef.current,
        shown_at_ms: shownAtRef.current,
      });
    }
    const next = idx + 1;
    indexRef.current = next;
    if (next >= seqRef.current.letters.length) {
      if (isScored) {
        stageRef.current = "finished";
        setStage("finished");
        onDoneRef.current(trialsRef.current);
      } else {
        stageRef.current = "interstitial";
        setStage("interstitial");
        setLetter(null);
      }
      return;
    }
    runTrial(next);
  }

  function startPractice() {
    seqRef.current = practiceSeq;
    indexRef.current = 0;
    stageRef.current = "practice";
    setStage("practice");
    runTrial(0);
  }

  function startScored() {
    seqRef.current = scoredSeq;
    indexRef.current = 0;
    trialsRef.current = [];
    stageRef.current = "scored";
    setStage("scored");
    runTrial(0);
  }

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      if (event.code !== "Space") return;
      event.preventDefault();
      if (event.repeat) return;
      const stage = stageRef.current;
      if (stage !== "practice" && stage !== "scored") return;
      // One response per trial, anywhere within the SOA window.
      respondedRef.current = true;
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => clearTimers, []);

  if (stage === "instructions") {
    return (
      <Instructions
        title={ES.nback.title}
        body={ES.nback.instructions}
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
        {letter && (
          <span className="font-mono text-8xl font-bold tabular-nums">{letter}</span>
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
