// Author: Dr Diego Malpica MD
"use client";

import { useAppLocale } from "@/lib/i18n";
import { useMemo, useRef, useState } from "react";

import { ChoiceRT } from "@/components/screen/ChoiceRT";
import { NBack } from "@/components/screen/NBack";
import { SimpleRT } from "@/components/screen/SimpleRT";
import { Tracking } from "@/components/screen/Tracking";
import { useScreenStrings } from "@/components/screen/strings";
import {
  FAST_CONFIG, SCREEN_CONFIG, mulberry32,
  type ChoiceTrial, type NbackTrial, type RtTrial, type ScreenPayload,
} from "@/lib/screen";

const SUBTEST_COUNT = 4;

export function TaskRunner({ fast, onComplete }: {
  fast: boolean;
  onComplete: (payload: ScreenPayload) => void;
}) {
  const strings = useScreenStrings();
  const { locale } = useAppLocale();
  const config = fast ? FAST_CONFIG : SCREEN_CONFIG;
  const seed = useMemo(() => Math.floor(Math.random() * 2 ** 31), []);
  const rng = useMemo(() => mulberry32(seed), [seed]);
  const [step, setStep] = useState(0);
  const acc = useRef<Partial<ScreenPayload>>({});

  function advance() { setStep((s) => s + 1); }

  return (
    <div className="flex min-h-[70vh] flex-col">
      <p className="mb-4 text-center text-xs text-muted-foreground">
        {strings.common.subtestOf(Math.min(step + 1, SUBTEST_COUNT), SUBTEST_COUNT)}
      </p>
      {step === 0 && (
        <SimpleRT config={config} rng={rng} onDone={(trials: RtTrial[]) => {
          acc.current.simple_rt = { trials }; advance();
        }} />
      )}
      {step === 1 && (
        <ChoiceRT config={config} rng={rng} onDone={(trials: ChoiceTrial[]) => {
          acc.current.choice_rt = { trials }; advance();
        }} />
      )}
      {step === 2 && (
        <NBack config={config} rng={rng} onDone={(trials: NbackTrial[]) => {
          acc.current.nback = { trials, soa_ms: config.nbackSoaMs }; advance();
        }} />
      )}
      {step === 3 && (
        <Tracking config={config} onDone={(tracking) => {
          acc.current.tracking = tracking;
          onComplete({
            schema_version: 2,
            locale,
            seed,
            administered_at: new Date().toISOString(),
            fast_mode: fast,
            simple_rt: acc.current.simple_rt!,
            choice_rt: acc.current.choice_rt!,
            nback: acc.current.nback!,
            tracking,
          });
        }} />
      )}
    </div>
  );
}
