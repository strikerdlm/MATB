// Author: Dr Diego Malpica MD
"use client";

import { useEffect, useRef, useState } from "react";

import { ES } from "@/components/screen/strings_es";
import { Button } from "@/components/ui/button";
import { targetPosition, type ScreenConfig } from "@/lib/screen";

const DOT_PX = 16;

type Stage = "instructions" | "practice" | "interstitial" | "scored" | "finished";

export interface TrackingResult {
  samples: number[][];
  n_expected_samples: number;
  path_amplitude_px: number;
}

export function Tracking({
  config,
  onDone,
}: {
  config: ScreenConfig;
  onDone: (result: TrackingResult) => void;
}) {
  const scoredSeconds = config.trackingSeconds;
  const practiceSeconds = scoredSeconds >= 10 ? 10 : 3;

  const [stage, setStage] = useState<Stage>("instructions");
  const [remaining, setRemaining] = useState<number>(scoredSeconds);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const dotRef = useRef<HTMLDivElement | null>(null);
  const stageRef = useRef<Stage>("instructions");
  const mouseRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const samplesRef = useRef<number[][]>([]);
  const amplitudeRef = useRef<number>(0);
  const rafRef = useRef<number | null>(null);
  const startTimeRef = useRef<number>(0);
  const onDoneRef = useRef(onDone);
  onDoneRef.current = onDone;

  function clearRaf() {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
  }

  // Drive one timed run (practice or scored). Sampling happens only for the
  // scored run; the target is positioned every frame in both.
  function runBlock(durationSeconds: number, scored: boolean) {
    const container = containerRef.current;
    if (!container) return;
    const rect = container.getBoundingClientRect();
    const amplitude = 0.35 * Math.min(rect.width, rect.height);
    amplitudeRef.current = amplitude;
    samplesRef.current = [];
    setRemaining(durationSeconds);

    const loop = () => {
      const now = performance.now();
      const tMs = now - startTimeRef.current;
      const elapsedSeconds = tMs / 1000;
      const cont = containerRef.current;
      const dot = dotRef.current;
      if (!cont) return;
      const r = cont.getBoundingClientRect();
      const { x: ox, y: oy } = targetPosition(elapsedSeconds, amplitude);
      const targetX = r.width / 2 + ox;
      const targetY = r.height / 2 + oy;
      if (dot) {
        dot.style.left = `${targetX - DOT_PX / 2}px`;
        dot.style.top = `${targetY - DOT_PX / 2}px`;
      }
      // Mouse position relative to the container.
      const mouseX = mouseRef.current.x - r.left;
      const mouseY = mouseRef.current.y - r.top;
      if (scored) {
        samplesRef.current.push([
          Math.round(tMs),
          Math.round(mouseX),
          Math.round(mouseY),
          Math.round(targetX),
          Math.round(targetY),
        ]);
      }
      const remainingS = Math.max(0, durationSeconds - elapsedSeconds);
      setRemaining(Math.ceil(remainingS));
      if (elapsedSeconds >= durationSeconds) {
        rafRef.current = null;
        finishBlock(scored);
        return;
      }
      rafRef.current = requestAnimationFrame(loop);
    };
    startTimeRef.current = performance.now();
    rafRef.current = requestAnimationFrame(loop);
  }

  function finishBlock(scored: boolean) {
    clearRaf();
    if (scored) {
      stageRef.current = "finished";
      setStage("finished");
      onDoneRef.current({
        samples: samplesRef.current,
        n_expected_samples: scoredSeconds * 60,
        path_amplitude_px: amplitudeRef.current,
      });
    } else {
      stageRef.current = "interstitial";
      setStage("interstitial");
    }
  }

  function startPractice() {
    stageRef.current = "practice";
    setStage("practice");
    // Defer one tick so the container is laid out before measuring.
    requestAnimationFrame(() => runBlock(practiceSeconds, false));
  }

  function startScored() {
    stageRef.current = "scored";
    setStage("scored");
    requestAnimationFrame(() => runBlock(scoredSeconds, true));
  }

  useEffect(() => clearRaf, []);

  function onMouseMove(event: React.MouseEvent<HTMLDivElement>) {
    mouseRef.current = { x: event.clientX, y: event.clientY };
  }

  if (stage === "instructions") {
    return (
      <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 text-center">
        <h3 className="text-xl font-semibold">{ES.tracking.title}</h3>
        <p className="max-w-md text-sm leading-relaxed text-muted-foreground">
          {ES.tracking.instructions}
        </p>
        <Button onClick={startPractice}>{ES.common.start}</Button>
      </div>
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
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between text-xs uppercase tracking-wide text-muted-foreground">
        <span>{inPractice ? ES.common.practice : ""}</span>
        <span className="tabular-nums">{remaining}s</span>
      </div>
      <div
        ref={containerRef}
        onMouseMove={onMouseMove}
        className="relative h-[60vh] cursor-none overflow-hidden rounded-lg border border-border bg-background"
      >
        <div
          ref={dotRef}
          className="pointer-events-none absolute rounded-full bg-emerald-500"
          style={{ width: DOT_PX, height: DOT_PX }}
          aria-hidden
        />
      </div>
    </div>
  );
}
