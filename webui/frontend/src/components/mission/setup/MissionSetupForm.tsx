"use client";

import React, { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, Check, ChevronRight, Loader2, Radio, ShieldCheck } from "lucide-react";
import { listVisits } from "@/lib/api";
import {
  createSimulationSession,
  getSimulationSession,
  SimulationApiError,
} from "@/lib/simulation/api";
import { STRINGS, t, type TranslationKey } from "@/lib/simulation/i18n";
import type { Participant, Visit } from "@/types";
import type { Locale, PreparedSession, ScenarioSummary } from "@/types/simulation";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

const LEASE_KEY_PREFIX = "matb.simulation.";
const LEASE_KEY_SUFFIX = ".lease";
const TERMINAL_LIFECYCLES = new Set(["FINISHED", "ABORTED"]);
const EMPTY_VISITS: Visit[] = [];
const PROFILE_ORDER = ["PRACTICE", "LOW", "MEDIUM", "HIGH"] as const;

export interface MissionSetupFormProps {
  participants: Participant[];
  scenarios: ScenarioSummary[];
  /** Parent page data-loading state.  The form remains renderable for tests. */
  loading?: boolean;
  loadError?: string | null;
  /** Useful for embedding and component tests that already fetched visits. */
  initialVisits?: Visit[];
  visitsLoader?: (participantId: string) => Promise<Visit[]>;
}

function errorMessage(reason: unknown, locale: Locale): string {
  if (reason instanceof SimulationApiError) {
    const candidate = `error.${reason.code}` as TranslationKey;
    if (Object.prototype.hasOwnProperty.call(STRINGS.en, candidate)) return t(locale, candidate);
    return reason.message;
  }
  if (reason instanceof Error) return reason.message;
  return t(locale, "setup.prepare_error");
}

function leaseKey(sessionId: string): string {
  return `${LEASE_KEY_PREFIX}${sessionId}${LEASE_KEY_SUFFIX}`;
}

/**
 * Remove stale controller leases only when the backend confirms that the
 * corresponding session is terminal.  An unreachable session is retained so
 * an operator never loses the ability to recover an active run.
 */
async function clearTerminalLeases(currentSessionId: string): Promise<void> {
  if (typeof window === "undefined") return;
  const keys: string[] = [];
  for (let index = 0; index < window.sessionStorage.length; index += 1) {
    const key = window.sessionStorage.key(index);
    if (key && key.startsWith(LEASE_KEY_PREFIX) && key.endsWith(LEASE_KEY_SUFFIX)) keys.push(key);
  }

  await Promise.all(keys.map(async (key) => {
    const sessionId = key.slice(LEASE_KEY_PREFIX.length, -LEASE_KEY_SUFFIX.length);
    if (!sessionId || sessionId === currentSessionId) return;
    try {
      const session = await getSimulationSession(sessionId);
      if (TERMINAL_LIFECYCLES.has(session.lifecycle)) window.sessionStorage.removeItem(key);
    } catch {
      // Keep the lease if the session cannot be confirmed as terminal.
    }
  }));
}

function scenarioFleet(_scenario: ScenarioSummary): string {
  // The installed protocol supports a bounded 2–8 synthetic fleet.  The
  // scenario's exact count is authoritative in the live snapshot, while the
  // setup summary communicates the safe operating range.
  return "2–8 sUAS";
}

function manifestHash(scenario: ScenarioSummary): string {
  if (!scenario.scenario_sha256) return "—";
  return `${scenario.scenario_sha256.slice(0, 12)}…`;
}

