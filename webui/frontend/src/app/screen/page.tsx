// Author: Dr Diego Malpica MD
"use client";

import { useEffect, useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { TaskRunner } from "@/components/screen/TaskRunner";
import { useScreenStrings } from "@/components/screen/strings";
import {
  getScreenSummary, listParticipants, postScreen,
} from "@/lib/api";
import type { ScreenPayload } from "@/lib/screen";
import type { Participant, ScreenIngestResult, ScreenSummary } from "@/types";
import { useAppLocale } from "@/lib/i18n";

export default function ScreenPage() {
  const { copy } = useAppLocale();
  const strings = useScreenStrings();
  const [participants, setParticipants] = useState<Participant[]>([]);
  const [summary, setSummary] = useState<ScreenSummary | null>(null);
  const [activePid, setActivePid] = useState<string | null>(null);
  const [result, setResult] = useState<ScreenIngestResult | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fast = typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("fast") === "1";

  async function refresh() {
    const [ps, s] = await Promise.all([listParticipants(), getScreenSummary()]);
    setParticipants(ps);
    setSummary(s);
  }
  useEffect(() => { refresh().catch((e) => setError(String(e))); }, []);

  async function onComplete(payload: ScreenPayload) {
    if (!activePid) return;
    setSaving(true);
    try {
      setResult(await postScreen(activePid, payload));
      setActivePid(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setActivePid(null);
    } finally {
      setSaving(false);
    }
  }

  if (activePid) {
    return <TaskRunner fast={fast} onComplete={onComplete} />;
  }

  const screened = new Set(summary?.screens.map((s) => s.participant_id));
  const unscreened = participants.filter((p) => !screened.has(p.id));

  return (
    <div className="space-y-6">
      <PageHeader
        kicker={copy("Evaluación basal", "Baseline screen")}
        title={copy("Evaluación neurocognitiva", "Neurocognitive Screen")}
        description={
          <>
          {copy("Una administración por participante al ingreso. El mapeo HCF es exploratorio; se activa cuando se han evaluado al menos ", "One administration per participant at enrollment. HCF mapping is exploratory; active once >= ")}
          {summary?.min_cohort ?? 3} {copy("participantes", "participants")} ({summary?.n_screened ?? 0} {copy("hasta ahora", "so far")}{summary?.hcf_active ? copy(", activo", ", active") : copy(", inactivo", ", inactive")}).
          </>
        }
        stats={[
          { label: copy("Evaluados", "Screened"), value: summary?.n_screened ?? 0 },
          { label: copy("Mínimo", "Minimum"), value: summary?.min_cohort ?? 3 },
          { label: copy("Estado", "State"), value: summary?.hcf_active ? copy("Activo", "Live") : copy("En espera", "Hold") },
        ]}
      />

      {error && (
        <p className="rounded-[4px] border border-danger/40 bg-danger/10 px-4 py-2 text-sm text-danger">
          {error}
        </p>
      )}
      {saving && <p className="text-sm text-muted-foreground">{strings.common.saving}</p>}

      {result && (
        <div className="mission-panel p-4 text-sm">
          <h3 className="mb-2 font-medium">{copy("Calificado", "Scored")}: {result.participant_id}</h3>
          <pre className="overflow-x-auto text-xs text-muted-foreground">
            {JSON.stringify(result.scores, null, 2)}
          </pre>
        </div>
      )}

      <section className="space-y-2">
        <h3 className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{copy("Iniciar una evaluación", "Start a screen")}</h3>
        {unscreened.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {participants.length === 0 ? copy("Aún no hay participantes incluidos.", "No participants enrolled yet.") : copy("Todos los participantes han sido evaluados.", "All participants screened.")}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          {unscreened.map((p) => (
            <button
              key={p.id}
              onClick={() => { setResult(null); setActivePid(p.id); }}
              className="rounded-[3px] border border-white/10 px-4 py-2 font-mono text-xs uppercase tracking-[0.12em] hover:border-white/30 hover:bg-white/[0.06]"
            >
              {p.id}
            </button>
          ))}
        </div>
      </section>

      {summary && summary.screens.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-muted-foreground">{copy("Evaluaciones completadas", "Completed screens")}</h3>
          <div className="data-table-wrap overflow-x-auto">
            <table className="data-table">
              <thead>
                <tr>
                  <th className="py-1 pr-2">{copy("Participante", "Participant")}</th>
                  <th className="py-1 pr-2">{copy("TR simple (ms)", "Simple RT (ms)")}</th>
                  <th className="py-1 pr-2">{copy("TR de elección (ms)", "Choice RT (ms)")}</th>
                  <th className="py-1 pr-2">2-back d′</th>
                  <th className="py-1 pr-2">{copy("Seguimiento RMS", "Tracking RMS")}</th>
                  <th className="py-1">F/F₀ ({copy("exploratorio", "exploratory")})</th>
                </tr>
              </thead>
              <tbody>
                {summary.screens.map((s) => (
                  <tr key={s.participant_id}>
                    <td className="py-1 pr-2 font-mono text-xs">{s.participant_id}</td>
                    <td className="py-1 pr-2">{s.scores.simple_rt?.median_ms ?? "—"}</td>
                    <td className="py-1 pr-2">{s.scores.choice_rt?.median_ms ?? "—"}</td>
                    <td className="py-1 pr-2">{s.scores.nback?.d_prime?.toFixed(2) ?? "—"}</td>
                    <td className="py-1 pr-2">{s.scores.tracking?.rms_norm?.toFixed(3) ?? "—"}</td>
                    <td className="py-1">{s.hcf_value?.toFixed(3) ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
