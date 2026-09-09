"use client";
import React, { useState } from "react";
import type { DebriefView, Locale } from "@/types/simulation";
import type { PresentationConfig } from "@/lib/simulation/presentation/contracts";
import { geographyRequest } from "@/lib/geography/api";
import { controllerLeaseKey } from "@/lib/simulation/lease";
export function SaveTrafficCapture({
  debrief,
  locale,
}: {
  debrief: DebriefView;
  locale: Locale;
}) {
  const [title, setTitle] = useState(""),
    [status, setStatus] = useState(""),
    [busy, setBusy] = useState(false);
  const config = debrief.presentation as unknown as
    | PresentationConfig
    | undefined;
  if (
    debrief.session_mode !== "interactive_technical" ||
    config?.traffic?.mode !== "live"
  )
    return null;
  const es = locale === "es-CO";
  return (
    <form
      className="mission-panel space-y-2 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        setBusy(true);
        const id = String(debrief.session_id);
        const lease = sessionStorage.getItem(controllerLeaseKey(id));
        if (!lease) {
          setStatus(
            es
              ? "La sesión requiere su controlador original."
              : "This session requires its original controller.",
          );
          setBusy(false);
          return;
        }
        void geographyRequest(`/captures/${id}`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Simulation-Controller": lease,
          },
          body: JSON.stringify({ title }),
        })
          .then(() =>
            setStatus(
              es
                ? "Grabación verificada guardada para investigación."
                : "Verified recording saved for research.",
            ),
          )
          .catch((e) => setStatus(String(e)))
          .finally(() => setBusy(false));
      }}
    >
      <h2>{es ? "Guardar tráfico real" : "Save real traffic"}</h2>
      <p className="text-xs text-muted-foreground">
        {es
          ? "Guarde la captura antes de preparar otra sesión. Los bloques requieren una grabación de duración suficiente."
          : "Save this capture before preparing another session. Research blocks require a recording of sufficient duration."}
      </p>
      <input
        aria-label={es ? "Nombre de grabación" : "Recording name"}
        required
        maxLength={80}
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        className="bg-background p-2"
      />
      <button
        disabled={busy || !title.trim()}
        className="ml-2 rounded border border-info p-2"
      >
        {es ? "Guardar captura" : "Save capture"}
      </button>
      {status && <p role="status">{status}</p>}
    </form>
  );
}
