"use client";

import { useEffect, useRef, useState } from "react";

export function OpenMatbAudioBriefing({ onPlayingChange }: {
  onPlayingChange: (playing: boolean) => void;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    const audio = audioRef.current;
    return () => {
      audio?.pause();
      onPlayingChange(false);
    };
  }, [onPlayingChange]);

  return <section className="space-y-3 border border-info/40 bg-info/5 p-4" aria-label="Instrucciones de audio MATB">
    <h2 className="font-display text-xl font-semibold">Escuche las instrucciones antes de iniciar</h2>
    <p>Preste mucha atención a las instrucciones y a las llamadas durante toda la prueba. Complete primero la práctica y avise al investigador si algún sonido o control no funciona.</p>
    <audio
      ref={audioRef}
      controls
      preload="metadata"
      aria-label="Instrucciones MATB en español"
      className="w-full"
      src="/audio/instructions/openmatb-es.wav"
      onPlay={() => onPlayingChange(true)}
      onPause={() => onPlayingChange(false)}
      onEnded={() => onPlayingChange(false)}
      onError={() => { setUnavailable(true); onPlayingChange(false); }}
    />
    {unavailable && <p role="alert">No se pudo reproducir la explicación. Lea las instrucciones y avise al investigador para comprobar el sonido antes de comenzar.</p>}
    <p className="text-sm text-muted-foreground">Compruebe también las llamadas NAV/COM en la ventana nativa durante la práctica. Esta explicación utiliza una voz generada por IA y se reproduce sin conexión.</p>
    <a className="text-sm underline" href="/audio/instructions/openmatb-es.txt" target="_blank" rel="noreferrer">Leer la transcripción completa</a>
  </section>;
}
