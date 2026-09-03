"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { downloadSimulationBundle, getSimulationDebrief } from "@/lib/simulation/api";
import { DebriefScreen } from "@/components/mission/debrief/DebriefScreen";
import type { DebriefView, Locale } from "@/types/simulation";
import { useAppLocale } from "@/lib/i18n";

function DebriefPageContent() {
  const { copy } = useAppLocale();
  const params = useSearchParams();
  const router = useRouter();
  const id = params.get("session");
  const [debrief, setDebrief] = useState<DebriefView | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!id) { router.replace("/mission/setup"); return; }
    let mounted = true;
  void getSimulationDebrief(id).then((value) => { if (mounted) setDebrief(value); }).catch((reason: unknown) => { if (mounted) setError(reason instanceof Error ? reason.message : copy("El informe no está disponible.", "Debrief unavailable.")); });
    return () => { mounted = false; };
  }, [copy, id, router]);
  if (error) return <main className="grid min-h-screen place-items-center p-8"><div role="alert" className="mission-panel p-8 text-danger">{error}</div></main>;
  if (!debrief) return <main className="grid min-h-screen place-items-center p-8 text-muted-foreground">{copy("Cargando informe…", "Loading debrief…")}</main>;
  const locale = debrief.locale === "es-CO" ? "es-CO" : "en" as Locale;
  const download = () => {
    if (!id) return;
    void downloadSimulationBundle(id).then((blob) => {
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `${id}_suas_public_bundle.zip`;
      anchor.click();
      URL.revokeObjectURL(url);
    }).catch((reason: unknown) => {
      setError(reason instanceof Error ? reason.message : copy("Falló la descarga del paquete.", "Bundle download failed."));
    });
  };
  return <DebriefScreen debrief={debrief} locale={locale} onDownload={download} />;
}

export default function MissionDebriefPage() { const { copy } = useAppLocale(); return <Suspense fallback={<main className="grid min-h-screen place-items-center p-8 text-muted-foreground">{copy("Cargando informe…", "Loading debrief…")}</main>}><DebriefPageContent /></Suspense>; }
