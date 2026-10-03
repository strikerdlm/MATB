"use client";

import React, { useRef, useState } from "react";
import { Headphones, Pause, Play, RotateCcw } from "lucide-react";

import { useAppLocale } from "@/lib/i18n";

import { Button } from "@/components/ui/button";

export function InstructionAudio({ src, label, unavailableLabel }: {
  src: string;
  label: string;
  unavailableLabel: string;
}) {
  const { copy } = useAppLocale();
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [unavailable, setUnavailable] = useState(false);

  async function toggle() {
    const audio = audioRef.current;
    if (!audio || unavailable) return;
    if (audio.paused) {
      try {
        await audio.play();
      } catch {
        setUnavailable(true);
      }
    } else {
      audio.pause();
    }
  }

  function replay() {
    const audio = audioRef.current;
    if (!audio || unavailable) return;
    audio.currentTime = 0;
    void audio.play().catch(() => setUnavailable(true));
  }

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="instruction-audio">
      <audio
        ref={audioRef}
        src={src}
        preload="metadata"
        onPlay={() => setPlaying(true)}
        onPause={() => setPlaying(false)}
        onEnded={() => setPlaying(false)}
        onError={() => setUnavailable(true)}
      />
      <Button type="button" size="sm" variant="outline" onClick={() => void toggle()} disabled={unavailable}>
        {playing ? <Pause className="mr-2 h-4 w-4" /> : <Play className="mr-2 h-4 w-4" />}
        <Headphones className="mr-2 h-4 w-4" />{unavailable ? unavailableLabel : label}
      </Button>
      <Button type="button" size="sm" variant="ghost" onClick={replay} disabled={unavailable} aria-label={`${label} — replay`}>
        <RotateCcw className="h-4 w-4" />
      </Button>
      <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted-foreground">{copy("Instrucciones pregrabadas", "Prerecorded instructions")}</span>
    </div>
  );
}