export function MissionSetupForm({
  participants,
  scenarios,
  loading = false,
  loadError = null,
  initialVisits = EMPTY_VISITS,
  visitsLoader = listVisits,
}: MissionSetupFormProps) {
  const router = useRouter();
  const [participantId, setParticipantId] = useState("");
  const [visitOrdinal, setVisitOrdinal] = useState("");
  const [scenarioId, setScenarioId] = useState("");
  const [locale, setLocale] = useState<Locale>("en");
  const [acknowledged, setAcknowledged] = useState(false);
  const [visits, setVisits] = useState<Visit[]>(initialVisits);
  const [visitsLoading, setVisitsLoading] = useState(false);
  const [visitsError, setVisitsError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const selectedScenario = useMemo(
    () => scenarios.find((scenario) => scenario.scenario_id === scenarioId) ?? null,
    [scenarioId, scenarios],
  );
  const canSubmit = Boolean(
    participantId && visitOrdinal && scenarioId && locale && acknowledged
      && !loading && !visitsLoading && !submitting,
  );

  useEffect(() => {
    let mounted = true;
    setVisitOrdinal("");
    setVisitsError(null);
    if (!participantId) {
      setVisits(initialVisits);
      setVisitsLoading(false);
      return () => {
        mounted = false;
      };
    }

    const provided = initialVisits.filter((visit) => visit.participant_id === participantId);
    if (provided.length > 0) {
      setVisits(provided);
      setVisitsLoading(false);
      return () => {
        mounted = false;
      };
    }

    setVisits([]);
    setVisitsLoading(true);
    void visitsLoader(participantId)
      .then((rows) => {
        if (mounted) setVisits(rows);
      })
      .catch((reason: unknown) => {
        if (mounted) setVisitsError(reason instanceof Error ? reason.message : t(locale, "setup.load_error"));
      })
      .finally(() => {
        if (mounted) setVisitsLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [initialVisits, participantId, visitsLoader]);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      if (!acknowledged) setSubmitError(t(locale, "setup.acknowledgement_required"));
      return;
    }
    setSubmitError(null);
    setSubmitting(true);
    try {
      const prepared: PreparedSession = await createSimulationSession({
        participant_id: participantId,
        visit_ordinal: Number(visitOrdinal),
        scenario_id: scenarioId,
        locale,
      });
      // Confirm old sessions before deleting their leases, and never put the
      // lease in the URL, page state, or any rendered diagnostic.
      await clearTerminalLeases(prepared.id);
      if (typeof window !== "undefined") {
        window.sessionStorage.setItem(leaseKey(prepared.id), prepared.controller_lease);
      }
      router.push(`/mission?session=${encodeURIComponent(prepared.id)}`);
    } catch (reason: unknown) {
      setSubmitError(errorMessage(reason, locale));
    } finally {
      setSubmitting(false);
    }
  }

  const labels = STRINGS[locale];

  return (
    <main className="min-h-screen bg-background px-4 py-8 text-foreground sm:px-6 lg:px-10">
      <div className="mx-auto max-w-6xl space-y-7">
        <header className="flex flex-col justify-between gap-5 border-b border-white/10 pb-6 md:flex-row md:items-end">
          <div>
            <div className="mb-3 flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.24em] text-muted-foreground">
              <Radio className="h-3.5 w-3.5 text-success" aria-hidden="true" />
              <span>{labels["app.name"]}</span>
            </div>
            <h1 className="font-display text-3xl font-semibold uppercase tracking-tight text-white sm:text-4xl">
              {labels["setup.title"]}
            </h1>
            <p className="mt-2 max-w-2xl text-sm text-muted-foreground">{labels["setup.subtitle"]}</p>
          </div>
          <div className="flex items-center gap-2 border border-success/30 bg-success/5 px-3 py-2 font-mono text-[10px] uppercase tracking-[0.16em] text-success">
            <ShieldCheck className="h-4 w-4" aria-hidden="true" />
            {labels["setup.offline"]}
          </div>
        </header>

        <div role="note" className="flex gap-3 border border-warning/30 bg-warning/5 px-4 py-3 text-sm text-warning">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{labels["app.research_only"]}</span>
        </div>

        {loadError && (
          <div role="alert" className="border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-danger">
            {loadError}
          </div>
        )}
        {loading && (
          <p role="status" aria-live="polite" className="font-mono text-xs uppercase tracking-[0.14em] text-muted-foreground">
            {labels["a11y.loading"]}…
          </p>
        )}

        <form onSubmit={handleSubmit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
          <Card>
            <CardHeader>
              <CardTitle className="font-display text-xl uppercase tracking-wide">{labels["setup.title"]}</CardTitle>
              <CardDescription>{labels["setup.subtitle"]}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div className="grid gap-5 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="mission-participant">{labels["setup.participant"]}</Label>
                  <select
                    id="mission-participant"
                    aria-label={labels["setup.participant"]}
                    value={participantId}
                    onChange={(event) => setParticipantId(event.target.value)}
                    disabled={loading || submitting}
                    className="h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 text-sm outline-none transition focus:border-white/60 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">—</option>
                    {participants.map((participant) => (
                      <option key={participant.id} value={participant.id}>{participant.id}</option>
                    ))}
                  </select>
                  {!loading && participants.length === 0 && (
                    <p className="text-xs text-muted-foreground">{labels["setup.no_participants"]}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="mission-visit">{labels["setup.visit"]}</Label>
                  <select
                    id="mission-visit"
                    aria-label={labels["setup.visit"]}
                    value={visitOrdinal}
                    onChange={(event) => setVisitOrdinal(event.target.value)}
                    disabled={!participantId || visitsLoading || submitting}
                    className="h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 text-sm outline-none transition focus:border-white/60 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">{visitsLoading ? "…" : "—"}</option>
                    {visits
                      .slice()
                      .sort((left, right) => left.visit_ordinal - right.visit_ordinal)
                      .map((visit) => (
                        <option key={visit.id} value={String(visit.visit_ordinal)}>
                          {visit.visit_ordinal}
                        </option>
                      ))}
                  </select>
                  {visitsError && <p role="alert" className="text-xs text-danger">{visitsError}</p>}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="mission-scenario">{labels["setup.scenario"]}</Label>
                  <select
                    id="mission-scenario"
                    aria-label={labels["setup.scenario"]}
                    value={scenarioId}
                    onChange={(event) => setScenarioId(event.target.value)}
                    disabled={loading || submitting}
                    className="h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 text-sm outline-none transition focus:border-white/60 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="">—</option>
                    {scenarios.map((scenario) => (
                      <option key={scenario.scenario_id} value={scenario.scenario_id}>
                        {scenario.title || scenario.scenario_id}
                      </option>
                    ))}
                  </select>
                  {!loading && scenarios.length === 0 && (
                    <p className="text-xs text-muted-foreground">{labels["setup.no_scenarios"]}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="mission-language">{labels["setup.language"]}</Label>
                  <select
                    id="mission-language"
                    aria-label={labels["setup.language"]}
                    value={locale}
                    onChange={(event) => setLocale(event.target.value as Locale)}
                    disabled={submitting}
                    className="h-10 w-full rounded-[3px] border border-input bg-black/40 px-3 text-sm outline-none transition focus:border-white/60 focus:ring-2 focus:ring-white/15 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <option value="en">{labels["setup.language_en"]}</option>
                    <option value="es-CO">{labels["setup.language_es_co"]}</option>
                  </select>
                </div>
              </div>

              <label className="flex cursor-pointer items-start gap-3 border border-white/10 bg-white/[0.02] px-3 py-3 text-sm text-muted-foreground transition hover:border-white/25">
                <input
                  type="checkbox"
                  aria-label={`Research instrument — ${labels["setup.research_instrument"]}`}
                  checked={acknowledged}
                  onChange={(event) => setAcknowledged(event.target.checked)}
                  disabled={submitting}
                  className="mt-0.5 h-4 w-4 accent-white"
                />
                <span>{labels["setup.research_instrument"]}</span>
              </label>

              {submitError && (
                <p role="alert" className="border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-danger">
                  {submitError}
                </p>
              )}

              <Button
                type="submit"
                aria-label={`Prepare session — ${labels["setup.prepare_session"]}`}
                disabled={!canSubmit}
                className="w-full sm:w-auto"
              >
                {submitting ? <Loader2 className="mr-2 h-4 w-4 animate-spin" aria-hidden="true" /> : <ChevronRight className="mr-2 h-4 w-4" aria-hidden="true" />}
                {submitting ? labels["setup.preparing"] : labels["setup.prepare_session"]}
              </Button>
            </CardContent>
          </Card>

          <Card className={cn("h-fit", !selectedScenario && "opacity-80")}>
            <CardHeader>
              <CardTitle className="font-display text-lg uppercase tracking-wide">{labels["setup.manifest"]}</CardTitle>
              <CardDescription>{selectedScenario?.title || "—"}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 font-mono text-xs">
              <dl className="space-y-3">
                <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-2">
                  <dt className="text-muted-foreground">{labels["setup.manifest_hash"]}</dt>
                  <dd className="text-right text-foreground">{selectedScenario ? manifestHash(selectedScenario) : "—"}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-2">
                  <dt className="text-muted-foreground">{labels["setup.fleet_range"]}</dt>
                  <dd className="text-right text-foreground">{selectedScenario ? scenarioFleet(selectedScenario) : "2–8 sUAS"}</dd>
                </div>
                <div className="flex items-baseline justify-between gap-3 border-b border-white/10 pb-2">
                  <dt className="text-muted-foreground">{labels["setup.profiles"]}</dt>
                  <dd className="text-right text-foreground">
                    {(selectedScenario?.block_order?.length === PROFILE_ORDER.length
                      ? selectedScenario.block_order
                      : PROFILE_ORDER).join(" · ")}
                  </dd>
                </div>
                <div className="flex items-baseline justify-between gap-3">
                  <dt className="text-muted-foreground">{labels["setup.offline"]}</dt>
                  <dd className="inline-flex items-center gap-1.5 text-success"><Check className="h-3.5 w-3.5" aria-hidden="true" /> local runtime</dd>
                </div>
              </dl>
            </CardContent>
          </Card>
        </form>
      </div>
    </main>
  );
}
