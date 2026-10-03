"use client";
import { PresentationSetup } from "../presentation/PresentationSetup";
import type { PresentationConfig } from "@/lib/simulation/presentation/contracts";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Gauge, Loader2, Play, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { useAppLocale } from "@/lib/i18n";
import {
  createTechnicalSimulationSession,
  SimulationApiError,
  transitionSession,
} from "@/lib/simulation/api";
import { storePreparedSessionLease } from "@/lib/simulation/lease";
import { STRINGS, t, type TranslationKey } from "@/lib/simulation/i18n";
import type { Profile, ScenarioSummary } from "@/types/simulation";

const PROFILES: Profile[] = ["PRACTICE", "LOW", "MEDIUM", "HIGH"];

function profileName(profile: Profile, tr: ReturnType<typeof useAppLocale>["tr"]): string {
  return tr(`technical.${profile.toLowerCase()}` as "technical.practice" | "technical.low" | "technical.medium" | "technical.high");
}

function durationLabel(seconds?: number): string {
  if (!seconds) return "—";
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return remainder ? `${minutes} min ${remainder} s` : `${minutes} min`;
}

export interface TechnicalTestFormProps {
  scenarios: ScenarioSummary[];
  loading?: boolean;
  loadError?: string | null;
}

export function TechnicalTestForm({ scenarios, loading = false, loadError = null }: TechnicalTestFormProps) {
  const router = useRouter();
  const [presentation,setPresentation] = useState<PresentationConfig>();
  const { simulationLocale, tr } = useAppLocale();
  const [scenarioId, setScenarioId] = useState("");
  const [profile, setProfile] = useState<Profile>("LOW");
  const [acknowledged, setAcknowledged] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  useEffect(() => {
    if (!scenarioId && scenarios.length > 0) setScenarioId(scenarios[0].scenario_id);
  }, [scenarioId, scenarios]);

  const scenario = useMemo(
    () => scenarios.find((candidate) => candidate.scenario_id === scenarioId) ?? null,
    [scenarioId, scenarios],
  );
  const details = scenario?.profile_details?.[profile];
  const availableProfiles = scenario?.block_order?.length
    ? PROFILES.filter((candidate) => scenario.block_order.includes(candidate))
    : PROFILES;
  const canLaunch = Boolean(scenarioId && availableProfiles.includes(profile) && acknowledged && !loading && !submitting);

  async function launch() {
    if (!canLaunch) {
      if (!acknowledged) setSubmitError(tr("technical.acknowledgement_required"));
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      const prepared = await createTechnicalSimulationSession({
        execution_purpose: "practice",
        scenario_id: scenarioId,
        ...(presentation ? {presentation}:{}),
        block_id: profile,
        locale: simulationLocale,
      });
      await storePreparedSessionLease(prepared);
      try {
        if (presentation?.blocks[profile] !== "3d") await transitionSession(prepared.id, "start", prepared.controller_lease, { block_id: profile });
      } catch {
        // The prepared session and its controller lease are still valid. Open
        // the console so the operator can retry Start without creating a
        // second active session after a transient request failure.
        router.push(`/mission?session=${encodeURIComponent(prepared.id)}`);
        return;
      }
      router.push(`/mission?session=${encodeURIComponent(prepared.id)}`);
    } catch (reason: unknown) {
      const translated = reason instanceof SimulationApiError
        ? (() => {
            const key = `error.${reason.code}` as TranslationKey;
            return Object.prototype.hasOwnProperty.call(STRINGS.en, key) ? t(simulationLocale, key) : reason.message;
          })()
        : null;
      setSubmitError(
        translated ?? (reason instanceof Error
          ? reason.message
          : tr("common.error")),
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="space-y-6"><PresentationSetup allowLive locale={simulationLocale} value={presentation} onChange={setPresentation} profiles={[profile]}/>
      <header className="mission-panel flex flex-col gap-4 px-5 py-5 sm:px-6 xl:flex-row xl:items-end xl:justify-between">
        <div>
          <p className="page-kicker">{tr("technical.kicker")}</p>
          <h2 className="page-title mt-2">{tr("technical.title")}</h2>
          <p className="mt-2 max-w-3xl text-sm text-muted-foreground">{tr("technical.subtitle")}</p>
        </div>
        <div className="flex items-center gap-2 border border-warning/40 bg-warning/5 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-warning">
          <ShieldCheck className="h-4 w-4" aria-hidden="true" />
          {tr("technical.mode_badge")}
        </div>
      </header>

      <div role="note" className="flex gap-3 border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>{tr("technical.notice")}</span>
      </div>

      {loadError && <p role="alert" className="border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">{loadError}</p>}
      {loading && <p role="status" className="font-mono text-xs uppercase text-muted-foreground">{tr("common.loading")}</p>}

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <Card>
          <CardHeader>
            <CardTitle className="font-display text-xl uppercase tracking-wide">{tr("technical.profile")}</CardTitle>
            <CardDescription>{tr("technical.subtitle")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="space-y-2">
              <Label htmlFor="technical-scenario">{tr("technical.scenario")}</Label>
              <select
                id="technical-scenario"
                value={scenarioId}
                onChange={(event) => setScenarioId(event.target.value)}
                disabled={loading || submitting}
                className="native-select w-full"
              >
                <option value="">—</option>
                {scenarios.map((candidate) => (
                  <option key={candidate.scenario_id} value={candidate.scenario_id}>
                    {candidate.titles?.[simulationLocale] || candidate.title || candidate.scenario_id}
                  </option>
                ))}
              </select>
              {!loading && scenarios.length === 0 && <p className="text-xs text-muted-foreground">{tr("technical.no_scenarios")}</p>}
            </div>

            <fieldset>
              <legend className="mb-3 font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">
                {tr("technical.profile")}
              </legend>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {availableProfiles.map((candidate) => (
                  <label key={candidate} className="cursor-pointer">
                    <input
                      type="radio"
                      name="technical-profile"
                      value={candidate}
                      checked={profile === candidate}
                      onChange={() => setProfile(candidate)}
                      disabled={submitting}
                      className="peer sr-only"
                    />
                    <span className="block min-h-24 rounded-[4px] border border-white/10 bg-black/20 p-3 transition peer-checked:border-white peer-checked:bg-white peer-checked:text-black peer-focus-visible:ring-2 peer-focus-visible:ring-white">
                      <span className="font-display text-lg font-semibold uppercase">{profileName(candidate, tr)}</span>
                      <span className="mt-1 block font-mono text-[10px] uppercase tracking-wider opacity-60">{candidate}</span>
                      <span className="mt-3 block text-xs opacity-70">{durationLabel(scenario?.profile_details?.[candidate]?.duration_seconds)}</span>
                    </span>
                  </label>
                ))}
              </div>
            </fieldset>

            <label className="flex cursor-pointer items-start gap-3 border border-white/10 bg-white/[0.02] px-3 py-3 text-sm text-muted-foreground">
              <input
                type="checkbox"
                checked={acknowledged}
                onChange={(event) => setAcknowledged(event.target.checked)}
                disabled={submitting}
                className="mt-0.5 h-4 w-4 accent-white"
              />
              <span>{tr("technical.acknowledgement")}</span>
            </label>

            {submitError && <p role="alert" className="border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">{submitError}</p>}

            <Button
              type="button"
              onClick={() => void launch()}
              disabled={!canLaunch}
              className="h-auto min-h-10 w-full whitespace-normal py-3 text-left leading-snug sm:w-auto"
            >
              {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <Play className="mr-2 h-4 w-4" aria-hidden="true" />}
              {submitting ? tr("technical.starting") : `${tr("technical.start")} · ${profileName(profile, tr)} (${profile})`}
            </Button>
          </CardContent>
        </Card>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 font-display text-lg uppercase tracking-wide">
              <Gauge className="h-4 w-4 text-info" aria-hidden="true" />
              {profileName(profile, tr)} ({profile})
            </CardTitle>
            <CardDescription>{scenario?.titles?.[simulationLocale] || scenario?.title || "—"}</CardDescription>
          </CardHeader>
          <CardContent>
            <dl className="space-y-3 font-mono text-xs">
              <div className="flex justify-between gap-3 border-b border-white/10 pb-2"><dt className="text-muted-foreground">{tr("technical.duration")}</dt><dd>{durationLabel(details?.duration_seconds)}</dd></div>
              <div className="flex justify-between gap-3 border-b border-white/10 pb-2"><dt className="text-muted-foreground">{tr("technical.fleet")}</dt><dd>{details?.aircraft_count ?? scenario?.aircraft_count ?? "—"}</dd></div>
            </dl>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
